"""LLM provider for the optional Supplier Review Agent.

Configuration comes from environment variables (or a local ``.env`` file, see
``.env.example``); nothing secret lives in the code:

    SRA_LLM_PROVIDER         anthropic (the only provider implemented)
    SRA_LLM_MODEL            default claude-opus-5-5
    ANTHROPIC_API_KEY        required; without it the review is simply unavailable
    SRA_LLM_TIMEOUT_SECONDS  per request, default 90
    SRA_LLM_MAX_RETRIES      SDK retries on timeouts, 429 and 5xx, default 2
    SRA_LLM_MAX_TOKENS       default 16000

The ``anthropic`` package is an optional dependency (``pip install -e ".[llm]"``)
and imported only when a review is actually requested.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .models.ai_review import AIReviewDraft

SUPPORTED_PROVIDERS = ("anthropic",)
DEFAULT_MODEL = "claude-opus-5-5"
# Models that accept the server-side refusal fallback in its "default" form.
SERVER_FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMReviewError(Exception):
    """A failed review, with a message that can be shown to the user as is."""


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "anthropic"
    model: str = DEFAULT_MODEL
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 90.0
    max_retries: int = 2
    max_tokens: int = 16000

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        env = os.environ if env is None else env

        def number(name: str, default: float, cast=float):
            raw = env.get(name, "").strip()
            if not raw:
                return default
            try:
                return cast(raw)
            except ValueError as exc:
                raise LLMReviewError(f"{name} must be a number, got '{raw}'.") from exc

        return cls(
            provider=env.get("SRA_LLM_PROVIDER", "anthropic").strip().lower() or "anthropic",
            model=env.get("SRA_LLM_MODEL", "").strip() or DEFAULT_MODEL,
            api_key=env.get("ANTHROPIC_API_KEY", "").strip() or None,
            timeout_seconds=number("SRA_LLM_TIMEOUT_SECONDS", 90.0),
            max_retries=int(number("SRA_LLM_MAX_RETRIES", 2, int)),
            max_tokens=int(number("SRA_LLM_MAX_TOKENS", 16000, int)),
        )

    @property
    def unavailable_reason(self) -> str | None:
        """Why no review can be generated, or None if the provider is configured."""
        if self.provider not in SUPPORTED_PROVIDERS:
            return (f"LLM provider '{self.provider}' is not supported "
                    f"(SRA_LLM_PROVIDER: {', '.join(SUPPORTED_PROVIDERS)}).")
        if not self.api_key:
            return "No API key configured. Set ANTHROPIC_API_KEY (see .env.example) to enable the AI review."
        return None

    def describe(self) -> str:
        return f"{self.provider} / {self.model}"


def load_env_file(path: str | Path = ".env") -> bool:
    """Read KEY=VALUE lines into os.environ without overriding variables that are already set."""
    path = Path(path)
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))
    return True


class ReviewModel(Protocol):
    """What the review agent needs from a provider (tests use a fake)."""

    settings: LLMSettings

    def review(self, system: str, user: str) -> tuple[AIReviewDraft, str]:
        """Return the structured answer and the model that served it; raise LLMReviewError on failure."""


class AnthropicReviewer:
    """Claude via the official Anthropic SDK, with structured output and bounded retries."""

    def __init__(self, settings: LLMSettings, client=None):
        self.settings = settings
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise LLMReviewError(
                    "The 'anthropic' package is not installed. Run: pip install -e \".[llm]\""
                ) from exc
            client = anthropic.Anthropic(
                api_key=settings.api_key, timeout=settings.timeout_seconds, max_retries=settings.max_retries
            )
        self.client = client

    def review(self, system: str, user: str) -> tuple[AIReviewDraft, str]:
        import anthropic

        s = self.settings
        request = {
            "model": s.model,
            "max_tokens": s.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_format": AIReviewDraft,
        }
        try:
            if s.model in SERVER_FALLBACK_MODELS:
                # if the model declines on policy grounds, the API retries on a fallback model in the same call
                response = self.client.beta.messages.parse(
                    **request, betas=[SERVER_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self.client.messages.parse(**request)
        except anthropic.APITimeoutError as exc:
            raise LLMReviewError(
                f"The provider did not answer within {s.timeout_seconds:g} s "
                f"(tried {s.max_retries + 1} time(s)). Try again later or raise SRA_LLM_TIMEOUT_SECONDS."
            ) from exc
        except anthropic.AuthenticationError as exc:
            raise LLMReviewError("The API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMReviewError("The API key is not allowed to use this model or feature.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMReviewError(
                f"Model '{s.model}' was not found or is not available for this API key. Check SRA_LLM_MODEL."
            ) from exc
        except anthropic.RateLimitError as exc:
            raise LLMReviewError(
                f"Rate limit reached (still limited after {s.max_retries} retries). Try again in a minute."
            ) from exc
        except anthropic.BadRequestError as exc:
            raise LLMReviewError(f"The provider rejected the request: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMReviewError(
                f"The provider returned an error (HTTP {exc.status_code}) after {s.max_retries} retries. "
                "Try again later."
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMReviewError("Could not reach the provider. Check the network connection or proxy.") from exc
        except (ValidationError, ValueError) as exc:
            raise LLMReviewError("The answer did not match the expected review format.") from exc

        if response.stop_reason == "refusal":
            raise LLMReviewError("The model declined to answer this request.")
        if response.stop_reason == "max_tokens":
            raise LLMReviewError("The answer was cut off (max_tokens reached). Raise SRA_LLM_MAX_TOKENS.")
        draft = response.parsed_output
        if draft is None:
            raise LLMReviewError(f"The provider returned no structured answer (stop reason: {response.stop_reason}).")
        return draft, response.model


def reviewer_from_env(settings: LLMSettings | None = None) -> ReviewModel:
    """The configured provider; raises LLMReviewError with a readable reason if it is not available."""
    settings = settings or LLMSettings.from_env()
    if settings.unavailable_reason:
        raise LLMReviewError(settings.unavailable_reason)
    return AnthropicReviewer(settings)
