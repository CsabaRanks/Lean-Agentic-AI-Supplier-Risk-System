"""End-to-end tests of the spreadsheet UI (skipped if streamlit is not installed)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception
    return at


def click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if label in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_scoring_run_fills_portfolio():
    at = click(app(), "Recalculate")
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Suppliers"] == "6" and metrics["🔴 Critical"] == "2"
    assert metrics["Raised by escalation rule"] == "2"


def test_review_with_class_override_on_sample_data():
    at = click(app(), "Recalculate")  # SUP-006 has too little data and pauses for review
    assert any("Waiting for your decision" in s.value for s in at.subheader)
    at.text_input[next(i for i, t in enumerate(at.text_input) if t.label == "Reviewer")].input("alice")
    click(at, "Submit decision")
    assert any("Review completed by alice" in s.value for s in at.success)


def test_calibration_proposes_and_approval_applies_weights():
    at = app()
    at.selectbox(key="dataset_choice").select(
        next(o for o in at.selectbox(key="dataset_choice").options if "Calibration demo" in o)).run()
    click(at, "Load example")
    click(at, "Calibrate")
    assert any("accepted" in i.value for i in at.success)  # cross-validated, z >= 2
    assert at.session_state.state["calibration_report"].accepted
    assert not at.session_state.state["calibration_applied"]  # the UI always asks for approval

    approve = next(c for c in at.checkbox if c.label == "Approve proposed weights")
    approve.check()
    at.text_input[next(i for i, t in enumerate(at.text_input) if t.label == "Reviewer")].input("bob")
    click(at, "Submit decision")
    state = at.session_state.state
    assert state["calibration_applied"] and state["review_decision"].reviewer == "bob"
    assert all(r.weights_origin == "calibrated" for r in state["results"].values())


def test_portfolio_is_scored_on_start_without_clicking():
    at = app()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Suppliers"] == "6"
