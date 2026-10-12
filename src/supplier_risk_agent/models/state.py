"""Shared LangGraph state for one assessment run over a supplier portfolio.

A run evaluates a set of suppliers (optionally restricted to one material
group). Portfolio scope is required because calibration learns from many
expert-labelled suppliers at once.

Each agent node reads from this state and returns a *partial* update. Fields
annotated with ``operator.add`` are append-only: LangGraph concatenates the
lists returned by individual nodes, which yields a complete audit trail
without any node having to know about the others.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from .ai_review import AIReviewResult
from .config import WeightSet
from .domain import (
    AuditEntry,
    CalibrationReport,
    ClassOverride,
    ReviewDecision,
    RiskAssessment,
    SupplierProfile,
)

Step = Literal["collect_data", "score", "calibrate", "recommend", "human_review", "ai_review", "end"]


class SupplierRiskState(TypedDict, total=False):
    # --- input ---------------------------------------------------------------
    run_id: str  # also the LangGraph thread id used to resume a paused run
    supplier_ids: list[str]  # empty / missing = all suppliers in the source
    material_group: str | None  # restrict run (and calibration scope) to one group
    calibrate: bool  # per-run switch; overrides calibration.enabled in the config

    # --- data collection -----------------------------------------------------
    suppliers: dict[str, SupplierProfile]
    expert_labels: dict[str, float]  # supplier_id -> subjective risk score 0..100

    # --- weights ---------------------------------------------------------------
    # Weights in use for the last scoring round, keyed by scope ("global" or a
    # material group). The scoring agent picks the most specific scope per
    # supplier. Calibration writes its result to ``calibrated_weights`` and, if
    # accepted, into ``active_weights`` before scoring is triggered again.
    active_weights: dict[str, WeightSet]
    calibrated_weights: WeightSet | None

    # --- scoring ---------------------------------------------------------------
    results: dict[str, RiskAssessment]  # supplier_id -> assessment
    scoring_round: int

    # --- calibration -------------------------------------------------------------
    calibration_performed: bool
    calibration_applied: bool
    mse_before: float | None
    mse_after: float | None
    calibration_report: CalibrationReport | None

    # --- recommendation ----------------------------------------------------------
    recommendations_done: bool

    # --- optional LLM review (only on explicit request, never changes scores) ----
    ai_review_request: dict | None  # {"payload": ...}; cleared by the AI review node
    ai_reviews: dict[str, AIReviewResult]  # supplier_id -> latest validated review
    ai_review_errors: dict[str, str]  # supplier_id -> last error message

    # --- control flow & governance ------------------------------------------------
    next_step: Step
    requires_human_review: bool
    review_status: Literal["completed", "deferred"]  # absent while the run waits for review
    review_decision: ReviewDecision | None
    manual_overrides: dict[str, ClassOverride]  # kept across re-scoring
    review_reasons: Annotated[list[str], operator.add]  # portfolio-level reasons
    errors: Annotated[list[str], operator.add]
    audit_trail: Annotated[list[AuditEntry], operator.add]
