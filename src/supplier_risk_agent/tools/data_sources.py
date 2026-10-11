"""Supplier data access.

The data collection agent only depends on the :class:`SupplierDataSource`
protocol. Swap the bundled JSON source for an ERP export, a database, a
credit-rating API or a news/geopolitics feed without changing the graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from ..models.domain import SupplierProfile


class SupplierDataSource(Protocol):
    def get_supplier(self, supplier_id: str) -> SupplierProfile | None: ...

    def list_supplier_ids(self, material_group: str | None = None) -> list[str]: ...


class JsonFileSource:
    """Reads suppliers from a JSON file containing a list of supplier objects."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self._suppliers = {s["supplier_id"]: SupplierProfile.model_validate(s) for s in raw}

    def get_supplier(self, supplier_id: str) -> SupplierProfile | None:
        return self._suppliers.get(supplier_id)

    def list_supplier_ids(self, material_group: str | None = None) -> list[str]:
        return [
            sid for sid, s in self._suppliers.items()
            if material_group is None or s.material_group == material_group
        ]


class InMemorySource:
    """Convenience source for tests and notebooks."""

    def __init__(self, suppliers: list[SupplierProfile]):
        self._suppliers = {s.supplier_id: s for s in suppliers}

    def get_supplier(self, supplier_id: str) -> SupplierProfile | None:
        return self._suppliers.get(supplier_id)

    def list_supplier_ids(self, material_group: str | None = None) -> list[str]:
        return [
            sid for sid, s in self._suppliers.items()
            if material_group is None or s.material_group == material_group
        ]
