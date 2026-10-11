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
