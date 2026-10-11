# External data providers

Indicators come from three places, in this order of precedence:

1. **Expert ratings** in the supplier record, for example `switching_complexity = 4`. They always
   win over derived ratings.
2. **Values entered or imported** into the supplier data, through the sheet, a CSV or JSON.
3. **External providers**, which fill indicators that are still missing.

Providers only deliver raw indicators. Turning an indicator into a 1–5 rating is the job of the
rating sources in `tools/indicators.py`, so a provider can be replaced without changing the
method.

## The interface

```python
class ExternalDataProvider(Protocol):
    name: str
    indicators: tuple[str, ...]          # indicator names it can deliver
    def fetch(self, profile: SupplierProfile) -> ProviderResult | None: ...

ProviderResult(indicators={"esg_score": 62}, source="ESG platform export", as_of="2026-09")
```

How providers are applied:
- **When.** The Data Collection Agent applies them before scoring (`providers.enrich`).
- **No overwriting.** Missing indicators are filled; values entered by hand are kept.
- **Provenance.** It is recorded per indicator in `SupplierProfile.indicator_sources`.
- **Failures.** A failing or unconnected provider never stops an assessment. It appears as a
  message in the run's `errors`.

```python
from supplier_risk_agent import SupplierRiskEvaluator
from supplier_risk_agent.providers import WorldBankWgiProvider, CsvIndicatorProvider

evaluator = SupplierRiskEvaluator(source, providers=[
    WorldBankWgiProvider.from_csv("wgi_political_stability_2024.csv", year="2024"),
    CsvIndicatorProvider("erp_export.csv", "ERP export", {"OTD %": "on_time_rate", "PPM": "quality_ppm"},
                         key_column="Supplier", as_of="2026-09"),
])
```

## Available providers

| Provider | Delivers | Status |
|---|---|---|
| `WorldBankWgiProvider.mock()` | `wgi_political_stability` | **Placeholder.** Bundled **fictional** values for the fictional sample regions. For demos and tests only. CLI `--wgi-mock`; UI *Advanced*. |
| `WorldBankWgiProvider.from_csv(path)` | `wgi_political_stability` | **Usable.** Reads a WGI export you downloaded (columns `country`, `percentile_rank`). CLI `--wgi-csv`. |
| `WorldBankWgiProvider.from_api()` | — | **Placeholder.** Online retrieval is not implemented. |
| `CsvIndicatorProvider(path, name, columns)` | any indicator | **Usable.** Maps the columns of any system export (ERP, ESG platform, credit agency) to indicator names. Accepts `;` and decimal commas. |
| `EsgPlatformProvider` | `esg_score`, `compliance_status` | **Placeholder** for an ESG / sustainability rating platform API. |
| `ErpDeliveryProvider` | `on_time_rate`, `quality_ppm` | **Placeholder** for an ERP API (e.g. SAP) with delivery performance. |
| `CreditAgencyProvider` | `credit_score`, `distress_signals` | **Placeholder** for a credit agency API. |

Placeholders raise `NotImplementedError` and are reported as "not connected". Until an API
integration exists, export the data and use `CsvIndicatorProvider`.

## World Bank WGI: political stability

- **Indicator.** *Political Stability and Absence of Violence/Terrorism*, from the Worldwide
  Governance Indicators. Use the **percentile rank** (0–100, higher = more stable).
- **Matching.** Suppliers are matched on `SupplierProfile.country`. Use the same country codes or
  names in the supplier data and in the WGI file.
- **Mapping to 1–5** (rating source `political_stability`; illustrative bands):

  | Percentile rank | ≥ 80 | 60–80 | 40–60 | 20–40 | < 20 |
  |---|---|---|---|---|---|
  | Rating | 1 | 2 | 3 | 4 | 5 |

- **Fallback.** If no WGI value is available, the source falls back to a generic
  `country_risk_index` (0–100, higher = riskier).

## Adding a provider

1. Implement `name`, `indicators` and `fetch(profile)`, returning a `ProviderResult` or `None`.
2. If it delivers a new kind of indicator, add a rating source with
   `@register_source("my_source", reads=("my_indicator",))` and reference it from a criterion in
   `config/criteria.yaml`.
3. Pass it to `SupplierRiskEvaluator(..., providers=[...])`.
4. Mark the data vintage (`as_of`) so that the provenance stays traceable in the audit trail.
