# Notes & decisions

Lightweight decision log. Newest first.

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

- Persisting approved calibrated weights: write back to YAML, or a versioned weights store?
- Ordinal expert labels (low/medium/high/critical) instead of 0–100 scores?
- Cross-validation in the calibration report — which k for small samples?
- Which public sources to use for the country-risk index by default?

## Ideas backlog

- External-risk agent (news, disasters, geopolitical alerts) feeding a time-varying factor.
- Trend detection: score deltas between review cycles.
- Streamlit dashboard: portfolio heatmap, weight comparison before/after calibration.
