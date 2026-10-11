# Notes & decisions

Lightweight decision log. Newest first.

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

- Persistent checkpointer (SQLite) so reviews can be decided in a later session?
- Additionally support ordinal expert labels (low/medium/high/critical)?
- Cross-validation in the calibration report — which k for small samples?
- Which public sources to use for the country-risk index by default?

## Ideas backlog

- External-risk agent (news, disasters, geopolitical alerts) feeding a time-varying factor.
- Trend detection: score deltas between review cycles.
- Streamlit dashboard: portfolio heatmap, weight comparison before/after calibration.
