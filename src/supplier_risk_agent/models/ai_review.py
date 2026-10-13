"""Output schema of the optional LLM-based Supplier Review Agent.

``AIReviewDraft`` is what the language model must return. It has no numeric
fields; scores, classes and weights stay with the deterministic scoring engine
and are copied into ``AIReviewResult`` from the input payload, never from the
model's answer. The free-text fields can still mention numbers; these are not
checked (see ``tools.ai_review.validate_review``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ViewKey = Literal["risk", "performance"]
Priority = Literal["high", "medium", "low"]

DISCLAIMER = (
    "AI-generated explanation of the deterministic scoring trace. Scores, classes and weights are "
    "computed by the rule-based engine, not by the language model. Suggested actions are proposals for "
    "human review, not decisions."
)


def _trace_refs():
    return Field(description="Ids of the trace entries this statement relies on, e.g. 'risk:credit_risk'")


class RiskDriver(BaseModel):
    criterion: str = Field(description="Exact criterion key from the input payload")
    view: ViewKey
    explanation: str
    trace_refs: list[str] = _trace_refs()


class ViewDifference(BaseModel):
    topic: str
    explanation: str
    criteria: list[str] = Field(description="Criterion keys from the input payload")
    trace_refs: list[str] = _trace_refs()


class SuggestedAction(BaseModel):
    priority: Priority
    action: str
    rationale: str
    criteria: list[str] = Field(description="Criterion keys from the input payload")
    trace_refs: list[str] = _trace_refs()


class OpenQuestion(BaseModel):
    question: str
    criteria: list[str] = Field(description="Criterion keys whose data is missing or unclear")


class AIReviewDraft(BaseModel):
    """Structured answer requested from the language model."""

    management_summary: str
    summary_refs: list[str] = _trace_refs()
    risk_drivers: list[RiskDriver]
    view_differences: list[ViewDifference]
    suggested_actions: list[SuggestedAction]
    open_questions: list[OpenQuestion]


class AIReviewResult(BaseModel):
    """A validated review, stored in the run state and shown to the user."""

    supplier_id: str
    provider: str
    model: str
    created_at: str
    payload_sha256: str = Field(description="Hash of the exact payload sent to the provider")
    scores: dict[str, dict[str, Any]] = Field(
        description="Deterministic score, class and completeness per view, copied from the payload"
    )
    data_gaps: list[str] = Field(description="Missing criteria per view, derived from the payload (not by the LLM)")
    review: AIReviewDraft
    disclaimer: str = DISCLAIMER
    language: Literal["de", "en"] = "en"
