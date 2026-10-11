"""Human Review (human-in-the-loop).

When a run needs a human decision — suppliers with too little data, or
calibrated weights that were proposed but not auto-applied — this node pauses
the graph with LangGraph's ``interrupt()``. The run's state is kept by the
checkpointer under its ``run_id`` until a reviewer resumes it with a
:class:`ReviewDecision`:

* ``approve_weights``  — activate the proposed weights, persist them to the
  weight store and re-score the portfolio;
* ``overrides``        — set a manual risk class for individual suppliers
  (kept across re-scoring, marked as ``manual_override``);
* ``defer``            — close the run without decisions; items stay flagged.

After the decision the node hands control back to the supervisor, which
re-scores and/or regenerates recommendations as needed.

Note: LangGraph re-executes a node from the start when it is resumed, so all
side effects (e.g. writing weights) happen *after* ``interrupt()`` returns.
"""

from __future__ import annotations

from langgraph.types import interrupt

from ..models.config import GLOBAL_SCOPE, RiskModelConfig
from ..models.domain import AuditEntry, ReviewDecision
from ..models.state import SupplierRiskState
from ..tools.scoring import apply_override
from ..tools.weight_store import WeightStore
from .calibration import persist_weights

AGENT_NAME = "human_review"


def pending_weights(state: SupplierRiskState) -> bool:
    report = state.get("calibration_report")
    return bool(report and report.accepted and not state.get("calibration_applied"))


def review_request(state: SupplierRiskState, model: RiskModelConfig) -> dict:
    """JSON-serialisable payload shown to the reviewer."""
    flagged = [
        {
            "supplier_id": r.supplier_id,
            "name": r.supplier_name,
            "overall_score": r.overall_score,
            "risk_class": r.risk_class,
            "data_completeness": r.data_completeness,
            "reasons": r.review_reasons,
        }
        for r in state.get("results", {}).values()
        if r.requires_human_review
    ]
    proposed = None
    if pending_weights(state):
        rep = state["calibration_report"]
        proposed = {
            "scope": rep.scope,
            "old_weights": rep.old_weights,
            "new_weights": rep.new_weights,
            "mse_before": rep.mse_before,
            "mse_after": rep.mse_after,
            "acceptance_basis": rep.acceptance_basis,
            "cv_mse_before": rep.cv_mse_before,
            "cv_mse_after": rep.cv_mse_after,
            "n_samples": rep.n_samples,
            "class_agreement_before": rep.class_agreement_before,
            "class_agreement_after": rep.class_agreement_after,
        }
    return {
        "run_id": state.get("run_id"),
        "flagged_suppliers": flagged,
        "proposed_weights": proposed,
        "portfolio_reasons": state.get("review_reasons", []),
        "allowed_classes": [c.key for c in model.risk_classes],
    }


class HumanReviewAgent:
    def __init__(self, model: RiskModelConfig, store: WeightStore | None = None):
        self.model = model
        self.store = store

    def __call__(self, state: SupplierRiskState) -> dict:
        raw = interrupt(review_request(state, self.model))
        decision = raw if isinstance(raw, ReviewDecision) else ReviewDecision.model_validate(raw or {})

        update: dict = {"review_decision": decision}
        errors: list[str] = []
        details: dict = {"reviewer": decision.reviewer, "comment": decision.comment}

        if decision.defer:
            update["review_status"] = "deferred"
            update["audit_trail"] = [AuditEntry(agent=AGENT_NAME, event="review_deferred", details=details)]
            return update

        update["review_status"] = "completed"

        if decision.approve_weights:
            if pending_weights(state):
                weights, report = state["calibrated_weights"], state["calibration_report"]
                report = report.model_copy(update={"applied": True})
                weights, report = persist_weights(
                    self.store, weights, report, self.model, approved_by=decision.reviewer, status="approved"
                )
                active = dict(state.get("active_weights") or {})
                active[weights.scope or GLOBAL_SCOPE] = weights
                update |= {
                    "active_weights": active,
                    "calibrated_weights": weights,
                    "calibration_report": report,
                    "calibration_applied": True,  # supervisor re-scores
                    "recommendations_done": False,
                }
                details["weights_approved"] = {"scope": weights.scope, "stored_as": report.stored_as}
            else:
                errors.append("approve_weights ignored: no proposed weights pending")

        valid_classes = {c.key for c in self.model.risk_classes}
        overrides = dict(state.get("manual_overrides") or {})
        results = dict(state.get("results") or {})
        for sid, override in decision.overrides.items():
            if sid not in results:
                errors.append(f"override ignored: unknown supplier '{sid}'")
            elif override.risk_class not in valid_classes:
                errors.append(f"override ignored: unknown class '{override.risk_class}' for '{sid}'")
            else:
                overrides[sid] = override
                results[sid] = apply_override(results[sid], override, decision.reviewer)
        if overrides != (state.get("manual_overrides") or {}):
            update |= {"manual_overrides": overrides, "results": results, "recommendations_done": False}
            details["overrides"] = {sid: o.risk_class for sid, o in overrides.items()}

        update["errors"] = errors
        update["audit_trail"] = [AuditEntry(agent=AGENT_NAME, event="review_completed", details=details)]
        return update
