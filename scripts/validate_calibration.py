"""Validate the expert-label calibration on synthetic data.

Three experiments (results feed paper section 7 and its figures):

E1  Repeated k-fold cross-validation on the reference portfolio
    (data/calibration_portfolio.json, 32 labelled suppliers) over a grid of
    regularisation strengths lambda. Out-of-fold MSE of calibrated vs. default weights.
E2  Sample-size sensitivity: calibrate on n synthetic suppliers (many seeds,
    several lambdas), evaluate on a large independent test set, both against
    noisy labels and against the noise-free true scores.
E3  Seed stability at the reference size (n = 32): distribution of calibrated
    weights across seeds, and how often each weight moves in the direction of
    the hidden generating weighting.

All runs are deterministic. Outputs (CSV + JSON + Markdown summary) are written
to docs/paper/results/calibration-validation/.

    python scripts/validate_calibration.py           # full run (about a minute)
    python scripts/validate_calibration.py --quick   # small grid, used by tests
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from pathlib import Path

import numpy as np

from supplier_risk_agent import load_risk_model
from supplier_risk_agent.models import CalibrationSettings
from supplier_risk_agent.tools.calibration import (
    build_design_matrix,
    class_agreement,
    cross_validated_acceptance,
    mse,
    relative_improvement,
    solve_weights,
)
from supplier_risk_agent.tools.data_sources import JsonFileSource
from supplier_risk_agent.tools.synthetic import (
    hidden_weights,
    label_noise_floor,
    synthetic_portfolio,
)

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DATA = ROOT / "data" / "calibration_portfolio.json"
OUT_DIR = ROOT / "docs" / "paper" / "results" / "calibration-validation"

NOISE_SD, LABEL_STEP = 4.0, 5.0  # must match the generator defaults used for the reference portfolio

FULL = {
    "cv_k": 5, "cv_repeats": 20,
    "lambdas": [0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
    "sizes": [8, 12, 16, 24, 32, 48, 64, 96, 128, 192],
    "size_lambdas": [0.0, 0.05, 0.5],
    "size_seeds": 30, "test_n": 2000,
    "stability_n": 32, "stability_seeds": 100, "stability_lambda": 0.05,
}
QUICK = {
    "cv_k": 4, "cv_repeats": 1, "lambdas": [0.0, 0.05],
    "sizes": [12], "size_lambdas": [0.05], "size_seeds": 2, "test_n": 100,
    "stability_n": 32, "stability_seeds": 3, "stability_lambda": 0.05,
}


class Context:
    def __init__(self) -> None:
        self.model = load_risk_model()
        self.keys = self.model.factor_keys()
        self.default = self.model.default_weights()
        self.hidden = hidden_weights()
        self.theta_default = self.vector(self.default)
        self.theta_hidden = self.vector(self.hidden)
        self.base = self.model.calibration

    def vector(self, weights) -> np.ndarray:
        return np.array([weights.factor_weights[k] for k in self.keys])

    def settings(self, lam: float) -> CalibrationSettings:
        return self.base.model_copy(update={"regularization": lam})

    def design(self, profiles) -> tuple[np.ndarray, np.ndarray]:
        X, y, _, _ = build_design_matrix(profiles, self.model, self.default)
        return X, y

    def fit(self, X: np.ndarray, y: np.ndarray, lam: float) -> tuple[np.ndarray, bool, bool]:
        """Calibrate on (X, y). Returns (weights, accepted by the in-sample rule, accepted by the CV rule).

        Both rules are evaluated exactly as in ``tools.calibration.calibrate_weights``.
        """
        settings = self.settings(lam)
        theta, success = solve_weights(X, y, self.theta_default, self.model, settings)[:2]
        in_sample = relative_improvement(mse(X, y, self.theta_default, self.model), mse(X, y, theta, self.model))
        cv_passes = cross_validated_acceptance(X, y, self.theta_default, self.theta_default, self.model, settings)[0]
        threshold = settings.min_improvement
        return theta, bool(success and in_sample >= threshold), bool(success and cv_passes)

    def l1_to_hidden(self, theta: np.ndarray) -> float:
        return float(np.abs(theta - self.theta_hidden).sum())


# --- experiments --------------------------------------------------------------------------


def run_cv(ctx: Context, cfg: dict) -> tuple[list[dict], list[dict]]:
    profiles = JsonFileSource(REFERENCE_DATA)
    X, y = ctx.design([profiles.get_supplier(i) for i in profiles.list_supplier_ids()])
    n, k = len(y), cfg["cv_k"]
    rows = []
    for rep in range(cfg["cv_repeats"]):
        idx = list(range(n))
        random.Random(1000 + rep).shuffle(idx)
        folds = [idx[f::k] for f in range(k)]
        for f, test in enumerate(folds):
            train = [i for i in idx if i not in set(test)]
            for lam in cfg["lambdas"]:
                theta, acc_in, acc_cv = ctx.fit(X[train], y[train], lam)
                rows.append({
                    "lambda": lam, "repeat": rep, "fold": f, "n_train": len(train), "n_test": len(test),
                    "mse_train_default": mse(X[train], y[train], ctx.theta_default, ctx.model),
                    "mse_train_calibrated": mse(X[train], y[train], theta, ctx.model),
                    "mse_test_default": mse(X[test], y[test], ctx.theta_default, ctx.model),
                    "mse_test_calibrated": mse(X[test], y[test], theta, ctx.model),
                    "class_agreement_test_default": class_agreement(X[test], y[test], ctx.theta_default, ctx.model),
                    "class_agreement_test_calibrated": class_agreement(X[test], y[test], theta, ctx.model),
                    "l1_to_hidden": ctx.l1_to_hidden(theta),
                    "accepted_in_sample": acc_in,
                    "accepted_cv": acc_cv,
                })
    summary = []
    for lam in cfg["lambdas"]:
        r = [row for row in rows if row["lambda"] == lam]
        # pool out-of-fold errors per repeat (each supplier tested once per repeat), then average over repeats
        per_rep = {}
        for row in r:
            agg = per_rep.setdefault(row["repeat"], {"sse_d": 0.0, "sse_c": 0.0, "n": 0})
            agg["sse_d"] += row["mse_test_default"] * row["n_test"]
            agg["sse_c"] += row["mse_test_calibrated"] * row["n_test"]
            agg["n"] += row["n_test"]
        cv_d = [a["sse_d"] / a["n"] for a in per_rep.values()]
        cv_c = [a["sse_c"] / a["n"] for a in per_rep.values()]
        summary.append({
            "lambda": lam,
            "cv_mse_default": statistics.mean(cv_d),
            "cv_mse_calibrated": statistics.mean(cv_c),
            "cv_mse_calibrated_sd_over_repeats": statistics.pstdev(cv_c),
            "cv_relative_improvement": 1 - statistics.mean(cv_c) / statistics.mean(cv_d),
            "in_sample_mse_calibrated": statistics.mean(row["mse_train_calibrated"] for row in r),
            "class_agreement_test_default": statistics.mean(row["class_agreement_test_default"] for row in r),
            "class_agreement_test_calibrated": statistics.mean(row["class_agreement_test_calibrated"] for row in r),
            "l1_to_hidden": statistics.mean(row["l1_to_hidden"] for row in r),
            "acceptance_rate_in_sample": statistics.mean(row["accepted_in_sample"] for row in r),
            "acceptance_rate_cv": statistics.mean(row["accepted_cv"] for row in r),
        })
    return rows, summary


def run_sample_size(ctx: Context, cfg: dict) -> tuple[list[dict], list[dict]]:
    # independent test set: same suppliers once with noisy labels, once with noise-free true scores
    X_test, y_test = ctx.design(synthetic_portfolio(cfg["test_n"], 99_999, ctx.model, prefix="TEST"))
    _, y_true = ctx.design(synthetic_portfolio(cfg["test_n"], 99_999, ctx.model, noise_sd=0.0, label_step=0,
                                               prefix="TEST"))
    rows = []
    for n in cfg["sizes"]:
        for seed in range(cfg["size_seeds"]):
            X, y = ctx.design(synthetic_portfolio(n, seed, ctx.model))
            for lam in cfg["size_lambdas"]:
                theta, acc_in, acc_cv = ctx.fit(X, y, lam)
                true_default = mse(X_test, y_true, ctx.theta_default, ctx.model)
                true_calibrated = mse(X_test, y_true, theta, ctx.model)
                rows.append({
                    "n": n, "seed": seed, "lambda": lam,
                    "mse_in_sample": mse(X, y, theta, ctx.model),
                    "mse_test_labels_default": mse(X_test, y_test, ctx.theta_default, ctx.model),
                    "mse_test_labels_calibrated": mse(X_test, y_test, theta, ctx.model),
                    "mse_test_true_default": true_default,
                    "mse_test_true_calibrated": true_calibrated,
                    "l1_to_hidden": ctx.l1_to_hidden(theta),
                    "accepted_in_sample": acc_in,
                    "accepted_cv": acc_cv,
                    # error of the weights that would actually be in use after each rule's decision
                    "mse_test_true_applied_in_sample": true_calibrated if acc_in else true_default,
                    "mse_test_true_applied_cv": true_calibrated if acc_cv else true_default,
                })
    summary = []
    for n in cfg["sizes"]:
        for lam in cfg["size_lambdas"]:
            r = [row for row in rows if row["n"] == n and row["lambda"] == lam]
            summary.append({
                "n": n, "lambda": lam,
                **{f"{m}_mean": statistics.mean(row[m] for row in r) for m in (
                    "mse_in_sample", "mse_test_labels_calibrated", "mse_test_true_calibrated", "l1_to_hidden")},
                "mse_test_true_calibrated_p90": float(np.percentile([row["mse_test_true_calibrated"] for row in r], 90)),
                "mse_test_labels_default": r[0]["mse_test_labels_default"],
                "mse_test_true_default": r[0]["mse_test_true_default"],
                "share_better_than_default_true": statistics.mean(
                    bool(row["mse_test_true_calibrated"] < row["mse_test_true_default"]) for row in r),
                "acceptance_rate_in_sample": statistics.mean(row["accepted_in_sample"] for row in r),
                "acceptance_rate_cv": statistics.mean(row["accepted_cv"] for row in r),
                "mse_test_true_applied_in_sample_mean": statistics.mean(
                    row["mse_test_true_applied_in_sample"] for row in r),
                "mse_test_true_applied_cv_mean": statistics.mean(row["mse_test_true_applied_cv"] for row in r),
                # share of runs in which the applied weights are worse than keeping the defaults
                "harm_rate_in_sample": statistics.mean(
                    bool(row["mse_test_true_applied_in_sample"] > row["mse_test_true_default"]) for row in r),
                "harm_rate_cv": statistics.mean(
                    bool(row["mse_test_true_applied_cv"] > row["mse_test_true_default"]) for row in r),
            })
    return rows, summary


def run_stability(ctx: Context, cfg: dict) -> tuple[list[dict], list[dict]]:
    rows = []
    for seed in range(cfg["stability_seeds"]):
        X, y = ctx.design(synthetic_portfolio(cfg["stability_n"], seed, ctx.model))
        theta, acc_in, acc_cv = ctx.fit(X, y, cfg["stability_lambda"])
        rows.append({"seed": seed, "accepted_in_sample": acc_in, "accepted_cv": acc_cv,
                     "l1_to_hidden": ctx.l1_to_hidden(theta),
                     **{k: float(v) for k, v in zip(ctx.keys, theta)}})
    summary = []
    for j, k in enumerate(ctx.keys):
        vals = [row[k] for row in rows]
        target_dir = np.sign(ctx.theta_hidden[j] - ctx.theta_default[j])
        summary.append({
            "factor": k,
            "default": float(ctx.theta_default[j]), "hidden": float(ctx.theta_hidden[j]),
            "mean": statistics.mean(vals), "sd": statistics.pstdev(vals),
            "p05": float(np.percentile(vals, 5)), "p95": float(np.percentile(vals, 95)),
            # undefined when default and hidden weight coincide
            "share_moved_towards_hidden": None if target_dir == 0 else statistics.mean(
                bool(np.sign(v - ctx.theta_default[j]) == target_dir) for v in vals),
        })
    return rows, summary


# --- output -------------------------------------------------------------------------------


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})


def r(x: float, d: int = 2) -> float:
    return round(float(x), d)


def headline(ctx: Context, cfg: dict, cv: list[dict], size: list[dict], stab_rows: list[dict],
             stab: list[dict]) -> dict:
    default_lam = ctx.base.regularization
    cv_def = next(s for s in cv if s["lambda"] == default_lam) if default_lam in cfg["lambdas"] else cv[0]
    best = min(cv, key=lambda s: s["cv_mse_calibrated"])
    return {
        "config": cfg,
        "noise_floor_mse": label_noise_floor(NOISE_SD, LABEL_STEP),
        "cv_reference_portfolio": {
            "n_labelled": 32, "k": cfg["cv_k"], "repeats": cfg["cv_repeats"],
            "at_default_lambda": {key: r(v, 4) for key, v in cv_def.items()},
            "best_lambda": best["lambda"], "best_cv_mse": r(best["cv_mse_calibrated"], 3),
        },
        "sample_size_at_default_lambda": [
            {key: r(v, 3) for key, v in s.items()} for s in size if s["lambda"] == default_lam
        ],
        "stability": {
            "n": cfg["stability_n"], "seeds": cfg["stability_seeds"], "lambda": cfg["stability_lambda"],
            "acceptance_rate_in_sample": r(statistics.mean(row["accepted_in_sample"] for row in stab_rows), 3),
            "acceptance_rate_cv": r(statistics.mean(row["accepted_cv"] for row in stab_rows), 3),
            "l1_to_hidden_mean": r(statistics.mean(row["l1_to_hidden"] for row in stab_rows), 3),
            "l1_default_to_hidden": r(ctx.l1_to_hidden(ctx.theta_default), 3),
            "factors_moving_towards_hidden_in_most_seeds": [
                s["factor"] for s in stab if (s["share_moved_towards_hidden"] or 0) >= 0.5],
        },
    }


def markdown_summary(h: dict, cv: list[dict], size: list[dict], stab: list[dict], default_lam: float) -> str:
    lines = [
        "<!-- GENERATED by scripts/validate_calibration.py: do not edit by hand -->",
        "# Calibration validation: summary",
        "",
        "Synthetic data only. Labels = hidden-weighting score + N(0, 4²), rounded to steps of 5.",
        f"Irreducible label noise (MSE floor vs. labels): **{h['noise_floor_mse']:.2f}** score points².",
        f"Default regularisation λ = {default_lam}.",
        "",
        (f"## E1 · Repeated {h['config']['cv_k']}-fold CV on the reference portfolio (32 labelled suppliers, "
        f"{h['config']['cv_repeats']} repeats)"),
        "",
        ("| λ | CV MSE default | CV MSE calibrated (± sd) | rel. improvement | in-sample MSE | "
        "class agreement (test) default → calibrated | L1 to hidden | accepted: in-sample / CV rule |"),
        "|---:|---:|---:|---:|---:|---|---:|---:|",
    ]
    for s in cv:
        lines.append(
            f"| {s['lambda']:g} | {s['cv_mse_default']:.2f} | {s['cv_mse_calibrated']:.2f} "
            f"(± {s['cv_mse_calibrated_sd_over_repeats']:.2f}) | {s['cv_relative_improvement']:.1%} | "
            f"{s['in_sample_mse_calibrated']:.2f} | {s['class_agreement_test_default']:.0%} → "
            f"{s['class_agreement_test_calibrated']:.0%} | {s['l1_to_hidden']:.3f} | "
            f"{s['acceptance_rate_in_sample']:.0%} / {s['acceptance_rate_cv']:.0%} |")
    lines += [
        "",
        "## E2 · Sample size (independent test set; MSE vs. noise-free true scores)",
        "",
        ("| n | λ | in-sample MSE | test MSE vs labels | test MSE vs true (default → calibrated, p90) | "
        "better than default | L1 to hidden |"),
        "|---:|---:|---:|---:|---|---:|---:|",
    ]
    for s in size:
        lines.append(
            f"| {s['n']} | {s['lambda']:g} | {s['mse_in_sample_mean']:.2f} | {s['mse_test_labels_calibrated_mean']:.2f} | "
            f"{s['mse_test_true_default']:.2f} → {s['mse_test_true_calibrated_mean']:.2f} "
            f"(p90 {s['mse_test_true_calibrated_p90']:.2f}) | {s['share_better_than_default_true']:.0%} | "
            f"{s['l1_to_hidden_mean']:.3f} |")
    lines += [
        "",
        "### E2b · Acceptance rules: what ends up in use",
        "",
        ("Applied weights = calibrated weights if the rule accepts them, otherwise the defaults. "
        "Harm = applied weights worse than the defaults (test MSE vs. true scores)."),
        "",
        ("| n | λ | accepted: in-sample / CV | applied MSE: in-sample rule / CV rule (default) | "
        "harm rate: in-sample / CV |"),
        "|---:|---:|---|---|---|",
    ]
    for s in size:
        lines.append(
            f"| {s['n']} | {s['lambda']:g} | {s['acceptance_rate_in_sample']:.0%} / {s['acceptance_rate_cv']:.0%} | "
            f"{s['mse_test_true_applied_in_sample_mean']:.2f} / {s['mse_test_true_applied_cv_mean']:.2f} "
            f"({s['mse_test_true_default']:.2f}) | {s['harm_rate_in_sample']:.0%} / {s['harm_rate_cv']:.0%} |")
    st = h["stability"]
    lines += [
        "",
        f"## E3 · Weight stability (n = {st['n']}, {st['seeds']} seeds, λ = {st['lambda']})",
        "",
        (f"Accepted: {st['acceptance_rate_in_sample']:.0%} (in-sample rule) / {st['acceptance_rate_cv']:.0%} "
         "(CV rule); mean L1 distance to hidden weights "
        f"{st['l1_to_hidden_mean']:.3f} (default weights: {st['l1_default_to_hidden']:.3f})."),
        "",
        "| factor | default | hidden | calibrated mean ± sd | p05–p95 | moved towards hidden |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for s in stab:
        lines.append(
            f"| {s['factor']} | {s['default']:.3f} | {s['hidden']:.3f} | {s['mean']:.3f} ± {s['sd']:.3f} | "
            f"{s['p05']:.3f}–{s['p95']:.3f} | "
            + ("n/a (default = hidden)" if s["share_moved_towards_hidden"] is None
               else f"{s['share_moved_towards_hidden']:.0%}") + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="small grid for smoke tests")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    cfg = QUICK if args.quick else FULL

    ctx = Context()
    cv_rows, cv = run_cv(ctx, cfg)
    size_rows, size = run_sample_size(ctx, cfg)
    stab_rows, stab = run_stability(ctx, cfg)

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in [("e1_cv_folds", cv_rows), ("e1_cv_summary", cv), ("e2_sample_size_runs", size_rows),
                       ("e2_sample_size_summary", size), ("e3_stability_runs", stab_rows),
                       ("e3_stability_summary", stab)]:
        write_csv(args.out / f"{name}.csv", rows)
    h = headline(ctx, cfg, cv, size, stab_rows, stab)
    (args.out / "summary.json").write_text(json.dumps(h, indent=2) + "\n", encoding="utf-8")
    (args.out / "SUMMARY.md").write_text(markdown_summary(h, cv, size, stab, ctx.base.regularization),
                                         encoding="utf-8")
    print(f"wrote results to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
