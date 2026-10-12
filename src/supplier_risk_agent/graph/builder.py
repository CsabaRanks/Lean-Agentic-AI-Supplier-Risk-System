"""Builds the LangGraph workflow.

Topology (hub-and-spoke around a supervisor):

    START -> supervisor -> collect_data | score | calibrate | recommend | human_review | END
             ^                  every worker returns to the supervisor  |
             +---------------------------------------------------------+

* ``calibrate`` is optional (config or per-run switch). When it applies new
  weights, the supervisor routes back to ``score`` once (feedback loop).
* ``human_review`` pauses the run with ``interrupt()`` until a reviewer resumes
  it. Approved weights or class overrides lead to re-scoring and/or new
  recommendations before the run ends.
* ``ai_review`` (optional) is the only node that calls a language model. It
  runs only on an explicit follow-up request and interprets results that are
  already final (see :class:`~supplier_risk_agent.agents.AIReviewAgent`).

A checkpointer is required for pausing; an in-memory one is used by default.
Pass a persistent checkpointer (e.g. SQLite) to resume runs across processes;
give it ``serde=state_serializer()`` so the state types can be restored.

New agents (e.g. external risk monitoring) are added by registering a node and
one routing rule in :class:`~supplier_risk_agent.agents.Supervisor`.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from ..agents import (
    AIReviewAgent,
    CalibrationAgent,
    DataCollectionAgent,
    HumanReviewAgent,
    RecommendationAgent,
    ScoringAgent,
    Supervisor,
)
from ..llm import ReviewModel
from ..models import ai_review as ai_review_models
from ..models import config as config_models
from ..models import domain as domain_models
from ..models.config import RiskModelConfig
from ..models.state import SupplierRiskState
from ..tools.data_sources import SupplierDataSource
from ..tools.weight_store import WeightStore

WORKERS = ("collect_data", "score", "calibrate", "recommend", "human_review", "ai_review")

# Domain types stored in the state. Checkpointers only deserialize allow-listed
# types, so they must be registered explicitly to pause and resume runs.
STATE_TYPES = [
    ai_review_models.AIReviewDraft,
    ai_review_models.AIReviewResult,
    ai_review_models.OpenQuestion,
    ai_review_models.RiskDriver,
    ai_review_models.SuggestedAction,
    ai_review_models.ViewDifference,
    config_models.WeightSet,
    domain_models.ActionRecommendation,
    domain_models.AuditEntry,
    domain_models.CalibrationReport,
    domain_models.ClassOverride,
    domain_models.DimensionScore,
    domain_models.Escalation,
    domain_models.FactorScore,
    domain_models.ReviewDecision,
    domain_models.RiskAssessment,
    domain_models.SupplierProfile,
]


def state_serializer() -> JsonPlusSerializer:
    """Checkpoint serializer that allows exactly this package's state types."""
    return JsonPlusSerializer(allowed_msgpack_modules=[(t.__module__, t.__name__) for t in STATE_TYPES])


def build_graph(
    model: RiskModelConfig,
    source: SupplierDataSource,
    weight_store: WeightStore | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    providers=(),
    ai_reviewer: ReviewModel | None = None,
):
    """Return a compiled LangGraph app for portfolio assessments.

    Invoke it with ``config={"configurable": {"thread_id": run_id}}``.
    """
    graph = StateGraph(SupplierRiskState)
    graph.add_node("supervisor", Supervisor(model))
    graph.add_node("collect_data", DataCollectionAgent(source, model, providers))
    graph.add_node("score", ScoringAgent(model))
    graph.add_node("calibrate", CalibrationAgent(model, weight_store))
    graph.add_node("recommend", RecommendationAgent(model))
    graph.add_node("human_review", HumanReviewAgent(model, weight_store))
    graph.add_node("ai_review", AIReviewAgent(model, ai_reviewer))

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["next_step"],
        {**{w: w for w in WORKERS}, "end": END},
    )
    for worker in WORKERS:
        graph.add_edge(worker, "supervisor")

    return graph.compile(checkpointer=checkpointer or InMemorySaver(serde=state_serializer()))
