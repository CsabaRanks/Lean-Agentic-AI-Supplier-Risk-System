"""Assess the fictional sample portfolio and print a ranked overview.

    python examples/run_portfolio.py
"""

from pathlib import Path

from supplier_risk_agent import SupplierRiskEvaluator

DATA = Path(__file__).resolve().parents[1] / "data" / "sample_suppliers.json"

evaluator = SupplierRiskEvaluator.from_json(DATA)
state = evaluator.run()

for r in sorted(state["results"].values(), key=lambda r: r.overall_score or -1, reverse=True):
    flag = " (review)" if r.requires_human_review else ""
    print(f"{r.supplier_id}  {r.overall_score:6.1f}  {r.risk_class:<9} {r.supplier_name}{flag}")
    for action in r.recommendations[:2]:
        print(f"           -> {action.action}")

print("\nAudit trail:")
for entry in state["audit_trail"]:
    print(f"  {entry.agent:<16} {entry.event}")
