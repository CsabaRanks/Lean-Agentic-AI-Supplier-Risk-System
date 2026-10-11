"""Builds the LangGraph workflow.

Topology (hub-and-spoke around a supervisor):

                         +-----------------+
          +------------->|   supervisor    |<-------------+
          |              +--------+--------+              |
          |                       | next_step             |
          |     +--------------+--+-----------+--------+  |
          |     v              v              v        v  |
     collect_data            score  <--   calibrate  recommend
                                    (re-score with           |
                                     calibrated weights)     |
                                                              v
                                              human_review (only if flagged) -> END

Every worker returns to the supervisor, which inspects the state and picks the
next step. ``calibrate`` is optional (config or per-run switch) and, when it
applies new weights, causes exactly one additional ``score`` round. New agents
(e.g. external risk monitoring) are added by registering a node and one
routing rule in :class:`~supplier_risk_agent.agents.Supervisor`.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..agents import (
    CalibrationAgent,
    DataCollectionAgent,
    RecommendationAgent,
    ScoringAgent,
    Supervisor,
    human_review_node,
)
from ..models.config import RiskModelConfig
from ..models.state import SupplierRiskState
from ..tools.data_sources import SupplierDataSource

WORKERS = ("collect_data", "score", "calibrate", "recommend")


def build_graph(model: RiskModelConfig, source: SupplierDataSource):
    """Return a compiled LangGraph app for portfolio assessments."""
    graph = StateGraph(SupplierRiskState)
    graph.add_node("supervisor", Supervisor(model))
    graph.add_node("collect_data", DataCollectionAgent(source))
    graph.add_node("score", ScoringAgent(model))
    graph.add_node("calibrate", CalibrationAgent(model))
    graph.add_node("recommend", RecommendationAgent(model))
    graph.add_node("human_review", human_review_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["next_step"],
        {**{w: w for w in WORKERS}, "human_review": "human_review", "end": END},
    )
    for worker in WORKERS:
        graph.add_edge(worker, "supervisor")
    graph.add_edge("human_review", END)

    return graph.compile()
