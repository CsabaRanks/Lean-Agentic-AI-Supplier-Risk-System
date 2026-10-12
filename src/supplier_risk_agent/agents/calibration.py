"""Calibration Agent.

Learns factor weights from the judgement of category managers.

Input:  computed scores + factor ratings of the portfolio and holistic expert
        labels (``expert_risk_score``, 0..100) for some of the suppliers.
Output: calibrated weights that minimise the MSE between model score and expert
        label under the constraints  weight >= w_min  and  sum = 1,
        plus a report of old vs. new weights and the MSE before / after.

If the result is accepted (by default: the cross-validated MSE improves by at
least ``min_improvement`` and by at least ``cv_min_z`` standard errors) and
``auto_apply`` is on, the calibrated weights become the active weights for the
calibration scope, are persisted to the weight store (if configured) and the
supervisor routes back to the Scoring Agent (feedback loop). Otherwise the
weights are only *proposed* and the run pauses at human review — weights that
drive supplier decisions should not change silently.

Scope: the MVP calibrates one weight set per run — globally, or for the
material group the run is restricted to (``state["material_group"]``).
The math lives in :mod:`supplier_risk_agent.tools.calibration`.
"""

from __future__ import annotations

from ..models.config import GLOBAL_SCOPE, RiskModelConfig, WeightSet
from ..models.domain import AuditEntry, CalibrationReport
from ..models.state import SupplierRiskState
from ..tools.calibration import calibrate_weights
from ..tools.scoring import resolve_weights
from ..tools.weight_store import WeightStore

AGENT_NAME = "calibration"


def persist_weights(
    store: WeightStore | None,
    weights: WeightSet,
    report: CalibrationReport,
    model: RiskModelConfig,
    approved_by: str,
    status: str,
) -> tuple[WeightSet, CalibrationReport]:
    """Save applied weights to the store (if any); return copies with version / path set."""
    if store is None:
        return weights, report
    path, version = store.save(weights, model, approved_by=approved_by, status=status, report=report)
    return (
        weights.model_copy(update={"version": version}),
        report.model_copy(update={"stored_as": str(path)}),
    )


class CalibrationAgent:
    def __init__(self, model: RiskModelConfig, store: WeightStore | None = None):
        self.model = model
        self.settings = model.calibration
        self.store = store

    def __call__(self, state: SupplierRiskState) -> dict:
        scope = state.get("material_group") or GLOBAL_SCOPE
        active = dict(state.get("active_weights") or {})
        prior = resolve_weights(state.get("material_group"), active, self.model)

        anchor = self.model.default_weights(state.get("material_group"))
        report, new_weights = calibrate_weights(
            list(state["suppliers"].values()), self.model, prior, self.settings, scope=scope, anchor=anchor
        )

        update: dict = {"calibration_performed": True, "calibration_applied": False}
        review_reasons: list[str] = []
        level_blocks = report.level_bias_detected and self.settings.level_bias_action == "review"
        if report.accepted and self.settings.auto_apply and not level_blocks:
            report.applied = True
            new_weights, report = persist_weights(
                self.store, new_weights, report, self.model, approved_by="auto_apply", status="auto_applied"
            )
            active[scope] = new_weights
            update |= {"active_weights": active, "calibration_applied": True}
        elif report.accepted:
            update["requires_human_review"] = True
            if level_blocks:
                review_reasons.append(
                    f"calibrated weights for scope '{scope}' not auto-applied: level offset of "
                    f"{report.level_offset:+.1f} points between labels and scores — review class thresholds"
                )
            else:
                review_reasons.append(f"calibrated weights for scope '{scope}' proposed — approval required")

        update |= {
            "calibration_report": report,
            "calibrated_weights": new_weights,
            "mse_before": report.mse_before,
            "mse_after": report.mse_after,
            "review_reasons": review_reasons,
            "audit_trail": [
                AuditEntry(
                    agent=AGENT_NAME,
                    event="weights_calibrated" if report.applied else "calibration_not_applied",
                    details={
                        "scope": scope,
                        "n_samples": report.n_samples,
                        "excluded": report.excluded,
                        "old_weights": report.old_weights,
                        "new_weights": report.new_weights,
                        "mse_before": report.mse_before,
                        "mse_after": report.mse_after,
                        "improvement": report.improvement,
                        "acceptance_basis": report.acceptance_basis,
                        "cv_mse": [report.cv_mse_before, report.cv_mse_after],
                        "class_agreement": [report.class_agreement_before, report.class_agreement_after],
                        "stored_as": report.stored_as,
                        "level_offset": report.level_offset,
                        "level_bias_detected": report.level_bias_detected,
                        "warnings": report.warnings,
                        "message": report.message,
                    },
                )
            ],
        }
        return update
