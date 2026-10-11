"""Supervisor / Orchestrator.

Decides which agent runs next based on what is already in the state. Routing
is deliberately rule-based: it is cheap, deterministic and easy to test. The
``route`` method is the single place to plug in an LLM-based supervisor later
(e.g. to decide when external data must be refreshed).

Flow:
    collect_data -> score -> [calibrate -> score] -> recommend -> [human_review] -> end

Calibration runs at most once per run, and only if enabled (per run via
``state["calibrate"]`` or globally via ``calibration.enabled``). If it applies
new weights, the supervisor routes back to scoring exactly once — the
calibration feedback loop is bounded by construction.
"""

from __future__ import annotations

from ..models.config import RiskModelConfig
from ..models.domain import AuditEntry
from ..models.state import Step, SupplierRiskState

AGENT_NAME = "supervisor"


class Supervisor:
    def __init__(self, model: RiskModelConfig):
        self.model = model

    def calibration_enabled(self, state: SupplierRiskState) -> bool:
        return state.get("calibrate", self.model.calibration.enabled)

    def route(self, state: SupplierRiskState) -> Step:
        if "suppliers" not in state:
            return "collect_data"
        if not state["suppliers"]:
            return "end"  # nothing to evaluate; errors are already recorded
        if "results" not in state:
            return "score"
        if self.calibration_enabled(state) and not state.get("calibration_performed"):
            return "calibrate"
        if state.get("calibration_applied") and state.get("scoring_round", 0) < 2:
            return "score"  # feedback loop: re-score with calibrated weights
        if not state.get("recommendations_done"):
            return "recommend"
        if state.get("requires_human_review") and "review_status" not in state:
            return "human_review"
        return "end"

    def __call__(self, state: SupplierRiskState) -> dict:
        step = self.route(state)
        return {
            "next_step": step,
            "audit_trail": [AuditEntry(agent=AGENT_NAME, event="routed", details={"next_step": step})],
        }


def human_review_node(state: SupplierRiskState) -> dict:
    """Placeholder for human-in-the-loop review.

    Currently it only marks the run as pending review. A later version can use
    LangGraph's ``interrupt()`` to pause the graph until a reviewer confirms or
    overrides results or proposed weights.
    """
    flagged = [sid for sid, r in state.get("results", {}).items() if r.requires_human_review]
    return {
        "review_status": "pending",
        "audit_trail": [
            AuditEntry(
                agent="human_review",
                event="review_requested",
                details={"suppliers": flagged, "portfolio_reasons": state.get("review_reasons", [])},
            )
        ],
    }
