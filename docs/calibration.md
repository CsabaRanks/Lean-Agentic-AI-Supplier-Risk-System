# Calibration against expert judgement

Most supplier risk scorecards use weights that were set once in a workshop and never validated.
The **Calibration Agent** closes that loop: it learns weights from how category managers actually
judge their suppliers, so the model gets closer to practice with every review cycle.

## Inputs

- Factor ratings of the suppliers in scope (computed by the Scoring Agent).
- A holistic **expert label** per supplier: `expert_risk_score` (0–100), e.g. collected during the
  annual supplier review (*“How risky is this supplier overall?”*). Not every supplier needs one.

Only suppliers with a label **and** complete factor data are used (missing-data re-weighting would
make the score non-linear in the weights). Excluded suppliers are listed in the report.

## Optimisation problem

For n suppliers with rating vectors x_i (1..5) and labels y_i (0..100), find effective factor
weights θ:

```
s_i(θ) = (x_i·θ − 1) / 4 · 100

minimise    1/n Σ ((s_i(θ) − y_i) / 100)²   +   λ · ‖θ − θ₀‖²
subject to  θ_f ≥ w_min  for all f
            Σ θ_f = 1
```

| Term | Meaning | Config |
|---|---|---|
| first term | mean squared error between model and expert | — |
| λ‖θ − θ₀‖² | ridge pull towards the prior (configured) weights; stabilises results with few labels | `regularization` (0.05) |
| θ_f ≥ w_min | every criterion keeps a minimum influence | `min_factor_weight` (0.02) |
| Σθ = 1 | weights stay a proper weighting | — |

This is a convex quadratic program; it is solved with SciPy `SLSQP` and an analytic gradient
(`tools/calibration.py`). The design goal is that calibration **adjusts** an expert-defined
methodology rather than replacing it with a black box.

## Acceptance and feedback loop

1. MSE before (prior weights) and after (calibrated weights) is computed on the same sample and
   reported in score points² (0–100 scale).
2. The new weights are **accepted** only if the MSE drops by at least `min_improvement`
   (default 5 %) and the solver converged.
3. If accepted and `auto_apply: true`, they become the active weights for the calibration scope and
   the supervisor routes back to the **Scoring Agent** for one re-score.
   With `auto_apply: false` they are only proposed, and the run is flagged for human review.
4. Old vs. new weights (factor and dimension level), MSE before/after, sample size and exclusions
   are written to `state["calibration_report"]` and to the audit trail.

## Scope: global vs. material group

- **MVP:** one weight set per run. Without `material_group` the scope is `global`.
- Run with `material_group="plastics"` and the agent calibrates only on that group and stores
  the result under that scope. The Scoring Agent always uses the most specific weight set
  available, so global and group-specific weights can coexist.

## Usage

```bash
# synthetic labelled portfolio (fictional, reproducible)
python examples/generate_calibration_dataset.py

supplier-risk --data data/calibration_portfolio.json --calibrate
supplier-risk --data data/calibration_portfolio.json --material-group plastics --calibrate
python examples/calibrate_weights.py
```

```python
state = SupplierRiskEvaluator.from_json("data/calibration_portfolio.json").run(calibrate=True)
report = state["calibration_report"]
print(report.mse_before, report.mse_after, report.new_weights)
```

Example output on the synthetic portfolio (labels generated from a hidden weighting plus noise):

```
Calibration [global] — 32 labelled supplier(s): accepted: MSE 37.8 -> 13.3 (64.9% better)
  factor                     old     new  delta
  business_impact          14.0%   18.1%  +4.1%
  sourcing_strategy         8.8%   14.6%  +5.8%
  esg_rating               12.0%    7.5%  -4.5%
  ...
```

## Practical guidance

- **Sample size.** With 10 factors, aim for clearly more than 10 labelled suppliers per scope;
  `min_labels` (default 8) is a hard floor, regularisation does the rest.
- **Label quality.** Labels should be given *before* seeing the model score to avoid anchoring.
- **Persist decisions.** Treat calibrated weights like a model release: review, version the YAML,
  re-run next cycle. Persisting approved weights automatically is on the roadmap.
- **Overfitting check.** Planned: k-fold cross-validated MSE in the report.

## Possible refinements

- cross-validation and confidence intervals for weights
- ordinal labels (low/medium/high/critical) with ordinal regression instead of 0–100 scores
- calibrating class thresholds in addition to weights
- hierarchical (partial pooling) calibration across material groups
