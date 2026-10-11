# Paper outline (working draft)

**Format target:** 15–20 pages, two-column style. The structure follows the companion paper
*"Benchmarking Sustainable Raw Material Alternatives Without a Sustainability Score"* (same author
series), whose formal conventions are reused:

- **Opening figure.** A profile figure opens the argument.
- **Success-dimension table.** Dimensions are listed with measurement indicators.
- **Demonstrator.** A synthetic, clearly labelled dataset with a deterministic pipeline.
- **Explicit statements of what is *not* established.**
- **Section order.** Limitations, then Future work, then Conclusion.

Status: outline with bullet points. Sources: `research/` files, linked per section.
**Draft text:** all sections 1–12 are drafted in [paper.md](paper.md) (working draft v0.5).

### Remaining gaps (draft v0.5)

- **[TBD-RESULT] Section 7:**
  - optional label-vs-score scatter
  - λ: done. Scaled with 1/n by default; CV selection tested and not adopted (Section 7.4).
  - E4 (misspecification, noise) is done: Section 7.7, Table 6, Figure 7
- Section 7.7: the level-offset diagnostic is implemented and evaluated on E4. Residual and
  knock-out diagnostics remain future work.
- **Figure 3 (workflow):** rendered as a static TikZ figure in the typeset version (`paper.tex`,
  Figure 2 there); `paper.md` keeps the Mermaid version.
- **Section 9, Table 9:** provider and data vintage are recorded per indicator; the source data
  itself is not versioned.
- **References:** verify wording against full texts (read at abstract level).
- **Typesetting:** done. `paper.tex` is a condensed version of `paper.md` in the two-column
  template of the companion paper, built to `paper.pdf` (18 pages). The appendix table is generated
  by `scripts/generate_spider.py`. Keep both files in step when the content changes.

---

## Title (working)

**Lean Agentic AI for Supplier Risk Evaluation**
*Turning spreadsheet scorecards into transparent, expert-calibrated multi-agent systems:
a benchmark of four approaches and an open-source demonstrator*

Alternative: *"Owning the Method: Expert-Calibrated, Deterministic Supplier Risk Scoring
with Open Agentic Workflows"*

## Abstract (~250 words, write last)

- **Problem.** Supplier risk evaluation sits between error-prone spreadsheets and costly,
  partly opaque platforms. Open-source agent projects show architectures, not methods.
- **Contribution 1.** A set of 15 success factors (model v0.4) and a profile comparison of four
  approaches: spreadsheet practice; proprietary SCRM platforms, with Prewave and Sphera as named
  examples; open-source agent repos; and the Lean Agentic approach (Fig. 1).
- **Contribution 2.** The Lean Agentic approach and an open-source demonstrator:
  - deterministic, configurable scoring
  - calibration against expert labels (constrained least squares)
  - human-in-the-loop via graph interrupts
  - versioned weights
- **Results.** On synthetic data with labels generated from a hidden weighting:
  - MSE 37.8 → 13.3
  - class agreement 84 % → 88 %
  - weights move towards the hidden weighting
- **Not established:** predictive validity, real-world labels, external signal feeds.
- All data is synthetic and labelled as such. No ranking of approaches is derived.

## 1 Introduction

- Why supplier risk evaluation matters now:
  - disruptions
  - due-diligence regulation (the generic notion; specific laws are named only as examples)
  - pressure on mid-sized firms
- **The practical gap.** The Excel ↔ SaaS spectrum (→ `research/lean-agentic-positioning.md`).
- **Hidden problem.** Weights are set once and never validated against the people who know the
  suppliers.
- **Research questions:**
  - **RQ1** Which success factors distinguish approaches to supplier risk evaluation?
  - **RQ2** How do existing approaches compare on them?
  - **RQ3** Can a lean, open, agentic design keep the strengths of spreadsheets (transparency,
    cost) and gain systematic learning and governance?
- **Contributions** (as in the abstract).
- **Figure 1:** radar chart, placed early as the paper's signature figure.
  - Generated from `research/comparison-matrix.yaml` by `scripts/generate_spider.py`.
  - Files: `docs/images/spider-diagram.png` / `.svg`.
  - Specification and caption draft: `research/spider-diagram-spec.md`.
- Structure of the paper.

## 2 Background and related work

- **2.1 Supplier risk assessment practice:**
  - scorecards and weighted multi-criteria assessment
  - severity × likelihood thinking
  - typical dimensions: severity, financial, supply chain, ESG/compliance
- **2.2 Commercial SCRM platforms.** **Prewave** and **Sphera Supply Chain Risk Management**
  (formerly riskmethods) as named examples, based on public information only (vendor sites, help
  centre, press releases, vendor-commissioned studies; → `research/saas-references.md`).
  - **Prewave** publishes its score composition: peer 30 %, alerts 40 %, assessments 20 %,
    external data 10 %. Event weights are configurable.
  - **Sphera:** no public scoring methodology was found.
  - **Finding:** heterogeneous methodological disclosure within "SaaS".
  - Neither vendor documents calibration against the customer's own expert labels.
  - Brief context on other vendors (Resilinc, EcoVadis, Everstream, Interos).
  - State the evidence date (October 2026) and "not a product test".
- **2.3 Open-source agentic supply-chain projects.** The five reviewed repos (→
  `research/github-references.md`, `research/comparison.md`). Main pattern: supervisor plus
  specialised agents. Main gap: scoring, tests, licences.
- **2.4 Calibration and expert judgement.** Weight elicitation versus learning weights from
  holistic judgements (regression on expert ratings, policy capturing); regularisation towards
  priors. *To do: literature search (MCDA weight elicitation, policy capturing / judgement
  analysis, constrained regression).*
- **2.5 LLMs and determinism.** Why numbers stay in code. Evidence from the reviewed repos: an
  LLM-judged score with arithmetic errors.

## 3 Success dimensions for supplier risk evaluation

- Fifteen success factors (**model v0.4**) as a **flat** list: definition and how to assess it
  (→ `research/success-factors.md`).
  1. Structured criteria & weights (objective + subjective)
  2. Traceability & reproducibility
  3. Methodological transparency
  4. Expert calibration / ability to learn
  5. Action framework
  6. Human-in-the-loop & governance
  7. External signals & data coverage
  8. Regulatory evidence
  9. Cost / total cost of ownership
  10. Time-to-value
  11. Customisability & data sovereignty
  12. Scalability
  13. Agentic orchestration & extensibility
  14. Operational maturity & support
  15. Integration of risk management and performance evaluation
- **Table 1:** factor, short definition, assessable by.
- **3.x How the model was derived.** From working model v0.1 to v0.4:
  - means reframed as outcomes (open source → customisability; multi-agent → extensibility)
  - overlaps merged
  - two platform-strength factors added against home-field bias (regulatory evidence,
    operational maturity)
  - v0.3 adds risk/performance integration and sharpens orchestration and total cost of ownership
  - v0.4 folds material-group adaptation into customisability, retaining 15 axes and all remaining scores
  - predictive validity deliberately not an axis, because nobody can rate it today

  This methodological self-correction is part of the contribution.
- Explicit statement: the factors are a working model. No weighting or aggregation is applied.

## 4 Benchmark: four approaches compared

- **Method.** Expert assessment on a 1–5 scale with rationale and confidence (H / M / L).
  - Evidence types: practitioner assumption, public information, code review, own implementation.
  - Prewave and Sphera are rated separately. The SaaS profile is their mean, and the spread is
    shown (factors 2, 3, 8, 13).
  - Lean Agentic is rated as implemented, not as planned.
- **Table 2:** comparison matrix, generated from `research/comparison-matrix.yaml`
  (→ `research/comparison-matrix.md`). Single source of truth for table and figure.
- **Figure 1 revisited.** Reading the profiles:
  - SaaS is strong on data, scale and workflows
  - LEAN is strong on method and governance, and weak on external signals
- **Key observation.** The profiles are complementary, which motivates a hybrid target
  architecture.
- Threats to validity of the benchmark:
  - author bias
  - stereotyped Excel profile
  - SaaS rated on public information only
  - date dependency

## 5 The Lean Agentic approach

- **Principles:**
  - start from existing practice
  - reuse open blueprints
  - deterministic numbers, AI for language
  - configuration over code
  - governance by construction
  - the team owns the method
- How the synthesis maps onto the three source traditions (Excel / SaaS / OSS).
- **Figure 2:** "From spreadsheet to agentic system", a migration path showing the same
  criteria and weights before and after.

## 6 Architecture of the demonstrator

- **6.1 Workflow graph.**
  - Supervisor with Data Collection, Scoring, Calibration, Recommendation and Human Review
  - bounded feedback loops
  - **Figure 3:** graph (→ `docs/architecture.md`)
- **6.2 Scoring model.**
  - 1–5 ratings, effective weights, min-max normalisation (R − 1)/4 · 100 and its rationale
  - escalation rules
  - missing-data re-weighting
  - **Table 3:** default template (→ `docs/scoring-model.md`)
- **6.3 Weights as first-class objects.**
  - `WeightSet`
  - material-group resolution
  - versioned weight store
- **6.4 Calibration.** Constrained, regularised least squares:
  - anchor vs. prior
  - acceptance rule
  - class agreement
  - **Equation box** (→ `docs/calibration.md`)
- **6.5 Human-in-the-loop.** Graph interrupt, review decisions, overrides that survive
  re-scoring, approval of weights.
- **6.6 Two views.** Performance evaluation and risk management on one criteria catalogue; one
  configuration per view; separate labels, weights and reviews.
- **6.7 Actions, data providers and history.** Factor-level action framework with owners; provider
  interface (political stability from WGI, tabular exports, API placeholders); timestamped
  snapshots; spreadsheet surface.
- **6.8 Engineering quality.** Tests, CI, determinism, allow-listed checkpoint types.

## 7 Demonstration on synthetic data

- **Dataset.**
  - six hand-crafted suppliers that exercise each scoring path
  - 36 synthetic suppliers whose labels were generated from a hidden weighting plus noise
  - everything clearly marked as synthetic
- **Results:**
  - portfolio classes
  - escalation examples
  - data-completeness flag
  - calibration (MSE, class agreement, weight shifts towards the hidden weighting)
  - re-calibration stability (no drift)
- **Figure 4:** weights before and after calibration, next to the hidden weighting.
- **Figure 5:** expert label vs. model score before and after.
- **What the demonstration shows and does not show.** It shows that the method recovers a known
  weighting. It does not show real-world fit or predictive power.

## 8 Comparison and discussion

- RQ1–RQ3 answered.
- Where Lean Agentic adds value and where it does not:
  - external signals
  - regulatory modules
  - operational maturity
- **Hybrid deployment.** SaaS or open data as signal providers, combined with an in-house
  transparent, calibrated model.
- **Organisational implications.** Category managers as model co-owners; calibration as part of
  the annual review cycle.

## 9 Governance and decision ownership

- Who approves weights.
- Who may override classes.
- Audit trail and versioning as accountability tools.

## 10 Limitations

- Synthetic data only; no field study.
- Calibration fits expert agreement, not predictive validity.
- Small-sample risks; no cross-validation yet.
- Benchmark ratings are author-assessed; public information only for SaaS.
- The demonstrator is not production-hardened: no roles or permissions, in-memory checkpoints, no
  external feeds.
- The factor model is a working hypothesis.

## 11 Future work

- Field pilot with real expert labels (one or two material groups).
- Cross-validated calibration; ordinal labels.
- Independent multi-rater benchmark.
- External signal agent (open data) and LLM explanation agent.
- Persistent checkpointer and role model.
- Predictive validation against observed disruptions.

## 12 Conclusion

- Three to five sentences, mirroring the core message in
  `research/lean-agentic-positioning.md`.

## Appendix (optional)

- A: Full comparison matrix with rationale.
- B: Calibration derivation and solver settings.
- C: Default risk-model YAML (excerpt).
- D: Reproducibility: commands to regenerate all results and figures.

---

## Figures and tables plan

| # | Content | Source | Status |
|---|---|---|---|
| Fig. 1 | Radar chart: 4 approaches × 15 factors (v0.4) | `docs/images/spider-diagram.png/.svg`, generated by `scripts/generate_spider.py` | **generated** |
| Fig. 2 | Spreadsheet → agentic migration path | new | idea |
| Fig. 3 | Workflow graph | `docs/architecture.md` (Mermaid) | exists as Mermaid |
| Fig. 4 | Weights: default / calibrated / hidden | `examples/calibrate_weights.py` | data available |
| Fig. 5 | Label vs. score scatter before/after | calibration run | data available |
| Tab. 1 | Success factors v0.4 | `research/success-factors.md` | ready |
| Tab. 2 | Comparison matrix | `research/comparison-matrix.yaml` → `.md` | ready (generated) |
| Tab. 3 | Default scoring template | `docs/scoring-model.md` | ready |

## Decisions taken

- Factor model **v0.2** adopted (October 2026).
- SaaS examples are **named** (Prewave, Sphera), with public sources and an evidence date.
- Profiles only: no weighting, total or ranking of approaches.

## Open decisions

- Language and venue: English preprint (e.g. arXiv or SSRN) plus a practitioner version?
- IP check: confirm that publishing a success-factor profile and benchmark is compatible with
  the author's other, non-public work.
