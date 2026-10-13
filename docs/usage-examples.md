# CLI, Python and worked examples

[Back to the product overview](../README.md)

Run these commands from the repository root after the [demo installation](../README.md#try-the-demo).
The examples below use synthetic suppliers and synthetic expert labels; calibration outputs are
illustrative reference results, not production performance claims.

## CLI

```bash
supplier-risk --data data/sample_suppliers.json                         # risk view
supplier-risk --data data/sample_suppliers.json --view performance      # performance view
supplier-risk --data data/sample_suppliers.json --supplier SUP-003      # one supplier in detail
supplier-risk --data data/calibration_portfolio.json --calibrate --weights-dir data/weights
supplier-risk --data data/sample_suppliers.json --review interactive    # decide pending reviews
supplier-risk --data data/sample_suppliers.json --wgi-mock --history-dir data/history
```

`supplier-risk --help` lists all options. Generated weights (`data/weights/<view>/`) and history
(`data/history/`) are git-ignored.

## Python

```python
from supplier_risk_agent import SupplierRiskEvaluator

evaluator = SupplierRiskEvaluator.from_json("data/sample_suppliers.json", view="risk")
result = evaluator.assess("SUP-003")
print(result.overall_score, result.risk_class)          # 84.0 critical
for action in result.recommendations:
    print(action.priority, action.action)
```

## 1. The same supplier, seen from two sides

```bash
supplier-risk --data data/sample_suppliers.json                      # risk view
supplier-risk --data data/sample_suppliers.json --view performance   # performance view
```

| Supplier (fictional) | Risk score | Risk class | Performance score | Performance class |
|---|---:|---|---:|---|
| Cobalt Specialty Chemicals | 84.0 | critical | 75.6 | A |
| Evergreen Packaging | 19.5 | critical\* | 79.4 | A |
| Delta Fibre Media | 41.8 | high\* | 38.8 | C |
| Alpha Precision Parts | 12.2 | low | 77.5 | A |

\* class raised by an escalation rule (Evergreen: acute insolvency signals; Delta: critical
compliance finding).

Cobalt and Evergreen deliver well (A suppliers) but are critical from a risk perspective: single
source and high country risk for Cobalt, acute insolvency signals for Evergreen despite a low
weighted score. A performance-only evaluation would not show this; a risk platform alone would not
show that these are suppliers worth protecting rather than replacing.
`supplier-risk --data data/sample_suppliers.json --supplier SUP-003` explains every factor, its
weight, its data source and the resulting actions.

## 2. Checking the weights against the category managers

```bash
supplier-risk --data data/calibration_portfolio.json --calibrate --weights-dir data/weights --review interactive
```

The demo portfolio contains 36 synthetic suppliers, 32 of them with a synthetic expert judgement.
The Calibration Agent fits new weights and tests them out of sample before accepting them:

```
Calibration [global] — 32 labelled supplier(s): accepted: cross-validated MSE 37.8 -> 22.8, z = 2.4
  in-sample MSE 37.77 -> 13.265  |  class agreement 84% -> 88%  |  applied: False
  mean label - score: +2.2 points (t = +2.1)
  factor                     old     new  delta
  business_impact          14.0%   18.1%  +4.1%
  sourcing_strategy         8.8%   14.6%  +5.8%
  esg_rating               12.0%    7.5%  -4.5%
  ...
```

Read as: the synthetic "experts" weight sourcing strategy and business impact more and ESG less
than the template. The change is accepted because the error drops by about 40 % on held-out
suppliers *and* the drop is clearly larger than its own uncertainty (z ≥ 2). With fewer or noisier
labels the same step rejects the change, or flags patterns that weights cannot express (a level
offset between experts and model, knock-out logic). Accepted weights are only **proposed**: the run
pauses, a reviewer approves or rejects them in the terminal or in the **Approvals** view, and
approved weights are stored as a new version with the reviewer's name.

For the acceptance rule, uncertainty limits and reproducible experiments, see
[calibration](calibration.md) and the [working paper](paper/paper.md).
