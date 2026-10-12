"""Command line interface.

Examples:
    supplier-risk --data data/sample_suppliers.json
    supplier-risk --data data/sample_suppliers.json --supplier SUP-003
    supplier-risk --data data/calibration_portfolio.json --calibrate
    supplier-risk --data data/calibration_portfolio.json --material-group plastics --calibrate
    supplier-risk --data data/calibration_portfolio.json --calibrate --weights-dir data/weights
    supplier-risk --data data/sample_suppliers.json --review interactive
    supplier-risk --data data/sample_suppliers.json --json
    supplier-risk --data data/sample_suppliers.json --ai-review SUP-003   # optional LLM review
"""

from __future__ import annotations

import argparse
import json
import sys

from .graph import SupplierRiskEvaluator, ai_review_payload, ranked
from .llm import LLMReviewError, LLMSettings, load_env_file
from .models.ai_review import AIReviewResult
from .models.config import RiskModelConfig, available_views, load_risk_model
from .models.domain import CalibrationReport, ClassOverride, ReviewDecision, RiskAssessment
from .providers import WorldBankWgiProvider
from .tools import HistoryStore, JsonFileSource, WeightStore
from .tools.ai_review import payload_json


def _print_portfolio(results: list[RiskAssessment], model: RiskModelConfig) -> None:
    print(f"View: {model.view_label} — {model.view_question}\n")
    print(f"{'ID':<9} {'Supplier':<28} {'Score':>6}  {'Class':<9} {'Data':>5}  {'Weights':<20} Review")
    print("-" * 94)
    raised = False
    for r in results:
        shown = model.to_display(r.overall_score)
        score = f"{shown:6.1f}" if shown is not None else "   n/a"
        cls = r.risk_class or "n/a"
        if r.calculated_class and r.risk_class != r.calculated_class:
            cls += "*"
            raised = True
        print(
            f"{r.supplier_id:<9} {r.supplier_name[:28]:<28} {score}  {cls:<9} "
            f"{r.data_completeness:5.0%}  {r.weights_scope + '/' + r.weights_origin:<20} "
            f"{'yes' if r.requires_human_review else ''}"
        )
    if raised:
        print("\n* class raised by an escalation rule")


def _print_detail(r: RiskAssessment, model: RiskModelConfig) -> None:
    print(f"\n{r.supplier_name} ({r.supplier_id}) — model {r.model_name}@{r.model_version}")
    print(f"Material group: {r.material_group or '-'}  |  weights: {r.weights_scope}/{r.weights_origin}")
    print(f"{model.score_label}: {model.to_display(r.overall_score)}  |  class: {r.risk_class}  |  "
          f"data: {r.data_completeness:.0%}\n")
    for d in r.dimension_scores:
        shown = model.to_display(d.score)
        score = f"{shown:5.1f}" if shown is not None else "  n/a"
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
    if rep.cv_mse_before is not None:
        print(f"  cross-validated MSE {rep.cv_mse_before} -> {rep.cv_mse_after}, z = {rep.cv_improvement_z} "
              "(acceptance basis)")
    print(f"  in-sample MSE {rep.mse_before} -> {rep.mse_after}  |  class agreement "
          f"{rep.class_agreement_before:.0%} -> {rep.class_agreement_after:.0%}  |  applied: {rep.applied}")
    if rep.stored_as:
        print(f"  stored as: {rep.stored_as}")
    if rep.regularization_used is not None:
        print(f"  regularisation λ = {rep.regularization_used:.4g} ({rep.lambda_selection})")
    if rep.level_offset is not None:
        print(f"  mean label - score: {rep.level_offset:+.1f} points (t = {rep.level_offset_t:+.1f})")
    for warning in rep.warnings:
        print(f"  WARNING: {warning}")
    print(f"  {'factor':<22} {'old':>7} {'new':>7}  delta")
    for key, old in rep.old_weights.items():
        new = rep.new_weights[key]
        print(f"  {key:<22} {old:7.1%} {new:7.1%}  {new - old:+.1%}")


def _interactive_review(request: dict, ask=None) -> ReviewDecision:
    """Ask the reviewer in the terminal; returns the decision to resume the run."""
    ask = ask or input
    print("\n=== Human review required ===")
    for item in request["flagged_suppliers"]:
        print(f"  {item['supplier_id']} {item['name']}: class {item['risk_class']}")
        for reason in item["reasons"]:
            print(f"      - {reason}")
    approve = False
    proposed = request.get("proposed_weights")
    if proposed:
        print(f"  Proposed weights [{proposed['scope']}], {proposed['n_samples']} labels: "
              f"cross-validated MSE {proposed['cv_mse_before']} -> {proposed['cv_mse_after']} "
              f"(in-sample {proposed['mse_before']} -> {proposed['mse_after']})")
        for key, old in proposed["old_weights"].items():
            print(f"      {key:<22} {old:6.1%} -> {proposed['new_weights'][key]:6.1%}")
        for warning in proposed.get("warnings", []):
            print(f"  WARNING: {warning}")
        approve = ask("Approve proposed weights? [y/N] ").strip().lower() in {"y", "yes", "j", "ja"}

    overrides: dict[str, ClassOverride] = {}
    allowed = ", ".join(request["allowed_classes"])
    raw = ask(f"Class overrides, e.g. 'SUP-006=high' ({allowed}); empty to skip: ").strip()
    for part in filter(None, (p.strip() for p in raw.split(","))):
        sid, _, cls = part.partition("=")
        overrides[sid.strip()] = ClassOverride(risk_class=cls.strip())
    reviewer = ask("Reviewer name: ").strip() or "unknown"
    return ReviewDecision(reviewer=reviewer, approve_weights=approve, overrides=overrides)


def _print_ai_review(result: AIReviewResult) -> None:
    r = result.review
    print(f"\n=== AI review of {result.supplier_id} ({result.provider} / {result.model}) ===")
    for view, s in result.scores.items():
        print(f"  {view:<12} {s['score_label']}: {s['score']}  class: {s['class']}  "
              f"data: {s['data_completeness']:.0%}   (deterministic)")
    print(f"\nSummary\n  {r.management_summary}")
    print("\nMain drivers")
    for d in r.risk_drivers:
        print(f"  - [{d.view}] {d.criterion}: {d.explanation}")
    if r.view_differences:
        print("\nRisk vs. performance")
        for d in r.view_differences:
            print(f"  - {d.topic}: {d.explanation} ({', '.join(d.criteria) or '-'})")
    print("\nSuggested actions (for human review)")
    for a in r.suggested_actions:
        print(f"  - ({a.priority}) {a.action} — {a.rationale} ({', '.join(a.criteria) or '-'})")
    if r.open_questions or result.data_gaps:
        print("\nOpen questions")
        for q in r.open_questions:
            print(f"  - {q.question} ({', '.join(q.criteria) or '-'})")
        if result.data_gaps:
            print(f"  Missing data (from the input): {', '.join(result.data_gaps)}")
    print(f"\n{result.disclaimer}")


def _ai_review(args, store, providers, ask=None) -> int:
    """Run both views, show the payload, and call the LLM only after confirmation."""
    ask = ask or input
    load_env_file(".env")
    try:
        settings = LLMSettings.from_env()
    except LLMReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    runs = []
    for view in ("risk", "performance"):
        model = load_risk_model(args.model if view == args.view else None, view=view)
        evaluator = SupplierRiskEvaluator(JsonFileSource(args.data), model, store, providers=providers)
        runs.append((evaluator, evaluator.run(supplier_ids=[args.ai_review])))
    try:
        payload = ai_review_payload(args.ai_review, *runs)
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"Data that will be sent to the LLM provider ({settings.describe()}):\n")
    print(payload_json(payload))
    if settings.unavailable_reason:
        print(f"\nAI review not available: {settings.unavailable_reason}")
        print("The deterministic evaluation works without it.")
        return 0
    if not args.yes:
        try:
            answer = ask("\nSend this data to the provider? [y/N] ")
        except EOFError:  # no interactive input (e.g. piped or in CI): never send
            answer = ""
        if answer.strip().lower() not in {"y", "yes", "j", "ja"}:
            print("\nNot sent.")
            return 0

    evaluator, state = runs[0]
    state = evaluator.ai_review(state["run_id"], payload)
    error = state.get("ai_review_errors", {}).get(args.ai_review)
    if error:
        print(f"error: AI review failed: {error}", file=sys.stderr)
        return 1
    _print_ai_review(state["ai_reviews"][args.ai_review])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="supplier-risk", description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, help="JSON file with supplier records")
    parser.add_argument("--view", choices=available_views(), default="risk",
                        help="evaluation view: risk (default) or performance")
    parser.add_argument("--model", help="model YAML for the view (default: bundled example template)")
    parser.add_argument("--supplier", help="assess a single supplier ID")
    parser.add_argument("--material-group", help="restrict the run (and calibration scope) to one material group")
    cal = parser.add_mutually_exclusive_group()
    cal.add_argument("--calibrate", dest="calibrate", action="store_true", default=None,
                     help="calibrate weights against expert labels before recommending")
    cal.add_argument("--no-calibrate", dest="calibrate", action="store_false")
    parser.add_argument("--weights-dir", help="versioned weight store: load latest approved weights, save new ones")
    parser.add_argument("--history-dir", help="append a timestamped snapshot of the results (one file per view)")
    wgi = parser.add_mutually_exclusive_group()
    wgi.add_argument("--wgi-mock", action="store_true",
                     help="fill political stability from the bundled FICTIONAL World Bank WGI placeholder table")
    wgi.add_argument("--wgi-csv", help="fill political stability from a downloaded WGI CSV (country, percentile_rank)")
    parser.add_argument("--review", choices=["defer", "interactive"], default="defer",
                        help="when review is needed: leave it open (default) or ask in the terminal")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument("--ai-review", metavar="SUPPLIER_ID",
                        help="optional LLM review of one supplier across both views (needs ANTHROPIC_API_KEY); "
                             "shows the data to be sent and asks before calling the provider")
    parser.add_argument("--yes", action="store_true", help="with --ai-review: send without asking")
    args = parser.parse_args(argv)

    providers = []
    if args.wgi_mock:
        providers.append(WorldBankWgiProvider.mock())
    elif args.wgi_csv:
        providers.append(WorldBankWgiProvider.from_csv(args.wgi_csv))
    store = WeightStore(args.weights_dir) if args.weights_dir else None
    if args.ai_review:
        return _ai_review(args, store, providers)
    model = load_risk_model(args.model, view=args.view)
    evaluator = SupplierRiskEvaluator(JsonFileSource(args.data), model, store, providers=providers)
    state = evaluator.run(
        supplier_ids=[args.supplier] if args.supplier else None,
        material_group=args.material_group,
        calibrate=args.calibrate,
    )
    request = evaluator.pending_review(state)
    if request and args.review == "interactive" and not args.json:
        state = evaluator.resume(state["run_id"], _interactive_review(request))
        request = None

    for err in state.get("errors", []):
        print(f"error: {err}", file=sys.stderr)
    results = ranked(state)
    if not results:
        return 1
    if args.history_dir:
        written = HistoryStore(args.history_dir).record(
            results, evaluator.model, run_id=state["run_id"], note="cli, review pending" if request else "cli")
        print(f"history: {written} rows appended to {args.history_dir}/{evaluator.model.view}.jsonl",
              file=sys.stderr)

    report = state.get("calibration_report")
    if args.json:
        print(json.dumps({
            "run_id": state["run_id"],
            "results": [r.model_dump() for r in results],
            "calibration": report.model_dump() if report else None,
            "pending_review": request,
        }, indent=2))
        return 0

    if args.supplier:
        _print_detail(results[0], evaluator.model)
    else:
        _print_portfolio(results, evaluator.model)
    if report:
        _print_calibration(report)
    if request:
        pending = []
        if request["flagged_suppliers"]:
            pending.append(f"{len(request['flagged_suppliers'])} supplier(s)")
        if request["proposed_weights"]:
            pending.append("proposed weights")
        print(f"\nReview pending for {' and '.join(pending)} — rerun with --review interactive to decide.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
