"""Calibrate the default weights against expert labels.

Uses the synthetic, labelled portfolio (see generate_calibration_dataset.py),
runs the graph with calibration enabled and shows old vs. new weights, the
MSE before / after and how risk classes changed through re-scoring.

    python examples/calibrate_weights.py
    python examples/calibrate_weights.py plastics   # calibrate one material group
"""

import sys
from pathlib import Path

from supplier_risk_agent import SupplierRiskEvaluator

DATA = Path(__file__).resolve().parents[1] / "data" / "calibration_portfolio.json"
group = sys.argv[1] if len(sys.argv) > 1 else None

evaluator = SupplierRiskEvaluator.from_json(DATA)
before = evaluator.run(material_group=group, calibrate=False)["results"]
after_state = evaluator.run(material_group=group, calibrate=True)
after = after_state["results"]
report = after_state["calibration_report"]

print(f"Scope: {report.scope}  |  samples: {report.n_samples}  |  {report.message}\n")
print(f"{'dimension':<16} {'old':>7} {'new':>7}")
for dim, old in report.old_dimension_weights.items():
    print(f"{dim:<16} {old:7.1%} {report.new_dimension_weights[dim]:7.1%}")

print(f"\n{'supplier':<9} {'expert':>6} {'before':>7} {'after':>7}  class change")
for sid, r in after.items():
    label = evaluator.source.get_supplier(sid).expert_risk_score
    b = before[sid]
    change = "" if b.risk_class == r.risk_class else f"{b.risk_class} -> {r.risk_class}"
    label_txt = f"{label:6.0f}" if label is not None else "     -"
    print(f"{sid:<9} {label_txt} {b.overall_score:7.1f} {r.overall_score:7.1f}  {change}")
