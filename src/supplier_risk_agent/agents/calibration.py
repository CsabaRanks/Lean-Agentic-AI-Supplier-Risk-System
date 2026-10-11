"""Calibration Agent.

Learns factor weights from the judgement of category managers.

Input:  computed scores + factor ratings of the portfolio and holistic expert
        labels (``expert_risk_score``, 0..100) for some of the suppliers.
Output: calibrated weights that minimise the MSE between model score and
        expert label under the constraints  weight >= w_min  and  sum = 1,
        plus a report of old vs. new weights and the MSE before / after.

If the result is accepted (MSE improves by at least ``min_improvement``) and
``auto_apply`` is on, the calibrated weights become the active weights for the
calibration scope and the supervisor routes back to the Scoring Agent
(feedback loop). Otherwise the weights are only *proposed* and the run is
flagged for human review — weights that drive supplier decisions should not
change silently.

Scope: the MVP calibrates one weight set per run — globally, or for the
material group the run is restricted to (``state["material_group"]``). This
already allows per-material-group weights by running calibration per group.
The math lives in :mod:`supplier_risk_agent.tools.calibration`.
"""

from __future__ import annotations

from ..models.config import GLOBAL_SCOPE, RiskModelConfig
from ..models.domain import AuditEntry
from ..models.state import SupplierRiskState
from ..tools.calibration import calibrate_weights
from ..tools.scoring import resolve_weights

AGENT_NAME = "calibration"


class CalibrationAgent:
    def __init__(self, model: RiskModelConfig):
        self.model = model
        self.settings = model.calibration

    def __call__(self, state: SupplierRiskState) -> dict:
        scope = state.get("material_group") or GLOBAL_SCOPE
        active = dict(state.get("active_weights") or {})
        prior = resolve_weights(state.get("material_group"), active, self.model)

        report, new_weights = calibrate_weights(
            list(state["suppliers"].values()), self.model, prior, self.settings, scope=scope
        )

        update: dict = {
            "calibration_performed": True,
            "calibration_applied": False,
            "calibration_report": report,
            "calibrated_weights": new_weights,
            "mse_before": report.mse_before,
            "mse_after": report.mse_after,
        }
        review_reasons: list[str] = []
        if report.accepted and self.settings.auto_apply:
            active[scope] = new_weights
            report.applied = True
            update |= {"active_weights": active, "calibration_applied": True}
        elif report.accepted:
            update["requires_human_review"] = True
            review_reasons.append(f"calibrated weights for scope '{scope}' proposed — approval required")

        update["review_reasons"] = review_reasons
        update["audit_trail"] = [
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
                    "message": report.message,
                },
            )
        ]
        return update
