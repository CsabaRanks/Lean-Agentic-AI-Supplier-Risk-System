# Scoring model

> The bundled model (`src/supplier_risk_agent/config/default_risk_model.yaml`) is an **example
> template**. Criteria, weights, bands and thresholds are illustrative and must be adapted and
> calibrated for a real supplier base.

## Structure

The model is a two-level hierarchy: **dimensions** made up of **factors**.

| Dimension | Default weight | Factors (weight within dimension) | Typical data |
|---|---|---|---|
| Severity Index | 35 % | availability of alternatives (30 %), change complexity (30 %), business consequence (40 %) | expert assessment by category manager |
| Financial Stability | 20 % | credit risk (70 %), insolvency / distress signals (30 %) | credit score, negative signals |
| Supply Chain Risk | 25 % | country / geopolitical risk (40 %), sourcing strategy (35 %), transport dependency (25 %) | country risk index, number of qualified sources, transport mode |
| ESG & Compliance | 20 % | ESG rating (60 %), compliance status (40 %) | ESG score, code-of-conduct / audit status |

The *Severity Index* is a weighted sub-score of how replaceable a supplier is and how much a
failure would hurt; the other dimensions describe the likelihood and structure of a disruption.

## Rating scale

Every factor is rated **1 (low risk) … 5 (high risk)**. Ratings come from either

- an **expert rating** (`expert_ratings` in the supplier record) — always wins, so judgement can
  override any derived value, or
- a **rating source** (`tools/indicators.py`) that converts a raw indicator into 1..5.

Example conversions (illustrative bands):

| Source | Raw value | Rating |
|---|---|---|
| `credit_score` (0–100, higher = healthier) | ≥80 / 65–80 / 50–65 / 35–50 / <35 | 1 / 2 / 3 / 4 / 5 |
| `country_risk_index` (0–100, higher = riskier) | <20 / 20–40 / 40–60 / 60–80 / ≥80 | 1 / 2 / 3 / 4 / 5 |
| `qualified_sources` | ≥3 / 2 / 1 | 1 / 3 / 5 |
| `transport_mode` | road / rail / air / sea (+1 if intercontinental) | 1 / 2 / 3 / 4 |
| `compliance_status` | compliant … critical_findings | 1 … 5 |

## Calculation

With effective factor weights θ (from a `WeightSet`, Σθ = 1):

```
W_d  = Σ θ_f                      (f in dimension d)
R_d  = Σ θ_f · r_f / Σ θ_f        (available f in d)
R    = Σ W_d · R_d / Σ W_d        (dimensions with data)
S    = (R − 1) / (5 − 1) · 100    → 0..100
```

The normalisation is **min-max**: a supplier rated 1 everywhere scores 0, rated 5 everywhere
scores 100. (A naive `R / 5` would map the best possible supplier to 20 %, which compresses the
usable range.)

### Missing data

Missing factors are excluded and the remaining weights are re-normalised within their dimension.
`data_completeness` = share of total weight backed by data. Below `min_data_completeness`
(default 75 %) the supplier is flagged for human review.

## Risk classes

| Class | Score range (default) | Review cycle | Example actions |
|---|---|---|---|
| Low | 0 – <30 | annual | standard evaluation |
| Medium | 30 – <50 | semi-annual | monitor indicators, discuss weak points |
| High | 50 – <70 | quarterly | mitigation plan, alternative sources, safety stock |
| Critical | ≥70 | monthly | escalation, immediate mitigation, contingency owner |

## Escalation rules

A weighted average can hide a single severe finding. Escalation rules set a **class floor** when a
factor reaches a rating, e.g.

- `compliance_status ≥ 5` → at least **high**
- `insolvency_signals ≥ 5` → at least **critical**

They only ever raise the class. The class before escalation is kept as `calculated_class`.

## Dimension triggers

Independently of the overall class, a dimension score above a threshold (default 60) adds a
targeted action, e.g. *“Evaluate regional or second-source alternatives”* for supply chain risk.

## Worked example

Fictional supplier `SUP-003` with default weights:

| Dimension | Ratings | R_d | Score |
|---|---|---|---|
| Severity | 5, 5, 5 | 5.00 | 100.0 |
| Financial | 4 (×0.7), 3 (×0.3) | 3.70 | 67.5 |
| Supply chain | 4 (×0.40), 5 (×0.35), 5 (×0.25) | 4.60 | 90.0 |
| ESG & compliance | 4 (×0.6), 3 (×0.4) | 3.60 | 65.0 |

R = 0.35·5 + 0.20·3.7 + 0.25·4.6 + 0.20·3.6 = 4.36 → S = (4.36 − 1)/4 · 100 = **84.0 → critical**.

## Weights per material group

One weighting rarely fits every commodity. `material_group_weights` in the YAML overrides
effective weights for a group; unlisted factors keep their default; the set is re-normalised.
Calibration can also produce group-specific weights (see [calibration.md](calibration.md)).
