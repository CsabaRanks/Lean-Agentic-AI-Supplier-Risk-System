"""E5: choosing the uncertainty threshold of the cross-validated acceptance rule.

The cross-validated rule accepts calibrated weights if the out-of-fold error
falls by at least ``min_improvement`` (5 %). E4 showed that this is not enough
when experts disagree: the improvement estimate itself is noisy. The rule can
additionally require z = mean per-supplier error reduction / its standard
error to reach ``cv_min_z``. Because out-of-fold errors are not independent,
z is optimistic and the threshold is chosen empirically here.

For each scenario (expert policy x number of labels x seed) the calibration is
fitted once; each threshold is then applied to the same run. Per threshold:

* acceptance rate
* harm rate: weights in use worse than the defaults (vs. noise-free truth)
* missed gain: error of the weights in use minus the better of (default, calibrated),
  i.e. what an oracle choosing between the two would have avoided

    python scripts/acceptance_study.py           # full run
    python scripts/acceptance_study.py --quick   # smoke test
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

import numpy as np
from robustness_calibration import MODEL, POLICIES, THETA_DEFAULT, labels, ratings

from supplier_risk_agent.tools.calibration import (
    cross_validated_errors,
    fit_weights,
    improvement_z,
    mse,
    relative_improvement,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "paper" / "results" / "acceptance-threshold"

FULL = {"policies": ["linear", "noise_high", "interaction", "knockout", "two_experts"],
        "sizes": [8, 16, 32, 64], "seeds": 100, "test_n": 2000,
        "z_grid": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]}
QUICK = {"policies": ["linear", "two_experts"], "sizes": [16], "seeds": 3, "test_n": 200,
         "z_grid": [0.0, 1.0, 2.0]}


def run(cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
    settings = MODEL.calibration
    X_test = ratings(cfg["test_n"], 99_999, "TEST")
    runs = []
    for p_idx, name in enumerate(cfg["policies"]):
        policy = POLICIES[name]
        y_true = policy[0](X_test)
        default_err = mse(X_test, y_true, THETA_DEFAULT, MODEL)
        for n in cfg["sizes"]:
            for seed in range(cfg["seeds"]):
                X = ratings(n, 50_000 + seed, "CAL")
                y = labels(X, policy, np.random.default_rng(20_000 * (p_idx + 1) + 97 * n + seed))
                theta, _, _, used, _ = fit_weights(X, y, THETA_DEFAULT, MODEL, settings)
                err_prior, err_refit = cross_validated_errors(X, y, THETA_DEFAULT, THETA_DEFAULT, MODEL, used)
                runs.append({
                    "policy": name, "n": n, "seed": seed,
                    "rel_improvement": relative_improvement(float(err_prior.mean()), float(err_refit.mean())),
                    "z": min(improvement_z(err_prior, err_refit), 99.0),
                    "mse_default": default_err,
                    "mse_calibrated": mse(X_test, y_true, theta, MODEL),
                })

    def accepts(r: dict, z_min: float) -> bool:
        return r["rel_improvement"] >= settings.min_improvement and r["z"] >= z_min

    by_cell, overall = [], []
    for z_min in cfg["z_grid"]:
        for name in cfg["policies"]:
            for n in cfg["sizes"]:
                cell = [r for r in runs if r["policy"] == name and r["n"] == n]
                accepted = [accepts(r, z_min) for r in cell]
                applied = [r["mse_calibrated"] if a else r["mse_default"] for a, r in zip(accepted, cell)]
                by_cell.append({
                    "z_min": z_min, "policy": name, "n": n,
                    "acceptance_rate": statistics.mean(accepted),
                    "harm_rate": statistics.mean(a > r["mse_default"] for a, r in zip(applied, cell)),
                    "mse_applied_mean": statistics.mean(applied),
                    "mse_default": cell[0]["mse_default"],
                    "missed_gain_mean": statistics.mean(
                        a - min(r["mse_default"], r["mse_calibrated"]) for a, r in zip(applied, cell)),
                })
        cells = [c for c in by_cell if c["z_min"] == z_min]
        overall.append({
            "z_min": z_min,
            "harm_rate_mean": statistics.mean(c["harm_rate"] for c in cells),
            "harm_rate_max": max(c["harm_rate"] for c in cells),
            "acceptance_rate_mean": statistics.mean(c["acceptance_rate"] for c in cells),
            # relative to the default error of each cell, so that policies with large errors do not dominate
            "missed_gain_rel_mean": statistics.mean(c["missed_gain_mean"] / c["mse_default"] for c in cells),
            "error_vs_default_mean": statistics.mean(c["mse_applied_mean"] / c["mse_default"] for c in cells),
        })
    return runs, by_cell, overall


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})


def markdown(by_cell: list[dict], overall: list[dict], cfg: dict) -> str:
    lines = [
        "<!-- GENERATED by scripts/acceptance_study.py: do not edit by hand -->",
        "# E5 · Uncertainty threshold for cross-validated acceptance: summary",
        "",
        (f"Synthetic data only. Policies {', '.join(cfg['policies'])}; n ∈ {cfg['sizes']}; "
         f"{cfg['seeds']} seeds per cell; λ = 0.05 × 32 / n (scaled default); min_improvement 5 %. Errors vs. noise-free truth."),
        "",
        "## Overall (mean over all policy × n cells)",
        "",
        ("| z_min | harm rate (mean / worst cell) | acceptance | missed gain (share of default error) | "
         "error in use / default error |"),
        "|---:|---|---:|---:|---:|",
    ]
    for o in overall:
        lines.append(
            f"| {o['z_min']:g} | {o['harm_rate_mean']:.1%} / {o['harm_rate_max']:.0%} | {o['acceptance_rate_mean']:.0%} | "
            f"{o['missed_gain_rel_mean']:.1%} | {o['error_vs_default_mean']:.2f} |")
    lines += ["", "## Per scenario: harm rate / acceptance rate", "",
              "| policy | n | " + " | ".join(f"z ≥ {z:g}" for z in cfg["z_grid"]) + " |",
              "|---|---:|" + "---|" * len(cfg["z_grid"])]
    for name in cfg["policies"]:
        for n in cfg["sizes"]:
            cells = {c["z_min"]: c for c in by_cell if c["policy"] == name and c["n"] == n}
            lines.append(f"| {name} | {n} | " + " | ".join(
                f"{cells[z]['harm_rate']:.0%} / {cells[z]['acceptance_rate']:.0%}" for z in cfg["z_grid"]) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    cfg = QUICK if args.quick else FULL

    runs, by_cell, overall = run(cfg)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "e5_runs.csv", runs)
    write_csv(args.out / "e5_by_scenario.csv", by_cell)
    write_csv(args.out / "e5_overall.csv", overall)
    (args.out / "summary.json").write_text(json.dumps({"config": cfg, "overall": overall}, indent=2) + "\n",
                                           encoding="utf-8")
    (args.out / "SUMMARY.md").write_text(markdown(by_cell, overall, cfg), encoding="utf-8")
    print(f"wrote results to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
