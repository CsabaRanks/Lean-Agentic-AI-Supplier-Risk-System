"""Performance and risk views: shared criteria, own weights, calibration and material groups for both."""

import pytest
import yaml
from conftest import DATA_DIR

from supplier_risk_agent import SupplierProfile, SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.models.config import available_views, criteria_catalogue
from supplier_risk_agent.tools import WeightStore


@pytest.fixture(scope="module")
def risk():
    return load_risk_model(view="risk")


@pytest.fixture(scope="module")
def performance():
    return load_risk_model(view="performance")


def test_views_share_criteria_but_not_weights(risk, performance):
    assert set(available_views()) >= {"risk", "performance"}
    shared = set(risk.factor_keys()) & set(performance.factor_keys())
    assert shared == {"credit_risk", "esg_rating", "compliance_status"}
    catalogue = criteria_catalogue()
    for key in shared:  # same meaning and data source in both views ...
        definitions = [f for m in (risk, performance) for d in m.dimensions for f in d.factors if f.key == key]
        assert {(f.label, f.source) for f in definitions} == {(catalogue[key]["label"], catalogue[key]["source"])}
    # ... but their own weights
    assert risk.default_weights().factor_weights["credit_risk"] != performance.default_weights().factor_weights["credit_risk"]


def test_performance_score_is_presented_higher_is_better(performance, risk):
    assert performance.to_display(20.0) == 80.0 and risk.to_display(20.0) == 20.0
    p = SupplierProfile(supplier_id="X", name="X", expert_risk_score=30, expert_scores={"performance": 85})
    assert risk.label_of(p) == 30
    assert performance.label_of(p) == 15  # labels are given as 'higher = better' and read internally


def test_the_two_views_can_disagree():
    risk = {a.supplier_id: a for a in SupplierRiskEvaluator.from_json(DATA_DIR / "sample_suppliers.json").assess_all()}
    perf = {a.supplier_id: a for a in
            SupplierRiskEvaluator.from_json(DATA_DIR / "sample_suppliers.json", view="performance").assess_all()}
    assert risk["SUP-003"].risk_class == "critical" and perf["SUP-003"].risk_class == "A"
    assert perf["SUP-004"].risk_class == "C" and perf["SUP-004"].view == "performance"


def test_performance_escalation_floor():
    perf = {a.supplier_id: a for a in
            SupplierRiskEvaluator.from_json(DATA_DIR / "sample_suppliers.json", view="performance").assess_all()}
    sup4 = perf["SUP-004"]  # critical compliance finding
    assert any(e.floor_class == "C" for e in sup4.escalations)


def test_performance_calibration_and_material_group(tmp_path):
    ev = SupplierRiskEvaluator.from_json(DATA_DIR / "calibration_portfolio.json", view="performance",
                                         weights_dir=tmp_path)
    report = ev.run(calibrate=True)["calibration_report"]
    assert report.accepted and report.n_samples == 32
    assert report.new_weights["on_time_delivery"] > report.old_weights["on_time_delivery"]  # hidden: delivery-heavy
    assert (tmp_path / "performance" / "global_v001.yaml").exists()  # stored per view
    assert not (tmp_path / "risk").exists()

    group = ev.run(material_group="plastics", calibrate=True)
    assert group["calibration_report"].scope == "plastics"
    assert {r.material_group for r in group["results"].values()} == {"plastics"}


def test_weights_of_one_view_are_not_used_by_the_other(tmp_path):
    perf = SupplierRiskEvaluator.from_json(DATA_DIR / "calibration_portfolio.json", view="performance",
                                           weights_dir=tmp_path)
    perf.run(calibrate=True)
    risk = SupplierRiskEvaluator.from_json(DATA_DIR / "calibration_portfolio.json", weights_dir=tmp_path)
    assert all(r.weights_origin == "default" for r in risk.run()["results"].values())
    assert WeightStore(tmp_path).for_view("performance").load("global").origin == "calibrated"


def test_custom_view_file_references_the_catalogue(tmp_path):
    view = {
        "name": "sustainability-view", "version": "0.1", "view": "sustainability", "view_label": "Sustainability",
        "dimensions": [{"key": "esg", "label": "ESG", "weight": 1,
                        "factors": [{"key": "esg_rating", "weight": 2}, {"key": "compliance_status", "weight": 1}]}],
        "risk_classes": [{"key": "ok", "label": "ok", "min_score": 0}, {"key": "watch", "label": "watch", "min_score": 50}],
    }
    path = tmp_path / "view.yaml"
    path.write_text(yaml.safe_dump(view))
    model = load_risk_model(path)
    assert model.view == "sustainability" and model.factor_keys() == ["esg_rating", "compliance_status"]
    assert model.dimensions[0].factors[0].source == "esg_score"  # filled from the catalogue

    view["dimensions"][0]["factors"].append({"key": "unknown_criterion", "weight": 1})
    path.write_text(yaml.safe_dump(view))
    with pytest.raises(ValueError, match="neither in the catalogue"):
        load_risk_model(path)
