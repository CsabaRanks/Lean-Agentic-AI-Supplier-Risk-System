# Product benefits and benchmark dimensions

[Back to the product overview](../README.md#key-benefits)

The eight README benefits describe implemented capabilities or, for benchmarking, a development
process. They do not imply equal strength across the chart or superiority over SaaS.
The [comparison matrix](comparison-matrix.md) remains the scoring reference: **15 factors, model v0.5**,
with exact labels from [comparison-matrix.yaml](comparison-matrix.yaml). No axes or scores were changed
for this product overview. The chart uses shortened labels for space.

## Mapping to the existing 15 dimensions

Benefit numbers refer to the README: **B1** Risk and performance together; **B2** Trace every assessment;
**B3** Correct with confidence; **B4** Calibrate against expertise; **B5** Keep people in control;
**B6** Use AI where it helps; **B7** Adapt an open, modular system; **B8** Turn benchmarks into priorities.

| # | Exact dimension label | Benefit connection and supporting evidence | Boundary |
|---|---|---|---|
| 1 | Structured criteria & weights (objective + subjective) | B1, B2, B5, B7: shared criteria, configurable weights and rules; [scoring model](../docs/scoring-model.md). | Template criteria and weights need domain validation. |
| 2 | Explainability & traceability (per result) | B2, B3, B6: inputs, rules, weights, additive contributions, correction preview and cited optional explanations; [Explain & correct](../docs/explain-correct.md). | LLM citation checks do not establish semantic correctness. |
| 3 | Methodological transparency | B2, B5, B6, B7: documented formulas and editable configuration; deterministic results are separate from LLM prose; [architecture](../docs/architecture.md). | Inspectability does not establish predictive validity. |
| 4 | Expert calibration / ability to learn | B4: fitting against expert labels with held-out acceptance checks; [calibration](../docs/calibration.md). | Evidence uses synthetic labels; no automatic self-optimisation is claimed. |
| 5 | Action framework | B5: configured actions follow classes, dimensions and factors; [scoring model](../docs/scoring-model.md). | No action-closure tracking or supplier collaboration. |
| 6 | Human review & correction | B3, B5: reason, preview, confirmation, history, class overrides and weight approvals; [workflow](../docs/explain-correct.md). | Single-user workflow; typed names are not verified identities. |
| 7 | External signals & data coverage | B7 provides extension points for data sources; [data providers](../docs/data-providers.md). | File-based providers exist; live APIs and continuous monitoring do not. |
| 8 | Regulatory evidence (due-diligence documentation) | Context for B8: the [matrix rationale](comparison-matrix.md) identifies a documentation gap. | A correction history is not a regulation-specific due-diligence workflow. |
| 9 | Cost / total cost of ownership | Context for B7: [MIT licensing](../LICENSE) permits modification and reuse. | No measured total-cost saving; hosting, maintenance and optional API costs remain. |
| 10 | Time-to-value / ease of adoption | B1–B3 can be explored using the [local synthetic demo](../docs/demo-guide.md). | No measured onboarding time; Python setup and real-data mapping are still needed. |
| 11 | Customisability & data sovereignty | B7: editable criteria, rules and material-group weights; [architecture extension points](../docs/architecture.md#extension-points). | An explicitly requested LLM explanation sends its previewed payload to a provider. |
| 12 | Scalability | Context for B8: [operational limits](../docs/limitations.md) inform future validation needs. | No scale benchmark or production-capacity claim. |
| 13 | Agentic orchestration & extensibility | B7: specialised agents, typed shared state, bounded routing and extension interfaces; [architecture](../docs/architecture.md). | Rule-based supervisor; LLM planning and document extraction are not implemented. |
| 14 | Operational maturity & support | Context for B8: [limits](../docs/limitations.md) identify production-readiness gaps. | No production deployment, support organisation or multi-user security model. |
| 15 | Integration of risk management and performance evaluation | B1, B3: two views on shared inputs, displayed together and recomputed together after corrections; [demo guide](../docs/demo-guide.md). | Shared results do not establish real-world predictive or procurement value. |

B8 spans the comparison as a whole; **benchmarking is not a separate diagram axis**.
The 15-axis profile includes limitations as well as strengths. It is not a checklist of eight
benefits, and this mapping does not rescore the assessment. The current joint portfolio UI is
newer than the matrix's original factor-15 rationale; this documentation task leaves that dated
assessment and its score unchanged.

## Benchmarking as a development process

The repository records comparisons of commercial platforms and open-source projects alongside
its own implementation. This supports the following development workflow:

1. Record dated evidence, confidence and uncertainty for each factor.
2. Compare the documented capability with the intended procurement workflow and identify gaps.
3. Translate gaps into proposed priorities, then validate them before implementation.
4. Revisit the evidence when capabilities change; update ratings only with a documented rationale.

For example, limited external coverage points to provider integration and monitoring work;
limited operational maturity points to identity, persistence and deployment work; the absence of
field validation points to independent category-manager evaluation. These are **candidate priorities**,
not delivered features or a committed roadmap. The [reference-project comparison](comparison.md)
records which architecture ideas were adopted and why.

Regular benchmark updates are a **goal**; no established recurring review cadence is evidenced here.
Benchmarking does not automatically change software, scores or weights. Expert weight calibration
is a separate, bounded numerical procedure with held-out checks and human approval in the UI.

To maintain the benchmark, edit only `research/comparison-matrix.yaml`, record rationale and
confidence, then regenerate with `python scripts/generate_spider.py` (the `research` extra is required).
`python scripts/generate_spider.py --check` checks that the generated matrix matches its source.
Do not change scores to support product claims.

## Evidence and interpretation

- [Factor definitions and model history](success-factors.md).
- [Scores, rating anchors, rationale, confidence and known weaknesses](comparison-matrix.md).
- [Commercial-platform references](saas-references.md) and [reviewed repositories](github-references.md).
- [Working paper](../docs/paper/paper.pdf) and [source](../docs/paper/paper.md).

This is the author's qualitative assessment based on public information and code review, with
an evidence date of October 2026. The author also built the evaluated system and wrote the
Explain & correct anchors after implementing that workflow. There is no independent re-rating,
empirical measurement, total score or overall ranking. Missing public evidence means unknown,
not absent; “≥” indicates a documented minimum and “*” an uncertain retained value.
Commercial platforms offer coverage and operational capabilities this prototype lacks; a hybrid
setup can combine external signals with a procurement team's own transparent scoring method.
