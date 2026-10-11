"""Plot paper Figures 4–6 from the calibration validation results.

Reads the CSV summaries written by scripts/validate_calibration.py and writes

    docs/paper/figures/fig04_lambda_curve.{png,svg}       E1: error vs. regularisation strength
    docs/paper/figures/fig05_learning_curve.{png,svg}     E2: error vs. number of labels; acceptance rules
    docs/paper/figures/fig06_weight_stability.{png,svg}   E3: recovered weights across seeds

    python scripts/plot_calibration_validation.py
    python scripts/plot_calibration_validation.py --results <dir> --out <dir>

Requires matplotlib (pip install -e ".[research]"). Output is deterministic.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "paper" / "results" / "calibration-validation"
OUT = ROOT / "docs" / "paper" / "figures"

NOISE_FLOOR = 16 + 25 / 12  # sigma = 4, rounding to steps of 5 (see tools.synthetic.label_noise_floor)
DEFAULT_LAMBDA = 0.05

# palette shared with the radar chart (scripts/generate_spider.py)
GREEN, RED, BLUE, GREY = "#1f7a5a", "#b03a2e", "#3b6ea8", "#5f6368"
LAMBDA_STYLE = {0.0: (BLUE, "D", (0, (1.2, 2.2))), 0.05: (GREEN, "o", "-"), 0.5: (GREY, "^", (0, (5, 3)))}


def read(name: str, results: Path) -> list[dict]:
    with (results / f"{name}.csv").open(encoding="utf-8") as fh:
        return [{k: _num(v) for k, v in row.items()} for row in csv.DictReader(fh)]


def _num(value: str):
    if value in ("True", "False"):
        return value == "True"
    try:
        return float(value)
    except ValueError:
        return value


def _style() -> None:
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams.update({
        "font.family": [n for n in ("Inter", "Segoe UI", "DejaVu Sans") if n in available] or ["sans-serif"],
        "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#6b7580", "axes.labelcolor": "#1f2328", "xtick.color": "#4a525a",
        "ytick.color": "#4a525a", "axes.grid": True, "grid.color": "#e3e6e9", "grid.linewidth": 0.8,
        "legend.frameon": False, "svg.hashsalt": "calibration-validation",
    })


def _save(fig, out: Path, name: str) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / f"{name}.png", out / f"{name}.svg"]
    tight = {"bbox_inches": "tight", "pad_inches": 0.15, "facecolor": "white"}
    fig.savefig(paths[0], dpi=200, metadata={"Software": None}, **tight)
    fig.savefig(paths[1], metadata={"Date": None, "Creator": None}, **tight)
    plt.close(fig)
    return paths


def fig_lambda(results: Path, out: Path) -> list[Path]:
    rows = sorted(read("e1_cv_summary", results), key=lambda r: r["lambda"])
    lam = [r["lambda"] for r in rows]
    cv = [r["cv_mse_calibrated"] for r in rows]
    sd = [r["cv_mse_calibrated_sd_over_repeats"] for r in rows]

    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ax.set_xscale("symlog", linthresh=0.01)
    ax.fill_between(lam, [c - s for c, s in zip(cv, sd)], [c + s for c, s in zip(cv, sd)],
                    color=GREEN, alpha=0.15, lw=0)
    ax.plot(lam, cv, color=GREEN, marker="o", mfc="white", lw=2.2, label="Calibrated: cross-validated MSE (± sd)")
    ax.plot(lam, [r["in_sample_mse_calibrated"] for r in rows], color=GREEN, ls=(0, (4, 3)), lw=1.6,
            label="Calibrated: in-sample MSE")
    ax.axhline(rows[0]["cv_mse_default"], color=GREY, lw=1.6, label="Default weights (cross-validated)")
    ax.axhline(NOISE_FLOOR, color=RED, ls=(0, (1, 2)), lw=1.6, label=f"Label-noise floor ({NOISE_FLOOR:.1f})")
    ax.set_ylim(min(NOISE_FLOOR, min(r["in_sample_mse_calibrated"] for r in rows)) - 2,
                rows[0]["cv_mse_default"] + 4)
    ax.axvline(DEFAULT_LAMBDA, color="#9aa1a8", lw=0.9)
    ax.annotate("default λ", (DEFAULT_LAMBDA, ax.get_ylim()[0]), xytext=(4, 6), textcoords="offset points",
                fontsize=8.5, color="#6b7580")
    ax.set_xlabel("Regularisation strength λ (symmetric log scale)")
    ax.set_ylabel("MSE vs. expert labels (score points²)")
    ax.set_xticks(lam)
    ax.set_xticklabels([f"{v:g}" for v in lam], fontsize=8.5)
    ax.legend(loc="center left", bbox_to_anchor=(0.0, 0.72), fontsize=8.5)
    return _save(fig, out, "fig04_lambda_curve")


def fig_learning(results: Path, out: Path) -> list[Path]:
    rows = read("e2_sample_size_summary", results)
    lambdas = sorted({r["lambda"] for r in rows})
    default_err = rows[0]["mse_test_true_default"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.4, 4.0), gridspec_kw={"width_ratios": [1.25, 1]})
    for lam in lambdas:
        color, marker, ls = LAMBDA_STYLE.get(lam, (GREY, "s", "-"))
        r = sorted((x for x in rows if x["lambda"] == lam), key=lambda x: x["n"])
        n = [x["n"] for x in r]
        ax1.plot(n, [x["mse_test_true_calibrated_mean"] for x in r], color=color, marker=marker, ls=ls,
                 mfc="white", lw=2.0, label=f"λ = {lam:g}")
        ax1.fill_between(n, [x["mse_test_true_calibrated_mean"] for x in r],
                         [x["mse_test_true_calibrated_p90"] for x in r], color=color, alpha=0.10, lw=0)
    ax1.axhline(default_err, color=GREY, lw=1.6, label=f"Default weights ({default_err:.1f})")
    ax1.set_xscale("log")
    ax1.set_xticks(sorted({r["n"] for r in rows}))
    ax1.set_xticklabels([f"{int(v)}" for v in sorted({r["n"] for r in rows})], fontsize=8.5)
    ax1.minorticks_off()
    ax1.set_xlabel("Labelled suppliers n (log scale)")
    ax1.set_ylabel("Test MSE vs. true scores (score points²)")
    ax1.set_title("(a) Calibrated weights: mean, band to p90", fontsize=10, loc="left")
    ax1.legend(fontsize=8.5)

    for lam in [x for x in lambdas if x in (0.0, DEFAULT_LAMBDA)]:
        color, marker, _ = LAMBDA_STYLE[lam]
        r = sorted((x for x in rows if x["lambda"] == lam), key=lambda x: x["n"])
        n = [x["n"] for x in r]
        ax2.plot(n, [100 * x["harm_rate_in_sample"] for x in r], color=color, marker=marker, mfc="white",
                 ls=(0, (4, 3)), lw=1.6, label=f"in-sample rule, λ = {lam:g}")
        ax2.plot(n, [100 * x["harm_rate_cv"] for x in r], color=color, marker=marker, ls="-", lw=2.0,
                 label=f"cross-validated rule, λ = {lam:g}")
    ax2.set_xscale("log")
    ax2.set_xticks(sorted({r["n"] for r in rows}))
    ax2.set_xticklabels([f"{int(v)}" for v in sorted({r["n"] for r in rows})], fontsize=8.5)
    ax2.minorticks_off()
    ax2.set_ylim(-2, 55)
    ax2.set_xlabel("Labelled suppliers n (log scale)")
    ax2.set_ylabel("Runs where applied weights are worse than defaults (%)")
    ax2.set_title("(b) Harm rate by acceptance rule", fontsize=10, loc="left")
    ax2.legend(fontsize=8)
    fig.tight_layout()
    return _save(fig, out, "fig05_learning_curve")


def fig_stability(results: Path, out: Path) -> list[Path]:
    rows = read("e3_stability_summary", results)
    rows = sorted(rows, key=lambda r: r["hidden"] - r["default"])
    y = list(range(len(rows)))

    fig, ax = plt.subplots(figsize=(6.8, 4.6))
    for i, r in zip(y, rows):
        ax.plot([r["p05"] * 100, r["p95"] * 100], [i, i], color=GREEN, lw=5, alpha=0.25, solid_capstyle="round")
    ax.scatter([r["default"] * 100 for r in rows], y, marker="^", s=46, color=GREY, zorder=3, label="Default")
    ax.scatter([r["hidden"] * 100 for r in rows], y, marker="s", s=40, facecolor="white", edgecolor=RED, lw=1.6,
               zorder=4, label="Hidden (generating)")
    ax.scatter([r["mean"] * 100 for r in rows], y, marker="o", s=44, color=GREEN, zorder=5,
               label="Calibrated: mean, bar p05–p95")
    ax.set_yticks(y)
    ax.set_yticklabels([r["factor"].replace("_", " ") for r in rows])
    ax.set_xlabel("Effective factor weight (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", fontsize=8.5)
    return _save(fig, out, "fig06_weight_stability")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    _style()
    for paths in (fig_lambda(args.results, args.out), fig_learning(args.results, args.out),
                  fig_stability(args.results, args.out)):
        for p in paths:
            print(f"wrote {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
