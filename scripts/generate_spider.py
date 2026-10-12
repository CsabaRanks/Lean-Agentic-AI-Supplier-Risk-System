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
An unknown value (``value: null``: no public evidence either way) is never
drawn as a low value: the profile line has a gap on that spoke and a "?"
marks it.

Optional per factor: ``anchors`` (what each level means on that factor) and,
per rating, ``evidence`` (repository paths, checked to exist, or URLs) and
``at_least`` (the value is the documented minimum; further functions are
unknown) and ``uncertain`` (the value is kept, but the evidence does not
cover the anchor fully; shown with "*"). Per example, both take a list of
example names.
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

# Radius of the "?" marking an unknown value, per approach (spread so markers do not overlap).
UNKNOWN_RADIUS = {"xls": 0.55, "oss": 0.9, "saas": 1.25, "lean": 1.6}

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
        for level in (f.get("anchors") or {}):
            if level not in range(lo, hi + 1):
                errors.append(f"factor {f['id']}: anchor level {level} outside {lo}..{hi}")
        for key, r in f["ratings"].items():
            where = f"factor {f['id']} / {key}"
            if r["value"] is not None and not lo <= r["value"] <= hi:
                errors.append(f"{where}: value {r['value']} outside {lo}..{hi}")
            for ref in r.get("evidence") or []:
                if not str(ref).startswith("http") and not (ROOT / str(ref).split("#")[0].split("::")[0]).exists():
                    errors.append(f"{where}: evidence path '{ref}' does not exist")
            if r.get("confidence") not in CONFIDENCE:
                errors.append(f"{where}: confidence must be one of {sorted(CONFIDENCE)}")
            if not str(r.get("rationale", "")).strip():
                errors.append(f"{where}: rationale missing")
            examples = r.get("by_example")
            if examples:
                mean = known_mean(examples)
                if mean is None and r["value"] is not None:
                    errors.append(f"{where}: all examples unknown, so the value must be null")
                elif mean is not None and (r["value"] is None or not math.isclose(mean, r["value"])):
                    errors.append(f"{where}: value {r['value']} must equal the mean of by_example ({mean})")
    if errors:
        raise ValueError("invalid comparison matrix:\n  " + "\n  ".join(errors))


def known_mean(examples: dict) -> float | None:
    """Mean of the examples with a known value (None if all are unknown)."""
    known = [v for v in examples.values() if v is not None]
    return sum(known) / len(known) if known else None


def known_spread(examples: dict) -> tuple[float, float] | None:
    known = [v for v in (examples or {}).values() if v is not None]
    return (min(known), max(known)) if len(set(known)) > 1 else None


def point_note(rating: dict) -> str:
    """Short note next to a plotted point: documented minimum and/or partly unknown examples."""
    examples = rating.get("by_example") or {}
    parts = []
    at_least = rating.get("at_least")
    if at_least is True or (at_least and not examples):
        parts.append("≥")
    elif at_least:
        parts.append(" ".join(f"{name[0]}≥" for name in at_least))
    unknown = [name for name, v in examples.items() if v is None]
    if unknown and rating["value"] is not None:
        parts.append(" ".join(f"{name[0]}?" for name in unknown))
    uncertain = rating.get("uncertain")
    if uncertain:
        names = examples if uncertain is True else uncertain
        parts.append(" ".join(f"{name[0]}*" for name in names) if examples else "*")
    return " ".join(parts)


def fmt(value: float | None) -> str:
    return "unknown" if value is None else f"{value:g}"


# --- Markdown ----------------------------------------------------------------------


def _flagged(rating: dict, key: str, name: str | None = None) -> bool:
    flag = rating.get(key)
    return flag is True if name is None else (flag is True or (isinstance(flag, list) and name in flag))


def _min_mark(rating: dict, name: str | None = None) -> str:
    return "≥" if _flagged(rating, "at_least", name) else ""


def _uncertain_mark(rating: dict, name: str | None = None) -> str:
    return "*" if _flagged(rating, "uncertain", name) else ""


def cell(rating: dict) -> str:
    examples = rating.get("by_example")
    if examples and len(set(examples.values())) > 1:
        detail = " · ".join(f"{name[0]} {_min_mark(rating, name) if v is not None else ''}{fmt(v)}"
                            f"{_uncertain_mark(rating, name) if v is not None else ''}"
                            for name, v in examples.items())
        return f"{fmt(rating['value'])} ({detail})"
    if examples:
        flags = [f"{n[0]} {_min_mark(rating, n)}{fmt(v)}{_uncertain_mark(rating, n)}" for n, v in examples.items()
                 if _min_mark(rating, n) or _uncertain_mark(rating, n)]
        if flags:
            return f"{fmt(rating['value'])} ({' · '.join(flags)})"
    mark = "≥" if rating.get("at_least") is True else ""
    return f"{mark}{fmt(rating['value'])}{'*' if rating.get('uncertain') is True else ''}"


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
        "the cell shows the mean of the known values and both values. **unknown** means that no public "
        "evidence was found either way; it is not rated as absent and not plotted as a low value. "
        "**≥** marks a documented minimum: the value covers what is publicly documented, further functions "
        "are unknown. **\\*** marks an uncertain value: kept at its earlier level because the public evidence "
        "neither confirms nor contradicts the anchor."),
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
        if f.get("scope"):
            lines += [f"*Scope:* {f['scope'].strip()}", ""]
        if f.get("anchors"):
            lines += ["| Level | Anchor |", "|:-:|---|"]
            lines += [f"| {level} | {text.strip()} |" for level, text in sorted(f["anchors"].items())]
            lines.append("")
        for k in keys:
            r = f["ratings"][k]
            line = f"- **{shorts[k]}** *({r['confidence']})*: {r['rationale'].strip()}"
            if r.get("evidence"):
                line += " Evidence: " + ", ".join(
                    f"<{e}>" if str(e).startswith("http") else f"`{e}`" for e in r["evidence"]) + "."
            lines.append(line)
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
        plotted = [math.nan if v is None else v for v in values]  # unknown: gap in the profile, never 0
        (line,) = ax.plot(full, plotted + plotted[:1], color=st["color"], ls=st["ls"], lw=st["lw"],
                          marker=st["marker"], ms=6.5, mfc="white", mew=1.6, zorder=st["z"],
                          label=ap["label"])
        handles.append(line)
        for f, a, v in zip(factors, angles, values):
            # spread between rated examples (e.g. Prewave vs Sphera)
            spread = known_spread(f["ratings"][ap["key"]].get("by_example"))
            if spread:
                ax.plot([a, a], list(spread), color=st["color"], lw=5, alpha=0.28,
                        solid_capstyle="round", zorder=st["z"] - 0.5)
            if v is None:
                ax.text(a, UNKNOWN_RADIUS[ap["key"]], "?", color=st["color"], fontsize=13, fontweight="bold",
                        ha="center", va="center", zorder=st["z"] + 1)
            note = point_note(f["ratings"][ap["key"]])
            if note:
                # place the note towards the centre, away from the outer profile lines
                ax.annotate(note.replace("≥", r"$\geq$"), (a, v), xytext=(-math.cos(a) * 20 + math.sin(a) * 20, -math.sin(a) * 20 - math.cos(a) * 20), textcoords="offset points",
                            ha="center", va="center", rotation=0, color=st["color"], fontsize=10, fontweight="bold",
                            zorder=st["z"] + 1, bbox={"boxstyle": "round,pad=0.1", "fc": "white", "ec": "none"})

    order = ["lean", "saas", "oss", "xls"]
    by_key = {ap["key"]: h for ap, h in zip(approaches, handles)}
    fig.legend([by_key[k] for k in order], [next(a["label"] for a in data["approaches"] if a["key"] == k)
                                             for k in order],
               loc="lower center", bbox_to_anchor=(0.5, 0.075), ncol=2, frameon=False, fontsize=11,
               handlelength=3.2, columnspacing=2.5)
    fig.text(0.5, 0.05,
             f"Illustrative assessment, scale {lo}–{hi} · evidence {data['meta']['evidence_date']} · "
             "shaded bars: spread between Prewave and Sphera · ? = unknown (no public evidence), not rated low · "
             "≥ documented minimum · ? unknown · * uncertain (P = Prewave, S = Sphera) · no weighting, total or ranking",
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
        plotted = [math.nan if v is None else v for v in values]  # unknown: gap in the profile, never 0
        ax.plot(full, plotted + plotted[:1], color=st["color"], ls=st["ls"], lw=1.4, zorder=st["z"])
        ax.plot(angles, plotted, ls="none", marker=st["marker"], ms=4.2, mfc="white", mec=st["color"],
                mew=1.3, zorder=st["z"])
        for f, a, v in zip(factors, angles, values):
            spread = known_spread(f["ratings"][ap["key"]].get("by_example"))
            if spread:
                ax.plot([a, a], list(spread), color=st["color"],
                        lw=4, alpha=0.25, solid_capstyle="round", zorder=st["z"] - 0.5)
            if v is None:
                ax.text(a, UNKNOWN_RADIUS[ap["key"]], "?", color=st["color"], fontsize=9, fontweight="bold",
                        ha="center", va="center", zorder=st["z"] + 1)
            note = point_note(f["ratings"][ap["key"]])
            if note:
                # theta zero is north and clockwise here: display direction is (sin a, cos a)
                ax.annotate(note.replace("≥", r"$\geq$"), (a, v), xytext=(-math.sin(a) * 13 - math.cos(a) * 14, -math.cos(a) * 13 + math.sin(a) * 14), textcoords="offset points",
                            ha="center", va="center", rotation=0, color=st["color"], fontsize=7, fontweight="bold",
                            zorder=st["z"] + 1, bbox={"boxstyle": "round,pad=0.08", "fc": "white", "ec": "none"})

    labels = {a["key"]: a["label"] for a in data["approaches"]}
    handles = [Line2D([], [], color=PAPER_STYLE[k]["color"], ls=PAPER_STYLE[k]["ls"], lw=1.4,
                      marker=PAPER_STYLE[k]["marker"], ms=4.2, mfc="white", mec=PAPER_STYLE[k]["color"],
                      mew=1.3, label=labels[k]) for k in ("lean", "saas", "oss", "xls")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=8.6,
               bbox_to_anchor=(0.5, 0.035), handlelength=2.8, columnspacing=2.2)
    fig.text(0.5, 0.012, "? = unknown (no public evidence), not rated low · ≥ = documented minimum · "
             "* = uncertain · P = Prewave, S = Sphera", ha="center", fontsize=7.6, color=PAPER_INK3)

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
        spread = (f" ({'/'.join('?' if v is None else f'{v:g}' for v in examples.values())})"
                  if len(set(examples.values())) > 1 else "")
        value = "?" if r["value"] is None else f"{r['value']:g}"
        if r.get("at_least") is True:
            value = "$\\geq$" + value
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
