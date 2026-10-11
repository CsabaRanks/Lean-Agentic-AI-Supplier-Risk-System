import pytest

from supplier_risk_agent.models import SupplierProfile, WeightSet, load_risk_model
from supplier_risk_agent.models.config import RiskModelConfig
from supplier_risk_agent.tools import (
    aggregate,
    apply_escalations,
    classify,
    normalise,
    resolve_weights,
    score_factors,
)


def profile_with(model, rating: int) -> SupplierProfile:
    return SupplierProfile(supplier_id="X", name="X", expert_ratings={f: rating for f in model.factor_keys()})


def run(profile, model, weights=None):
    return aggregate(score_factors(profile, model, weights or model.default_weights()), model)


def test_default_weights_come_from_config_and_sum_to_one(model):
    w = model.default_weights()
    assert w.origin == "default"
    assert sum(w.factor_weights.values()) == pytest.approx(1.0)
    dims = w.dimension_weights(model)
    assert dims["severity"] == pytest.approx(0.35)
    assert w.factor_weights["business_impact"] == pytest.approx(0.35 * 0.40)


def test_weightset_rejects_negative_and_normalises():
    with pytest.raises(ValueError):
        WeightSet(factor_weights={"a": -1, "b": 2})
    assert WeightSet(factor_weights={"a": 1, "b": 3}).factor_weights == {"a": 0.25, "b": 0.75}


@pytest.mark.parametrize("rating,expected", [(1, 0.0), (3, 50.0), (5, 100.0)])
def test_uniform_ratings_map_to_scale_ends(model, rating, expected):
    agg = run(profile_with(model, rating), model)
    assert agg.overall_score == pytest.approx(expected)
    assert agg.data_completeness == pytest.approx(1.0)


def test_normalise_is_min_max(model):
    assert normalise(1, model) == 0
    assert normalise(4.36, model) == pytest.approx(84.0)


@pytest.mark.parametrize(
    "score,cls", [(0, "low"), (29.9, "low"), (30, "medium"), (50, "high"), (70, "critical"), (100, "critical")]
)
def test_classify_boundaries(model, score, cls):
    assert classify(score, model) == cls


def test_missing_factor_reweights_within_dimension(model):
    p = SupplierProfile(supplier_id="X", name="X", expert_ratings={"availability": 5, "switching_complexity": 1})
    agg = run(p, model)
    severity = next(d for d in agg.dimension_scores if d.dimension == "severity")
    assert severity.weighted_rating == pytest.approx(3.0)  # equal weights -> mean
    assert severity.completeness == pytest.approx(0.6)
    assert agg.overall_score == pytest.approx(50.0)  # only one dimension has data
    assert agg.data_completeness == pytest.approx(0.35 * 0.6)


def test_no_data_yields_no_score(model):
    agg = run(SupplierProfile(supplier_id="X", name="X"), model)
    assert agg.overall_score is None
    assert agg.data_completeness == 0


def test_custom_weights_change_score(model):
    p = profile_with(model, 1)
    p.expert_ratings["business_impact"] = 5
    only_impact = WeightSet(origin="manual", factor_weights={k: (1.0 if k == "business_impact" else 0.0) for k in model.factor_keys()})
    assert run(p, model, only_impact).overall_score == pytest.approx(100.0)
    assert run(p, model).overall_score == pytest.approx(14.0)


def test_escalation_only_raises_class(model):
    p = profile_with(model, 1)
    p.expert_ratings["compliance_status"] = 5
    factors = score_factors(p, model, model.default_weights())
    assert apply_escalations("low", factors, model)[0] == "high"
    assert apply_escalations("critical", factors, model)[0] == "critical"


def test_expert_rating_overrides_indicator(model):
    p = SupplierProfile(supplier_id="X", name="X", expert_ratings={"credit_risk": 2}, indicators={"credit_score": 10})
    credit = next(f for f in score_factors(p, model, model.default_weights()) if f.factor == "credit_risk")
    assert credit.rating == 2
    assert credit.rationale == "expert rating"


def test_invalid_expert_rating_is_treated_as_missing(model):
    p = SupplierProfile(supplier_id="X", name="X", expert_ratings={"availability": 7})
    f = next(f for f in score_factors(p, model, model.default_weights()) if f.factor == "availability")
    assert f.rating is None


def test_material_group_weights_resolution():
    raw = load_risk_model().model_dump()
    raw["material_group_weights"] = {"electronics": {"country_risk": 0.5}}
    model = RiskModelConfig.model_validate(raw)

    group = resolve_weights("electronics", {}, model)
    assert group.scope == "electronics" and group.origin == "material_group_default"
    assert group.factor_weights["country_risk"] > model.default_weights().factor_weights["country_risk"]

    assert resolve_weights("packaging", {}, model).scope == "global"
    calibrated = WeightSet(scope="electronics", origin="calibrated", factor_weights={"country_risk": 1})
    assert resolve_weights("electronics", {"electronics": calibrated}, model) is calibrated


def test_config_rejects_unknown_rule_reference():
    raw = load_risk_model().model_dump()
    raw["escalation_rules"] = [{"factor": "nope", "min_rating": 5, "floor_class": "high"}]
    with pytest.raises(ValueError, match="unknown factor"):
        RiskModelConfig.model_validate(raw)
