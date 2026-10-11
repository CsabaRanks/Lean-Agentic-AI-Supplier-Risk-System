"""Generic provider for system exports (ERP, ESG platform, credit agency, ...).

Most organisations can export a table long before they can build an API
integration. ``CsvIndicatorProvider`` reads such an export and maps its columns
to indicator names. Examples:

* an ERP export with on-time delivery and PPM per supplier
  (columns -> ``on_time_rate``, ``quality_ppm``)
* an ESG platform export with scores per supplier (-> ``esg_score``)
* a credit agency export (-> ``credit_score``)

Rows are matched on ``supplier_id`` by default.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..models.domain import SupplierProfile
from .base import ProviderResult


class CsvIndicatorProvider:
    def __init__(
        self, path: str | Path, name: str, columns: dict[str, str], key_column: str = "supplier_id",
        as_of: str | None = None,
    ):
        """``columns`` maps CSV column -> indicator name, e.g. {"OTD %": "on_time_rate"}."""
        self.name = name
        self.columns = columns
        self.indicators = tuple(columns.values())
        self.as_of = as_of
        with Path(path).open(encoding="utf-8-sig") as fh:
            sample = fh.read(2048)
            fh.seek(0)
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
            self.rows = {r[key_column].strip(): r for r in csv.DictReader(fh, delimiter=delimiter)}

    def fetch(self, profile: SupplierProfile) -> ProviderResult | None:
        row = self.rows.get(profile.supplier_id)
        if row is None:
            return None
        values = {}
        for column, indicator in self.columns.items():
            raw = (row.get(column) or "").strip().replace(",", ".")
            if raw:
                try:
                    values[indicator] = float(raw)
                except ValueError:
                    values[indicator] = raw
        return ProviderResult(values, source=self.name, as_of=self.as_of)
