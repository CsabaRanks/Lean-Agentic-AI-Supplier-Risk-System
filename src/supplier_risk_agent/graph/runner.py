"""High-level entry points: assess a portfolio, a material group or one supplier."""

from __future__ import annotations

import uuid
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from ..models.config import RiskModelConfig, load_risk_model
from ..models.domain import ReviewDecision, RiskAssessment
from ..models.state import SupplierRiskState
from ..tools.data_sources import JsonFileSource, SupplierDataSource
from ..tools.weight_store import WeightStore
from .builder import build_graph


class SupplierRiskEvaluator:
    """Convenience facade around the compiled graph.

    A run that needs human review pauses and returns its state with a
    ``"__interrupt__"`` entry. Inspect it with :meth:`pending_review` and
    continue with :meth:`resume`.
    """

    def __init__(
        self,
        source: SupplierDataSource,
        model: RiskModelConfig | None = None,
        weight_store: WeightStore | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
    ):
        self.model = model or load_risk_model()
        self.source = source
        # weights are stored per view (<dir>/<view>/<scope>_vNNN.yaml)
        self.weight_store = weight_store.for_view(self.model.view) if weight_store else None
        self.app = build_graph(self.model, source, self.weight_store, checkpointer)

    @classmethod
    def from_json(
        cls,
        data_path: str | Path,
        model_path: str | Path | None = None,
        weights_dir: str | Path | None = None,
        view: str = "risk",
    ) -> SupplierRiskEvaluator:
        store = WeightStore(weights_dir) if weights_dir else None
        return cls(JsonFileSource(data_path), load_risk_model(model_path, view=view), store)

    @staticmethod
    def _config(run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    def run(
        self,
        supplier_ids: list[str] | None = None,
        material_group: str | None = None,
        calibrate: bool | None = None,
        run_id: str | None = None,
    ) -> SupplierRiskState:
        """Run the graph and return the state (incl. audit trail).

        ``calibrate=None`` falls back to ``calibration.enabled`` in the model.
        With a weight store, the latest stored weights per scope are the
        starting weights of the run.
        """
        run_id = run_id or uuid.uuid4().hex[:12]
        initial: SupplierRiskState = {
            "run_id": run_id,
            "supplier_ids": supplier_ids or [],
            "material_group": material_group,
        }
        if calibrate is not None:
            initial["calibrate"] = calibrate
        if self.weight_store is not None:
            active, warnings = self.weight_store.load_active(self.model)
            initial["active_weights"] = active
            initial["errors"] = warnings
        return self.app.invoke(initial, self._config(run_id))

    @staticmethod
    def pending_review(state: SupplierRiskState) -> dict | None:
        """The review request if the run is paused at human review, else None."""
        interrupts = state.get("__interrupt__")
        return interrupts[0].value if interrupts else None

    def resume(self, run_id: str, decision: ReviewDecision | dict) -> SupplierRiskState:
        """Continue a paused run with a reviewer's decision."""
        payload = decision.model_dump() if isinstance(decision, ReviewDecision) else decision
        return self.app.invoke(Command(resume=payload), self._config(run_id))

    def assess(self, supplier_id: str) -> RiskAssessment:
        state = self.run([supplier_id])
        if supplier_id not in state.get("results", {}):
            raise LookupError("; ".join(state.get("errors", [])) or f"unknown supplier {supplier_id}")
        return state["results"][supplier_id]

    def assess_all(self, material_group: str | None = None, calibrate: bool | None = None) -> list[RiskAssessment]:
        return ranked(self.run(material_group=material_group, calibrate=calibrate))


def ranked(state: SupplierRiskState) -> list[RiskAssessment]:
    """Results of a run, highest risk first."""
    results = state.get("results", {}).values()
    return sorted(results, key=lambda r: r.overall_score if r.overall_score is not None else -1, reverse=True)
