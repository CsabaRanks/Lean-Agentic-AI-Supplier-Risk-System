# Sample data

All data in this folder is **entirely fictional**.

- `sample_suppliers.json` — six hand-crafted suppliers covering the main scoring paths (below).
- `calibration_portfolio.json` — 36 synthetic suppliers in three material groups, 32 of them with an
  expert label. Generated reproducibly by `examples/generate_calibration_dataset.py` from a hidden
  weighting plus noise, to demonstrate the Calibration Agent. **The expert labels are synthetic**,
  not real judgements.
- `weights/` — versioned weight store (see [weights/README.md](weights/README.md)).

In `sample_suppliers.json`, names, regions and all indicator values are invented to exercise the
different paths of the risk model:

| ID | Purpose |
|----|---------|
| SUP-001 | Healthy, multi-sourced supplier → low risk |
| SUP-002 | Average profile → medium risk |
| SUP-003 | Single source, weak finances, high country risk → critical |
| SUP-004 | Good score overall, but a critical compliance finding → escalation rule raises class |
| SUP-005 | Low score, but acute insolvency signals → escalation rule raises class |
| SUP-006 | Most data missing → flagged for human review |

The six suppliers also carry performance data: on-time rate, PPM, price competitiveness and
responsiveness. Some deliberately score differently in the two views. SUP-003 and SUP-005 are
critical in the risk view and A suppliers in the performance view. The calibration portfolio
carries synthetic performance labels (`expert_scores.performance`, higher = better), generated
from a delivery-heavy hidden weighting.

## Record format

```jsonc
{
  "supplier_id": "SUP-001",
  "name": "…",
  "material_group": "plastics",   // optional; selects group-specific weights
  "country": "…",
  "annual_spend": 1200000,
  // subjective 1..5 ratings (1 = low risk); override any derived rating
  "expert_ratings": {"availability": 2, "switching_complexity": 2, "business_impact": 3},
  // raw indicators, converted to 1..5 by src/supplier_risk_agent/tools/indicators.py
  "indicators": {
    "credit_score": 84,          // 0..100, higher = healthier
    "distress_signals": 0,       // count of negative financial signals
    "country_risk_index": 12,    // 0..100, higher = riskier
    "qualified_sources": 3,      // qualified sources for the supplied scope
    "transport_mode": "road",    // road | rail | air | sea
    "intercontinental": false,
    "esg_score": 78,             // 0..100, higher = better
    "compliance_status": "compliant"  // compliant | minor_findings | open_findings | major_findings | critical_findings
  },
  // optional holistic expert label used for calibration: 0..100 on the model's score scale
  // (the expert's class is derived from it with the model's thresholds)
  "expert_risk_score": 20
}
```
