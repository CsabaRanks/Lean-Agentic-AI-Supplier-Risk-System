"""End-to-end tests of the spreadsheet UI (skipped if streamlit is not installed)."""

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240)
    # keep snapshots written by the tests (e.g. after an approved review) out of the repository's data/history
    at.session_state["history_dir"] = tempfile.mkdtemp(prefix="sra-ui-history-")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if label in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def state(at: AppTest, view: str = "risk") -> dict:
    return at.session_state.runs[view]["state"]


def metrics(at: AppTest) -> dict:
    return {m.label: m.value for m in at.metric}


def load_calibration_demo(at: AppTest) -> AppTest:
    box = at.selectbox(key="dataset_choice")
    box.select(next(o for o in box.options if "Calibration demo" in o)).run()
    return click(at, "Load example")


def reviewer(at: AppTest, name: str) -> None:
    next(t for t in at.text_input if t.label == "Reviewer").input(name)


def test_portfolio_is_scored_on_start_without_clicking():
    m = metrics(app())
    assert m["Suppliers"] == "6" and m["🔴 critical"] == "2"
    assert m["Raised by escalation rule"] == "2"


def test_recalculate_keeps_results():
    at = click(app(), "Recalculate")
    assert metrics(at)["Suppliers"] == "6"


def test_review_with_class_override_on_sample_data():
    at = app()  # SUP-006 has too little data and pauses for review
    assert any("Waiting for your decision" in s.value for s in at.subheader)
    reviewer(at, "alice")
    click(at, "Submit decision")
    assert any("Review completed by alice" in s.value for s in at.success)


def test_view_switch_to_performance_uses_its_own_classes():
    at = app()
    at.radio(key="view").set_value("performance").run()
    assert not at.exception
    m = metrics(at)
    assert m["Suppliers"] == "6" and "🔴 C" in m  # A / B / C classes of the performance view
    perf = state(at, "performance")["results"]
    assert perf["SUP-003"].risk_class == "A" and state(at, "risk")["results"]["SUP-003"].risk_class == "critical"


def test_calibration_proposes_and_approval_applies_weights():
    at = load_calibration_demo(app())
    click(at, "Calibrate")
    assert state(at)["calibration_report"].accepted
    assert not state(at)["calibration_applied"]  # the UI always asks for approval
    next(c for c in at.checkbox if c.label == "Approve proposed weights").check()
    reviewer(at, "bob")
    click(at, "Submit decision")
    s = state(at)
    assert s["calibration_applied"] and s["review_decision"].reviewer == "bob"
    assert all(r.weights_origin == "calibrated" for r in s["results"].values())


def test_performance_calibration_in_ui():
    at = load_calibration_demo(app())
    at.radio(key="view").set_value("performance").run()
    click(at, "Calibrate")
    report = state(at, "performance")["calibration_report"]
    assert report.accepted and report.n_samples == 32
    assert "on_time_delivery" in report.new_weights
    assert "calibration_report" not in state(at, "risk")  # views keep separate runs


def test_dashboard_actions_and_history(tmp_path):
    at = app()
    m = metrics(at)
    assert m["Suppliers"] == "6"  # portfolio tab
    # dashboard: per material group selection
    at.selectbox(key="dash_group").select("chemicals").run()
    assert not at.exception
    assert any(mm.label == "Suppliers" and mm.value == "1" for mm in at.metric)
    # history: snapshot to a temporary folder, then it is listed
    at.text_input(key="history_dir").input(str(tmp_path)).run()
    click(at, "Save snapshot")
    assert (tmp_path / "risk.jsonl").exists()
    assert any("snapshot(s)" in c.value for c in at.caption)


def test_wgi_mock_option_and_recalculate_now():
    at = app()
    at.checkbox(key="use_wgi_mock").check().run()
    click(at, "Recalculate now")
    sup1 = state(at)["results"]["SUP-001"]
    assert "WGI" in next(f.rationale for f in sup1.factor_scores if f.factor == "country_risk")


# --- optional AI review --------------------------------------------------------------------------


def ai_button(at: AppTest):
    return next(b for b in at.button if b.label == "Generate AI Review")


def test_ai_review_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = app()
    assert ai_button(at).disabled
    assert any("AI review not available" in i.value for i in at.info)
    assert any('"views"' in c.value for c in at.code)  # the payload preview is shown anyway


def test_ai_review_button_calls_provider_once(monkeypatch):
    from test_ai_review import FakeReviewer

    reviewer = FakeReviewer()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("supplier_risk_agent.agents.ai_review.reviewer_from_env", lambda: reviewer)
    at = app()
    assert not ai_button(at).disabled and reviewer.calls == []

    ai_button(at).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(reviewer.calls) == 1
    assert any("Management summary" in m.value for m in at.markdown)
    assert ai_button(at).disabled  # kept for this exact input; no second paid call

    at.run()  # plain rerun, e.g. after any widget interaction
    assert len(reviewer.calls) == 1
