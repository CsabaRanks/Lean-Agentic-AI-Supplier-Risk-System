# Spider diagram: specification

The radar chart is the project's signature figure. It appears in the README in the section
"Where this approach sits", after the problem statement. It is also Figure 1 of the paper. It
places the Lean Agentic approach relative to three other approaches across the 16 success factors
of model v0.3.

> **The values are illustrative and must stay defensible.**
> - Every value has a rationale, evidence and a confidence mark in the single source of truth,
>   [comparison-matrix.yaml](comparison-matrix.yaml).
> - The chart and [comparison-matrix.md](comparison-matrix.md) are **generated** from that file,
>   so they cannot drift apart.
> - Captions must say "illustrative assessment, not an empirical measurement".
> - The chart shows **profiles**: no area, total or ranking is derived from it.

## Pipeline

```
research/comparison-matrix.yaml        ← edit ratings here only
        │  python scripts/generate_spider.py
        ├── research/comparison-matrix.md     (tables + rationale, generated)
        ├── docs/images/spider-diagram.png    (README, paper)
        └── docs/images/spider-diagram.svg    (vector version for the paper)
```

- `python scripts/generate_spider.py --check` validates the YAML. It checks:
  - value range
  - confidence codes
  - non-empty rationales
  - SaaS value equals the mean of the Prewave and Sphera values

  It also fails if the Markdown is stale. The test suite runs this check, and so does CI.
- Rendering needs matplotlib (`pip install -e ".[research]"`). The check does not.

## Axes (model v0.3, in this order)

The order puts related factors next to each other so that the shapes are readable:
- method (1–5)
- governance and actions (6–7)
- data and compliance (8–9)
- economics and adoption (10–12)
- operations (13–15)
- integration of risk and performance (16)

This is an ordering for the eye only. It is not a hierarchy, and it carries no weights.

| Axis | Chart label | Factor |
|---|---|---|
| 1 | Criteria & weights | Structured criteria & weights (objective + subjective) |
| 2 | Traceability & reproducibility | Traceability & reproducibility |
| 3 | Method transparency | Methodological transparency |
| 4 | Expert calibration | Expert calibration / ability to learn |
| 5 | Material-group fit | Material-group-specific adaptation |
| 6 | Action framework | Action framework |
| 7 | Human-in-the-loop | Human-in-the-loop & governance |
| 8 | External signals & coverage | External signals & data coverage |
| 9 | Regulatory evidence | Regulatory evidence (due-diligence documentation) |
| 10 | Cost / TCO | Cost / total cost of ownership |
| 11 | Time-to-value | Time-to-value / ease of adoption |
| 12 | Customisability & data sovereignty | Customisability & data sovereignty |
| 13 | Scalability | Scalability |
| 14 | Agentic orchestration & extensibility | Agentic orchestration & extensibility |
| 15 | Operational maturity | Operational maturity & support |
| 16 | Risk & performance integration | Integration of risk management and performance evaluation |

Values: see the generated [comparison-matrix.md](comparison-matrix.md).

## Visual rules (implemented in `scripts/generate_spider.py`)

- Rings 1–5 with light grid lines. Ring labels sit on an empty half-step spoke, so no data point
  covers them.
- One colour, line style and marker per profile, so the chart also works in greyscale and for
  colour-blind readers:
  - Lean Agentic: green, solid, circles
  - SaaS: red, solid, squares
  - Open repos: blue, dotted, diamonds
  - Excel: grey, dashed, triangles
- Lean Agentic is drawn last, on top, with a heavier line.
- **No filled areas.** An area would suggest a total.
- **Prewave and Sphera are rated separately.** The SaaS line plots their mean. Where they differ,
  a shaded bar on the spoke shows the spread (factors 2, 3, 9 and 14).
- Legend and a footnote ("illustrative · evidence date · no weighting, total or ranking") are part
  of the image, so it stays honest when shared on its own.
- Deterministic output: fixed SVG hash salt, no timestamps in the metadata.

## Expected shape (sanity check after every change)

- **Lean Agentic** spans the method side: transparency, calibration, material-group fit,
  customisability, agentic orchestration and risk & performance integration.
- **SaaS** spans external signals, regulatory evidence, scalability and operational maturity.
- **Excel** is strong only on transparency and customisability.
- **Open repos** are low except for cost and agentic orchestration.
- **Lean Agentic visibly dips at regulatory evidence (2) and operational maturity (2), and stays
  in the middle on external signals (2.5).** These dips are part of the honest message and must not be hidden.

## Paper caption (draft)

> *Figure 1. Four approaches to supplier risk management and performance evaluation profiled on
> 16 success factors (model v0.3). Illustrative assessment based on public information and code review (October 2026).
> Proprietary SaaS is plotted as the mean of Prewave and Sphera; shaded bars show where the two
> differ. Rationale and confidence for every value are given in Table 2 / the comparison matrix.
> No weighting is applied and no total or ranking is derived.*

## Open points

- [ ] Optional dashed "Lean Agentic (roadmap)" profile, clearly marked as planned.
- [ ] Independent re-rating by 3–5 practitioners; report the spread (e.g. as min–max bars).
- [ ] Paper layout: check label size at two-column width; use the SVG.
