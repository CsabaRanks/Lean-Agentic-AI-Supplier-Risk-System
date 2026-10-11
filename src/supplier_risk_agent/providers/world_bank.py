"""World Bank Worldwide Governance Indicators (WGI): political stability per country.

Indicator used: "Political Stability and Absence of Violence/Terrorism", as a
percentile rank 0..100 among all countries (higher = more stable). The rating
source ``political_stability`` maps it to the 1..5 scale:

    >= 80 -> 1,  60-80 -> 2,  40-60 -> 3,  20-40 -> 4,  < 20 -> 5

Three ways to obtain the data:

* ``WorldBankWgiProvider.mock()``: a bundled, **fictional** table for the
  fictional regions of the sample data. It is a placeholder for demos and
  tests and contains no real country values.
* ``WorldBankWgiProvider.from_csv(path)``: real data you downloaded yourself
  (WGI data portal / World Bank DataBank), as a CSV with a country column and a
  percentile-rank column. This is the recommended way today.
* ``WorldBankWgiProvider.from_api()``: online retrieval, **not implemented**.
  It is a placeholder for a later version.

Supplier records are matched on ``SupplierProfile.country``. Use the same
country codes or names in both files.
"""

from __future__ import annotations

import csv
from importlib import resources
from pathlib import Path

from ..models.domain import SupplierProfile
from ..tools.indicators import WGI_INDICATOR
from .base import ProviderResult


class WorldBankWgiProvider:
    name = "world_bank_wgi"
    indicators = (WGI_INDICATOR,)

    def __init__(self, table: dict[str, float], year: str | None, label: str):
        self.table = {k.strip().lower(): v for k, v in table.items()}
        self.year = year
        self.label = label

    @classmethod
    def mock(cls) -> WorldBankWgiProvider:
        """Fictional placeholder values for the fictional sample regions. Not real data."""
        text = resources.files("supplier_risk_agent.providers").joinpath("mock_data/wgi_mock.csv").read_text("utf-8")
        rows = list(csv.DictReader(line for line in text.splitlines() if not line.startswith("#")))
        return cls({r["country"]: float(r["percentile_rank"]) for r in rows}, rows[0]["year"] if rows else None,
                   "World Bank WGI (MOCK - fictional values)")

    @classmethod
    def from_csv(
        cls, path: str | Path, country_column: str = "country", value_column: str = "percentile_rank",
        year: str | None = None,
    ) -> WorldBankWgiProvider:
        """Load a WGI export you downloaded (one row per country)."""
        with Path(path).open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        table = {r[country_column]: float(r[value_column]) for r in rows if r.get(value_column) not in (None, "")}
        return cls(table, year, f"World Bank WGI{f' {year}' if year else ''}")

    @classmethod
    def from_api(cls, *_, **__) -> WorldBankWgiProvider:
        raise NotImplementedError(
            "online WGI retrieval is a placeholder; download the data and use WorldBankWgiProvider.from_csv()"
        )

    def fetch(self, profile: SupplierProfile) -> ProviderResult | None:
        value = self.table.get((profile.country or "").strip().lower())
        if value is None:
            return None
        return ProviderResult({WGI_INDICATOR: value}, source=self.label, as_of=self.year)
