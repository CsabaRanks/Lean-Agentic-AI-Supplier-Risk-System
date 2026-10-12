"""Supplier Review Agent (optional, LLM-based).

The only agent in the workflow that calls a language model. It runs only when
a caller explicitly requests it (``state["ai_review_request"]``), after
scoring and recommendations are complete, and it never changes the state's
scores, classes or weights.

Input: the provider payload built by
:func:`~supplier_risk_agent.tools.ai_review.build_review_payload` from the
supplier's results in the risk and performance views. The caller shows that
payload to the user before requesting the review; this node checks that the
section for its own view still matches the run's results (no stale or edited
preview) and sends exactly that payload.

Output: ``state["ai_reviews"][supplier_id]`` with a validated
:class:`~supplier_risk_agent.models.ai_review.AIReviewResult`, or an entry in
``state["ai_review_errors"]``. Failures never break the deterministic run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..llm import LLMReviewError, ReviewModel, reviewer_from_env
from ..models.ai_review import AIReviewResult
from ..models.config import RiskModelConfig
from ..models.domain import AuditEntry
from ..models.state import SupplierRiskState
from ..tools.ai_review import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    data_gaps,
    payload_hash,
    payload_json,
    prioritised,
    score_summary,
    section_from_state,
    validate_review,
)

AGENT_NAME = "ai_review"


class AIReviewAgent:
    def __init__(self, model: RiskModelConfig, reviewer: ReviewModel | None = None):
        self.model = model
        self.reviewer = reviewer  # None: configured from the environment when a review is requested

    def _check_request(self, state: SupplierRiskState, request: dict) -> str:
        payload = request.get("payload") or {}
        sid = (payload.get("supplier") or {}).get("id")
        try:
            expected = section_from_state(state, sid, self.model)
        except LookupError as exc:
            raise LLMReviewError(f"Supplier '{sid}' is not part of this run.") from exc
        sent = (payload.get("views") or {}).get(self.model.view)
        if sent != expected:
            raise LLMReviewError("The previewed data no longer matches the current results. Recalculate and retry.")
        return sid

    def __call__(self, state: SupplierRiskState) -> dict:
        request = state.get("ai_review_request") or {}
        payload = request.get("payload") or {}
        sid = (payload.get("supplier") or {}).get("id", "?")
        reviews = dict(state.get("ai_reviews") or {})
        errors = dict(state.get("ai_review_errors") or {})
        details: dict = {"supplier_id": sid, "payload_sha256": payload_hash(payload) if payload else None}
        try:
            sid = self._check_request(state, request)
            reviewer = self.reviewer or reviewer_from_env()
            details["provider"] = reviewer.settings.describe()
            draft, served_by = reviewer.review(SYSTEM_PROMPT, USER_TEMPLATE.format(payload=payload_json(payload)))
            problems = validate_review(draft, payload)
            if problems:
                raise LLMReviewError("The answer failed validation: " + "; ".join(problems))
            reviews[sid] = AIReviewResult(
                supplier_id=sid,
                provider=reviewer.settings.provider,
                model=served_by or reviewer.settings.model,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                payload_sha256=details["payload_sha256"],
                scores=score_summary(payload),
                data_gaps=data_gaps(payload),
                review=prioritised(draft),
            )
            errors.pop(sid, None)
            event = "ai_review_created"
        except LLMReviewError as exc:
            errors[sid] = str(exc)
            details["error"] = str(exc)
            event = "ai_review_failed"
        return {
            "ai_review_request": None,  # one-shot: never repeated by later routing
            "ai_reviews": reviews,
            "ai_review_errors": errors,
            "audit_trail": [AuditEntry(agent=AGENT_NAME, event=event, details=details)],
        }
