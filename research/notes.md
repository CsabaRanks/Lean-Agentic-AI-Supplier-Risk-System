# Notes & decisions

Lightweight decision log. Newest first.

## 2026-10 — Two views: performance and risk

**D29: Supplier performance evaluation and supplier risk management are separate views.**
- **Shared catalogue.** Criteria (meaning and rating source) are defined once in
  `config/criteria.yaml`.
- **One YAML per view.** Each view selects criteria and sets its own dimensions, weights, classes,
  escalation rules, actions and calibration. Shared criteria in the template: credit_risk,
  esg_rating, compliance_status.
- **Same engine.** Every view computes internally 0 = favourable … 100 = unfavourable.
  `score_orientation: higher_is_better` changes only the presentation, and the reading of expert
  labels, for the performance view.
- **Per-view separation.** Labels (`expert_risk_score`, `expert_scores[view]` /
  `expert_<view>_score`), weight-store sub-folders and the UI runs are kept per view.

**Bugs found while building it:**
1. A criterion named like a numeric indicator (`quality_ppm`) made PPM values be read as expert
   ratings. The criterion was renamed `delivered_quality`. A naming rule is now in the catalogue,
   with a test.
2. Spreadsheet rows were parsed against the active view's criteria only, so risk ratings became
   "indicators" in the performance view. Rows are now parsed against the whole catalogue. A test
   checks that one sheet gives identical results per view.

**Result on sample data.** SUP-003 and SUP-005 are critical in the risk view and A in the
performance view. This illustrates why practice keeps both.

## 2026-10 — Spreadsheet UI ("wolf in sheep's clothing")

**D28: `ui/app.py` (Streamlit).** It feels like a spreadsheet; the full workflow runs underneath.

**Design choices:**
- **`st.data_editor` instead of streamlit-aggrid:** native and version-safe. It is testable with
  Streamlit's `AppTest`, and the end-to-end tests run in CI. Sorting and editing come built in;
  filters are one row of controls above the table.
- **No logic in the UI:** all numbers come from `SupplierRiskEvaluator`. Row/CSV conversion
  lives in `supplier_risk_agent.tools.tabular` and is tested, including a CSV round trip that gives
  identical assessments.
- **Scoring on load:** data is scored as soon as it is loaded (start, example, CSV import), like a
  spreadsheet that is always calculated. The button is "Recalculate".
- **Approval enforced:** in the UI, calibrated weights always go through the review tab
  (`auto_apply` off).
- **Labels edited in one place:** expert labels are edited only in the calibration tab, so that
  two editors never compete for the same cell.
- **Colours:** risk classes use the fixed status palette, always as icon + label (never colour
  alone). Current/proposed weights use categorical slots 1/2 of the validated reference palette.

**Found by looking at screenshots** (headless Chromium):
- The class chart overlapped its bars.
- The weight chart was cramped.
- The portfolio started empty.

All three are fixed. Known cosmetic: `st.dataframe` shows missing numbers as a grey "None".

## 2026-10 — Fit diagnostics: residual and knock-out candidates

**D27: Three hints in the calibration report.** They are warn only; they appear in the review
request and the audit trail.
1. **High residual.** CV error after calibration ≥ 40 % of the label variance.
2. **Knock-out candidate.** Suppliers with a rating ≥ 4 on a factor (≥ 3 of them) are judged
   ≥ 5 points and ≥ 2 SE riskier than the calibrated model predicts. The residual is **centred**
   first, because without centring every level shift looks like a knock-out on every factor.
3. **Pushed to the minimum weight.**

**Probe before building.** The user's hypothesis "factor pushed to the minimum = knock-out
candidate" was checked first. It is unspecific: it fires with level shifts and knock-outs, but
also in 13–17 % of linear and up to 53 % of very noisy runs. A knock-out makes its factor look
more important, not less. The minimum-weight hint is therefore kept, but worded as "check this
factor". The real knock-out signal is the subgroup residual.

**E4b rates (n = 16 / 32 / 64):**
- **Knock-out candidate:** 13 / 53 / 97 % on the knock-out policy; ≤ 3 % false hints for linear
  experts.
- **High residual:** 63–100 % on non-additive, knock-out and level-shifted policies; 0–7 % for
  linear experts.
- **Not reliably detected:** disagreement between experts.

## 2026-10 — Regularisation scaled with 1/n

**D26: Default `lambda_selection: scaled`**, i.e. λ = 0.05 × 32 / n (`lambda_reference_n: 32`).

**Why.** The error term is a mean, so a fixed λ is a prior whose relative weight never fades. In
E2 it biased the fit at large n (2.5 vs. 0.8 at 192 labels).

**Compared variants** (E2, 30 seeds per n):
- **Fixed 0.05:** good at small n, biased at large n.
- **Scaled (chosen):** better than the default weights in 100 % of seeds at every n; equals the
  unregularised fit at large n; no harmful acceptance at any n. Slightly worse than fixed at
  16–24 labels (11.5 vs. 9.9).
- **CV, one-SE rule:** over-regularises in the middle range (10.6 vs. 5.9 at 32).
- **CV, minimum rule:** good from 32 labels, noisy below (24.5 vs. 18.4 at 8). Both CV variants
  are about 10× slower. They stay available as options.

**Consequence for D25.** The z ≥ 2 threshold was re-checked with the scaled λ.
- With 40 seeds, one scenario showed 8 % harm (3/40 runs), which looked like a breach of the 5 %
  criterion.
- A rerun with 100 seeds gave 4 % worst case, so z ≥ 2 stays. z ≥ 1.5 has 8 %.
- E5 now runs with 100 seeds.

**Caveat.** The scaling constant is tuned on the same synthetic data.

## 2026-10 — Uncertainty-aware acceptance (E5)

**D25: Acceptance also requires z ≥ 2.**
- **Statistic.** z = mean per-supplier out-of-fold error reduction divided by its standard error
  (`cv_min_z`, default 2.0).
- **Selection.** Study E5 (`scripts/acceptance_study.py`: 5 policies × n 8–64 × 40 seeds,
  thresholds 0–3). The criterion was the smallest z with ≤ 5 % harm in every scenario: z = 2.
  - Mean harm falls from 8.8 % to 1.1 %, worst scenario from 35 % to 5 %.
  - Error in use rises from 0.83 to 0.88 of the default error.
- **Effect in the re-runs.**
  - E4: two experts 43/23 % → 0/0 % harm; knock-out 10/13 % → 0/3 %; all other policies 0 %.
  - E2: harm ≤ 3 % everywhere.
  - Acceptance at 32 labels: 87 %. At 16 labels: 50 %.
- **Caveats.**
  - The SE ignores fold dependence, so z is a screening statistic.
  - The threshold was chosen and evaluated on the same synthetic scenarios.

The acceptance logic now lives in one library function (`cross_validated_acceptance`) that the
agent and all experiment scripts share, so the scripts cannot drift from production behaviour.

## 2026-10 — Level-offset diagnostic

**D24: The calibration report flags a level offset.** The flag fires when the mean of
(label − score) under the active weights is ≥ 5 points and ≥ 2 standard errors from zero.
- **Default action `review`:** such weights are never auto-applied and go to human review with a
  hint to check the class thresholds.
- **Threshold derivation:** on E4 runs the flag catches 100 % of level-shift and worst-factor
  runs and 30–37 % of knock-out runs. It produces ≤ 7 % false flags for linear experts (0 % from
  32 labels). The reference portfolio (+2.2) is not flagged.
- **Side effect:** harm under the knock-out policy is halved (10 → 3 % at 16 labels,
  13 → 7 % at 32).
- **Not addressed:** disagreeing experts.

**Bug found on the way:** a numpy float in the report broke checkpoint serialisation. Values are
now cast to Python floats. The graph-level test with the level-shifted portfolio covers it.

## 2026-10 — Robustness to misspecified expert policies (E4)

**D23: E4 run** (`scripts/robustness_calibration.py`, Figure 7, paper Section 7.7). Eight constructed
expert policies; production settings; 16/32/64 labels; 30 seeds.

| Situation | What calibration does |
|---|---|
| Noise / rounding | Robust, but costs labels: σ = 8 needs about 64 labels for 75 % of the gain. |
| Non-additive policies (interaction, worst factor) | A large floor remains that no weighting removes; class agreement barely improves. |
| Knock-out judgements | Weights cannot learn them. At 16 labels calibration is worse than the defaults; the CV rule still lets 10–13 % harm through at 16–32 labels. Encode knock-outs as escalation rules. |
| Level offset (experts uniformly stricter) | Weights cannot shift the level. Calibration distorts them: the shift correlates 0.89 with factor mean rating, and insolvency and compliance are pushed to the minimum weight. Handle via thresholds or an offset term. |
| Disagreeing experts, little to gain | Worst case for the acceptance rule: 43 % harm at 16 labels, 23 % at 32. Measure inter-rater agreement first; require the CV improvement to exceed its standard error. |

**Open follow-ups (code):**
- ~~level-bias diagnostic~~ (done, D24); residual / knock-out diagnostics
- significance-based acceptance
- λ by CV

## 2026-10 — Cross-validated acceptance and validation figures

**D21: Acceptance is tested out of sample by default.**
- Refit on k − 1 folds, then pool out-of-fold MSE.
- 5 folds × 3 repeats, deterministic.
- Accept only if the pooled MSE improves by ≥ `min_improvement`.

Consequence on the shipped data: the 10-label "plastics" calibration is now rejected. In-sample
it showed 36.8 → 10.4; cross-validated it was 36.8 → 41.7. This is the behaviour the rule exists
for.

**D22: Figures 4–6 are generated.** `scripts/plot_calibration_validation.py` builds them from
the validation CSVs into `docs/paper/figures/`.

## 2026-10 — Calibration validation (paper section 7)

**D20: Calibration validated on synthetic data** (`scripts/validate_calibration.py`):
- **E1:** repeated 5-fold CV on the reference portfolio
- **E2:** sample size × λ against an independent test set
- **E3:** stability across 100 seeds

At λ = 0.05 and 32 labels:
- CV MSE is 37.8 → 20.6, against a noise floor of 18.1
- the in-sample MSE of 12.4 is optimistic
- weights move about half-way to the hidden weighting

**Issues found:**
1. **The acceptance rule used in-sample improvement.** It accepted almost everything, including
   overfitted fits on 8 labels.

   **Fixed (D21):** `acceptance: cross_validated` is now the default. In E2 (8 labels, λ = 0),
   the share of runs whose applied weights are worse than the defaults fell from 50 % to 7 %; with
   λ = 0.05 it fell from 10 % to 3 %.

   **Trade-off:** the CV rule is conservative. At 8–16 labels with λ = 0.05 it rejects some useful
   fits, so the mean applied error rises (8 labels: 16.7 → 20.8 vs. a default of 29.7). From 24
   labels on, both rules decide identically. The in-sample rule stays available as
   `acceptance: in_sample` for experiments and is documented as a known limitation.
2. **A fixed λ does not fade with n.** *Still open.* The error term is a mean and the penalty is unscaled, so
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
