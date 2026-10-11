<!-- GENERATED FILE: do not edit by hand.
     Source: research/comparison-matrix.yaml · Generator: scripts/generate_spider.py -->

# Comparison matrix: four approaches × success factors

Rates four approaches to supplier risk evaluation against the **15 success factors of model v0.2** (see [success-factors.md](success-factors.md)). Evidence as of 2026-10.

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

| # | Success factor (v0.2) | Excel | SaaS | Open repos | Lean Agentic | from v0.1 |
|---|---|:-:|:-:|:-:|:-:|:-:|
| 1 | Structured criteria & weights (objective + subjective) | 3 | 4 | 2 | 4 | 1, 5 |
| 2 | Traceability & reproducibility | 2 | 2.5 (P 3 · S 2) | 2 | 4 | 2, 8 |
| 3 | Methodological transparency | 4 | 2.5 (P 3 · S 2) | 3 | 5 | 13 |
| 4 | Expert calibration / ability to learn | 1 | 2 | 1 | 4 | 3 |
| 5 | Material-group-specific adaptation | 3 | 3 | 1 | 4 | 4 |
| 6 | Action framework | 2 | 4 | 2 | 3 | 6 |
| 7 | Human-in-the-loop & governance | 2 | 4 | 2 | 3 | 7 |
| 8 | External signals & data coverage | 1 | 5 | 2 | 1 | 11 |
| 9 | Regulatory evidence (due-diligence documentation) | 2 | 4.5 (P 5 · S 4) | 1 | 2 | new |
| 10 | Cost / accessibility | 5 | 2 | 5 | 4 | 9 |
| 11 | Time-to-value / ease of adoption | 4 | 3 | 2 | 3 | 14 |
| 12 | Customisability & data sovereignty | 4 | 2 | 3 | 5 | 10 |
| 13 | Scalability | 2 | 5 | 2 | 3 | 12 |
| 14 | Extensibility & automation potential | 1 | 2.5 (P 3 · S 2) | 4 | 4 | 15 |
| 15 | Operational maturity & support | 3 | 5 | 1 | 2 | new |

## Reading the profiles (without aggregation)

- **Excel:** cheap, transparent and quick to start; weak audit trail, no learning, no external signals, no extensibility.
- **Proprietary SaaS:** strongest on data coverage, scale, workflows, regulatory evidence and operational maturity; weaker on cost, self-determined customisation, recomputability by the user and, depending on the vendor, methodological transparency (Prewave publishes its score composition, Sphera does not).
- **Open repos:** strong architecture ideas and free, but demonstrators: scoring often absent, hard-coded or LLM-judged; unclear or copyleft licences; no tests.
- **Lean Agentic:** strongest where the method itself matters (transparency, reproducibility, calibration, material-group weights, customisability); deliberately weak today on external signals, regulatory evidence and operational maturity.
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
- **Lean Agentic** *(H)*: Pure scoring functions with automated tests; append-only audit trail per run; versioned weight files with approver; model version on every result. Not 5: runs are not persisted centrally yet.

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

### 5. Material-group-specific adaptation: Excel 3 · SaaS 3 · Open repos 1 · Lean Agentic 4

- **Excel** *(M)*: A separate sheet per group is easy, but logic diverges between copies.
- **SaaS** *(L)*: Commodity is part of Prewave's peer score and customised perspectives exist; segmentation per commodity was not documented publicly in detail for either vendor.
- **Open repos** *(H)*: None.
- **Lean Agentic** *(H)*: Material-group weights in the config, per-group calibration, most-specific weight resolution.

### 6. Action framework: Excel 2 · SaaS 4 · Open repos 2 · Lean Agentic 3

- **Excel** *(M)*: Actions are usually free text.
- **SaaS** *(M)*: Response playbooks, action planners and tracked closure are described on product pages.
- **Open repos** *(H)*: Narrative recommendations.
- **Lean Agentic** *(H)*: Rule-based actions per class and per elevated dimension, review cycles; no action tracking / closure.

### 7. Human-in-the-loop & governance: Excel 2 · SaaS 4 · Open repos 2 · Lean Agentic 3

- **Excel** *(M)*: Fully manual, but without structured review or approval points.
- **SaaS** *(M)*: Incident management, ownership and approval workflows are described.
- **Open repos** *(H)*: One repo has a human-review exit.
- **Lean Agentic** *(H)*: Graph interrupt with weight approval and class overrides, recorded and surviving re-scoring; no roles / permissions, in-memory pauses only.

### 8. External signals & data coverage: Excel 1 · SaaS 5 · Open repos 2 · Lean Agentic 1

- **Excel** *(H)*: Manual research only.
- **SaaS** *(M)*: Core strength: continuous multi-source monitoring, many languages, Tier-N mapping (feature verified; volumes are vendor claims).
- **Open repos** *(H)*: Internal databases, retrieval, mocks.
- **Lean Agentic** *(H)*: Not implemented; indicators are provided as data. On the roadmap.

### 9. Regulatory evidence (due-diligence documentation): Excel 2 · SaaS 4.5 · Open repos 1 · Lean Agentic 2

- **Excel** *(M)*: Documentation is possible but manual and unstructured.
- **SaaS** *(M)*: Prewave: dedicated modules for several due-diligence regulations (e.g. LkSG, CSDDD, EUDR). Sphera: LkSG bundle documented (2023); CSDDD-specific support not found publicly.
- **Open repos** *(H)*: Not addressed.
- **Lean Agentic** *(H)*: Audit trail and an ESG / compliance factor help, but no regulation-specific workflows or reports.

### 10. Cost / accessibility: Excel 5 · SaaS 2 · Open repos 5 · Lean Agentic 4

- **Excel** *(M)*: No additional licence; hidden labour cost.
- **SaaS** *(M)*: Pricing not public; quote-based enterprise subscriptions by supplier count and modules.
- **Open repos** *(H)*: Free (licence restrictions are rated under customisability).
- **Lean Agentic** *(M)*: MIT licence, runs locally; implementation and data integration still need internal effort.

### 11. Time-to-value / ease of adoption: Excel 4 · SaaS 3 · Open repos 2 · Lean Agentic 3

- **Excel** *(M)*: Immediate start.
- **SaaS** *(L)*: Fast onboarding is claimed by vendors, but enterprise procurement and integration cycles apply; no public implementation timelines.
- **Open repos** *(H)*: Demo-grade; one repo does not run as committed.
- **Lean Agentic** *(M)*: First results in minutes on sample data; mapping real data takes effort.

### 12. Customisability & data sovereignty: Excel 4 · SaaS 2 · Open repos 3 · Lean Agentic 5

- **Excel** *(M)*: Fully modifiable and kept in-house, but not maintainable as shared software.
- **SaaS** *(M)*: Configurable within the product; method and code are not; data hosted by the vendor.
- **Open repos** *(H)*: Code visible, but 2 repos have no licence and 1 is GPL, which restricts reuse.
- **Lean Agentic** *(H)*: MIT licence, config-driven, data and model stay in-house.

### 13. Scalability: Excel 2 · SaaS 5 · Open repos 2 · Lean Agentic 3

- **Excel** *(M)*: Degrades beyond a few hundred suppliers.
- **SaaS** *(M)*: Large enterprise deployments; vendor claims of more than a million suppliers assessed (Prewave).
- **Open repos** *(H)*: Demonstrators.
- **Lean Agentic** *(L)*: Deterministic batch scoring is cheap, but untested at scale; in-memory checkpoints; no automated feeds.

### 14. Extensibility & automation potential: Excel 1 · SaaS 2.5 · Open repos 4 · Lean Agentic 4

- **Excel** *(H)*: None beyond macros.
- **SaaS** *(M)*: Prewave: REST APIs, ERP write-back and connectors for AI agents; Sphera: workflow embedding stated, public API documentation not found. Both closed.
- **Open repos** *(H)*: Agent architectures are their main asset.
- **Lean Agentic** *(H)*: Supervisor graph with documented extension points (data sources, rating sources, agents); few agents yet.

### 15. Operational maturity & support: Excel 3 · SaaS 5 · Open repos 1 · Lean Agentic 2

- **Excel** *(M)*: Office tooling is supported by IT; no model-specific operations needed.
- **SaaS** *(M)*: Vendor support, hosting and service levels.
- **Open repos** *(H)*: No maintenance commitment.
- **Lean Agentic** *(H)*: Tests and CI exist, but no production deployment, security hardening or support organisation.

## Known weaknesses of this comparison

- **Author bias.** Factors and ratings come from the authors of the Lean Agentic approach. Mitigations: factors where SaaS is stronger are included (v0.2), Lean Agentic is rated as implemented, every rating carries rationale and confidence. Recommended: independent re-rating by 3-5 practitioners, reporting the spread.
- **The Excel profile is a stereotype.** Real spreadsheet practices vary widely.
- **SaaS rated on public information only.** Hands-on evaluation could move several ratings, especially traceability, material-group fit, action framework, human-in-the-loop and time-to-value.
- **No factor measures predictive validity**, i.e. whether a score anticipates real disruptions (see research/success-factors.md).
- **Date dependency.** Products change; all SaaS ratings refer to public information as of October 2026.
