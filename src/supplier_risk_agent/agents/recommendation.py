"""Action & Recommendation Agent.

Maps each supplier's risk class, elevated dimensions and fired escalation
rules to concrete, rule-based actions and a review cycle from the configured
action framework.

Planned extension: an optional LLM step that writes a short narrative
justification per supplier from the (already computed) scores — the LLM
explains, it never changes the numbers.
"""

from __future__ import annotations

from ..models.config import RiskModelConfig
from ..models.domain import AuditEntry
from ..models.state import SupplierRiskState
from ..tools.scoring import recommend

AGENT_NAME = "recommendation"


class RecommendationAgent:
    def __init__(self, model: RiskModelConfig):
        self.model = model

    def __call__(self, state: SupplierRiskState) -> dict:
        results = {
            sid: r.model_copy(update={"recommendations": recommend(r, self.model)})
            for sid, r in state["results"].items()
        }
        return {
            "results": results,
            "recommendations_done": True,
            "audit_trail": [
                AuditEntry(
                    agent=AGENT_NAME,
                    event="recommendations_created",
                    details={"actions": sum(len(r.recommendations) for r in results.values())},
                )
            ],
        }
