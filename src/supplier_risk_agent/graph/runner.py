"""High-level entry points: assess a portfolio, a material group or one supplier."""

from __future__ import annotations

from pathlib import Path

from ..models.config import RiskModelConfig, load_risk_model
from ..models.domain import RiskAssessment
from ..models.state import SupplierRiskState
from ..tools.data_sources import JsonFileSource, SupplierDataSource
from .builder import build_graph


class SupplierRiskEvaluator:
    """Convenience facade around the compiled graph."""

    def __init__(self, source: SupplierDataSource, model: RiskModelConfig | None = None):
        self.model = model or load_risk_model()
        self.source = source
        self.app = build_graph(self.model, source)

    @classmethod
    def from_json(cls, data_path: str | Path, model_path: str | Path | None = None) -> SupplierRiskEvaluator:
        return cls(JsonFileSource(data_path), load_risk_model(model_path))

    def run(
        self,
        supplier_ids: list[str] | None = None,
        material_group: str | None = None,
        calibrate: bool | None = None,
    ) -> SupplierRiskState:
        """Run the graph and return the full final state (incl. audit trail).

        ``calibrate=None`` falls back to ``calibration.enabled`` in the model.
        """
        initial: SupplierRiskState = {"supplier_ids": supplier_ids or [], "material_group": material_group}
        if calibrate is not None:
            initial["calibrate"] = calibrate
        return self.app.invoke(initial)

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
