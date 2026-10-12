import pytest
import yaml

from supplier_risk_agent import SupplierRiskEvaluator, WeightSet
from supplier_risk_agent.tools import WeightStore


def test_save_creates_incrementing_versions(model, tmp_path):
    store = WeightStore(tmp_path / "weights")
    w = model.default_weights()
    p1, v1 = store.save(w, model, approved_by="alice")
    p2, v2 = store.save(w, model, approved_by="bob")
    assert (v1, v2) == (1, 2)
    assert (p1.name, p2.name) == ("global_v001.yaml", "global_v002.yaml")

    data = yaml.safe_load(p2.read_text())
    assert data["approved_by"] == "bob" and data["status"] == "approved"
    assert data["model"]["name"] == model.name
    assert "created_at" in data


def test_load_latest_specific_and_per_scope(model, tmp_path):
    store = WeightStore(tmp_path)
    base = model.default_weights()
    store.save(base, model, approved_by="a")
    changed = WeightSet(scope="global", origin="calibrated",
                        factor_weights={**base.factor_weights, "business_impact": 0.5})
    store.save(changed, model, approved_by="a")
    group = WeightSet(scope="plastics", origin="calibrated", factor_weights=base.factor_weights)
    store.save(group, model, approved_by="a")

    latest = store.load("global")
    assert latest.version == 2 and latest.origin == "calibrated"
    assert latest.factor_weights["business_impact"] == pytest.approx(changed.factor_weights["business_impact"], abs=1e-6)
    assert store.load("global", version=1).origin == "default"
    assert store.load("unknown") is None

    active, warnings = store.load_active(model)
    assert set(active) == {"global", "plastics"} and not warnings


def test_mismatching_factor_set_is_skipped(model, tmp_path):
    store = WeightStore(tmp_path)
    store.save(WeightSet(scope="global", factor_weights={"something_else": 1.0}), model, approved_by="a")
    active, warnings = store.load_active(model)
    assert active == {} and "do not match" in warnings[0]


def test_auto_applied_calibration_is_persisted_and_reused(auto_apply_evaluator, tmp_path):
    ev = SupplierRiskEvaluator(auto_apply_evaluator.source, auto_apply_evaluator.model, WeightStore(tmp_path))

    first = ev.run(calibrate=True)
    assert first["calibration_report"].stored_as.endswith("global_v001.yaml")

    # next run starts from the stored weights; calibrating again brings no
    # meaningful improvement, so no new version is written
    second = ev.run(calibrate=True)
    assert all(r.weights_origin == "calibrated" for r in second["results"].values())
    assert second["calibration_report"].mse_before == pytest.approx(first["calibration_report"].mse_after, abs=0.1)
    assert not second["calibration_report"].applied
    assert sorted(p.name for p in (tmp_path / "risk").iterdir()) == ["global_v001.yaml"]
