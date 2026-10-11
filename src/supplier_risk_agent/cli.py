"""Command line interface.

Examples:
    supplier-risk --data data/sample_suppliers.json
    supplier-risk --data data/sample_suppliers.json --supplier SUP-003
    supplier-risk --data data/calibration_portfolio.json --calibrate
    supplier-risk --data data/calibration_portfolio.json --material-group plastics --calibrate
    supplier-risk --data data/sample_suppliers.json --json
"""

from __future__ import annotations

import argparse
import json
import sys

from .graph import SupplierRiskEvaluator, ranked
from .models.domain import CalibrationReport, RiskAssessment


def _print_portfolio(results: list[RiskAssessment]) -> None:
    print(f"{'ID':<9} {'Supplier':<28} {'Score':>6}  {'Class':<9} {'Data':>5}  {'Weights':<20} Review")
    print("-" * 94)
    for r in results:
        score = f"{r.overall_score:6.1f}" if r.overall_score is not None else "   n/a"
        cls = r.risk_class or "n/a"
        if r.calculated_class and r.risk_class != r.calculated_class:
            cls += "*"
        print(
            f"{r.supplier_id:<9} {r.supplier_name[:28]:<28} {score}  {cls:<9} "
            f"{r.data_completeness:5.0%}  {r.weights_scope + '/' + r.weights_origin:<20} "
            f"{'yes' if r.requires_human_review else ''}"
        )
    print("\n* class raised by an escalation rule")


def _print_detail(r: RiskAssessment) -> None:
    print(f"\n{r.supplier_name} ({r.supplier_id}) — model {r.model_name}@{r.model_version}")
    print(f"Material group: {r.material_group or '-'}  |  weights: {r.weights_scope}/{r.weights_origin}")
    print(f"Overall score: {r.overall_score}  |  class: {r.risk_class}  |  data: {r.data_completeness:.0%}\n")
    for d in r.dimension_scores:
        score = f"{d.score:5.1f}" if d.score is not None else "  n/a"
        print(f"  {d.label:<22} weight {d.weight:5.1%}  score {score}")
        for f in (f for f in r.factor_scores if f.dimension == d.dimension):
            rating = f.rating if f.rating is not None else "-"
            print(f"      {f.factor:<22} {rating}  w={f.weight:5.1%}  ({f.rationale})")
    if r.escalations:
        print("\nEscalations:")
        for e in r.escalations:
            print(f"  - {e.rule_factor}: floor '{e.floor_class}' — {e.reason}")
    print("\nRecommended actions:")
    for a in r.recommendations:
        cycle = f" [review: {a.review_cycle}]" if a.review_cycle else ""
        print(f"  - ({a.priority}) {a.action}{cycle}")
    if r.requires_human_review:
        print("\nHuman review required:")
        for reason in r.review_reasons:
            print(f"  - {reason}")


def _print_calibration(rep: CalibrationReport) -> None:
    print(f"\nCalibration [{rep.scope}] — {rep.n_samples} labelled supplier(s): {rep.message}")
    if rep.excluded:
        print(f"  excluded: {', '.join(f'{k} ({v})' for k, v in rep.excluded.items())}")
    if rep.new_weights is None:
        return
    print(f"  MSE {rep.mse_before} -> {rep.mse_after}  |  applied: {rep.applied}")
    print(f"  {'factor':<22} {'old':>7} {'new':>7}  delta")
    for key, old in rep.old_weights.items():
        new = rep.new_weights[key]
        print(f"  {key:<22} {old:7.1%} {new:7.1%}  {new - old:+.1%}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="supplier-risk", description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="JSON file with supplier records")
    parser.add_argument("--model", help="risk model YAML (default: bundled example template)")
    parser.add_argument("--supplier", help="assess a single supplier ID")
    parser.add_argument("--material-group", help="restrict the run (and calibration scope) to one material group")
    cal = parser.add_mutually_exclusive_group()
    cal.add_argument("--calibrate", dest="calibrate", action="store_true", default=None,
                     help="calibrate weights against expert labels before recommending")
    cal.add_argument("--no-calibrate", dest="calibrate", action="store_false")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    evaluator = SupplierRiskEvaluator.from_json(args.data, args.model)
    state = evaluator.run(
        supplier_ids=[args.supplier] if args.supplier else None,
        material_group=args.material_group,
        calibrate=args.calibrate,
    )
    for err in state.get("errors", []):
        print(f"error: {err}", file=sys.stderr)
    results = ranked(state)
    if not results:
        return 1

    report = state.get("calibration_report")
    if args.json:
        print(json.dumps({
            "results": [r.model_dump() for r in results],
            "calibration": report.model_dump() if report else None,
        }, indent=2))
        return 0

    if args.supplier:
        _print_detail(results[0])
    else:
        _print_portfolio(results)
    if report:
        _print_calibration(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
