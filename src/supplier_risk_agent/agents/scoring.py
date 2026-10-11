"""Scoring Agent.

Turns supplier data into factor ratings, weighted dimension scores, a
normalised overall score and a risk class for every supplier in scope. All
arithmetic is delegated to the deterministic engine in
:mod:`supplier_risk_agent.tools.scoring`.

Weights come from ``state["active_weights"]`` (initialised from the config
defaults on the first round). When the Calibration Agent has accepted new
weights it replaces the relevant entry and the supervisor triggers this agent
again — that re-score is the feedback loop of the calibration.

It also performs the first governance check: results backed by too little data
are flagged for human review instead of being presented as final.
"""

from __future__ import annotations

from ..models.config import GLOBAL_SCOPE, RiskModelConfig
from ..models.domain import AuditEntry
from ..models.state import SupplierRiskState
from ..tools.scoring import assess_profile, resolve_weights

AGENT_NAME = "scoring"


class ScoringAgent:
    def __init__(self, model: RiskModelConfig):
        self.model = model

    def __call__(self, state: SupplierRiskState) -> dict:
        active = dict(state.get("active_weights") or {})
        if GLOBAL_SCOPE not in active:
            active[GLOBAL_SCOPE] = self.model.default_weights()

        results = {}
        for sid, profile in state["suppliers"].items():
            weights = resolve_weights(profile.material_group, active, self.model)
            results[sid] = assess_profile(profile, self.model, weights)

        round_no = state.get("scoring_round", 0) + 1
        flagged = [sid for sid, r in results.items() if r.requires_human_review]
        return {
            "results": results,
            "active_weights": active,
            "scoring_round": round_no,
            "requires_human_review": bool(flagged),
            "audit_trail": [
                AuditEntry(
                    agent=AGENT_NAME,
                    event="portfolio_scored",
                    details={
                        "model": f"{self.model.name}@{self.model.version}",
                        "round": round_no,
                        "weights": {scope: ws.origin for scope, ws in active.items()},
                        "scored": len(results),
                        "class_distribution": _distribution(results),
                        "flagged_for_review": flagged,
                    },
                )
            ],
        }


def _distribution(results: dict) -> dict[str, int]:
    dist: dict[str, int] = {}
    for r in results.values():
        key = r.risk_class or "n/a"
        dist[key] = dist.get(key, 0) + 1
    return dist
