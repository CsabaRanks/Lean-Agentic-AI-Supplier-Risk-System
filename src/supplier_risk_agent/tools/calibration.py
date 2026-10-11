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

Acceptance
----------
New weights are accepted only if the MSE drops by at least ``min_improvement``.
By default this is tested **out of sample**: the calibration is refitted on
k-1 folds and evaluated on the held-out fold, repeated with reshuffled folds,
and the pooled out-of-fold MSE is compared with that of the prior weights.
An in-sample test (legacy option) accepts almost any fit, including fits that
mostly reproduce label noise when only a few labels are available.

Level-offset diagnostic
-----------------------
Weights sum to one, so they cannot shift the level of the score. If experts are
systematically stricter or more lenient than the model's scale, a calibration
distorts the weights to imitate the offset (in experiment E4 it pushed the
rarely-high factors, insolvency and compliance, to the minimum weight). The
report therefore states the mean label-score difference and flags it when it
is both material (``level_bias_threshold`` points) and clear
(``level_bias_min_t`` standard errors). A flagged offset is a reason to review
the class thresholds, not to approve new weights.

Fit diagnostics
---------------
After fitting, three hints are added to the report (they inform the reviewer,
they do not block):

* high residual share: the error left after calibration is a large share of
  the label variance. Typical causes: non-additive judgement, inconsistent
  labels, very noisy labels.
* factors at the minimum weight: a factor was pushed from a clearly higher
  weight to the minimum. Either experts disregard it, or their judgement on it
  is not additive (level offset, knock-out logic).
* knock-out candidates: suppliers with a severe rating on a factor are judged
  clearly riskier than the calibrated model predicts, after removing the
  overall offset. This is the signature of a knock-out rule, which belongs in an
  escalation rule rather than in the weights.

Thresholds were derived on the constructed expert policies of experiment E4.

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
        label = model.label_of(p)
        if label is None:
            continue
        ratings = {f.factor: f.rating for f in score_factors(p, model, prior)}
        missing = [k for k in keys if ratings[k] is None]
        if missing:
            excluded[p.supplier_id] = f"incomplete data ({', '.join(missing)})"
            continue
        rows.append([ratings[k] for k in keys])
        labels.append(label)
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


def level_offset(X: np.ndarray, y: np.ndarray, theta: np.ndarray, model: RiskModelConfig) -> tuple[float, float]:
    """Mean of (label - score) and its t-statistic (0 if undefined)."""
    residual = y - _predict(X, theta, model)
    mean = float(residual.mean()) if len(residual) else 0.0
    if len(residual) < 2:
        return mean, 0.0
    se = float(residual.std(ddof=1) / np.sqrt(len(residual)))
    return mean, (float(mean / se) if se > 0 else 0.0)


def diagnose_fit(
    X: np.ndarray,
    y: np.ndarray,
    theta: np.ndarray,
    theta_prior: np.ndarray,
    model: RiskModelConfig,
    settings: CalibrationSettings,
    error_after: float,
) -> tuple[float | None, list[str], dict[str, float]]:
    """Residual share, factors pushed to the minimum weight, knock-out candidates (see module docstring)."""
    keys = model.factor_keys()
    variance = float(np.var(y))
    residual_share = error_after / variance if variance > 0 else None

    floor = settings.min_factor_weight
    at_minimum = [k for k, new, old in zip(keys, theta, theta_prior) if new <= floor + 0.005 and old >= 2 * floor]

    residual = y - _predict(X, theta, model)
    residual = residual - residual.mean()  # an overall offset is the level-offset check's job
    candidates: dict[str, float] = {}
    for j, key in enumerate(keys):
        severe = X[:, j] >= settings.knockout_severe_rating
        if severe.sum() < settings.knockout_min_suppliers:
            continue
        mean = float(residual[severe].mean())
        se = float(residual[severe].std(ddof=1) / np.sqrt(severe.sum()))
        if mean >= settings.knockout_residual_threshold and se > 0 and mean / se >= 2:
            candidates[key] = round(mean, 1)
    return residual_share, at_minimum, candidates


def relative_improvement(before: float, after: float) -> float:
    # Below ABS_TOL the prior already reproduces the labels (up to rounding);
    # a relative improvement of numerical noise must not count as a gain.
    return (before - after) / before if before - after > ABS_TOL else 0.0


def cross_validated_errors(
    X: np.ndarray,
    y: np.ndarray,
    theta_prior: np.ndarray,
    theta_anchor: np.ndarray,
    model: RiskModelConfig,
    settings: CalibrationSettings,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-fold squared error per supplier: (prior weights, weights refitted without that supplier).

    Each repeat reshuffles the folds (fixed seed, deterministic) and tests every
    supplier exactly once; errors are averaged over repeats, so each supplier
    contributes one value per array.
    """
    n = len(y)
    k = min(settings.cv_folds, n)
    rng = np.random.default_rng(seed)
    err_prior = np.zeros(n)
    err_refit = np.zeros(n)
    for _ in range(settings.cv_repeats):
        for test in np.array_split(rng.permutation(n), k):
            train = np.setdiff1d(np.arange(n), test)
            theta = solve_weights(X[train], y[train], theta_anchor, model, settings)[0]
            err_prior[test] += (_predict(X[test], theta_prior, model) - y[test]) ** 2
            err_refit[test] += (_predict(X[test], theta, model) - y[test]) ** 2
    return err_prior / settings.cv_repeats, err_refit / settings.cv_repeats


def cross_validated_mse(
    X: np.ndarray,
    y: np.ndarray,
    theta_prior: np.ndarray,
    theta_anchor: np.ndarray,
    model: RiskModelConfig,
    settings: CalibrationSettings,
    seed: int = 0,
) -> tuple[float, float]:
    """Pooled out-of-fold MSE of (prior weights, weights refitted on each training fold)."""
    err_prior, err_refit = cross_validated_errors(X, y, theta_prior, theta_anchor, model, settings, seed)
    return float(err_prior.mean()), float(err_refit.mean())


def improvement_z(err_prior: np.ndarray, err_refit: np.ndarray) -> float:
    """Mean per-supplier error reduction divided by its standard error.

    Out-of-fold errors are not independent (training sets overlap), so this
    standard error is optimistic: z is a screening statistic, not a test with
    nominal coverage. The acceptance threshold ``cv_min_z`` was therefore chosen
    empirically (see docs/calibration.md).
    """
    diff = err_prior - err_refit
    if len(diff) < 2:
        return 0.0
    se = float(diff.std(ddof=1) / np.sqrt(len(diff)))
    mean = float(diff.mean())
    if se == 0:
        return float("inf") if mean > 0 else 0.0
    return mean / se


def cross_validated_acceptance(
    X: np.ndarray,
    y: np.ndarray,
    theta_prior: np.ndarray,
    theta_anchor: np.ndarray,
    model: RiskModelConfig,
    settings: CalibrationSettings,
) -> tuple[bool, float, float, float]:
    """The cross-validated acceptance test. Returns (passes, cv_mse_before, cv_mse_after, z).

    Passes if the pooled out-of-fold error falls by at least ``min_improvement``
    AND the mean per-supplier reduction is at least ``cv_min_z`` standard errors.
    Shared by ``calibrate_weights`` and the validation scripts.
    """
    err_prior, err_refit = cross_validated_errors(X, y, theta_prior, theta_anchor, model, settings)
    before, after = float(err_prior.mean()), float(err_refit.mean())
    z = improvement_z(err_prior, err_refit)
    passes = relative_improvement(before, after) >= settings.min_improvement and z >= settings.cv_min_z
    return passes, before, after, z


def select_lambda(
    X: np.ndarray,
    y: np.ndarray,
    theta_anchor: np.ndarray,
    model: RiskModelConfig,
    settings: CalibrationSettings,
    seed: int = 1,
) -> tuple[float, dict[float, float]]:
    """Regularisation strength for this calibration. Returns (lambda, cross-validated MSE per candidate).

    With ``lambda_selection = cv``, every candidate in ``lambda_grid`` is
    cross-validated and the one-standard-error rule picks the *largest* lambda
    whose error is within one standard error of the best (Hastie, Tibshirani &
    Friedman, 2009, ch. 7): the most conservative fit that is not clearly worse.

    Selection uses a different fold seed than the acceptance test, which
    reduces but does not remove the optimism of selecting and testing on the
    same labels; the validation experiments measure the effect on independent data.
    """
    if settings.lambda_selection == "fixed":
        return settings.regularization, {}
    if settings.lambda_selection == "scaled":
        return settings.regularization * settings.lambda_reference_n / max(len(y), 1), {}
    n = len(y)
    errors: dict[float, np.ndarray] = {}
    for lam in sorted(set(settings.lambda_grid)):
        candidate = settings.model_copy(update={"regularization": lam})
        errors[lam] = cross_validated_errors(X, y, theta_anchor, theta_anchor, model, candidate, seed)[1]
    curve = {lam: float(err.mean()) for lam, err in errors.items()}
    best = min(curve, key=curve.get)
    se = float(errors[best].std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    if settings.lambda_rule == "min":
        return best, curve
    chosen = max(lam for lam, value in curve.items() if value <= curve[best] + se)
    return chosen, curve


def fit_weights(
    X: np.ndarray, y: np.ndarray, theta_anchor: np.ndarray, model: RiskModelConfig, settings: CalibrationSettings
) -> tuple[np.ndarray, bool, str, CalibrationSettings, dict[float, float]]:
    """Select lambda (if configured) and fit. Returns (theta, success, message, settings used, lambda curve)."""
    lam, curve = select_lambda(X, y, theta_anchor, model, settings)
    used = settings.model_copy(update={"regularization": lam})
    theta, success, message = solve_weights(X, y, theta_anchor, model, used)
    return theta, success, message, used, curve


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

    offset, offset_t = level_offset(X, y, theta_prior, model)
    report.level_offset = round(offset, 2)
    report.level_offset_t = round(offset_t, 2)
    report.level_bias_detected = bool(
        abs(offset) >= settings.level_bias_threshold and abs(offset_t) >= settings.level_bias_min_t
    )
    if report.level_bias_detected:
        direction = "higher (stricter)" if offset > 0 else "lower (more lenient)"
        report.warnings.append(
            f"level offset: expert labels are on average {abs(offset):.1f} points {direction} than model "
            f"scores (t = {offset_t:.1f}). Weights cannot express a level offset; calibrating them would "
            "distort them. Review the class thresholds instead of approving new weights."
        )

    theta, success, solver_msg, settings, curve = fit_weights(X, y, theta_anchor, model, settings)
    report.regularization_used = settings.regularization
    report.lambda_selection = settings.lambda_selection
    report.lambda_cv_curve = {f"{lam:g}": round(v, 3) for lam, v in curve.items()}

    before, after = mse(X, y, theta_prior, model), mse(X, y, theta, model)
    improvement = relative_improvement(before, after)
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
    report.acceptance_basis = settings.acceptance

    basis_improvement, basis_text = improvement, f"MSE {before:.1f} -> {after:.1f}"
    if settings.acceptance == "cross_validated":
        _, cv_before, cv_after, z = cross_validated_acceptance(X, y, theta_prior, theta_anchor, model, settings)
        basis_improvement = relative_improvement(cv_before, cv_after)
        report.cv_mse_before = round(cv_before, 3)
        report.cv_mse_after = round(cv_after, 3)
        report.cv_improvement = round(basis_improvement, 4)
        report.cv_improvement_z = round(z, 2) if np.isfinite(z) else 99.0
        basis_text = (f"cross-validated MSE {cv_before:.1f} -> {cv_after:.1f}, z = {z:.1f} "
                      f"(in-sample {before:.1f} -> {after:.1f})")

    error_after = report.cv_mse_after if report.cv_mse_after is not None else after
    share, at_minimum, candidates = diagnose_fit(X, y, theta, theta_prior, model, settings, error_after)
    report.residual_share = round(share, 3) if share is not None else None
    report.factors_at_minimum = at_minimum
    report.knockout_candidates = candidates
    if share is not None and share >= settings.residual_share_warning:
        report.warnings.append(
            f"high residual: {share:.0%} of the label variance remains unexplained after calibration. "
            "Expert judgement may be non-additive, inconsistent between experts, or very noisy; "
            "weights alone cannot represent it."
        )
    if at_minimum:
        report.warnings.append(
            f"pushed to the minimum weight: {', '.join(at_minimum)}. Either experts disregard these factors, "
            "or their judgement on them is not additive (level offset, knock-out logic). Check before approving."
        )
    for key, extra in candidates.items():
        report.warnings.append(
            f"knock-out candidate: suppliers with a severe {key.replace('_', ' ')} rating are judged "
            f"{extra:.1f} points riskier than the calibrated model predicts. Consider an escalation rule."
        )

    large_enough = basis_improvement >= settings.min_improvement
    certain_enough = settings.acceptance != "cross_validated" or z >= settings.cv_min_z
    report.accepted = success and large_enough and certain_enough
    if not success:
        report.message = f"solver did not converge: {solver_msg}"
    elif not large_enough:
        report.message = (
            f"rejected: {basis_text}, improvement {basis_improvement:.1%} below required "
            f"{settings.min_improvement:.0%}"
        )
    elif not certain_enough:
        report.message = (
            f"rejected: {basis_text}, improvement {basis_improvement:.1%} is not clear enough "
            f"(z below required {settings.cv_min_z:g})"
        )
    else:
        report.message = f"accepted: {basis_text}, {basis_improvement:.1%} better"
    return report, new
