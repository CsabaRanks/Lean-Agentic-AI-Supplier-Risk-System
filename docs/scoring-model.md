# Scoring model

> The bundled models are **example templates**. Criteria, weights, bands and thresholds are
> illustrative and must be adapted and calibrated for a real supplier base:
> - risk view: `src/supplier_risk_agent/config/default_risk_model.yaml`
> - performance view: `default_performance_model.yaml`

## Views and the shared criteria catalogue

Supplier **performance evaluation** ("How well does this supplier deliver?") and supplier **risk
management** ("How exposed are we if it fails?") are distinct practices. They use overlapping
information. The model reflects this in two layers.

**Criteria catalogue** (`config/criteria.yaml`)
- Every criterion is defined once: label, description and the rating source that turns data into
  a 1–5 rating.
- Ratings are always oriented 1 = favourable, 5 = unfavourable.

**Views** (one YAML each)
- A view selects criteria from the catalogue and groups them into its own dimensions with its own
  weights.
- It also defines its own classes, escalation rules, actions, material-group weights and
  calibration settings.
- A view can define extra criteria under `criteria:`.

| Criterion | Risk view | Performance view |
|---|---|---|
| availability, switching_complexity, business_impact | Severity Index | — |
| credit_risk | Financial Stability | Stability & Compliance |
| insolvency_signals | Financial Stability | — |
| country_risk, sourcing_strategy, transport_dependency | Supply Chain Risk | — |
| esg_rating, compliance_status | ESG & Compliance | Stability & Compliance |
| on_time_delivery, delivered_quality | — | Delivery, Quality |
| price_competitiveness, responsiveness | — | Commercial, Cooperation |

**Reading direction.** Internally, every view computes 0 = favourable … 100 = unfavourable, using
the same engine. The performance view *presents* its score as 100 − internal (higher = better),
and its expert labels (`expert_performance_score`) are given on that scale. Class thresholds in
the YAML refer to the internal scale.

**Performance view template.**
- Dimensions:
  - Delivery 30 % (on-time rate: ≥ 98 % → 1 … < 85 % → 5)
  - Quality 30 % (PPM: < 50 → 1 … ≥ 1000 → 5)
  - Commercial 20 %
  - Cooperation 10 %
  - Stability & Compliance 10 %
- Classes: A (performance ≥ 75), B (50–75), C (< 50).
- Escalation: a critical compliance finding → at least C.

**Separation between views.** Expert labels and stored weights are kept per view. Weight files
live in `<weights-dir>/<view>/`. Calibrating one view never changes the other.

**Naming rule for new criteria.** A criterion key must not equal the name of a *numeric* raw
indicator. In a spreadsheet row, a number under a criterion's name is read as an expert rating.
This is why the quality criterion is `delivered_quality` and its indicator is `quality_ppm`.

The rest of this document describes the risk view; the mechanics are identical for every view.

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

### Why `(R − 1) / 4 · 100`?

The rating scale is 1..5, so it has **no zero point**. The lowest possible risk is 1, not 0.
Min-max normalisation maps the *actual* range of the scale onto 0–100:

| Weighted rating R | `(R − 1) / 4 · 100` | naive `R / 5 · 100` |
|---|---|---|
| 1.0 (best possible) | **0** | 20 |
| 3.0 (scale midpoint) | **50** | 60 |
| 5.0 (worst possible) | **100** | 100 |

- **Uses the full range.** With `R / 5`, scores below 20 cannot occur. 20 % of the scale is dead
  space, and the remaining differences are compressed.
- **Intuitive anchors.** 0 = lowest risk the model can express, 50 = "medium" on every factor,
  100 = highest. The class thresholds (30 / 50 / 70) can be read directly against these anchors.
- **Compatible with expert labels.** Category managers give holistic risk labels on 0–100. An
  expert who says "lowest risk" means 0, not 20. Calibration compares labels and scores on the
  same scale (see [calibration.md](calibration.md)).
- **Linear.** The transformation is affine, so it does not change rankings or relative distances.
  That keeps calibration a linear least-squares problem.

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
