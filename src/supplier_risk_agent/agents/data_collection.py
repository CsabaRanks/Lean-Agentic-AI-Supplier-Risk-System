"""Data Collection Agent.

Loads master data, raw indicators and expert labels for the suppliers in scope.

Today: reads from a pluggable :class:`SupplierDataSource` (JSON by default).
Planned extensions: credit-rating APIs, ESG platforms, news / geopolitical
feeds, and an optional LLM step that extracts indicators from unstructured
documents (audit reports, self-assessment questionnaires).
"""

from __future__ import annotations

from ..models.domain import AuditEntry
from ..models.state import SupplierRiskState
from ..tools.data_sources import SupplierDataSource

AGENT_NAME = "data_collection"


class DataCollectionAgent:
    def __init__(self, source: SupplierDataSource):
        self.source = source

    def __call__(self, state: SupplierRiskState) -> dict:
        group = state.get("material_group")
        requested = state.get("supplier_ids") or self.source.list_supplier_ids(group)

        suppliers, errors = {}, []
        for sid in requested:
            profile = self.source.get_supplier(sid)
            if profile is None:
                errors.append(f"supplier '{sid}' not found in data source")
            elif group and profile.material_group != group:
                errors.append(f"supplier '{sid}' is not in material group '{group}'")
            else:
                suppliers[sid] = profile

        labels = {sid: p.expert_risk_score for sid, p in suppliers.items() if p.expert_risk_score is not None}
        return {
            "suppliers": suppliers,
            "expert_labels": labels,
            "errors": errors,
            "audit_trail": [
                AuditEntry(
                    agent=AGENT_NAME,
                    event="suppliers_loaded",
                    details={
                        "material_group": group,
                        "requested": len(requested),
                        "loaded": len(suppliers),
                        "expert_labels": len(labels),
                        "errors": errors,
                    },
                )
            ],
        }
