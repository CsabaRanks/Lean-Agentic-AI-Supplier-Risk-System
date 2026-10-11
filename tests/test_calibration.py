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


def _shifted(profiles, points):
    for p in profiles:
        p.expert_risk_score = float(min(100, max(0, p.expert_risk_score + points)))
    return profiles


def test_level_offset_is_detected_and_warned(model):
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    report, _ = calibrate_weights(_shifted(portfolio(32, 1, model), 10), model, model.default_weights())
    assert report.level_bias_detected
    assert report.level_offset > 5 and report.level_offset_t > 2
    assert any("level offset" in w and "stricter" in w for w in report.warnings)

    lenient, _ = calibrate_weights(_shifted(portfolio(32, 1, model), -12), model, model.default_weights())
    assert lenient.level_bias_detected and lenient.level_offset < 0
    assert any("lenient" in w for w in lenient.warnings)


def test_no_level_flag_without_offset(model):
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    flagged = sum(
        calibrate_weights(portfolio(32, seed, model), model, model.default_weights())[0].level_bias_detected
        for seed in range(10)
    )
    assert flagged == 0


def test_improvement_z():
    from supplier_risk_agent.tools.calibration import improvement_z

    prior = np.array([10.0, 12.0, 9.0, 11.0])
    assert improvement_z(prior, prior - np.array([1.0, 3.0, 2.0, 2.0])) == pytest.approx(2.0 / (0.8165 / 2), rel=1e-3)
    assert improvement_z(prior, prior) == 0.0
    assert improvement_z(prior, prior - 1.0) == float("inf")  # identical improvement for every supplier


def test_uncertainty_threshold_only_ever_rejects_more(model):
    """cv_min_z adds a condition: whatever it accepts, the plain 5 % rule accepts too, and it rejects noisy fits."""
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    plain = CalibrationSettings(cv_min_z=0.0)
    strict = CalibrationSettings(cv_min_z=2.0)
    decisions = []
    for seed in range(15):
        profiles = portfolio(12, seed, model, noise_sd=12.0)
        a = calibrate_weights(profiles, model, model.default_weights(), plain)[0]
        b = calibrate_weights(profiles, model, model.default_weights(), strict)[0]
        assert b.cv_improvement_z == a.cv_improvement_z
        decisions.append((a.accepted, b.accepted, b.message))
    assert all(plain_ok or not strict_ok for plain_ok, strict_ok, _ in decisions)
    assert sum(s for _, s, _ in decisions) < sum(p for p, _, _ in decisions)
    assert any("not clear enough" in msg for _, _, msg in decisions)


def test_scaled_lambda_fades_with_number_of_labels(model):
    from supplier_risk_agent.tools.calibration import build_design_matrix, select_lambda
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    settings = CalibrationSettings()  # default: scaled, 0.05 at 32 labels
    assert settings.lambda_selection == "scaled"
    for n, expected in [(16, 0.1), (32, 0.05), (64, 0.025)]:
        X, y, _, _ = build_design_matrix(portfolio(n, 0, model), model, model.default_weights())
        assert select_lambda(X, y, np.zeros(len(model.factor_keys())), model, settings)[0] == pytest.approx(expected)


def test_cv_lambda_selection_reports_curve_and_one_se_is_more_conservative(model):
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    profiles = portfolio(40, 2, model)
    one_se, _ = calibrate_weights(profiles, model, model.default_weights(),
                                  CalibrationSettings(lambda_selection="cv", lambda_rule="one_se"))
    best, _ = calibrate_weights(profiles, model, model.default_weights(),
                                CalibrationSettings(lambda_selection="cv", lambda_rule="min"))
    grid = CalibrationSettings().lambda_grid
    assert one_se.lambda_selection == "cv" and set(one_se.lambda_cv_curve) == {f"{g:g}" for g in grid}
    assert best.regularization_used == min(grid, key=lambda g: best.lambda_cv_curve[f"{g:g}"])
    assert one_se.regularization_used >= best.regularization_used


def test_fixed_lambda_is_used_as_is(model):
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio as portfolio

    report, _ = calibrate_weights(portfolio(20, 0, model), model, model.default_weights(),
                                  CalibrationSettings(lambda_selection="fixed", regularization=0.3))
    assert report.regularization_used == 0.3 and report.lambda_cv_curve == {}
