# Notes & decisions

Lightweight decision log. Newest first.

## 2026-10 — Calibration validation (paper section 7)

**D20: Calibration validated on synthetic data** (`scripts/validate_calibration.py`):
- **E1:** repeated 5-fold CV on the reference portfolio
- **E2:** sample size × λ against an independent test set
- **E3:** stability across 100 seeds

At λ = 0.05 and 32 labels:
- CV MSE is 37.8 → 20.6, against a noise floor of 18.1
- the in-sample MSE of 12.4 is optimistic
- weights move about half-way to the hidden weighting

**Issues found, not yet fixed:**
1. **The acceptance rule uses in-sample improvement.** It accepts almost everything, including
   overfitted fits on 8 labels. A cross-validated acceptance rule is needed.
2. **A fixed λ does not fade with n.** The error term is a mean and the penalty is unscaled, so
   λ becomes a bias at large n. Choose λ by CV or scale it with 1/n.
3. **The synthetic labels are the best case.** They come from the fitted linear model family.
   Misspecification experiments are still missing.

## 2026-10 — Factor model v0.2, single source of truth, radar chart

**D16: Factor model v0.2 adopted.** Key changes from v0.1:
- open source → *customisability & data sovereignty*
- multi-agent → *extensibility* (means reframed as outcomes to avoid a circular comparison)
- merged *criteria + objective/subjective* and *audit trail + determinism*
- external signals broadened to *data coverage*
- added *regulatory evidence* and *operational maturity*, where platforms are stronger, to
  counter home-field bias
- predictive validity deliberately not an axis

Full table with rationale: `success-factors.md` → "Changes from v0.1 to v0.2".

**D17: `comparison-matrix.yaml` is the single source of truth.** `scripts/generate_spider.py`
generates `comparison-matrix.md` and `docs/images/spider-diagram.png/.svg`. A test fails if the
Markdown is stale or the YAML is inconsistent.

**D18: Prewave and Sphera are named and rated separately.** The SaaS line is their mean. The spread
is drawn on the spoke, because the vendors differ markedly in methodological disclosure.

**D19: The radar chart is in the README** in the section "Where this approach sits", between the
problem statement and the features, as planned (see below).

## 2026-10 — Research & benchmark track (paper preparation)

New files:
- `success-factors.md`: working model v0.1 plus critical review and proposed v0.2
- `comparison-matrix.md`: four approaches × factors, with rationale and confidence
- `saas-references.md`: public information on SaaS examples, with sources
- `lean-agentic-positioning.md`
- `spider-diagram-spec.md`
- `docs/paper/paper-outline.md`

**D13: Profiles, not scores.** Approaches are compared factor by factor. No weights, no total,
no ranking, following the convention of the companion paper. This also keeps the comparison
from becoming a weighted ranking of competitors.

**D14: Rate LEAN as implemented, not as planned.** Roadmap items may appear only as a separate,
clearly marked dashed profile.

**D15: The SaaS profile is based on public information only, dated October 2026.** Where vendors
differ (e.g. methodological transparency), the matrix gives a range and the chart plots the
midpoint, with a note.

### README placement of the spider diagram (planned)

Position: **directly after "The problem" and before "What it does"** (key features). The reader
first sees the gap, then where this approach sits in it, then the features that produce that
position.

Planned README block:

```markdown
## Where this approach sits

<radar chart: Mermaid radar-beta, or PNG fallback docs/paper/figures/fig01_approach_profile.png>

*Illustrative assessment (public information and code review, Oct 2026). Rationale and
confidence for every value: research/comparison-matrix.md. No weighting, total or ranking.*

**Reading it:** platforms lead on data coverage and scale. This project leads where the
*method* matters: expert calibration, reproducibility, transparency and material-group
weights. It deliberately does not compete on external signal coverage (yet).
```

Then a one-line bridge to the calibration differentiator section, so that the spike on the
"expert calibration" axis is explained immediately below the chart.

Preconditions: factor model version decided; vendor naming decided; Mermaid radar support on
GitHub verified (otherwise PNG); values generated from one machine-readable source.

## 2026-10 — Weight store and human-in-the-loop

**D9 — Versioned weight files instead of overwriting the model YAML.**
Each applied weight set becomes `<scope>_v<NNN>.yaml` with timestamp, approver, model version
and calibration metrics. The files are append-only and reviewable in git, and rollback is
possible. The model YAML stays the methodology definition, with the default weights as the
regularisation anchor.

**D10 — Regularisation anchored on configured defaults, not on the last calibration.**
Found by a test: with the previous calibration as the anchor, repeated runs on the same labels
drifted further from the methodology every time. With the defaults as the anchor, re-calibration
converges, and the min-improvement gate prevents redundant new versions.

**D11 — Human review via LangGraph `interrupt()` + checkpointer.**
The run pauses with a structured review request and resumes with a `ReviewDecision`: approve
weights, class overrides, or defer. Side effects happen only after `interrupt()` returns, because
nodes are re-executed on resume. Manual overrides are kept across re-scoring. State types are
explicitly allow-listed for checkpoint deserialization (`state_serializer()`); unregistered types
are going to be blocked by LangGraph.

**D12 — Expert labels as 0–100 scores, classes derived.**
Labels carry more information than classes and keep the fit linear. Class agreement is reported
in addition to the MSE.

## 2026-10 — Initial architecture

**D1 — Deterministic scoring, LLM later and only for language.**
Reproducibility and auditability matter more than flexibility for supplier decisions. LLM
extraction (documents → indicators) and explanations (scores → narrative) are planned as optional
agents that never change numbers.

**D2 — Rule-based supervisor.**
The workflow order is known, so routing is a few `if` statements. `Supervisor.route()` is the
single place to plug in an LLM supervisor if dynamic planning becomes useful.

**D3 — Portfolio-level graph run.**
Calibration needs many labelled suppliers at once. A single-supplier assessment is the same graph
with `supplier_ids=[id]`.

**D4 — Weights as a first-class `WeightSet`.**
Defaults come from YAML; material-group defaults and calibrated weights are interchangeable. The
scoring engine never reads weights from code.

**D5 — Calibration = constrained, regularised least squares.**
Convex, explainable, solvable with SciPy SLSQP. Regularisation towards the prior keeps results
stable with few labels. Accept only on a minimum relative MSE improvement (plus an absolute
tolerance, see test `test_rejected_when_no_meaningful_improvement`).

**D6 — Min-max normalisation `(R−1)/4·100`.**
Uses the full 0–100 range; a naive `R/5` maps the best possible supplier to 20 %.

**D7 — Escalation rules as class floors.**
A severe compliance or insolvency finding must not be averaged away.

**D8 — Material group in data and state from day one.**
MVP calibrates globally or per run scope; the structure allows per-group weights without
refactoring.

## Open questions

- Independent re-rating of the comparison matrix by practitioners: who, and how many?

- Persistent checkpointer (SQLite) so reviews can be decided in a later session?
- Additionally support ordinal expert labels (low/medium/high/critical)?
- Cross-validation in the calibration report — which k for small samples?
- Which public sources to use for the country-risk index by default?

## Ideas backlog

- External-risk agent (news, disasters, geopolitical alerts) feeding a time-varying factor.
- Trend detection: score deltas between review cycles.
- Streamlit dashboard: portfolio heatmap, weight comparison before/after calibration.
