import numpy as np
import pytest

from supplier_risk_agent.models import CalibrationSettings, SupplierProfile, WeightSet
from supplier_risk_agent.tools import aggregate, calibrate_weights, score_factors


def synthetic_portfolio(model, true_weights: WeightSet, n=40, seed=0, noise=0.0):
    rng = np.random.default_rng(seed)
    profiles = []
    for i in range(n):
        p = SupplierProfile(
            supplier_id=f"S{i}", name=f"S{i}",
            expert_ratings={k: int(rng.integers(1, 6)) for k in model.factor_keys()},
        )
        score = aggregate(score_factors(p, model, true_weights), model).overall_score
        p.expert_risk_score = float(np.clip(score + rng.normal(0, noise), 0, 100))
        profiles.append(p)
    return profiles


def test_recovers_hidden_weights_without_noise(model):
    keys = model.factor_keys()
    true = WeightSet(origin="manual", factor_weights={k: (i % 3 + 1) for i, k in enumerate(keys)})
    profiles = synthetic_portfolio(model, true)
    settings = CalibrationSettings(regularization=0.0, min_factor_weight=0.0)

    report, new = calibrate_weights(profiles, model, model.default_weights(), settings)

    assert report.accepted
    assert report.mse_after == pytest.approx(0.0, abs=1e-3)
    for k in keys:
        assert new.factor_weights[k] == pytest.approx(true.factor_weights[k], abs=1e-3)


def test_constraints_hold(model):
    keys = model.factor_keys()
    true = WeightSet(origin="manual", factor_weights={k: (10 if k == "business_impact" else 0.01) for k in keys})
    profiles = synthetic_portfolio(model, true, noise=3, seed=1)
    settings = CalibrationSettings(min_factor_weight=0.03, regularization=0.01)

    report, new = calibrate_weights(profiles, model, model.default_weights(), settings)

    assert sum(new.factor_weights.values()) == pytest.approx(1.0)
    assert min(new.factor_weights.values()) >= 0.03 - 1e-9
    assert report.mse_after < report.mse_before


def test_regularization_keeps_weights_close_to_prior(model):
    keys = model.factor_keys()
    true = WeightSet(origin="manual", factor_weights={k: (i + 1) for i, k in enumerate(keys)})
    profiles = synthetic_portfolio(model, true, noise=2)
    prior = model.default_weights()

    def distance(lam):
        _, new = calibrate_weights(profiles, model, prior, CalibrationSettings(regularization=lam))
        return sum(abs(new.factor_weights[k] - prior.factor_weights[k]) for k in keys)

    assert distance(5.0) < distance(0.0)


def test_skips_with_too_few_labels(model):
    profiles = synthetic_portfolio(model, model.default_weights(), n=3)
    report, new = calibrate_weights(profiles, model, model.default_weights(), CalibrationSettings(min_labels=8))
    assert new is None and not report.accepted
    assert "skipped" in report.message


def test_incomplete_suppliers_are_excluded(model):
    profiles = synthetic_portfolio(model, model.default_weights(), n=10)
    del profiles[0].expert_ratings["availability"]
    report, _ = calibrate_weights(profiles, model, model.default_weights(), CalibrationSettings(min_labels=5))
    assert "S0" in report.excluded and report.n_samples == 9


def test_rejected_when_no_meaningful_improvement(model):
    # labels generated with the prior itself -> nothing to improve
    profiles = synthetic_portfolio(model, model.default_weights(), n=20)
    report, _ = calibrate_weights(profiles, model, model.default_weights())
    assert not report.accepted


def test_cross_validated_acceptance_is_default_and_reports_cv(model):
    keys = model.factor_keys()
    true = WeightSet(origin="manual", factor_weights={k: (i % 3 + 1) for i, k in enumerate(keys)})
    report, _ = calibrate_weights(synthetic_portfolio(model, true, n=40, noise=3), model, model.default_weights())
    assert report.acceptance_basis == "cross_validated"
    assert report.cv_mse_after < report.cv_mse_before
    assert report.accepted


def test_cross_validated_rule_rejects_more_overfit_fits_than_in_sample_rule(model):
    """Few labels, no regularisation: the in-sample rule accepts fits that are worse out of sample."""
    from supplier_risk_agent.tools.calibration import build_design_matrix, mse
    from supplier_risk_agent.tools.synthetic import hidden_weights
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    test = portfolio(400, 12345, model, noise_sd=0.0, label_step=0)
    X_test, y_true, _, _ = build_design_matrix(test, model, model.default_weights())
    theta_default = np.array([model.default_weights().factor_weights[k] for k in model.factor_keys()])
    base = mse(X_test, y_true, theta_default, model)

    accepted = {"in_sample": 0, "cross_validated": 0}
    applied_error = {"in_sample": [], "cross_validated": []}
    for seed in range(12):
        profiles = portfolio(8, seed, model, hidden=hidden_weights())
        for rule in accepted:
            settings = CalibrationSettings(regularization=0.0, acceptance=rule, min_labels=8)
            report, new = calibrate_weights(profiles, model, model.default_weights(), settings)
            theta = np.array([new.factor_weights[k] for k in model.factor_keys()]) if report.accepted else theta_default
            accepted[rule] += report.accepted
            applied_error[rule].append(mse(X_test, y_true, theta, model))

    assert accepted["cross_validated"] < accepted["in_sample"]
    assert np.mean(applied_error["in_sample"]) > base  # the legacy rule makes things worse on average
    # the CV rule reduces the damage; with 8 labels and no regularisation it does not remove it
    assert np.mean(applied_error["cross_validated"]) < np.mean(applied_error["in_sample"])
