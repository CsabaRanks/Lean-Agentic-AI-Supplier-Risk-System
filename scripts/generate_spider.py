"""Generate the approach comparison artefacts from research/comparison-matrix.yaml.

The YAML file is the single source of truth. This script renders:

* research/comparison-matrix.md   tables and rationale (generated, do not edit by hand)
* docs/images/spider-diagram.png  radar chart for README (plus .svg)
* docs/paper/figures/fig01_benchmark_profile.png  print variant for the typeset paper: circular web,
  thin lines, legend only; the disclaimer belongs in the caption

Usage:
    python scripts/generate_spider.py            # validate, write Markdown and chart
    python scripts/generate_spider.py --check    # validate, fail if the Markdown is stale (no matplotlib needed)

Design rules for the chart (see research/spider-diagram-spec.md):
profiles only: no filled areas, no totals, no ranking; Lean Agentic is drawn
last; where the SaaS examples differ, their spread is marked on the spoke.
"""

from __future__ import annotations

import argparse
import math
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research" / "comparison-matrix.yaml"
MARKDOWN = ROOT / "research" / "comparison-matrix.md"
IMAGE = ROOT / "docs" / "images" / "spider-diagram.png"
PAPER_IMAGE = ROOT / "docs" / "paper" / "figures" / "fig01_benchmark_profile.png"
PAPER_TABLE = ROOT / "docs" / "paper" / "generated" / "comparison_matrix.tex"

CONFIDENCE = {"H": "verified from code / primary documentation",
              "M": "plausible, partly documented",
              "L": "assumption, little public evidence"}

# Visual identity per approach: colour, line style, marker, line width, draw order.
STYLE = {
    "xls": {"color": "#5f6368", "ls": (0, (5, 3)), "marker": "^", "lw": 1.8, "z": 3},
    "oss": {"color": "#3b6ea8", "ls": (0, (1.2, 2.2)), "marker": "D", "lw": 2.0, "z": 4},
    "saas": {"color": "#b03a2e", "ls": "-", "marker": "s", "lw": 2.0, "z": 5},
    "lean": {"color": "#1f7a5a", "ls": "-", "marker": "o", "lw": 2.8, "z": 6},
}

# Print variant (typeset paper): the visual language of the companion paper's benchmark profile.
PAPER_INK, PAPER_INK3, PAPER_RULE = "#14181B", "#6E7B82", "#C9D1D5"
PAPER_STYLE = {
    "xls": {"color": "#14181B", "ls": (0, (4, 2.2)), "marker": "^", "z": 3},
    "oss": {"color": "#2E5A87", "ls": (0, (1, 1.8)), "marker": "D", "z": 4},
    "saas": {"color": "#B3372C", "ls": "-", "marker": "s", "z": 5},
    "lean": {"color": "#3E8F63", "ls": "-", "marker": "o", "z": 6},
}


# --- loading & validation ------------------------------------------------------------


def load(path: Path = SOURCE) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(data)
    return data


def validate(data: dict) -> None:
    lo, hi = data["meta"]["scale"]["min"], data["meta"]["scale"]["max"]
    keys = [a["key"] for a in data["approaches"]]
    errors: list[str] = []
    ids = [f["id"] for f in data["factors"]]
    if ids != list(range(1, len(ids) + 1)):
        errors.append(f"factor ids must be 1..n in order, got {ids}")
    for f in data["factors"]:
        missing = set(keys) - set(f["ratings"])
        if missing:
            errors.append(f"factor {f['id']}: missing ratings for {sorted(missing)}")
        for key, r in f["ratings"].items():
            where = f"factor {f['id']} / {key}"
            if not lo <= r["value"] <= hi:
                errors.append(f"{where}: value {r['value']} outside {lo}..{hi}")
            if r.get("confidence") not in CONFIDENCE:
                errors.append(f"{where}: confidence must be one of {sorted(CONFIDENCE)}")
            if not str(r.get("rationale", "")).strip():
                errors.append(f"{where}: rationale missing")
            examples = r.get("by_example")
            if examples:
                mean = sum(examples.values()) / len(examples)
                if not math.isclose(mean, r["value"]):
                    errors.append(f"{where}: value {r['value']} must equal the mean of by_example ({mean})")
    if errors:
        raise ValueError("invalid comparison matrix:\n  " + "\n  ".join(errors))


def fmt(value: float) -> str:
    return f"{value:g}"


# --- Markdown ----------------------------------------------------------------------


def cell(rating: dict) -> str:
    examples = rating.get("by_example")
    if examples and len(set(examples.values())) > 1:
        detail = " · ".join(f"{name[0]} {fmt(v)}" for name, v in examples.items())
        return f"{fmt(rating['value'])} ({detail})"
    return fmt(rating["value"])


def render_markdown(data: dict) -> str:
    meta, approaches, factors = data["meta"], data["approaches"], data["factors"]
    keys = [a["key"] for a in approaches]
    shorts = {a["key"]: a["short"] for a in approaches}
    lines = [
        "<!-- GENERATED FILE: do not edit by hand.",
        "     Source: research/comparison-matrix.yaml · Generator: scripts/generate_spider.py -->",
        "",
        "# Comparison matrix: four approaches × success factors",
        "",
        (f"Rates four approaches to supplier risk evaluation against the **{len(factors)} success factors of "
        f"model v{meta['model_version']}** (see [success-factors.md](success-factors.md)). "
        f"Evidence as of {meta['evidence_date']}."),
        "",
        "> **Read this as a reasoned, illustrative assessment, not a measurement.** Every rating has a",
        "> rationale and a confidence mark. No weights are applied, no total is formed and no ranking is",
        "> derived: the approaches are compared as **profiles**, factor by factor. The radar chart",
        "> `docs/images/spider-diagram.png` is generated from the same source.",
        "",
        "## The four approaches",
        "",
        "| Approach | What exactly is rated | Evidence base |",
        "|---|---|---|",
    ]
    for a in approaches:
        lines.append(f"| **{a['label']}** | {a['rated']} | {a['evidence'].strip()} |")
    lines += [
        "",
        (f"**Scale:** {meta['scale']['min']} = weak / absent · 2 = rudimentary · 3 = adequate · 4 = strong · "
        f"{meta['scale']['max']} = very strong. "
        "For proprietary SaaS, values are rated per example; where Prewave (P) and Sphera (S) differ, "
        "the cell shows the mean and both values."),
        "",
        "**Confidence:** " + " · ".join(f"**{k}** = {v}" for k, v in CONFIDENCE.items()) + ".",
        "",
        "## Matrix",
        "",
        "| # | Success factor (v" + meta["model_version"] + ") | " + " | ".join(shorts[k] for k in keys)
        + " | from v0.1 |",
        "|---|---|" + ":-:|" * len(keys) + ":-:|",
    ]
    for f in factors:
        origin = ", ".join(str(i) for i in f["v01"]) if f["v01"] else "new"
        row = " | ".join(cell(f["ratings"][k]) for k in keys)
        lines.append(f"| {f['id']} | {f['label']} | {row} | {origin} |")

    lines += ["", "## Reading the profiles (without aggregation)", ""]
    lines += [f"- {t.strip()}" for t in data["narrative"]["reading_profiles"]]
    lines += ["", "## Rationale per factor", ""]
    for f in factors:
        summary = " · ".join(f"{shorts[k]} {fmt(f['ratings'][k]['value'])}" for k in keys)
        lines += [f"### {f['id']}. {f['label']}: {summary}", ""]
        for k in keys:
            r = f["ratings"][k]
            lines.append(f"- **{shorts[k]}** *({r['confidence']})*: {r['rationale'].strip()}")
        lines.append("")
    lines += ["## Known weaknesses of this comparison", ""]
    lines += [f"- {t.strip()}" for t in data["narrative"]["known_weaknesses"]]
    return "\n".join(lines) + "\n"


# --- chart -------------------------------------------------------------------------


def _font_family() -> list[str]:
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    return [name for name in ("Inter", "Segoe UI", "DejaVu Sans") if name in available] or ["sans-serif"]


def render_chart(data: dict, out: Path = IMAGE) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = _font_family()
    plt.rcParams["svg.hashsalt"] = "spider"  # deterministic SVG ids

    factors = data["factors"]
    lo, hi = data["meta"]["scale"]["min"], data["meta"]["scale"]["max"]
    n = len(factors)
    # start at 12 o'clock, clockwise
    angles = [math.pi / 2 - 2 * math.pi * i / n for i in range(n)]

    fig = plt.figure(figsize=(11, 11), dpi=200)
    ax = fig.add_axes([0.21, 0.22, 0.58, 0.58], polar=True)
    ax.set_ylim(0, hi)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    # rings and spokes
    full = [a for a in angles] + [angles[0]]
    tick_angle = angles[0] - math.pi / n  # between the first two spokes: never covered by data
    for level in range(lo, hi + 1):
        ax.plot(full, [level] * (n + 1), color="#c9ced3" if level < hi else "#6b7580",
                lw=0.8 if level < hi else 1.4, zorder=1)
        ax.text(tick_angle, level * math.cos(math.pi / n), str(level), fontsize=8.5, color="#7a838c",
                ha="center", va="center", zorder=2,
                bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none"})
    for a in angles:
        ax.plot([a, a], [0, hi], color="#c9ced3", lw=0.8, zorder=1)

    # axis labels outside the outer ring
    for f, a in zip(factors, angles):
        label = "\n".join(textwrap.wrap(f["short_label"], 18))
        deg = math.degrees(a) % 360
        ha = "center" if deg in (90, 270) or abs(deg - 90) < 8 or abs(deg - 270) < 8 else (
            "left" if (deg < 90 or deg > 270) else "right")
        ax.text(a, hi + 0.42, label, fontsize=11, color="#1f2328", ha=ha, va="center",
                linespacing=1.15)

    # profiles: Lean Agentic last so it sits on top
    approaches = sorted(data["approaches"], key=lambda ap: STYLE[ap["key"]]["z"])
    handles = []
    for ap in approaches:
        st = STYLE[ap["key"]]
        values = [f["ratings"][ap["key"]]["value"] for f in factors]
        (line,) = ax.plot(full, values + values[:1], color=st["color"], ls=st["ls"], lw=st["lw"],
                          marker=st["marker"], ms=6.5, mfc="white", mew=1.6, zorder=st["z"],
                          label=ap["label"])
        handles.append(line)
        # spread between rated examples (e.g. Prewave vs Sphera)
        for f, a in zip(factors, angles):
            examples = f["ratings"][ap["key"]].get("by_example") or {}
            if len(set(examples.values())) > 1:
                vmin, vmax = min(examples.values()), max(examples.values())
                ax.plot([a, a], [vmin, vmax], color=st["color"], lw=5, alpha=0.28,
                        solid_capstyle="round", zorder=st["z"] - 0.5)

    order = ["lean", "saas", "oss", "xls"]
    by_key = {ap["key"]: h for ap, h in zip(approaches, handles)}
    fig.legend([by_key[k] for k in order], [next(a["label"] for a in data["approaches"] if a["key"] == k)
                                             for k in order],
               loc="lower center", bbox_to_anchor=(0.5, 0.075), ncol=2, frameon=False, fontsize=11,
               handlelength=3.2, columnspacing=2.5)
    fig.text(0.5, 0.05,
             f"Illustrative assessment, scale {lo}–{hi} · evidence {data['meta']['evidence_date']} · "
             "shaded bars: spread between Prewave and Sphera · no weighting, total or ranking",
             ha="center", fontsize=8.5, color="#6b7580")

    out.parent.mkdir(parents=True, exist_ok=True)
    svg = out.with_suffix(".svg")
    tight = {"bbox_inches": "tight", "pad_inches": 0.35, "facecolor": "white"}
    fig.savefig(out, dpi=200, metadata={"Software": None}, **tight)
    fig.savefig(svg, metadata={"Date": None, "Creator": None}, **tight)
    plt.close(fig)
    return [out, svg]


def render_paper_chart(data: dict, out: Path = PAPER_IMAGE) -> list[Path]:
    """Circular engineering radar for print: thin unfilled profiles, labels outside the web."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    plt.rcParams["font.family"] = _font_family()
    factors = data["factors"]
    lo, hi = data["meta"]["scale"]["min"], data["meta"]["scale"]["max"]
    n = len(factors)
    angles = [2 * math.pi * i / n for i in range(n)]

    fig = plt.figure(figsize=(8.8, 7.9), dpi=300)
    ax = fig.add_axes([0.16, 0.15, 0.68, 0.68], polar=True)
    ax.set_theta_direction(-1)
    ax.set_theta_zero_location("N")
    ax.set_ylim(0, hi + 0.35)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["polar"].set_visible(False)
    ax.grid(False)

    fine = [2 * math.pi * k / 360 for k in range(361)]
    for level in range(lo, hi + 1):
        ax.plot(fine, [level] * len(fine), color=PAPER_RULE if level < hi else PAPER_INK3,
                lw=0.7 if level < hi else 1.0, zorder=1)
        ax.text(math.pi / n, level, str(level), fontsize=7.2, color=PAPER_INK3, ha="center", va="center",
                zorder=2, bbox={"boxstyle": "square,pad=0.14", "fc": "white", "ec": "none"})
    for a in angles:
        ax.plot([a, a], [0, hi], color=PAPER_RULE, lw=0.7, zorder=1)

    for f, a in zip(factors, angles):
        deg = math.degrees(a) % 360
        ha = "left" if 10 < deg < 170 else "right" if 190 < deg < 350 else "center"
        ax.text(a, hi + 0.62, "\n".join(textwrap.wrap(f["short_label"], 18)), fontsize=8.6,
                color=PAPER_INK, ha=ha, va="center", linespacing=1.22, clip_on=False)

    full = angles + angles[:1]
    for ap in sorted(data["approaches"], key=lambda ap: PAPER_STYLE[ap["key"]]["z"]):
        st = PAPER_STYLE[ap["key"]]
        values = [f["ratings"][ap["key"]]["value"] for f in factors]
        ax.plot(full, values + values[:1], color=st["color"], ls=st["ls"], lw=1.4, zorder=st["z"])
        ax.plot(angles, values, ls="none", marker=st["marker"], ms=4.2, mfc="white", mec=st["color"],
                mew=1.3, zorder=st["z"])
        for f, a in zip(factors, angles):
            examples = f["ratings"][ap["key"]].get("by_example") or {}
            if len(set(examples.values())) > 1:
                ax.plot([a, a], [min(examples.values()), max(examples.values())], color=st["color"],
                        lw=4, alpha=0.25, solid_capstyle="round", zorder=st["z"] - 0.5)

    labels = {a["key"]: a["label"] for a in data["approaches"]}
    handles = [Line2D([], [], color=PAPER_STYLE[k]["color"], ls=PAPER_STYLE[k]["ls"], lw=1.4,
                      marker=PAPER_STYLE[k]["marker"], ms=4.2, mfc="white", mec=PAPER_STYLE[k]["color"],
                      mew=1.3, label=labels[k]) for k in ("lean", "saas", "oss", "xls")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=8.6,
               bbox_to_anchor=(0.5, 0.035), handlelength=2.8, columnspacing=2.2)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=300, metadata={"Software": None}, bbox_inches="tight", pad_inches=0.12,
                facecolor="white")
    plt.close(fig)
    return [out]


def render_latex_table(data: dict, out: Path = PAPER_TABLE) -> list[Path]:
    """Values and confidence per factor and approach, for the paper's appendix (rationales: Markdown)."""
    order = ["xls", "saas", "oss", "lean"]
    head = {"xls": "Excel", "saas": "SaaS", "oss": "OSS", "lean": "Lean"}

    def cell(r: dict) -> str:
        examples = r.get("by_example") or {}
        spread = f" ({'/'.join(str(v) for v in examples.values())})" if len(set(examples.values())) > 1 else ""
        value = f"{r['value']:g}"
        return f"{value}{spread}\\,\\textsuperscript{{{r['confidence']}}}"

    def tex(text: str) -> str:
        return text.replace("&", "\\&")

    rows = [f"{f['id']} & {tex(f['label'])} & " + " & ".join(cell(f["ratings"][k]) for k in order) + " \\\\"
            for f in data["factors"]]
    lines = [
        "% generated by scripts/generate_spider.py from research/comparison-matrix.yaml -- do not edit",
        "\\begin{tabular}{@{}r>{\\raggedright\\arraybackslash}p{0.36\\columnwidth}cccc@{}}",
        "\\toprule",
        "\\# & Success factor & " + " & ".join(head[k] for k in order) + " \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [out]


# --- CLI ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only validate and check the Markdown is current")
    args = parser.parse_args(argv)

    data = load()
    markdown = render_markdown(data)

    if args.check:
        current = MARKDOWN.read_text(encoding="utf-8") if MARKDOWN.exists() else ""
        if current != markdown:
            print(f"{MARKDOWN.relative_to(ROOT)} is out of date: run python scripts/generate_spider.py",
                  file=sys.stderr)
            return 1
        print("comparison matrix: valid and up to date")
        return 0

    MARKDOWN.write_text(markdown, encoding="utf-8")
    written = render_chart(data) + render_paper_chart(data) + render_latex_table(data)
    for path in [MARKDOWN, *written]:
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
