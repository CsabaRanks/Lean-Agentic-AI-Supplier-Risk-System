"""Calibration of factor weights against expert judgement.

Problem
-------
Category managers often have a well-founded *overall* feeling for how risky a
supplier is, even if they cannot state exact weights. Given ``n`` suppliers
with complete factor ratings ``X`` (n x F, values 1..5) and holistic expert
labels ``y`` (0..100), we look for effective factor weights ``theta`` so that the
model score reproduces the expert view as closely as possible:

    s_i(theta) = (x_i . theta - r_min) / (r_max - r_min) * 100

    minimise   1/n * sum_i ((s_i(theta) - y_i) / 100)^2  +  lambda * ||theta - theta_0||^2
    subject to theta_f >= w_min  for all f,     sum_f theta_f = 1

* The first term is the mean squared error (MSE) in normalised units.
* The ridge term pulls towards the *anchor* weights ``theta_0`` — always the
  configured defaults, never the result of a previous calibration. It keeps
  the solution stable with few labels and prevents single criteria from being
  switched off — calibration *adjusts* expert-defined weights, it does not
  replace the methodology. Anchoring on the defaults also means repeated
  calibration on the same labels converges to the same weights instead of
  drifting a little further every run.
* "MSE before" is measured with the currently active weights (``prior``),
  which may be defaults or previously approved weights.
* ``w_min`` guarantees every criterion keeps a minimum influence.

The problem is a convex quadratic program; we solve it with SciPy's SLSQP,
which handles the bound and equality constraints directly. Only suppliers with
an expert label *and* complete data are used, because missing-data
re-weighting would make the score non-linear in ``theta``.

Expert labels are expected as 0..100 scores; classes for the labels are
derived with the model's own thresholds (used for the class-agreement metric).
Reported MSE values are in score points squared (0..100 scale).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from ..models.config import CalibrationSettings, RiskModelConfig, WeightSet
from ..models.domain import CalibrationReport, SupplierProfile
from .scoring import classify, score_factors

ABS_TOL = 1e-3  # minimum absolute MSE reduction (score points^2) to count as improvement


def build_design_matrix(
    profiles: list[SupplierProfile], model: RiskModelConfig, prior: WeightSet
) -> tuple[np.ndarray, np.ndarray, list[str], dict[str, str]]:
    """Return (X, y, used_ids, excluded) for labelled suppliers with complete data."""
    keys = model.factor_keys()
    rows, labels, used = [], [], []
    excluded: dict[str, str] = {}
    for p in profiles:
        if p.expert_risk_score is None:
            continue
        ratings = {f.factor: f.rating for f in score_factors(p, model, prior)}
        missing = [k for k in keys if ratings[k] is None]
        if missing:
            excluded[p.supplier_id] = f"incomplete data ({', '.join(missing)})"
            continue
        rows.append([ratings[k] for k in keys])
        labels.append(p.expert_risk_score)
        used.append(p.supplier_id)
    return np.array(rows, dtype=float), np.array(labels, dtype=float), used, excluded


def _predict(X: np.ndarray, theta: np.ndarray, model: RiskModelConfig) -> np.ndarray:
    lo, hi = model.rating_scale.min, model.rating_scale.max
    return (X @ theta - lo) / (hi - lo) * 100


def mse(X: np.ndarray, y: np.ndarray, theta: np.ndarray, model: RiskModelConfig) -> float:
    return float(np.mean((_predict(X, theta, model) - y) ** 2))


def class_agreement(X: np.ndarray, y: np.ndarray, theta: np.ndarray, model: RiskModelConfig) -> float:
    """Share of suppliers whose model class equals the class derived from the expert label.

    Experts give 0..100 scores; their class follows from the same thresholds
    as the model's, so both are directly comparable.
    """
    pred = _predict(X, theta, model)
    hits = [classify(float(p), model) == classify(float(t), model) for p, t in zip(pred, y)]
    return float(np.mean(hits)) if hits else 0.0


def solve_weights(
    X: np.ndarray, y: np.ndarray, theta0: np.ndarray, model: RiskModelConfig, settings: CalibrationSettings
) -> tuple[np.ndarray, bool, str]:
    """Constrained, ridge-regularised least squares (see module docstring)."""
    n, k = X.shape
    lo, hi = model.rating_scale.min, model.rating_scale.max
    lam = settings.regularization

    def objective(theta: np.ndarray) -> float:
        e = (X @ theta - lo) / (hi - lo) - y / 100
        return float(e @ e / n + lam * np.sum((theta - theta0) ** 2))

    def gradient(theta: np.ndarray) -> np.ndarray:
        e = (X @ theta - lo) / (hi - lo) - y / 100
        return 2 * X.T @ e / (n * (hi - lo)) + 2 * lam * (theta - theta0)

    start = np.clip(theta0, settings.min_factor_weight, 1.0)
    start = start / start.sum()
    result = minimize(
        objective,
        start,
        jac=gradient,
        method="SLSQP",
        bounds=[(settings.min_factor_weight, 1.0)] * k,
        constraints=[{"type": "eq", "fun": lambda t: t.sum() - 1.0, "jac": lambda t: np.ones_like(t)}],
        options={"maxiter": 500, "ftol": 1e-12},
    )
    theta = np.clip(result.x, 0.0, None)
    return theta / theta.sum(), bool(result.success), str(result.message)


def calibrate_weights(
    profiles: list[SupplierProfile],
    model: RiskModelConfig,
    prior: WeightSet,
    settings: CalibrationSettings | None = None,
    scope: str | None = None,
    anchor: WeightSet | None = None,
) -> tuple[CalibrationReport, WeightSet | None]:
    """Calibrate against expert labels. Returns (report, new weights or None).

    ``prior``  — weights currently in use (baseline for "MSE before").
    ``anchor`` — regularisation target; defaults to ``prior``. Agents pass the
                 configured defaults here.
    """
    settings = settings or model.calibration
    anchor = anchor or prior
    scope = scope or prior.scope
    keys = model.factor_keys()
    X, y, used, excluded = build_design_matrix(profiles, model, prior)

    report = CalibrationReport(
        scope=scope,
        method=settings.method,
        n_samples=len(used),
        excluded=excluded,
        old_weights=prior.rounded(),
        old_dimension_weights={k: round(v, 4) for k, v in prior.dimension_weights(model).items()},
    )
    if len(used) < settings.min_labels:
        report.message = (
            f"skipped: {len(used)} usable expert label(s), at least {settings.min_labels} required"
        )
        return report, None

    theta_prior = np.array([prior.factor_weights.get(k, 0.0) for k in keys])
    theta_anchor = np.array([anchor.factor_weights.get(k, 0.0) for k in keys])
    theta, success, solver_msg = solve_weights(X, y, theta_anchor, model, settings)

    before, after = mse(X, y, theta_prior, model), mse(X, y, theta, model)
    # Below ABS_TOL the model already reproduces the labels (up to rounding);
    # a relative improvement of numerical noise must not count as a gain.
    improvement = (before - after) / before if before - after > ABS_TOL else 0.0
    new = WeightSet(
        scope=scope,
        origin="calibrated",
        factor_weights=dict(zip(keys, theta.tolist())),
        note=f"calibrated on {len(used)} expert labels",
    )

    report.new_weights = new.rounded()
    report.new_dimension_weights = {k: round(v, 4) for k, v in new.dimension_weights(model).items()}
    report.mse_before = round(before, 3)
    report.mse_after = round(after, 3)
    report.class_agreement_before = round(class_agreement(X, y, theta_prior, model), 4)
    report.class_agreement_after = round(class_agreement(X, y, theta, model), 4)
    report.improvement = round(improvement, 4)
    report.accepted = success and improvement >= settings.min_improvement
    if not success:
        report.message = f"solver did not converge: {solver_msg}"
    elif not report.accepted:
        report.message = (
            f"rejected: MSE improvement {improvement:.1%} below required {settings.min_improvement:.0%}"
        )
    else:
        report.message = f"accepted: MSE {before:.1f} -> {after:.1f} ({improvement:.1%} better)"
    return report, new
