# Positioning: Lean Agentic AI for supplier risk evaluation

## In one sentence

**Lean Agentic AI** starts from the practice that already exists, typically a spreadsheet
scorecard. Using open agentic workflows as blueprints, it builds a **tailored, transparent and
low-cost** system on top of that practice, rather than replacing it with a black-box platform.

## The gap

| | Excel practice | Proprietary SaaS | Open-source agent repos |
|---|---|---|---|
| Strength | Cheap, familiar, transparent formulas | Data coverage, scale, workflows, compliance modules | Modern architecture patterns, free |
| Limitation | No audit trail or learning, error-prone, does not scale | Cost, limited control over the method, scores not recomputable, vendor lock-in | Demonstrators; scoring absent, hard-coded or LLM-judged; licences unclear |

Many mid-sized procurement organisations sit between the first two columns. They have outgrown
spreadsheets but cannot justify, or do not want, an enterprise platform for their *method*.
The open-source column shows how such systems *could* be built, but not a production-grade
method.

## Why it is a synthesis

The approach deliberately inherits from all three:

- **From Excel practice:** the domain logic procurement already uses. Named criteria, 1–5
  ratings, weighted dimensions such as a severity index, and a class-based action framework.
  Teams keep their method and their language, and it becomes explicit, versioned and testable.
- **From SaaS:** the expectations of a professional system. Workflows, review steps, audit
  trail, and integration of objective indicators. External signal feeds are on the roadmap and
  can come from open data or from an existing SaaS subscription.
- **From open-source agent repos:** the architecture. A LangGraph supervisor with specialised
  agents and typed shared state. It also takes the lesson the better repos teach: compute
  numbers in code, and use AI for language and orchestration.

"Lean" means three things: build only what adds value, reuse open blueprints, and keep the
procurement team in control of the method.

## Distinctive features

1. **Calibration against expert judgement.** The weights are not just configurable; they
   *learn* from category managers' holistic labels.
   - **How:** constrained, regularised least squares, minimising the MSE between score and
     label. Constraints: weights ≥ a minimum and summing to 1. The regularisation anchors on the
     defined method.
   - **What is reported:** MSE and class agreement before and after.
   - **Governance:** applied only after approval, or automatically if configured, and stored
     as a new weight version.
   - **Novelty:** none of the reviewed open-source repos and neither SaaS example documents
     this publicly.
2. **Configurable weights as a first-class object.** Default weights, material-group weights and
   calibrated weights are interchangeable `WeightSet`s. They are never hard-coded, and they are
   versioned with approver and timestamp.
3. **Human-in-the-loop as a real pause.** The workflow stops (LangGraph `interrupt()`) when data
   is insufficient or weights are proposed. Reviewers approve, override classes with a comment,
   or defer. Decisions survive re-scoring and are recorded.
4. **Deterministic scoring.** Every number comes from pure, tested functions. The same input
   always gives the same score, and every score can be recomputed by hand. AI is reserved for
   tasks where language matters (extraction, explanation; on the roadmap), never for the score
   itself.
5. **Material-group awareness.** Weights and calibration per commodity, not one size fits all.
6. **Governance by construction.** Escalation rules that an average cannot hide, a
   data-completeness check, an append-only audit trail, and bounded feedback loops.

## What it is not (yet)

These limits are stated to keep the positioning honest; see
[comparison-matrix.md](comparison-matrix.md):

- **Not a data provider.** It does not monitor news, disasters or Tier-N networks. SaaS
  platforms are strong precisely there.
- **Not a regulatory compliance product.** It supports documentation, but has no
  regulation-specific workflows.
- **Not production-hardened.** There are no roles or permissions, no persistent run store and
  no support organisation.
- **Not empirically validated.** Calibration has been demonstrated on synthetic labels only, and
  predictive validity is open.

The most realistic deployment is therefore **complementary**: external signals from open data
or an existing SCRM subscription feed a transparent, calibrated in-house model that the
procurement team owns.

## Core message for README and paper

> Spreadsheets are transparent but don't scale or learn. Platforms scale but don't let you own
> the method. Lean Agentic AI turns your existing scorecard into a transparent, auditable,
> self-calibrating multi-agent system that you own and can afford.
