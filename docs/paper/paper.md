# Lean Agentic AI for Supplier Risk Evaluation

### Turning spreadsheet scorecards into transparent, expert-calibrated multi-agent systems: a benchmark of four approaches and an open-source demonstrator

*Csaba Bakay · Working draft v0.1 · October 2026*

> **Draft status.** Sections 1–6 are written as a first draft. Sections 7–12 are outlined in
> [paper-outline.md](paper-outline.md). Markers in the text:
> - **[TBD-RESULT]** — to be completed or confirmed with results from the local calibration runs
> - **[TBD-LIT]** — literature still to be searched and cited
> - **[TBD-INPUT]** — needs a decision or input from the author
>
> Numbers quoted from the demonstrator come from runs of commit `461592c` on synthetic data.

---

## Abstract

Supplier risk evaluation in mid-sized procurement organisations usually takes one of two forms:
- a spreadsheet scorecard, which is cheap and transparent but cannot learn or scale, and does not
  keep an audit trail
- a commercial supply-chain risk platform, which brings data coverage and workflows, but at a cost
  and with limited control over how scores are formed

Open-source agent projects show how such systems could be built, but mostly as demonstrators
without a defensible scoring method. A further problem cuts across all three: the weights that turn
criteria into a risk score are typically set once and never checked against the judgement of the
people who know the suppliers.

This paper makes three contributions.
1. It proposes fifteen success factors for supplier risk evaluation. They were derived and then
   corrected in a documented review that removed means-as-ends and added two factors on which
   commercial platforms are strong.
2. It profiles four approaches on these factors without aggregating them:
   - spreadsheet practice
   - two commercial platforms, Prewave and Sphera
   - five open-source repositories
   - the approach proposed here
3. It presents *Lean Agentic AI* and an open-source demonstrator. The approach starts from existing
   scorecard practice and builds on open agentic workflows. Its scoring is deterministic and
   configurable, with material-group-specific weights. Weights are calibrated against category
   managers' expert labels by constrained least squares. A human-in-the-loop step pauses the
   workflow for approval, and approved weights are versioned.

On a synthetic portfolio whose labels were generated from a hidden weighting:
- calibration reduced the mean squared error between model score and expert label from 37.8 to
  13.3 score points²
- it moved the weights 60 % closer to the hidden weighting

The paper states what this does not establish:
- the labels are synthetic
- the fit is in-sample
- predictive validity against real disruptions is untested
- the demonstrator does not provide the external signal coverage that commercial platforms offer

No ranking of approaches is derived at any point.

---

## 1 Introduction

Supplier risk evaluation has moved from an annual formality to a recurring management task.
Disruptions in logistics, energy and geopolitics have made supply concentration visible. Due-
diligence regulation expects documented risk analysis along the supply chain. Procurement teams
are asked to show not only *which* suppliers are risky, but *why*, and what was done about it.

A common organisational response is to extend the supplier scorecard. The criteria sheet gains
columns for financial stability, supply-chain exposure and ESG. A weighted average turns the
columns into a score, and the score into a traffic light. Where budgets allow, a commercial
platform is licensed to supply alerts and external data.

Both responses leave a gap. The spreadsheet keeps the method in the procurement team's hands but
does not keep a record: weights drift between versions, and no one can say afterwards why a
supplier was rated as it was. The platform brings data coverage and workflows, but the method by
which its score is formed is, depending on the vendor, partly or largely outside the customer's
view and control. Open-source agent projects, the third option a technically minded team might
consider, offer modern architecture patterns but rarely a scoring method that could stand up in an
audit.

One problem cuts across all three options and is rarely named: **the weights are not validated.**
A scorecard may weight business impact at fourteen per cent and ESG at twelve. Those numbers
usually come from a workshop, a template or a vendor default. They are seldom checked against the
holistic judgement of the category managers who know the suppliers best, and seldom revised when
the two disagree.

This paper takes a deliberately lean route. It does not propose a new risk taxonomy or a new data
source. Instead it starts from the scorecard practice that already exists and asks what it would
take to make that practice:
- **transparent**, with method and weights documented and inspectable
- **reproducible**, with every number recomputable from its inputs
- **governed**, with human approval at the points where judgement is required
- **able to learn**, by systematically aligning weights with expert judgement

It also asks whether this can be done at the cost profile of open-source software rather than an
enterprise licence.

The argument proceeds in two steps.
- **A benchmark.** Fifteen success factors are proposed, and four approaches are profiled on them
  (Figure 1). The profile is read factor by factor, without weighting, total or ranking.
- **A demonstrator.** The proposed approach is implemented as an open-source multi-agent workflow.
  Each claimed property can then be inspected in code, tests and documentation rather than
  asserted.

The demonstrator runs on synthetic data. This is a deliberate constraint, and it has a cost,
discussed in Section 10 [TBD: link]. It also has a benefit: because the expert labels in the
calibration experiment were generated from a known hidden weighting, it can be checked whether
calibration recovers that weighting, which no field dataset would allow.

![Figure 1](../images/spider-diagram.png)

*Figure 1. Four approaches to supplier risk evaluation profiled on fifteen success factors (model
v0.2). Illustrative assessment based on public information and code review (October 2026).
Proprietary SaaS is plotted as the mean of Prewave and Sphera; shaded bars mark where the two
differ. Rationale and confidence for every value: Table 2 and `research/comparison-matrix.md`. No
weighting is applied, and no total or ranking is derived.*

**Contributions.**
1. **Fifteen success factors** for supplier risk evaluation, each with a definition and the
   evidence by which it can be assessed. They are presented as a working model, together with the
   documented review that produced the current version (Section 3).
2. **A profile benchmark** of four approaches on these factors. Every value comes from a single
   machine-readable source with a rationale and a confidence mark. The two commercial examples are
   rated separately and their spread is shown (Section 4).
3. **The Lean Agentic approach**: a synthesis of scorecard practice, platform expectations and open
   agentic architecture. Calibration against expert labels is its central distinguishing feature
   (Section 5).
4. **An open-source demonstrator.** It is a LangGraph workflow with:
   - deterministic, configurable scoring
   - material-group weights
   - constrained least-squares calibration
   - a graph-interrupt human-review step
   - a versioned weight store
   - an automated test suite (Section 6)
5. **An explicit statement of what is not established**, and of the work that would close each gap
   (Sections 10–11) [TBD: to be written].

---

## 2 Background and related work

### 2.1 Supplier risk assessment in practice

Weighted multi-criteria scorecards are the dominant instrument for supplier risk assessment in
practice [TBD-LIT: MCDA in supplier selection and risk; scorecard practice]. A typical scorecard
has these parts:
- **dimensions.** A *severity* component asks how replaceable a supplier is and how badly a failure
  would hurt. *Likelihood* components cover financial stability, supply-chain exposure (country,
  sourcing strategy, transport) and ESG or compliance.
- **ratings** on an ordinal scale, often 1–5
- **weights** per criterion
- **an aggregation** into a single score and a class

The method is not in question here. What is in question is how it is run:
- definitions and scales are informal
- weights are set once
- results are not reproducible after the file has changed
- consequences are written as free text, if at all

### 2.2 Commercial supply-chain risk platforms

Commercial platforms address the data side of the problem. Two are used as named examples, assessed
**on public information only** (vendor websites, help-centre articles, press releases and
vendor-commissioned studies, as of October 2026). Nothing here is a product test.
→ `research/saas-references.md`.

**Prewave** combines continuous media and trade-data monitoring with supplier assessments and
due-diligence modules for several European regulations.
- **Signals.** It claims millions of processed signals per day in several hundred languages, and
  Tier-N mapping from trade data.
- **Scoring.** Unusually for the category, Prewave publishes the composition of its supplier
  score: a peer component (country, industry, commodity) at 30 %, alerts at 40 %, assessments at
  20 % and external data at 10 %. It describes the aggregation as non-linear and weighted.
- **Configuration.** Event types and their weights can be adjusted in customer-specific
  "perspectives", partly through the vendor's customer-success function.
- **Not disclosed:** how sources are weighted and how media signals are classified.

**Sphera Supply Chain Risk Management** (formerly riskmethods) offers:
- portfolio risk views, multi-tier mapping and early warnings
- response playbooks, incident management and supplier engagement campaigns
- a documented bundle for the German supply-chain due-diligence act (2023)

Its scores are described as "AI-scoring" tied to business impact, using indicator scorecards. No
public description of the scoring method or of customer-adjustable weights was found.

Two observations matter for this paper.
1. **"Platform" is not one methodological profile.** On methodological transparency the two
   examples differ by a full scale point. This is why they are rated separately in Section 4 rather
   than as a stereotype.
2. **Neither vendor documents calibration against the customer's own expert judgement** in public
   sources. Weight adjustment exists (Prewave), but as configuration, not as a fitted and reported
   procedure.

Other vendors were checked only briefly and are not part of the benchmark:
- **Resilinc:** fixed score components against universal standards.
- **EcoVadis:** published criteria with qualitatively described weighting.
- **Everstream, Interos:** no public scoring method found.

### 2.3 Open-source agentic supply-chain projects

Five public repositories were reviewed at source-code level (→ `research/github-references.md`,
`research/comparison.md`). They converge on one architectural pattern: specialised agents sharing a
typed state, coordinated either as a directed graph or by a supervisor. They diverge sharply on
scoring.
- **No scoring.** One repository returns fixed, simulated outputs and contains no scoring at all.
- **Deterministic, hard-coded weights.** Two compute deterministic weighted scores. One of them
  deliberately overwrites any numbers produced by the language model with values computed in code.
- **LLM-judged.** Two leave the risk judgement to a language model. In one of them, a published
  example contains arithmetic errors in the weighted totals, a small but telling illustration of
  why numbers should not be generated by a language model.
- **Licensing and tests.** Two repositories carry no licence, one is under a copyleft licence, and
  none ships an automated test suite.

The repositories are therefore valuable as **architectural blueprints**, not as methods. The
approach in this paper reuses ideas from them, but no code.

### 2.4 Calibrating weights against expert judgement

Two distinct practices both go by the name of "setting weights":
- **eliciting** weights directly, by asking experts how important each criterion is
- **inferring** them from holistic judgements, by asking experts how risky each supplier is overall
  and finding weights that reproduce those answers [TBD-LIT: policy capturing / judgement analysis;
  regression-based weight elicitation; comparison of direct vs. indirect weighting]

The second practice has a practical advantage in procurement. Category managers often find it
easier to judge a supplier than to state the relative importance of abstract criteria. It also has a
known risk: with few judgements and many weights, the fit adapts to noise. Regularisation towards a
prior weighting is a standard remedy [TBD-LIT: ridge / Tikhonov regularisation; shrinkage towards
expert priors]. The approach in Section 5 combines the two practices. Directly elicited weights
serve as the prior. Holistic labels adjust them under constraints.

### 2.5 Language models and determinism

Agentic systems invite the use of language models throughout. For risk scores this is the wrong
default.
- A score that changes when the same input is presented twice cannot be audited.
- A score that cannot be recomputed by hand cannot be challenged.

The reviewed repositories show both patterns:
- language-model-judged tiers without stable criteria
- language-model arithmetic that does not add up

The more mature designs among them compute numbers in code and reserve the language model for
language. This paper adopts that division strictly.

---

## 3 Success dimensions for supplier risk evaluation

An approach to supplier risk evaluation is easier to assess when the properties that matter are
named before any approach is rated. This section proposes fifteen such properties, called *success
factors*. Each is defined, and for each the observable evidence is named that would allow someone
else to check a rating (→ `research/success-factors.md`).

The factors form a **flat list**. They are not arranged in a hierarchy, not weighted and not
combined into a total. An approach is read as a **profile** across all fifteen. A profile that is
strong on twelve factors and absent on one is a different proposition from one that is uniformly
adequate. A single figure would treat the two alike.

**Table 1. Success factors for supplier risk evaluation (model v0.2).**

| # | Factor | What it means | Assessable by |
|---|---|---|---|
| 1 | Structured criteria & weights (objective + subjective) | Explicit criteria, scales and weights combining measurable indicators and structured expert assessment | Criteria with definition and scale; explicit weights; both input types with provenance |
| 2 | Traceability & reproducibility | Every result can be reconstructed afterwards and recomputed from documented inputs | Per-result record; change history; recomputation possible; tests |
| 3 | Methodological transparency | The method is documented and checkable *before* use | Published formula, weights, sources, rules |
| 4 | Expert calibration / ability to learn | Parameters are systematically fitted to expert judgement, with approval | Procedure; fit metric; logged old/new parameters; approval |
| 5 | Material-group-specific adaptation | Weights or thresholds can differ by commodity | Per-group weights and calibration |
| 6 | Action framework | Results map to defined actions, review cycles and owners | Actions per class and driver; tracking to closure |
| 7 | Human-in-the-loop & governance | Defined review and approval points, recorded decisions, roles | Approval steps; recorded overrides; roles |
| 8 | External signals & data coverage | Current external data and breadth of supplier coverage | Sources, update frequency, languages, Tier-N |
| 9 | Regulatory evidence | Support for due-diligence documentation duties | Regulation-specific workflows and reports |
| 10 | Cost / accessibility | Total cost of use and access barriers | Licence model, prices, implementation effort |
| 11 | Time-to-value | Time and effort to the first usable result | Time to first portfolio assessment |
| 12 | Customisability & data sovereignty | The organisation can change method and implementation and controls its data | Configurable without vendor; licence; data location |
| 13 | Scalability | Works as suppliers, users, groups and update frequency grow | Suppliers handled; marginal effort; automation |
| 14 | Extensibility & automation potential | New capabilities can be added without rebuilding the core | Extension points; APIs |
| 15 | Operational maturity & support | Production readiness | Support, SLAs, security, release process |

### 3.1 How the factor model was derived, and corrected

The fifteen factors are the second version of a working model. The first version (v0.1) was drawn
up from the requirements of the proposed approach. A critical review identified four problems.
Each was corrected, and the corrections are documented because they bear on how far the benchmark
can be trusted.

1. **Means presented as ends.** Two v0.1 factors named a *means*: "open source" and "multi-agent
   orchestration". Rating approaches on the means one has chosen makes the comparison circular.
   Both were reframed as outcomes: *customisability & data sovereignty* and *extensibility &
   automation potential*.
2. **Home-field bias.** v0.1 contained no factor on which commercial platforms are clearly
   stronger, apart from external signals. Two were added: *regulatory evidence* and *operational
   maturity & support*. Without them, the profile would flatter the proposed approach.
3. **Overlaps.** Two pairs measured the same strength twice and were merged:
   - *structured criteria* with *objective + subjective inputs*
   - *audit trail* with *determinism*

   *Methodological transparency* was kept separate from *traceability*. The first concerns
   understanding the method before use; the second concerns reconstructing a result afterwards.
4. **Validity, the factor that is missing.** No factor asks whether a score *predicts*
   disruptions. Calibration against experts measures agreement with judgement, not predictive
   validity. No approach reviewed reports predictive validity publicly, so the factor cannot be
   rated today. It is deliberately left off the radar and treated as an open question
   (Section 11) [TBD: link].

The resulting model keeps fifteen axes, which is about the readability limit of a radar chart.
It now contains four factors on which the commercial examples are clearly ahead: 8, 9, 13 and 15.

---

## 4 Benchmark: four approaches profiled

### 4.1 Method

Four approaches are rated on the fifteen factors on a five-point scale (1 weak or absent, 3
adequate, 5 very strong). Each rating carries a short rationale and a confidence mark:
- **H**: verified from code or primary documentation
- **M**: plausible, partly documented
- **L**: assumption

All ratings live in one machine-readable file, `research/comparison-matrix.yaml`. Table 2 and
Figure 1 are generated from it by a script that also validates the file. A consistency check fails
if the published table no longer matches the source. The evidence differs by approach, and this is
disclosed rather than hidden:

| Approach | What is rated | Evidence |
|---|---|---|
| Excel / manual | A typical procurement scorecard (criteria sheet, weights, annual update) | Practitioner experience; assumption-based |
| Proprietary SaaS | Prewave and Sphera, **rated separately**; the profile plots their mean and shows the spread | Public information only, October 2026 |
| Open-source repos | The five reviewed repositories | Source-code review |
| Lean Agentic | The demonstrator **as implemented**, not its roadmap | Code, tests and documentation |

**Table 2.** *Full matrix with rationale per cell, generated: `research/comparison-matrix.md`.*
[TBD-INPUT: in the typeset paper, include the generated table here, or move it to an appendix and
keep a condensed version in the text.]

### 4.2 Reading the profiles

Figure 1 is read factor by factor. Four patterns stand out.

**Spreadsheet practice is strong where simplicity helps.** It is cheap, starts immediately and
keeps formulas visible. It is weak everywhere a system property is needed: an audit trail,
learning, external data, extension. The profile describes a stereotype. Real spreadsheet
practices vary widely, and a well-governed workbook can do better on traceability than the rating
suggests.

**The commercial platforms are strongest on data, scale and operations.** They lead on four
factors:
- external signals and coverage
- regulatory evidence
- scalability
- operational maturity

They are also well developed on workflows and review steps. They are weaker on four others:
- cost
- self-determined customisation
- recomputability by the customer, which is a design consequence of continuous monitoring rather
  than a flaw
- for one of the two, methodological transparency

The spread between them is largest exactly there. Prewave publishes its score composition; Sphera
does not.

**The open-source repositories are blueprints.** They are free, and their agent architectures are
their main asset. On almost every methodological factor they are rudimentary.

**The Lean Agentic demonstrator is strongest where the method itself matters:**
- methodological transparency
- traceability and reproducibility
- expert calibration
- material-group adaptation
- customisability

It is deliberately weak on three factors:
- external signals (rated 1: none are implemented)
- regulatory evidence
- operational maturity

These dips are not hidden. They define what the approach is not.

### 4.3 Complementary, not ranked

The profiles do not order the approaches. In particular, Lean Agentic does not replace the data
coverage of a platform. The most realistic reading of Figure 1 is **complementary**. A platform
subscription or open data can serve as the *signal source*. A transparent, calibrated model owned
by the procurement team turns signals and internal knowledge into risk classes and actions.
Section 8 [TBD] returns to this hybrid.

### 4.4 Threats to validity of the benchmark

- **Author bias.** The factors and the ratings come from the authors of one of the rated
  approaches. Mitigations:
  - the v0.2 correction against home-field bias
  - rating the demonstrator as implemented rather than as planned
  - a rationale and confidence mark for every value

  These reduce the bias; they do not remove it. [TBD-INPUT: independent re-rating by 3–5
  practitioners, reporting the spread.]
- **Public information only for the platforms.** Hands-on evaluation could move several ratings,
  especially those on traceability, material-group adaptation, workflows and time-to-value.
- **Date dependency.** Products change. All platform ratings refer to public information as of
  October 2026.
- **Ordinal scale.** Ratings are ordinal judgements. Differences of one point should not be read as
  measured distances.

---

## 5 The Lean Agentic approach

### 5.1 Definition

*Lean Agentic AI* is defined here as an approach that:
- starts from the evaluation practice an organisation already has
- uses open agentic workflows as blueprints
- builds a tailored, transparent and low-cost system on top of that practice rather than
  replacing it

"Lean" means three things:
- **build only what adds value**
- **reuse open blueprints**
- **keep the method in the hands of the team that is accountable for it**

(→ `research/lean-agentic-positioning.md`.)

### 5.2 A synthesis of three traditions

The approach inherits deliberately from each of the three traditions in Section 2.

**From scorecard practice**, it takes the domain logic:
- named criteria and 1–5 ratings
- weighted dimensions, including a severity component that combines availability of alternatives,
  change complexity and business consequence
- a class-based action framework

Procurement keeps its method and its vocabulary. What changes is that the method becomes explicit,
versioned and testable.

**From commercial platforms**, it takes the expectations placed on a professional system:
- review and approval steps
- an audit trail
- integration of objective indicators with expert assessment
- an action framework with review cycles

External signal feeds are not implemented. They are intended to come from open data or an existing
platform subscription.

**From open-source agent projects**, it takes the architecture: a supervisor coordinating
specialised agents over a typed shared state. It also takes the lesson the better projects teach:
numbers are computed in code, and language models are reserved for language.

### 5.3 Distinguishing features

Six features distinguish the approach. The first is its central contribution.

**(1) Calibration against expert judgement.** Weights are not only configurable; they are fitted
to the holistic judgements of category managers.
- Each labelled supplier receives a risk score from 0 to 100 on the model's own scale.
- The weights are chosen to minimise the mean squared error between model score and label.
- Constraints: every weight stays above a minimum, and the weights sum to one.
- A ridge term pulls the solution towards the configured default weights. This keeps the
  procedure from overfitting small samples, and keeps it from silently switching off criteria the
  methodology considers relevant.

The anchor of the regularisation is always the configured default, never the result of a previous
calibration. This prevents repeated calibration on the same labels from drifting a little further
from the methodology each time. The problem was found by a test, and the fix is documented.

Calibrated weights are applied only if the error falls by a minimum relative amount. Depending on
configuration, they are either applied automatically or proposed for approval. Old and new weights,
the error before and after, and the share of suppliers whose model class matches the class implied
by the expert label are all reported. Formulation: Section 6.4.

None of the reviewed repositories, and neither commercial example in its public documentation,
offers this. It turns the scorecard from a fixed instrument into one that learns from the people
accountable for it, while every weight remains explainable.

**(2) Weights as first-class, versioned objects.** Default weights, material-group weights and
calibrated weights are interchangeable objects. They are never hard-coded. Every applied weight set
is written as a new, never-overwritten version, recording:
- timestamp
- approver
- model version
- calibration metrics

**(3) Material-group awareness.** One weighting rarely fits every commodity. Weights can be set,
and calibrated, per material group. Each supplier is scored with the most specific weight set
available.

**(4) Human-in-the-loop as a real pause.** When data is insufficient or weights are proposed, the
workflow stops and waits for a decision. A reviewer can:
- approve the weights
- set a supplier's class manually, with a comment
- defer

The decision is recorded, and manual classes survive re-scoring.

**(5) Deterministic scoring.** Every number is produced by pure, tested functions. The same input
always gives the same score, and every score can be recomputed by hand. Language models are kept
out of the numbers entirely. Their planned roles are extraction from documents and narrative
explanation.

**(6) Governance by construction.** Several controls are built into the method rather than added
around it:
- Escalation rules set a class floor that no weighted average can hide, for example for a
  critical compliance finding or acute insolvency signals.
- A data-completeness check flags results that rest on too little data.
- The audit trail is append-only.
- Every feedback loop is bounded.

### 5.4 What the approach is not

Equally important for the positioning, the approach is **not**:
- a data provider: it monitors no news, disasters or Tier-N networks
- a regulatory compliance product
- production-hardened: it has no roles or permissions and no persistent run store
- empirically validated: its calibration has so far been shown on synthetic labels only

The claim of this paper is narrower. The *method layer* of supplier risk evaluation can be made
transparent, reproducible, governed and able to learn at low cost. It is a layer that commercial
platforms leave partly opaque and spreadsheets leave ungoverned.

---

## 6 Architecture of the demonstrator

This section summarises the demonstrator. Design details are in `docs/architecture.md`,
`docs/scoring-model.md` and `docs/calibration.md`.

### 6.1 Workflow

The demonstrator is a LangGraph state graph in hub-and-spoke form (Figure 3 [TBD: render from
`docs/architecture.md`]). A rule-based **supervisor** inspects the shared state and routes to one
of five workers:
- **data collection**: loads the suppliers in scope, optionally restricted to one material group,
  together with indicators and expert labels from a pluggable source
- **scoring**: rates factors, aggregates, normalises and classifies, applies escalation rules and
  checks data completeness
- **calibration**: optional
- **recommendation**: maps classes and elevated dimensions to actions and review cycles
- **human review**

Every worker returns control to the supervisor. The routing rules fit in one function, which is
also the single extension point for a language-model-based supervisor.

```
collect_data → score → [calibrate → score] → recommend → [human_review ⏸ → score? → recommend] → end
```

Each loop runs at most once per run, by construction:
- calibration
- the re-score it triggers
- human review

### 6.2 Scoring model

**Ratings.**
- Each factor is rated on an ordinal scale from 1 (low risk) to 5 (high risk).
- A rating comes either from an expert or from a rule that converts a raw indicator, such as a
  credit score, a country risk index or the number of qualified sources.
- An expert rating always takes precedence, so judgement can override any derived value. The
  provenance of every rating is recorded.

**Aggregation.** With effective factor weights θ (non-negative, summing to one):
- dimension ratings are weighted means of their available factors
- the overall rating *R* is the weighted mean of the dimension ratings

**Normalisation.** *R* is mapped to a score *S* by min-max normalisation:

  *S* = (*R* − 1) / 4 · 100

The 1–5 scale has no zero. Min-max normalisation maps its actual range onto 0–100: the best
possible supplier scores 0, the scale midpoint 50 and the worst 100. A naive *R*/5 would start at
20 and leave a fifth of the range unused. The 0–100 scale is also the scale on which expert labels
are given. Because the mapping is affine, rankings are unchanged and calibration remains a linear
problem.

**Classes, escalations and missing data.**
- Classes follow from thresholds on *S* (in the default template: low below 30, medium below 50,
  high below 70, critical from 70).
- Escalation rules can raise a class but never lower it.
- Missing factors are excluded and the remaining weights re-normalised within their dimension. The
  share of weight actually backed by data is reported. Below a threshold, the result is flagged for
  review.

The default criteria, weights and thresholds are an **illustrative template**, not a
recommendation.

### 6.3 Weights as objects

The scoring engine never reads weights from code. It receives a *weight set* (effective factor
weights) chosen for each supplier from the most specific available source:
1. calibrated weights for its material group
2. configured weights for that group
3. calibrated global weights
4. configured global defaults

Applied weight sets are persisted in a versioned store and loaded at the start of the next run.

### 6.4 Calibration

For *n* suppliers with complete factor ratings **x**ᵢ and expert labels *y*ᵢ ∈ [0, 100], the
calibrated weights θ solve:

  minimise  (1/*n*) Σᵢ ((*s*ᵢ(θ) − *y*ᵢ) / 100)² + λ ‖θ − θ_anchor‖²
  subject to θ_f ≥ *w*_min for all *f*, and Σ_f θ_f = 1,

where *s*ᵢ(θ) = (**x**ᵢ · θ − 1) / 4 · 100, and θ_anchor is the configured default weighting.

The problem is a convex quadratic program, solved with a sequential least-squares method and an
analytic gradient. In the default configuration:
- λ = 0.05
- *w*_min = 0.02
- at least eight labelled suppliers with complete data are required
- acceptance requires a relative error reduction of at least 5 %

Only suppliers with complete data are used. Missing-data re-weighting would make the score
non-linear in θ.

The expert's class is derived from the label with the model's own thresholds. Labels are therefore
expected as scores rather than classes: a score carries more information than a class, and it keeps
the fit linear. Class agreement is reported alongside the error.

> **[TBD-RESULT] Calibration on the synthetic portfolio** (to be moved to Section 7, with
> Figures 4–5). Current values from `examples/calibrate_weights.py`, commit `461592c`:
> - **Data.** 36 synthetic suppliers. 32 have a label and complete data; 4 are unlabelled.
> - **MSE:** 37.8 → 13.3 score points² (RMSE 6.15 → 3.64).
> - **Class agreement:** 84 % → 88 %.
> - **Weights.** L1 distance to the hidden generating weighting fell from 0.345 to 0.138 (60 %
>   closer). Dimension weights moved towards it:
>   - supply chain 25 % → 32.8 % (hidden 32 %)
>   - ESG & compliance 20 % → 12.2 % (hidden 8 %)
>   - severity 35 % → 37.2 % (hidden 42 %)
> - **Classes.** Re-scoring changed the class of 2 of 36 suppliers.
>
> **Caveat that must stay in the text.** The fit is in-sample. The labels contain noise
> (σ = 4) and are rounded to steps of 5, which implies an irreducible RMSE of about 4.25. The
> calibrated in-sample RMSE (3.64) lies *below* that floor. This is consistent with in-sample
> optimism when fitting ten weights to 32 labels; regularisation limits it but does not remove
> it. Cross-validated error is required before any claim about fit quality.
> [TBD-RESULT: k-fold CV; sensitivity to λ and sample size; stability across seeds.]

### 6.5 Human review

The review step uses the graph framework's interrupt mechanism.
- **Pausing.** The run is checkpointed under its identifier. A structured request lists the
  flagged suppliers with their reasons and any proposed weights with their error metrics.
- **Resuming.** The run continues with a decision object.
- **Effects of a decision.**
  - Approved weights are stored with the reviewer's name, and the portfolio is re-scored.
  - Manual classes are kept across re-scoring and marked as overrides.
  - Recommendations are rebuilt after any change.
- **Invalid decisions** are reported and ignored.

### 6.6 Engineering properties

These properties make the claims in Sections 5 and 6 checkable:
- **Tests.** The demonstrator ships with 52 automated tests (commit `461592c`). They cover
  scoring, weights, calibration (including recovery of known weights from noise-free labels),
  the weight store, the human-review flow and the consistency of the benchmark data.
- **CI.** Continuous integration runs linting and tests on two Python versions.
- **Checkpoint types.** The checkpointer restores only explicitly allow-listed state types.
- **Licence and data.** The code is MIT-licensed. All data is fictional or synthetic and labelled
  as such.

---

## 7–12 (to be written)

See [paper-outline.md](paper-outline.md):
- **7 Demonstration on synthetic data**: results from the [TBD-RESULT] block; Figures 4–5
- **8 Comparison and discussion**: hybrid architecture
- **9 Governance and decision ownership**
- **10 Limitations**
- **11 Future work**
- **12 Conclusion**

---

## References (provisional)

*Access depth: [code] = source code reviewed; [doc] = documentation page read; [web] = vendor or
third-party web page read. To be converted to the final citation style.*

- aniket-work, *supply-chain-risk-intelligence*, GitHub. [code]
- Bhardwaj-Saurabh, *OmniSupply-AI Multi-Agent Supply Chain Intelligence Platform*, GitHub, GPL-3.0. [code]
- chinmaynadgir, *supplychain-ai-agent*, GitHub. [code]
- poshalanavateja, *Vendor-Bid-Evaluation-Ai*, GitHub. [code]
- mergisi, *awesome-openclaw-agents*, agent `vendor-evaluator`, GitHub, MIT. [code]
- Prewave, "How is the Prewave Score generated?", help.prewave.com. [doc]
- Prewave, product website, prewave.com. [web]
- Sphera, *Supply Chain Risk Management*, sphera.com. [web]
- Sphera, white paper on the German supply-chain due-diligence act, 2023. [web]
- LangGraph documentation: state graphs, interrupts, checkpointers. [doc]
- [TBD-LIT] Multi-criteria decision analysis in supplier selection and supplier risk.
- [TBD-LIT] Policy capturing / judgement analysis; direct vs. indirect weight elicitation.
- [TBD-LIT] Ridge / Tikhonov regularisation; shrinkage towards prior weights.
- [TBD-LIT] Supply-chain risk management surveys (disruption, resilience).
