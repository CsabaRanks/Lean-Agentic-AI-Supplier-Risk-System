"""Domain objects exchanged between agents.

All objects are Pydantic models so every intermediate result is typed,
serialisable and can be written to an audit log or report as-is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SupplierProfile(BaseModel):
    """Master data and raw indicators for one supplier.

    ``expert_ratings`` holds subjective 1..5 ratings given by a category
    manager or buyer. ``indicators`` holds raw, mostly objective inputs
    (credit score, country risk index, ...) that tools translate into ratings.
    """

    supplier_id: str
    name: str
    material_group: str | None = Field(
        default=None, description="Commodity / material group; selects group-specific weights"
    )
    country: str = ""
    annual_spend: float | None = None
    expert_ratings: dict[str, int] = Field(default_factory=dict)
    indicators: dict[str, Any] = Field(default_factory=dict)
    expert_risk_score: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Holistic subjective risk label (0..100) from a category manager; used for calibration",
    )


class FactorScore(BaseModel):
    """Rating of a single risk factor, including where it came from."""

    factor: str
    dimension: str
    rating: int | None = Field(description="1..5, None if no data was available")
    weight: float = Field(description="Effective weight (share of the overall score)")
    source: str
    rationale: str = ""

    @property
    def available(self) -> bool:
        return self.rating is not None


class DimensionScore(BaseModel):
    dimension: str
    label: str
    weight: float
    weighted_rating: float | None = Field(description="Weighted 1..5 rating of available factors")
    score: float | None = Field(description="Normalised 0..100")
    completeness: float = Field(description="Share of factor weight with data, 0..1")


class Escalation(BaseModel):
    rule_factor: str
    floor_class: str
    reason: str


class ActionRecommendation(BaseModel):
    priority: str = Field(description="Risk class or 'targeted' for dimension triggers")
    action: str
    trigger: str = Field(description="Why this action was proposed")
    review_cycle: str | None = None


class AuditEntry(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    """Final, self-contained result of one supplier evaluation."""

    supplier_id: str
    supplier_name: str
    material_group: str | None = None
    model_name: str
    model_version: str
    weights_scope: str = "global"
    weights_origin: str = "default"
    overall_score: float | None
    weighted_rating: float | None
    risk_class: str | None
    calculated_class: str | None = Field(description="Class before escalation rules")
    data_completeness: float
    factor_scores: list[FactorScore]
    dimension_scores: list[DimensionScore]
    escalations: list[Escalation] = []
    recommendations: list[ActionRecommendation] = []
    requires_human_review: bool = False
    review_reasons: list[str] = []
    manual_override: bool = Field(default=False, description="Risk class set by a reviewer")
    review_comment: str | None = None


class CalibrationReport(BaseModel):
    """Outcome of one calibration run — old vs. new weights and fit quality."""

    scope: str
    method: str
    n_samples: int
    excluded: dict[str, str] = Field(default_factory=dict, description="supplier_id -> reason")
    old_weights: dict[str, float]
    new_weights: dict[str, float] | None = None
    old_dimension_weights: dict[str, float] = {}
    new_dimension_weights: dict[str, float] | None = None
    mse_before: float | None = None
    mse_after: float | None = None
    improvement: float | None = Field(default=None, description="Relative MSE reduction, 0..1")
    class_agreement_before: float | None = Field(
        default=None, description="Share of suppliers whose model class equals the class derived from the label"
    )
    class_agreement_after: float | None = None
    acceptance_basis: str = "in_sample"
    cv_mse_before: float | None = Field(default=None, description="Out-of-fold MSE of the prior weights")
    cv_mse_after: float | None = Field(default=None, description="Out-of-fold MSE of weights refitted per fold")
    cv_improvement: float | None = None
    accepted: bool = False
    applied: bool = False
    stored_as: str | None = Field(default=None, description="Weight store file, if persisted")
    level_offset: float | None = Field(
        default=None, description="Mean (label - score) under the active weights, in score points"
    )
    level_offset_t: float | None = Field(default=None, description="level_offset / its standard error")
    level_bias_detected: bool = False
    warnings: list[str] = Field(default_factory=list)
    message: str = ""


class ClassOverride(BaseModel):
    risk_class: str
    comment: str = ""


class ReviewDecision(BaseModel):
    """What a reviewer sends to resume a run paused at the human-review step."""

    reviewer: str = "unknown"
    approve_weights: bool = Field(default=False, description="Approve proposed calibrated weights")
    overrides: dict[str, ClassOverride] = Field(
        default_factory=dict, description="supplier_id -> manual risk class"
    )
    defer: bool = Field(default=False, description="Close the run without decisions; items stay open")
    comment: str = ""
