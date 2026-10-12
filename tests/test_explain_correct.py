"""Explain & correct: scoring trace, controlled corrections, history, objections, outdated AI explanations.

Synthetic sample suppliers only; the LLM is replaced by a fake reviewer.
"""

import copy

import pytest
from conftest import DATA_DIR
from pydantic import ValidationError

from supplier_risk_agent import SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.graph import ai_review_payload
from supplier_risk_agent.providers import WorldBankWgiProvider
from supplier_risk_agent.tools import HistoryStore, InMemorySource, JsonFileSource
from supplier_risk_agent.tools.ai_review import review_is_current
from supplier_risk_agent.tools.corrections import (
    CorrectionRequest,
    FieldChange,
    apply_changes,
    assess_supplier,
    correctable_fields,
    preview_correction,
)
from supplier_risk_agent.tools.explain import scoring_trace, trace_ids
from supplier_risk_agent.tools.tabular import profile_to_row, rows_to_profiles

MODELS = [load_risk_model(view="risk"), load_risk_model(view="performance")]
RISK, PERF = MODELS


def sample_rows() -> list[dict]:
    source = JsonFileSource(DATA_DIR / "sample_suppliers.json")
    return [profile_to_row(source.get_supplier(i), RISK) for i in source.list_supplier_ids()]


def trace(sid: str, model=RISK, rows=None, providers=()):
    assessment, profile, weights = assess_supplier(rows or sample_rows(), sid, [model], providers=providers)[model.view]
    return scoring_trace(assessment, profile, model, weights)


def request(sid="SUP-003", field="qualified_sources", kind="data_correction", value=2, reason="Second source "
            "qualified (synthetic)", entered_by="tester") -> CorrectionRequest:
    return CorrectionRequest(supplier_id=sid, changes=[FieldChange(field=field, kind=kind, new_value=value)],
                             reason=reason, entered_by=entered_by)


# --- score contributions ---------------------------------------------------------------------


@pytest.mark.parametrize("model", MODELS, ids=lambda m: m.view)
@pytest.mark.parametrize("sid", [f"SUP-00{i}" for i in range(1, 7)])
def test_contributions_add_up_to_the_engine_score(model, sid):
    t = trace(sid, model)
    points = [c["contribution_points"] for c in t["criteria"] if c["contribution_points"] is not None]
    assert sum(points) == pytest.approx(t["score"]["internal_value"], abs=0.05)
    assert sum(c["effective_weight"] for c in t["criteria"]) == pytest.approx(1.0, abs=0.002)


def test_contribution_of_a_criterion_with_complete_data():
    """SUP-003, complete data: effective weight = nominal weight; contribution = weight x (rating-1)/4 x 100."""
    c = next(c for c in trace("SUP-003")["criteria"] if c["key"] == "sourcing_strategy")
    assert c["rating"] == 5 and c["effective_weight"] == pytest.approx(c["nominal_weight"], abs=1e-4)
    assert c["contribution_points"] == pytest.approx(c["nominal_weight"] * 100, abs=0.01)


def test_missing_data_has_no_contribution_and_weight_is_redistributed():
    t = trace("SUP-006")
    credit = next(c for c in t["criteria"] if c["key"] == "credit_risk")
    assert credit["rating"] is None and credit["effective_weight"] == 0 and credit["contribution_points"] is None
    assert credit["rating_origin"] == "missing"
    assert credit["inputs"] == [{"input": "credit_score", "value": None, "source": "missing: no value and no source"}]
    availability = next(c for c in t["criteria"] if c["key"] == "availability")
    assert availability["inputs"][0]["source"] == "missing: expert rating not entered"
    impact = next(c for c in t["criteria"] if c["key"] == "business_impact")
    assert impact["effective_weight"] > impact["nominal_weight"]  # carries the weight of missing criteria
    assert "credit_risk" in t["missing_criteria"]


def test_inputs_show_rule_and_source():
    credit = next(c for c in trace("SUP-003")["criteria"] if c["key"] == "credit_risk")
    assert credit["rule"].startswith("credit score: < 35 -> 5")
    assert credit["inputs"] == [{"input": "credit_score", "value": 41,
                                 "source": "entered by hand (no source or data date recorded)"}]
    country = next(c for c in trace("SUP-003", providers=[WorldBankWgiProvider.mock()])["criteria"]
                   if c["key"] == "country_risk")
    wgi = next(i for i in country["inputs"] if i["input"] == "wgi_political_stability")
    assert "WGI" in wgi["source"] or "World Bank" in wgi["source"]


# --- non-additive rules ----------------------------------------------------------------------------


def test_escalation_rule_is_explained_separately_from_the_score():
    t = trace("SUP-005")
    rule = next(r for r in t["non_additive"] if r["id"] == "risk:rule:insolvency_signals")
    assert rule["fired"] and rule["effect"] == "raised the class from 'low' to at least 'critical'"
    assert t["class"] == {**t["class"], "from_score": "low", "final": "critical"}
    assert t["score"]["sum_of_contributions"] == pytest.approx(19.5, abs=0.05)  # the rule adds no points


def test_triggered_rule_without_effect_and_not_evaluable_rule():
    perf = trace("SUP-004", PERF)
    rule = next(r for r in perf["non_additive"] if r["id"] == "performance:rule:compliance_status")
    assert rule["fired"] and rule["effect"].startswith("triggered, no effect")
    gaps = trace("SUP-006")
    assert any(r["effect"] == "not evaluable: criterion has no data" for r in gaps["non_additive"])
    completeness = next(r for r in gaps["non_additive"] if r["id"] == "risk:completeness")
    assert completeness["fired"] and "human review" in completeness["effect"]


def test_trace_ids_are_unique_and_citable():
    t = trace("SUP-003")
    ids = [c["id"] for c in t["criteria"]] + [d["id"] for d in t["dimensions"]] + [r["id"] for r in t["non_additive"]]
    assert len(ids) == len(set(ids)) and {"risk:score", "risk:class", "risk:credit_risk"} <= trace_ids(t)


# --- corrections: kinds and validation ---------------------------------------------------------------


def test_data_corrections_and_expert_overrides_are_separated():
    fields = correctable_fields(MODELS)
    assert fields["credit_score"]["kind"] == "data_correction"
    assert fields["credit_risk"]["kind"] == "expert_override"
    assert fields["business_impact"]["kind"] == "data_correction"  # the expert rating is the input itself
    assert fields["compliance_status"]["kind"] == "data_correction"  # no override: same name as its input
    assert set(fields["credit_score"]["criteria"]) == {"risk:credit_risk", "performance:credit_risk"}


@pytest.mark.parametrize("make, message", [
    (lambda: request(reason="  "), "reason"),
])
def test_a_reason_is_required(make, message):
    with pytest.raises(ValidationError, match=message):
        make()


@pytest.mark.parametrize("req, message", [
    (request(field="weight_credit_risk"), "cannot be corrected here"),
    (request(field="credit_risk", kind="data_correction", value=3), "is a expert override"),
    (request(field="credit_risk", kind="expert_override", value=6), "whole number from 1 to 5"),
    (request(field="qualified_sources", value=1), "equal the current values"),
    (request(sid="SUP-999"), "unknown supplier"),
])
def test_invalid_corrections_are_rejected(req, message):
    with pytest.raises(ValueError, match=message):
        apply_changes(sample_rows(), req, MODELS)


# --- preview without adoption, confirmed correction ------------------------------------------------------


def test_preview_changes_nothing_and_shows_before_and_after():
    rows = sample_rows()
    original = copy.deepcopy(rows)
    req = request()
    new_rows, comparison = preview_correction(rows, req, MODELS)

    assert rows == original  # nothing adopted yet
    assert req.changes[0].old_value == 1 and next(r for r in new_rows if r["supplier_id"] == "SUP-003")[
        "qualified_sources"] == 2
    risk = comparison["risk"]
    assert risk["score"] == [84.0, pytest.approx(79.63, abs=0.01)] and risk["class"] == ["critical", "critical"]
    assert risk["changed_criteria"] == [{"criterion": "sourcing_strategy", "rating": [5, 3],
                                         "origin": ["derived from input data by rule"] * 2,
                                         "contribution_points": [8.75, 4.38]}]
    assert comparison["performance"]["changed_criteria"] == []  # criterion not used there
    assert risk["model"] == "generic-supplier-risk-template@0.1.0" and risk["weights"] == "global/default"


def test_correction_that_removes_an_escalation_changes_the_class():
    _, comparison = preview_correction(sample_rows(), request(sid="SUP-004", field="compliance_status",
                                                              value="minor_findings"), MODELS)
    risk = comparison["risk"]
    assert risk["class"] == ["high", "medium"]
    assert risk["rules_no_longer_triggered"] == ["risk:rule:compliance_status"]
    assert comparison["performance"]["rules_no_longer_triggered"] == ["performance:rule:compliance_status"]


def test_expert_override_replaces_the_derived_rating_in_both_views():
    _, comparison = preview_correction(sample_rows(), request(field="credit_risk", kind="expert_override", value=2,
                                                              reason="Parent guarantee (synthetic)"), MODELS)
    for view in ("risk", "performance"):
        changed = next(c for c in comparison[view]["changed_criteria"] if c["criterion"] == "credit_risk")
        assert changed["rating"] == [4, 2]
        assert changed["origin"] == ["derived from input data by rule", "expert override of a derived rating"]


def test_confirmed_correction_is_rescored_and_recorded(tmp_path):
    rows = sample_rows()
    req = request()
    new_rows, comparison = preview_correction(rows, req, MODELS)
    store = HistoryStore(tmp_path)
    entry = store.record_correction(req, comparison, recorded_at="2026-10-12T10:00:00+00:00")

    after = assess_supplier(new_rows, "SUP-003", MODELS)
    assert after["risk"][0].overall_score == pytest.approx(79.63, abs=0.01)
    assert entry["changes"] == [{"field": "qualified_sources", "kind": "data_correction",
                                 "old_value": 1, "new_value": 2}]
    assert entry["reason"] == "Second source qualified (synthetic)" and entry["entered_by"] == "tester"
    assert entry["identity_verified"] is False and entry["status"] == "applied"
    assert entry["views"]["risk"]["model"] == "generic-supplier-risk-template@0.1.0"
    assert entry["views"]["risk"]["weights"] == "global/default"
    assert entry["views"]["risk"]["score"][0] == 84.0
    assert store.corrections("SUP-003") == [entry] and store.corrections("SUP-001") == []


# --- objections ----------------------------------------------------------------------------------------


def test_objection_is_recorded_and_changes_nothing(tmp_path):
    rows = sample_rows()
    before = assess_supplier(rows, "SUP-003", MODELS)
    store = HistoryStore(tmp_path)
    entry = store.record_objection("SUP-003", "risk", "country_risk", "Index looks outdated (synthetic)",
                                   entered_by=None, context={"rating": 4})
    assert entry["status"] == "open" and entry["identity_verified"] is False
    assert store.objections("SUP-003") == [entry]
    after = assess_supplier(rows, "SUP-003", MODELS)
    assert after["risk"][0].overall_score == before["risk"][0].overall_score
    assert not (tmp_path / "corrections.jsonl").exists() and not list(tmp_path.glob("*/"))  # no weights written
    with pytest.raises(ValueError, match="reason"):
        store.record_objection("SUP-003", "risk", "country_risk", " ")


# --- outdated AI explanation ---------------------------------------------------------------------------------


def evaluators(rows, reviewer=None):
    risk_profiles, _ = rows_to_profiles(rows, RISK)
    perf_profiles, _ = rows_to_profiles(rows, PERF)
    risk = SupplierRiskEvaluator(InMemorySource(risk_profiles), RISK, ai_reviewer=reviewer)
    perf = SupplierRiskEvaluator(InMemorySource(perf_profiles), PERF)
    return risk, risk.run(), perf, perf.run()


def test_ai_explanation_is_outdated_after_a_correction():
    from test_ai_review import FakeReviewer

    rows = sample_rows()
    risk, rs, perf, ps = evaluators(rows, FakeReviewer())
    payload = ai_review_payload("SUP-003", (risk, rs), (perf, ps))
    result = risk.ai_review(rs["run_id"], payload)["ai_reviews"]["SUP-003"]
    assert review_is_current(result, payload)

    new_rows, _ = preview_correction(rows, request(), MODELS)
    risk2, rs2, perf2, ps2 = evaluators(new_rows)
    new_payload = ai_review_payload("SUP-003", (risk2, rs2), (perf2, ps2))
    assert not review_is_current(result, new_payload)
    unchanged = evaluators(rows)
    assert review_is_current(result, ai_review_payload("SUP-003", unchanged[:2], unchanged[2:]))
