"""End-to-end tests of the spreadsheet UI (skipped if streamlit is not installed)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240).run()
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
