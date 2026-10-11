"""E4: robustness of the calibration when experts do NOT judge like the fitted model.

Experiments E1–E3 (validate_calibration.py) generate expert labels from the
same linear, additive model family that the calibration fits: the best case.
E4 replaces that labelling policy with alternatives a real expert panel might
follow, and asks:

* How close can ANY constrained linear weighting get to the policy?
  (approximation floor: fitted on 2,000 noise-free suppliers)
* How much of that does calibration achieve with 16 / 32 / 64 labels?
* Does the cross-validated acceptance rule still prevent harm?

Policies (true expert score as a function of the 1..5 factor ratings):

linear        hidden linear weighting (reference = E1–E3)
interaction   linear + synergy of business impact x sourcing strategy (both high = much worse)
knockout      linear, but a severe compliance or insolvency rating (>= 4) floors the score at 70
worst_factor  half linear, half the mean of the three worst factor ratings (non-compensatory)
level_shift   linear + 10 points: experts are uniformly stricter than the model's scale
two_experts   each supplier judged by one of two experts with different weightings;
              target = their average (panel consensus)
noise_low / noise_high / coarse
              linear policy with label noise sigma 2 or 8, or rounding to steps of 10

All labels: true score + N(0, sigma^2), rounded, clipped to 0..100 (sigma 4, step 5 unless stated).
Evaluation is against the policy's noise-free true score on an independent test set.
Calibration uses the production settings (lambda = 0.05, cross-validated acceptance).

    python scripts/robustness_calibration.py           # full run
    python scripts/robustness_calibration.py --quick   # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections.abc import Callable
from pathlib import Path

import numpy as np

from supplier_risk_agent import WeightSet, load_risk_model
from supplier_risk_agent.models import CalibrationSettings
from supplier_risk_agent.tools.calibration import (
    build_design_matrix,
    class_agreement,
    cross_validated_acceptance,
    level_offset,
    mse,
    solve_weights,
)
from supplier_risk_agent.tools.synthetic import HIDDEN_EXPERT_WEIGHTS, synthetic_portfolio

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "paper" / "results" / "calibration-robustness"

FULL = {"sizes": [16, 32, 64], "seeds": 30, "test_n": 2000}
QUICK = {"sizes": [16], "seeds": 2, "test_n": 200}

MODEL = load_risk_model()
KEYS = MODEL.factor_keys()
IDX = {k: i for i, k in enumerate(KEYS)}
LO, HI = MODEL.rating_scale.min, MODEL.rating_scale.max


def _vec(weights: dict[str, float]) -> np.ndarray:
    ws = WeightSet(origin="manual", factor_weights=weights)
    return np.array([ws.factor_weights[k] for k in KEYS])


THETA_HIDDEN = _vec(HIDDEN_EXPERT_WEIGHTS)
# a second expert who cares much more about ESG / compliance and less about business impact
THETA_EXPERT_B = _vec({**HIDDEN_EXPERT_WEIGHTS, "business_impact": 0.08, "esg_rating": 0.16,
                       "compliance_status": 0.14, "sourcing_strategy": 0.10})
THETA_DEFAULT = np.array([MODEL.default_weights().factor_weights[k] for k in KEYS])


def to_score(rating: np.ndarray) -> np.ndarray:
    return (rating - LO) / (HI - LO) * 100


def linear(X: np.ndarray, theta: np.ndarray = THETA_HIDDEN) -> np.ndarray:
    return to_score(X @ theta)


def interaction(X: np.ndarray) -> np.ndarray:
    bi = (X[:, IDX["business_impact"]] - 3) / 2
    ss = (X[:, IDX["sourcing_strategy"]] - 3) / 2
    return np.clip(linear(X) + 15 * bi * ss, 0, 100)


def knockout(X: np.ndarray) -> np.ndarray:
    severe = (X[:, IDX["compliance_status"]] >= 4) | (X[:, IDX["insolvency_signals"]] >= 4)
    return np.where(severe, np.maximum(linear(X), 70.0), linear(X))


def worst_factor(X: np.ndarray) -> np.ndarray:
    top3 = np.sort(X, axis=1)[:, -3:].mean(axis=1)
    return 0.5 * linear(X) + 0.5 * to_score(top3)


def level_shift(X: np.ndarray) -> np.ndarray:
    return np.clip(linear(X) + 10.0, 0, 100)


def consensus(X: np.ndarray) -> np.ndarray:
    return 0.5 * (linear(X, THETA_HIDDEN) + linear(X, THETA_EXPERT_B))


def two_experts_labels(X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    pick_b = rng.random(len(X)) < 0.5
    return np.where(pick_b, linear(X, THETA_EXPERT_B), linear(X, THETA_HIDDEN))


# name -> (true-score function used as target, labelling function, noise sigma, rounding step)
Policy = tuple[Callable, Callable | None, float, float]
POLICIES: dict[str, Policy] = {
    "linear": (linear, None, 4.0, 5.0),
    "interaction": (interaction, None, 4.0, 5.0),
    "knockout": (knockout, None, 4.0, 5.0),
    "worst_factor": (worst_factor, None, 4.0, 5.0),
    "level_shift": (level_shift, None, 4.0, 5.0),
    "two_experts": (consensus, two_experts_labels, 4.0, 5.0),
    "noise_low": (linear, None, 2.0, 5.0),
    "noise_high": (linear, None, 8.0, 5.0),
    "coarse": (linear, None, 4.0, 10.0),
}


def ratings(n: int, seed: int, prefix: str) -> np.ndarray:
    profiles = synthetic_portfolio(n, seed, MODEL, noise_sd=0.0, label_step=0, prefix=prefix)
    X, _, _, _ = build_design_matrix(profiles, MODEL, MODEL.default_weights())
    return X


def labels(X: np.ndarray, policy: Policy, rng: np.random.Generator) -> np.ndarray:
    target, labeller, sigma, step = policy
    true = labeller(X, rng) if labeller else target(X)
    noisy = true + rng.normal(0, sigma, len(X))
    rounded = step * np.round(noisy / step) if step else noisy
    return np.clip(rounded, 0, 100)


def fit(X: np.ndarray, y: np.ndarray, settings: CalibrationSettings) -> tuple[np.ndarray, bool]:
    theta, success = solve_weights(X, y, THETA_DEFAULT, MODEL, settings)[:2]
    passes = cross_validated_acceptance(X, y, THETA_DEFAULT, THETA_DEFAULT, MODEL, settings)[0]
    return theta, bool(success and passes)


def run(cfg: dict) -> tuple[list[dict], list[dict]]:
    settings = MODEL.calibration  # production defaults: lambda 0.05, cross-validated acceptance
    oracle_settings = settings.model_copy(update={"regularization": 0.0})
    X_test = ratings(cfg["test_n"], 99_999, "TEST")
    rows, summary = [], []
    for p_idx, (name, policy) in enumerate(POLICIES.items()):
        y_true = policy[0](X_test)
        theta_oracle = solve_weights(X_test, y_true, THETA_DEFAULT, MODEL, oracle_settings)[0]
        floor = mse(X_test, y_true, theta_oracle, MODEL)
        default_err = mse(X_test, y_true, THETA_DEFAULT, MODEL)
        ca_default = class_agreement(X_test, y_true, THETA_DEFAULT, MODEL)
        for n in cfg["sizes"]:
            runs = []
            for seed in range(cfg["seeds"]):
                X = ratings(n, seed, "CAL")
                y = labels(X, policy, np.random.default_rng(10_000 * (p_idx + 1) + seed))
                theta, accepted = fit(X, y, settings)
                offset, offset_t = level_offset(X, y, THETA_DEFAULT, MODEL)
                flagged = abs(offset) >= settings.level_bias_threshold and abs(offset_t) >= settings.level_bias_min_t
                calibrated = mse(X_test, y_true, theta, MODEL)
                applied = calibrated if accepted else default_err
                # with the level check, flagged calibrations go to review instead of being applied
                applied_checked = calibrated if accepted and not flagged else default_err
                row = {
                    "policy": name, "n": n, "seed": seed,
                    "mse_default": default_err, "mse_calibrated": calibrated, "mse_applied": applied,
                    "accepted_cv": accepted, "harm": bool(applied > default_err),
                    "level_offset": offset, "level_flag": bool(flagged),
                    "mse_applied_level_check": applied_checked, "harm_level_check": bool(applied_checked > default_err),
                    "class_agreement_calibrated": class_agreement(X_test, y_true, theta, MODEL),
                }
                rows.append(row)
                runs.append(row)
            summary.append({
                "policy": name, "n": n,
                "linear_floor_mse": floor,
                "mse_default": default_err,
                "mse_calibrated_mean": statistics.mean(r["mse_calibrated"] for r in runs),
                "mse_applied_mean": statistics.mean(r["mse_applied"] for r in runs),
                # share of the default weights' excess error (above the linear floor) removed by calibration
                "excess_error_removed": (default_err - statistics.mean(r["mse_calibrated"] for r in runs))
                / (default_err - floor) if default_err > floor else 0.0,
                "share_better_than_default": statistics.mean(
                    bool(r["mse_calibrated"] < r["mse_default"]) for r in runs),
                "acceptance_rate_cv": statistics.mean(r["accepted_cv"] for r in runs),
                "harm_rate_cv": statistics.mean(r["harm"] for r in runs),
                "level_offset_mean": statistics.mean(r["level_offset"] for r in runs),
                "level_flag_rate": statistics.mean(r["level_flag"] for r in runs),
                "harm_rate_level_check": statistics.mean(r["harm_level_check"] for r in runs),
                "class_agreement_default": ca_default,
                "class_agreement_calibrated_mean": statistics.mean(r["class_agreement_calibrated"] for r in runs),
            })
    return rows, summary


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})


def markdown(summary: list[dict], cfg: dict) -> str:
    lines = [
        "<!-- GENERATED by scripts/robustness_calibration.py: do not edit by hand -->",
        "# E4 · Calibration under misspecified expert policies: summary",
        "",
        (f"Synthetic data only. {cfg['seeds']} seeds per cell; independent test set of {cfg['test_n']} suppliers; "
        "errors are MSE (score points²) against the policy's noise-free true score. "
        "Production settings: λ = 0.05, cross-validated acceptance."),
        "",
        ("*Linear floor*: best constrained linear weighting fitted on the noise-free test set, i.e. what no "
        "linear model can beat. *Excess removed*: share of the default weights' error above that floor "
        "that calibration removes."),
        "",
        ("| policy | n | linear floor | default | calibrated | excess removed | better than default | "
        "accepted (CV) | harm (CV rule) | mean label−score | level flag | harm (CV + level check) | "
        "class agreement default → calibrated |"),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['policy']} | {s['n']} | {s['linear_floor_mse']:.1f} | {s['mse_default']:.1f} | "
            f"{s['mse_calibrated_mean']:.1f} | {s['excess_error_removed']:.0%} | "
            f"{s['share_better_than_default']:.0%} | {s['acceptance_rate_cv']:.0%} | {s['harm_rate_cv']:.0%} | "
            f"{s['level_offset_mean']:+.1f} | {s['level_flag_rate']:.0%} | {s['harm_rate_level_check']:.0%} | "
            f"{s['class_agreement_default']:.0%} → {s['class_agreement_calibrated_mean']:.0%} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    cfg = QUICK if args.quick else FULL

    rows, summary = run(cfg)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "e4_runs.csv", rows)
    write_csv(args.out / "e4_summary.csv", summary)
    (args.out / "summary.json").write_text(
        json.dumps({"config": cfg, "summary": [{k: (round(v, 4) if isinstance(v, float) else v)
                                                 for k, v in s.items()} for s in summary]}, indent=2) + "\n",
        encoding="utf-8")
    (args.out / "SUMMARY.md").write_text(markdown(summary, cfg), encoding="utf-8")
    print(f"wrote results to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
