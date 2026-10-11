# Success factors for supplier risk evaluation

**Status: model v0.2 adopted (October 2026).** The factors remain a working model, a reasoned
hypothesis for comparing approaches, not a validated or final framework. v0.2 came out of a critical
review of the initial working model v0.1, which is kept further down for traceability.
Ratings against v0.2 live in [comparison-matrix.yaml](comparison-matrix.yaml), the single source of
truth. The generated [comparison-matrix.md](comparison-matrix.md) and the radar chart are built from it.

**Conventions**

- The factors form a **flat list**. They are not grouped into a hierarchy, not weighted, and not
  aggregated into a total. Each approach is read factor by factor, as a profile. The same
  convention is used in the benchmark profile of the reference paper (no weighting, no total,
  no ranking).
- Assessment scale for comparisons: **1 (weak) … 5 (strong)**, always with a short rationale and a
  confidence mark (see [comparison-matrix.md](comparison-matrix.md)).
- "Measurable / assessable by" names **observable evidence**, so that a rating can be checked
  and argued by someone else.

---

## Current model v0.2: 15 factors

| # | Factor | Definition (short) | Assessable by | v0.1 |
|---|---|---|---|---|
| 1 | Structured criteria & weights (objective + subjective) | Explicit criteria, scales and weights combining measurable indicators and structured expert assessment | Criteria with definition and scale; explicit weights; both input types with provenance | 1 + 5 |
| 2 | Traceability & reproducibility | Every result can be reconstructed afterwards (inputs, weights, decisions, authors) and recomputed from documented inputs | Per-result record; change history; recomputation possible; automated tests; no LLM-generated numbers | 2 + 8 |
| 3 | Methodological transparency | How results are calculated is documented and checkable *before* use | Published formula, weights, data sources and rules | 13 |
| 4 | Expert calibration / ability to learn | Parameters are systematically fitted to expert judgement, with documented approval | Calibration procedure; fit metric; logged old/new parameters; approval step | 3 |
| 5 | Material-group-specific adaptation | Criteria, weights or thresholds can differ by commodity | Per-group weights; per-group calibration; effort per group | 4 |
| 6 | Action framework | Results map to defined actions, review cycles and owners | Actions per class and per driver; review cycles; tracking to closure | 6 |
| 7 | Human-in-the-loop & governance | Defined review and approval points; decisions recorded; roles | Review/approval steps; recorded overrides; approval of model changes; roles and permissions | 7 |
| 8 | External signals & data coverage | Use of current external data and breadth of supplier coverage | Sources and update frequency; languages and regions; Tier-N visibility | 11 |
| 9 | Regulatory evidence | Support for due-diligence documentation duties | Regulation-specific workflows and reports; evidence export | new |
| 10 | Cost / accessibility | Total cost of use and access barriers | Licence model and prices; implementation effort; minimum contract size | 9 |
| 11 | Time-to-value / ease of adoption | Time and effort until the first usable result | Time to first portfolio assessment; integrations and training needed | 14 |
| 12 | Customisability & data sovereignty | The organisation can change method and implementation itself and keeps control of data and model | Configurable without the vendor; code and licence; data location | 10 |
| 13 | Scalability | Works at acceptable effort as suppliers, users, groups or update frequency grow | Suppliers handled in practice; marginal effort; automated updates | 12 |
| 14 | Extensibility & automation potential | New capabilities can be added without rebuilding the core | Extension points; effort to add a source or agent; APIs | 15 |
| 15 | Operational maturity & support | Production readiness: support, hosting, security, service levels | Support organisation; SLAs; security and permission model; release process | new |

## Changes from v0.1 to v0.2, and why

| Change | v0.1 → v0.2 | Rationale |
|---|---|---|
| **Merged** | 1 *structured criteria* + 5 *objective + subjective* → **1** | Combining input types is a property of the criteria design. Kept apart, they double-count one strength. |
| **Merged** | 2 *audit trail* + 8 *determinism* → **2 traceability & reproducibility** | A record is only meaningful if the result can be recomputed. Determinism is the means; traceability is the outcome. |
| **Kept separate** | 13 *methodological transparency* → **3** | *Ex ante* understanding of the method is not the same as *ex post* traceability of one result. |
| **Reframed** | 10 *customisability / open source* → **12 customisability & data sovereignty** | Open source is a *means*. Rating means favours whoever uses them, and the comparison becomes circular. |
| **Reframed** | 15 *multi-agent orchestration* → **14 extensibility & automation potential** | Same reason: multi-agent is an architecture choice. The outcome is extensibility. |
| **Broadened** | 11 *external signals* → **8 external signals & data coverage** | Coverage of suppliers and tiers, not only signals, is the real differentiator of platforms. |
| **Added** | **9 regulatory evidence** | A factor where platforms are clearly stronger was missing. Without it, the profile flatters the proposed approach. |
| **Added** | **15 operational maturity & support** | Same reason. It is also a real adoption criterion. |
| **Not added** | *predictive validity* | Essential but not ratable today: no approach reports it publicly. Treated as an open question (paper: limitations / future work). |

Net effect: still 15 axes. The model is more balanced, and the radar now shows where platforms are
genuinely stronger (factors 8, 9, 13, 15). That makes the comparison more credible.

---

## Initial working model v0.1 (kept for traceability)

The definitions below are the basis that v0.2 was derived from.

### 1. Structured criteria & weights
*(Strukturierte Bewertungskriterien & Gewichtungen)*

- **Definition.** Risk is assessed against explicitly named criteria with defined scales and
  explicit weights. It is not a free-text judgement or an implicit gut feeling.
- **Why it matters.** It is the precondition for comparability across suppliers, buyers and years,
  and for every other factor below.
- **Assessable by:**
  - number of criteria with a written definition and scale
  - whether weights are explicit
  - whether the same criteria are applied to every supplier in scope

### 2. Traceability / audit trail
*(Nachvollziehbarkeit / Audit-Trail)*

- **Definition.** For each result it can be reconstructed *afterwards* which inputs, weights,
  rules and decisions led to it, and who changed what.
- **Why it matters.** Supplier risk decisions have consequences (delisting, dual sourcing,
  escalation) and increasingly face regulatory scrutiny, e.g. due-diligence documentation duties.
- **Assessable by:**
  - a per-result record of inputs, model version and weights
  - a change history with author and timestamp
  - whether the record can be exported

### 3. Expert calibration / ability to learn
*(Experten-Kalibrierung / Lernfähigkeit)*

- **Definition.** The model is systematically compared with expert judgement, and its parameters
  (e.g. weights) are adjusted in a documented way.
- **Why it matters.** Weights set once in a workshop are rarely validated. Calibration aligns the
  model with the people who know the suppliers and makes deviations visible.
- **Assessable by:**
  - whether a defined calibration procedure exists
  - whether its fit metric is reported (e.g. MSE, class agreement)
  - whether old and new parameters are logged
  - whether changes require approval

### 4. Material-group-specific adaptation
*(Warengruppen-spezifische Anpassung)*

- **Definition.** Criteria, weights or thresholds can differ by commodity or material group.
- **Why it matters.** Risk drivers differ between, for example, electronics (geopolitics,
  allocation) and packaging (price, availability). One weighting for everything distorts results.
- **Assessable by:**
  - whether weights or criteria can be set per group
  - whether group-specific calibration is possible
  - effort per additional group

### 5. Integration of objective and subjective factors
*(Integration objektiver + subjektiver Faktoren)*

- **Definition.** The approach combines measurable indicators (credit score, country index,
  sourcing status) with structured expert assessment (business impact, switching complexity)
  in one model.
- **Why it matters.** Purely objective data misses context known only internally. Purely
  subjective ratings are inconsistent.
- **Assessable by:**
  - whether both input types are present
  - whether each input's provenance is labelled
  - whether documented expert overrides are possible

### 6. Action framework / recommendations
*(Action Framework / Handlungsempfehlungen)*

- **Definition.** Results map to concrete, predefined actions, review cycles and owners.
- **Why it matters.** A score without a consequence does not reduce risk.
- **Assessable by:**
  - whether actions are defined per risk class
  - whether targeted actions exist per risk driver
  - whether review cycles are defined
  - whether actions are tracked to closure

### 7. Human-in-the-loop
*(Human-in-the-Loop)*

- **Definition.** Defined points where a human reviews, approves or corrects results or model
  changes, and these decisions are recorded.
- **Why it matters.** It keeps accountability with named people and catches data gaps and
  model errors.
- **Assessable by:**
  - whether there are explicit review or approval steps
  - whether overrides can be made and are recorded
  - whether model changes require approval
  - roles and permissions

### 8. Determinism & reproducibility
*(Determinismus & Reproduzierbarkeit)*

- **Definition.** The same inputs and model version always give the same result, and the user
  can recompute the result.
- **Why it matters.** Auditability, trust and testability. LLM-judged or opaque scores can
  change without any visible cause.
- **Assessable by:**
  - whether the result can be recomputed from documented inputs
  - automated tests
  - whether LLM-generated numbers are present

### 9. Cost / accessibility
*(Kosten / Zugänglichkeit)*

- **Definition.** The total cost of using the approach (licences, implementation, operation,
  internal effort) and the barriers to access.
- **Why it matters.** Mid-sized companies are often priced out of enterprise platforms but
  outgrow spreadsheets.
- **Assessable by:**
  - licence model and published prices
  - implementation effort in person-days
  - minimum contract size

### 10. Customisability / open source
*(Anpassbarkeit / Open Source)*

- **Definition.** The degree to which the organisation can change the method and its
  implementation itself, without depending on a vendor.
- **Why it matters.** Risk models must follow the company's category strategy, not the
  vendor's roadmap.
- **Assessable by:**
  - whether the source code is available and under which licence
  - what can be configured without the vendor
  - whether the organisation owns its data and model

### 11. Integration of external signals
*(Integration externer Signale)*

- **Definition.** Use of external, ideally current data: news, disasters, geopolitical events,
  financial warnings, trade data.
- **Why it matters.** Risk changes between annual reviews, so early warning needs external
  signals.
- **Assessable by:**
  - number and type of sources
  - update frequency
  - language and geographic coverage
  - sub-tier visibility

### 12. Scalability
*(Skalierbarkeit)*

- **Definition.** The approach still works, at acceptable effort and cost, as the number of
  suppliers, users, material groups or update frequency grows.
- **Why it matters.** Portfolios grow from dozens of key suppliers to thousands of active ones.
- **Assessable by:**
  - number of suppliers handled in practice
  - effort per additional supplier
  - automation of data updates

### 13. Methodological transparency
*(Transparenz der Methodik)*

- **Definition.** How the result is calculated is documented *before use* and can be checked by
  the user: criteria, scales, weights, aggregation, thresholds.
- **Why it matters.** People accept and challenge only what they can understand. Unlike
  factor 2 (traceability after the fact), this concerns the method itself.
- **Assessable by:**
  - whether the formula and weights are published
  - whether data sources and their weighting are disclosed
  - whether rules are documented

### 14. Time-to-value / ease of adoption
*(Time-to-Value / Einfachheit der Einführung)*

- **Definition.** The time and effort from the decision to adopt the approach to the first
  usable result.
- **Why it matters.** Long implementations consume budget and goodwill before any benefit is
  visible.
- **Assessable by:**
  - time to the first portfolio assessment
  - required integrations and training
  - setup steps

### 15. Multi-agent orchestration / extensibility
*(Multi-Agent-Orchestrierung / Erweiterbarkeit)*

- **Definition.** New capabilities (data sources, agents, workflows, AI functions) can be added
  without rebuilding the core.
- **Why it matters.** Requirements will grow: real-time signals, document extraction and
  explanations are already foreseeable.
- **Assessable by:**
  - documented extension points
  - effort to add a data source or an agent
  - APIs

---

## Critical review of the working model

### Observations

1. **Means vs. outcomes.** Two factors name a *means*, not an outcome:
   - *"Open Source"* (10) is a means to customisability and independence.
   - *"Multi-agent orchestration"* (15) is an architecture choice whose outcome is extensibility.

   Rating approaches on their means favours the approach that uses them, and the
   comparison becomes circular. **Proposal:** phrase factors as outcomes and treat open source and
   multi-agent as possible ways to reach them.

2. **Home-field bias.** The factors were derived from the strengths of the approach proposed
   here. Factors where established SaaS is clearly stronger are missing:
   - regulatory evidence (due-diligence documentation)
   - operational maturity: support, security, SLAs

   Without them, the radar would overstate the proposed approach. **Proposal:** add both.

3. **Overlaps.**
   - 1 and 5: combining objective and subjective inputs is a property of the criteria design.
   - 2 and 8: reproducibility is a precondition for a meaningful audit trail.

   **Proposal:** merge them. Keep 2 and 13 apart: *ex post* traceability is not the same as
   *ex ante* method transparency.

4. **Factor 11 is too narrow.** For SaaS, the real differentiator is *data coverage* (Tier-N
   mapping, global monitoring), not only "signals". **Proposal:** "External signals & data
   coverage".

5. **Validity is missing, and it matters most.** None of the factors asks whether the score
   actually *predicts* disruptions. Calibration against experts measures agreement with judgement,
   not predictive validity. Currently no approach reports this publicly. **Proposal:** do not make it
   a radar axis, since it cannot be rated today. Name it explicitly as an open question in the
   paper's limitations and future work.

6. **Readability.** 15–17 axes are at the limit of what a radar chart can show. The reference
   paper uses 10. The merges above keep the count at 15.

### Resulting model v0.2

| # | Factor (v0.2) | Origin in v0.1 | Change |
|---|---|---|---|
| 1 | Structured criteria & weights (objective + subjective) | 1 + 5 | merged |
| 2 | Traceability & reproducibility | 2 + 8 | merged |
| 3 | Methodological transparency | 13 | — |
| 4 | Expert calibration / ability to learn | 3 | — |
| 5 | Material-group-specific adaptation | 4 | — |
| 6 | Action framework | 6 | — |
| 7 | Human-in-the-loop & governance | 7 | sharpened (roles, approvals) |
| 8 | External signals & data coverage | 11 | broadened |
| 9 | Regulatory evidence (due-diligence documentation) | — | **new** |
| 10 | Cost | 9 | — |
| 11 | Time-to-value | 14 | — |
| 12 | Customisability & data sovereignty | 10 | reframed as an outcome |
| 13 | Scalability | 12 | — |
| 14 | Extensibility & automation potential | 15 | reframed as an outcome |
| 15 | Operational maturity & support | — | **new** |

v0.2 keeps 15 axes but is more balanced. In v0.2, the established SaaS profile is clearly
strongest on factors 8, 9, 13 and 15, and the proposed approach is weak there today. This
balance is what makes the comparison credible.

**Decision (October 2026): v0.2 adopted.** See "Current model v0.2" at the top.
