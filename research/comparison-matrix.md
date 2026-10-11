<!-- GENERATED FILE: do not edit by hand.
     Source: research/comparison-matrix.yaml · Generator: scripts/generate_spider.py -->

# Comparison matrix: four approaches × success factors

Rates four approaches to supplier risk evaluation against the **15 success factors of model v0.4** (see [success-factors.md](success-factors.md)). Evidence as of 2026-10.

> **Read this as a reasoned, illustrative assessment, not a measurement.** Every rating has a
> rationale and a confidence mark. No weights are applied, no total is formed and no ranking is
> derived: the approaches are compared as **profiles**, factor by factor. The radar chart
> `docs/images/spider-diagram.png` is generated from the same source.

## The four approaches

| Approach | What exactly is rated | Evidence base |
|---|---|---|
| **Excel / manual process** | A typical spreadsheet scorecard maintained by procurement (criteria sheet, weights, annual update). | Practitioner experience; assumption-based. |
| **Proprietary SaaS (Prewave, Sphera)** | Prewave and Sphera Supply Chain Risk Management as examples of commercial SCRM platforms. | Public information only (vendor websites, help centre, press releases, vendor-commissioned studies), see research/saas-references.md. No hands-on test. |
| **Open-source GitHub repos** | The five reviewed open-source blueprints. | Source code review, see research/github-references.md and research/comparison.md. |
| **Lean Agentic (this repo)** | This repository as implemented (v0.1.0, October 2026), not the roadmap. | Code, tests and documentation in this repository. |

**Scale:** 1 = weak / absent · 2 = rudimentary · 3 = adequate · 4 = strong · 5 = very strong. For proprietary SaaS, values are rated per example; where Prewave (P) and Sphera (S) differ, the cell shows the mean and both values.

**Confidence:** **H** = verified from code / primary documentation · **M** = plausible, partly documented · **L** = assumption, little public evidence.

## Matrix

| # | Success factor (v0.4) | Excel | SaaS | Open repos | Lean Agentic | from v0.1 |
|---|---|:-:|:-:|:-:|:-:|:-:|
| 1 | Structured criteria & weights (objective + subjective) | 3 | 4 | 2 | 4 | 1, 5 |
| 2 | Traceability & reproducibility | 2 | 2.5 (P 3 · S 2) | 2 | 4 | 2, 8 |
| 3 | Methodological transparency | 4 | 2.5 (P 3 · S 2) | 3 | 5 | 13 |
| 4 | Expert calibration / ability to learn | 1 | 2 | 1 | 4 | 3 |
| 5 | Action framework | 2 | 4 | 2 | 3.5 | 6 |
| 6 | Human-in-the-loop & governance | 2 | 4 | 2 | 3.5 | 7 |
| 7 | External signals & data coverage | 1 | 5 | 2 | 2.5 | 11 |
| 8 | Regulatory evidence (due-diligence documentation) | 2 | 4.5 (P 5 · S 4) | 1 | 2 | new |
| 9 | Cost / total cost of ownership | 3 | 2 | 4 | 4 | 9 |
| 10 | Time-to-value / ease of adoption | 3 | 3 | 2 | 4 | 14 |
| 11 | Customisability & data sovereignty | 4 | 2 | 3 | 5 | 4, 10 |
| 12 | Scalability | 2 | 5 | 2 | 3 | 12 |
| 13 | Agentic orchestration & extensibility | 1 | 2.5 (P 3 · S 2) | 4 | 4 | 15 |
| 14 | Operational maturity & support | 3 | 5 | 1 | 2 | new |
| 15 | Integration of risk management and performance evaluation | 2 | 2 | 2 | 4 | new |

## Reading the profiles (without aggregation)

- **Excel:** no licence, transparent and quick to start for a simple sheet; recurring manual effort, weak audit trail, no learning, no external signals, no extensibility. Risk and performance usually live in separate files.
- **Proprietary SaaS:** strongest on data coverage, scale, workflows, regulatory evidence and operational maturity; weaker on cost, self-determined customisation, recomputability by the user and, depending on the vendor, methodological transparency (Prewave publishes its score composition, Sphera does not). Both are risk platforms: supplier performance evaluation typically stays outside, often in Excel.
- **Open repos:** strong architecture ideas and free, but demonstrators: scoring often absent, hard-coded or LLM-judged; unclear or copyleft licences; no tests.
- **Lean Agentic:** strongest where the method itself matters (transparency, reproducibility, calibration, customisability including material-group weights), on agentic orchestration and on integrating risk management with performance evaluation; close to the platforms on actions and human review; partial on external signals (provider interface for open data and exports, live APIs still placeholders); weak today on regulatory evidence and operational maturity.
- The profiles are **complementary rather than ranked**. A realistic target architecture combines them: a SaaS subscription or open data as signal source feeding a transparent, calibrated in-house model.

## Rationale per factor

### 1. Structured criteria & weights (objective + subjective): Excel 3 · SaaS 4 · Open repos 2 · Lean Agentic 4

- **Excel** *(M)*: Scorecards with criteria and weights are common and can mix data and judgement, but definitions, scales and provenance are often informal and drift between versions.
- **SaaS** *(M)*: Prewave publishes a structured score combining peer, alert, assessment and external data; Sphera describes indicator scorecards combining monitoring and questionnaires.
- **Open repos** *(H)*: Only 2 of 5 repos have deterministic weighted scoring, both with hard-coded weights; mostly one input type.
- **Lean Agentic** *(H)*: Multi-dimensional criteria, 1-5 scales, weights in a validated config; expert ratings and indicator-derived ratings with provenance and documented overrides. Not 5: template is illustrative, not empirically validated; objective indicators are entered, not fetched.

### 2. Traceability & reproducibility: Excel 2 · SaaS 2.5 · Open repos 2 · Lean Agentic 4

- **Excel** *(M)*: Formulas are deterministic, but there is no per-result record and copy-paste / versioning errors are common.
- **SaaS** *(L)*: Audit-ready due-diligence documentation is claimed (Prewave); audit-trail controls not found publicly (Sphera). Continuously updated, partly NLP-based scores cannot be recomputed by the customer from documented inputs, a design consequence of real-time monitoring rather than a flaw.
- **Open repos** *(H)*: History lists / tracing in some repos; 2 of 5 repos use LLM-judged scores.
- **Lean Agentic** *(H)*: Pure scoring functions with automated tests; append-only audit trail per run; versioned weight files with approver; model version on every result; timestamped assessment snapshots per view (local JSONL files). Not 5: no central, access-controlled persistence of runs yet.

### 3. Methodological transparency: Excel 4 · SaaS 2.5 · Open repos 3 · Lean Agentic 5

- **Excel** *(M)*: Formulas are visible to everyone, provided they are documented.
- **SaaS** *(M)*: Prewave publishes its score composition and component weights, but not source weighting / NLP classification; for Sphera no scoring methodology was found publicly.
- **Open repos** *(H)*: Code is visible, but LLM-judged parts are opaque.
- **Lean Agentic** *(H)*: Formulas, weights, rules and calibration maths are documented and tested.

### 4. Expert calibration / ability to learn: Excel 1 · SaaS 2 · Open repos 1 · Lean Agentic 4

- **Excel** *(M)*: Weights are adjusted by discussion, if at all.
- **SaaS** *(L)*: Weights are adjustable by configuration (Prewave, partly via customer success); a documented fit against the customer's own expert labels was not found publicly for either vendor.
- **Open repos** *(H)*: None of the 5 repos.
- **Lean Agentic** *(H)*: Constrained least-squares calibration against expert labels with MSE and class agreement, approval step and versioning. Not 5: validated on synthetic labels only, no cross-validation yet.

### 5. Action framework: Excel 2 · SaaS 4 · Open repos 2 · Lean Agentic 3.5

- **Excel** *(M)*: Actions are usually free text.
- **SaaS** *(M)*: Response playbooks, action planners and tracked closure are described on product pages.
- **Open repos** *(H)*: Narrative recommendations.
- **Lean Agentic** *(H)*: Configurable action framework on three levels (risk class, elevated dimension, factor level), each action with owner and review cycle; filterable, exportable action plan per material group. Below the platforms: no tracking of actions to closure, no supplier collaboration.

### 6. Human-in-the-loop & governance: Excel 2 · SaaS 4 · Open repos 2 · Lean Agentic 3.5

- **Excel** *(M)*: Fully manual, but without structured review or approval points.
- **SaaS** *(M)*: Incident management, ownership and approval workflows are described.
- **Open repos** *(H)*: One repo has a human-review exit.
- **Lean Agentic** *(H)*: Graph-based review pause (interrupt / resume) for weight approval and class overrides with comment, recorded with the reviewer, surviving re-scoring and snapshotted to the history; review also in the UI. Below the platforms: no roles / permissions, in-memory pauses only.

### 7. External signals & data coverage: Excel 1 · SaaS 5 · Open repos 2 · Lean Agentic 2.5

- **Excel** *(H)*: Manual research only.
- **SaaS** *(M)*: Core strength: continuous multi-source monitoring, many languages, Tier-N mapping (feature verified; volumes are vendor claims).
- **Open repos** *(H)*: Internal databases, retrieval, mocks.
- **Lean Agentic** *(M)*: A provider interface is in place and reads open data and system exports (e.g. a downloaded governance indicator table, ERP or ESG exports), filling indicators with recorded origin and vintage. Live APIs are still placeholders and there is no continuous monitoring, so coverage is about half of a monitoring platform. The architecture allows further providers, and the agentic design leaves long-term upside in signal processing (e.g. an external-signal agent); that potential is not rated.

### 8. Regulatory evidence (due-diligence documentation): Excel 2 · SaaS 4.5 · Open repos 1 · Lean Agentic 2

- **Excel** *(M)*: Documentation is possible but manual and unstructured.
- **SaaS** *(M)*: Prewave: dedicated modules for several due-diligence regulations (e.g. LkSG, CSDDD, EUDR). Sphera: LkSG bundle documented (2023); CSDDD-specific support not found publicly.
- **Open repos** *(H)*: Not addressed.
- **Lean Agentic** *(H)*: Audit trail and an ESG / compliance factor help, but no regulation-specific workflows or reports.

### 9. Cost / total cost of ownership: Excel 3 · SaaS 2 · Open repos 4 · Lean Agentic 4

- **Excel** *(M)*: No additional licence, but high recurring manual effort: collecting data, consolidating sheets per category, keeping versions and weights consistent, rebuilding reports each cycle.
- **SaaS** *(M)*: Pricing not public; quote-based enterprise subscriptions by supplier count and modules.
- **Open repos** *(M)*: Free licence (restrictions rated under customisability), but demo-grade: turning them into a usable scoring system needs substantial development.
- **Lean Agentic** *(M)*: MIT licence, runs locally; scoring, actions and reports are automated once data is mapped. Not 5: ownership, data integration and maintenance still need internal effort.

### 10. Time-to-value / ease of adoption: Excel 3 · SaaS 3 · Open repos 2 · Lean Agentic 4

- **Excel** *(M)*: A simple sheet starts immediately; a governed scorecard with definitions, weights and consolidation across categories takes weeks to build by hand.
- **SaaS** *(L)*: Fast onboarding is claimed by vendors, but enterprise procurement and integration cycles apply; no public implementation timelines.
- **Open repos** *(H)*: Demo-grade; one repo does not run as committed.
- **Lean Agentic** *(M)*: Ready template, sample data, empty CSV template and spreadsheet UI: a first portfolio assessment in hours. Not 5: Python installation and mapping real data take effort.

### 11. Customisability & data sovereignty: Excel 4 · SaaS 2 · Open repos 3 · Lean Agentic 5

- **Excel** *(M)*: Fully modifiable and kept in-house; separate sheets allow material-group-specific criteria and weights. Not 5: logic diverges between copies and is not maintainable as shared software.
- **SaaS** *(M)*: Configurable within the product; method and code are not independently changeable; data hosted by the vendor. Prewave includes commodity in its peer score and offers customised perspectives, but detailed per-commodity configuration is not publicly documented for either vendor. Such product configuration does not establish customer control of the method, implementation or data.
- **Open repos** *(H)*: Code visible, but 2 repos have no licence and 1 is GPL, which restricts reuse. None provides material-group adaptation out of the box; adding it requires code changes. Visible code alone does not give unrestricted, ready-to-use control of the method.
- **Lean Agentic** *(H)*: MIT licence, config-driven, data and model stay in-house. Material-group weights and most-specific weight resolution provide a concrete, implemented case of customer-controlled adaptation; per-group fitting is assessed under expert calibration. No vendor is needed to modify the method or implementation.

### 12. Scalability: Excel 2 · SaaS 5 · Open repos 2 · Lean Agentic 3

- **Excel** *(M)*: Degrades beyond a few hundred suppliers.
- **SaaS** *(M)*: Large enterprise deployments; vendor claims of more than a million suppliers assessed (Prewave).
- **Open repos** *(H)*: Demonstrators.
- **Lean Agentic** *(L)*: Deterministic batch scoring is cheap, but untested at scale; in-memory checkpoints; no automated feeds.

### 13. Agentic orchestration & extensibility: Excel 1 · SaaS 2.5 · Open repos 4 · Lean Agentic 4

- **Excel** *(H)*: None beyond macros.
- **SaaS** *(M)*: Prewave: REST APIs, ERP write-back and connectors for external AI agents; Sphera: "agentic AI" capabilities marketed, workflow embedding stated, public API documentation not found. Neither documents a customer-inspectable multi-agent workflow (specialised agents over a shared state, calibration agent, graph-based review pause). Both closed.
- **Open repos** *(H)*: Agent architectures are their main asset: specialised agents over a typed shared state, graph or supervisor orchestration; review pauses rare, no calibration agent.
- **Lean Agentic** *(H)*: LangGraph supervisor over a typed shared state with specialised agents (data collection, scoring, calibration, recommendation, human review as graph interrupt); documented extension points (data sources, data providers, rating sources, views, agents). Not 5: rule-based supervisor, no LLM agents yet.

### 14. Operational maturity & support: Excel 3 · SaaS 5 · Open repos 1 · Lean Agentic 2

- **Excel** *(M)*: Office tooling is supported by IT; no model-specific operations needed.
- **SaaS** *(M)*: Vendor support, hosting and service levels.
- **Open repos** *(H)*: No maintenance commitment.
- **Lean Agentic** *(H)*: Tests and CI exist, but no production deployment, security hardening or support organisation.

### 15. Integration of risk management and performance evaluation: Excel 2 · SaaS 2 · Open repos 2 · Lean Agentic 4

- **Excel** *(M)*: Both are often kept in spreadsheets, but as separate files with their own criteria, scales and update cycles; no shared criteria or data base. Common practice: risk on a platform, evaluation in Excel.
- **SaaS** *(L)*: Risk platforms; supplier performance evaluation (delivery, quality, price, responsiveness with its own grades) is not documented as part of the platform in public sources. Performance data can enter as input.
- **Open repos** *(H)*: Single repos cover either risk assessment or vendor / bid evaluation; none combines both.
- **Lean Agentic** *(H)*: Two views on one shared criteria catalogue and one data sheet: performance (A/B/C) and risk (low-critical), each with its own weights, classes, actions, labels and review. Not 5: no joint portfolio reading (performance x risk) yet; performance view not calibrated in the template.

## Known weaknesses of this comparison

- **Author bias.** Factors and ratings come from the authors of the Lean Agentic approach. Mitigations: factors where SaaS is stronger are included (v0.2), Lean Agentic is rated as implemented, every rating carries rationale and confidence. v0.3 adds a factor (risk and performance integration) on which the proposed approach is strong, and re-rates five factors after practitioner feedback; both are disclosed. v0.4 folds material-group adaptation into customisability to remove a subset overlap; retained ratings and confidence are unchanged. Recommended: independent re-rating by 3-5 practitioners, reporting the spread.
- **The Excel profile is a stereotype.** Real spreadsheet practices vary widely.
- **SaaS rated on public information only.** Hands-on evaluation could move several ratings, especially traceability, customisability (including material-group fit), action framework, human-in-the-loop and time-to-value.
- **No factor measures predictive validity**, i.e. whether a score anticipates real disruptions (see research/success-factors.md).
- **Date dependency.** Products change; all SaaS ratings refer to public information as of October 2026.
