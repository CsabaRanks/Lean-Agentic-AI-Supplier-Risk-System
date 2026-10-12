import pytest


def agents(state):
    return [e.agent for e in state["audit_trail"]]


def test_portfolio_classes(evaluator):
    results = {r.supplier_id: r for r in evaluator.assess_all()}
    assert results["SUP-001"].risk_class == "low"
    assert results["SUP-002"].risk_class == "medium"
    assert results["SUP-003"].risk_class == "critical"
    assert results["SUP-003"].overall_score == pytest.approx(84.0)


def test_escalation_rules_fire(evaluator):
    r4 = evaluator.assess("SUP-004")
    assert r4.calculated_class == "medium" and r4.risk_class == "high"
    r5 = evaluator.assess("SUP-005")
    assert r5.calculated_class == "low" and r5.risk_class == "critical"


def test_incomplete_data_pauses_for_review(evaluator):
    state = evaluator.run(["SUP-006"])
    assert state["requires_human_review"] is True
    assert "review_status" not in state  # paused, not decided
    request = evaluator.pending_review(state)
    assert [s["supplier_id"] for s in request["flagged_suppliers"]] == ["SUP-006"]
    assert any("completeness" in r for r in state["results"]["SUP-006"].review_reasons)


def test_flow_without_calibration(evaluator):
    state = evaluator.run(["SUP-001"], calibrate=False)
    assert agents(state) == [
        "supervisor", "data_collection",
        "supervisor", "scoring",
        "supervisor", "recommendation",
        "supervisor",
    ]
    assert "calibration_performed" not in state


def test_flow_with_calibration_rescores_once(auto_apply_evaluator):
    state = auto_apply_evaluator.run(calibrate=True)
    assert agents(state) == [
        "supervisor", "data_collection",
        "supervisor", "scoring",
        "supervisor", "calibration",
        "supervisor", "scoring",  # feedback loop
        "supervisor", "recommendation",
        "supervisor",
    ]
    assert state["calibration_performed"] and state["calibration_applied"]
    assert state["mse_after"] < state["mse_before"]
    assert state["scoring_round"] == 2
    assert all(r.weights_origin == "calibrated" for r in state["results"].values())


def test_calibration_skipped_without_labels(evaluator):
    state = evaluator.run(calibrate=True)
    assert state["calibration_performed"] and not state["calibration_applied"]
    assert state["scoring_round"] == 1
    assert "skipped" in state["calibration_report"].message


def test_proposed_weights_need_approval_by_default(calibration_evaluator):
    """The bundled risk template never applies calibrated weights without a reviewer."""
    from supplier_risk_agent import SupplierRiskEvaluator

    assert calibration_evaluator.model.calibration.auto_apply is False
    state = calibration_evaluator.run(calibrate=True)
    assert state["calibration_report"].accepted and not state["calibration_applied"]
    assert all(r.weights_origin == "default" for r in state["results"].values())
    assert SupplierRiskEvaluator.pending_review(state)["proposed_weights"] is not None
    assert any("approval required" in r for r in state["review_reasons"])


def test_material_group_run_rejects_overfit_on_few_labels(calibration_evaluator):
    """10 plastics labels: in-sample the fit looks excellent, out of sample the gain is not clear."""
    state = calibration_evaluator.run(material_group="plastics", calibrate=True)
    report = state["calibration_report"]
    assert {r.material_group for r in state["results"].values()} == {"plastics"}
    assert report.scope == "plastics" and report.n_samples == 10
    assert report.mse_after < 0.5 * report.mse_before  # large in-sample "improvement"
    assert report.cv_improvement_z < 2  # out of sample: not distinguishable from noise
    assert not report.accepted and "plastics" not in state["active_weights"]


def test_material_group_run_applies_group_scope_with_in_sample_rule(auto_apply_evaluator):
    from supplier_risk_agent import SupplierRiskEvaluator

    model = auto_apply_evaluator.model.model_copy(deep=True)
    model.calibration.acceptance = "in_sample"
    state = SupplierRiskEvaluator(auto_apply_evaluator.source, model).run(material_group="plastics", calibrate=True)
    assert state["calibration_report"].accepted and state["calibration_report"].acceptance_basis == "in_sample"
    assert "plastics" in state["active_weights"]


def test_recommendations_include_review_cycle(evaluator):
    recs = evaluator.assess("SUP-003").recommendations
    assert any(r.review_cycle == "monthly" for r in recs)
    assert any(r.priority == "targeted" for r in recs)


def test_unknown_supplier_raises(evaluator):
    with pytest.raises(LookupError, match="not found"):
        evaluator.assess("DOES-NOT-EXIST")


def _level_shifted_source(model, points=10):
    from supplier_risk_agent.tools import InMemorySource
    from supplier_risk_agent.tools.synthetic import synthetic_portfolio

    profiles = synthetic_portfolio(32, 3, model)
    for p in profiles:
        p.expert_risk_score = float(min(100, p.expert_risk_score + points))
    return InMemorySource(profiles)


def test_level_offset_blocks_auto_apply(model):
    from supplier_risk_agent import SupplierRiskEvaluator

    state = SupplierRiskEvaluator(_level_shifted_source(model), model).run(calibrate=True)
    report = state["calibration_report"]
    assert report.level_bias_detected and report.accepted  # the fit "improves", but for the wrong reason
    assert not state["calibration_applied"]
    assert all(r.weights_origin == "default" for r in state["results"].values())
    assert any("level offset" in r for r in state["review_reasons"])
    assert SupplierRiskEvaluator.pending_review(state)["proposed_weights"]["warnings"]


def test_level_offset_warn_mode_applies(model):
    from supplier_risk_agent import SupplierRiskEvaluator

    warn = model.model_copy(deep=True)
    warn.calibration.level_bias_action = "warn"
    warn.calibration.auto_apply = True
    state = SupplierRiskEvaluator(_level_shifted_source(warn), warn).run(calibrate=True)
    assert state["calibration_report"].level_bias_detected and state["calibration_applied"]
