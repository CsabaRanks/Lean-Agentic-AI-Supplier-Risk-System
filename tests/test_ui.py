"""End-to-end tests of the spreadsheet UI (skipped if streamlit is not installed)."""

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "ui" / "app.py")


@pytest.fixture(autouse=True)
def no_local_llm_config(monkeypatch):
    """UI tests never read the developer's .env and never reach a real provider."""
    monkeypatch.setattr("supplier_risk_agent.llm.load_env_file", lambda *args, **kwargs: False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def app() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240)
    # keep snapshots written by the tests (e.g. after an approved review) out of the repository's data/history
    at.session_state["history_dir"] = tempfile.mkdtemp(prefix="sra-ui-history-")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return click(at, "Demo ausprobieren")


def click(at: AppTest, label: str) -> AppTest:
    next(b for b in at.button if label in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def state(at: AppTest, view: str = "risk") -> dict:
    return at.session_state.runs[view]["state"]


def metrics(at: AppTest) -> dict:
    return {m.label: m.value for m in at.metric}


def navigate(at: AppTest, page: str) -> AppTest:
    at.button(key=f"nav_{page}").click().run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def load_calibration_demo(at: AppTest) -> AppTest:
    navigate(at, "Daten & Import")
    box = at.selectbox(key="dataset_choice")
    box.select(next(o for o in box.options if "Calibration demo" in o)).run()
    click(at, "Beispieldaten laden")
    return navigate(at, "Kalibrierung")


def reviewer(at: AppTest, name: str) -> None:
    next(t for t in at.text_input if t.label == "Reviewer").input(name)


def test_welcome_requires_explicit_demo_start():
    at = AppTest.from_file(APP, default_timeout=240).run()
    assert not at.exception
    assert not at.session_state.rows and not at.session_state.runs
    assert any(b.label == "Demo ausprobieren" for b in at.button)


def test_demo_scores_both_views():
    at = app()
    m = metrics(at)
    assert m["Lieferanten"] == "6" and m["Erhöhtes Risiko"] == "4"
    assert m["Performance A"] == "3"
    assert set(at.session_state.runs) == {"risk", "performance"}


def test_recalculate_keeps_results():
    at = click(app(), "Neu berechnen")
    assert metrics(at)["Lieferanten"] == "6"


def test_review_with_class_override_on_sample_data():
    at = navigate(app(), "Freigaben")  # SUP-006 has too little data and pauses for review
    assert any("Waiting for your decision" in s.value for s in at.subheader)
    reviewer(at, "alice")
    click(at, "Submit decision")
    assert any("Review completed by alice" in s.value for s in at.success)


def test_view_switch_to_performance_uses_its_own_classes():
    at = navigate(app(), "Dashboard")
    at.radio(key="view").set_value("performance").run()
    assert not at.exception
    m = metrics(at)
    assert m["Suppliers"] == "6" and state(at, "performance")["results"]["SUP-004"].risk_class == "C"  # A / B / C classes of the performance view
    perf = state(at, "performance")["results"]
    assert perf["SUP-003"].risk_class == "A" and state(at, "risk")["results"]["SUP-003"].risk_class == "critical"


def test_calibration_proposes_and_approval_applies_weights():
    at = load_calibration_demo(app())
    click(at, "Calibrate")
    assert state(at)["calibration_report"].accepted
    assert not state(at)["calibration_applied"]  # the UI always asks for approval
    navigate(at, "Freigaben")
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
    assert not state(at, "risk").get("calibration_report")  # views keep separate runs


def test_dashboard_actions_and_history(tmp_path):
    at = app()
    m = metrics(at)
    assert m["Lieferanten"] == "6"
    navigate(at, "Dashboard")
    # dashboard: per material group selection
    at.selectbox(key="dash_group").select("chemicals").run()
    assert not at.exception
    assert any(mm.label == "Suppliers" and mm.value == "1" for mm in at.metric)
    # history: snapshot to a temporary folder, then it is listed
    navigate(at, "Einstellungen")
    at.text_input(key="history_dir").input(str(tmp_path)).run()
    navigate(at, "Historie")
    click(at, "Save snapshot")
    assert (tmp_path / "risk.jsonl").exists()
    assert any("snapshot(s)" in c.value for c in at.caption)


def test_wgi_mock_option_and_recalculate_now():
    at = navigate(app(), "Einstellungen")
    at.checkbox(key="use_wgi_mock").check().run()
    navigate(at, "Portfolio")
    click(at, "Neu berechnen")
    sup1 = state(at)["results"]["SUP-001"]
    assert "WGI" in next(f.rationale for f in sup1.factor_scores if f.factor == "country_risk")


# --- optional AI review --------------------------------------------------------------------------


def ai_button(at: AppTest):
    return next(b for b in at.button if b.label == "Generate AI Review")


def test_ai_review_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = navigate(app(), "Lieferantendetail")
    assert ai_button(at).disabled
    assert any("AI explanation not available" in i.value for i in at.info)
    assert any('"views"' in c.value for c in at.code)  # the payload preview is shown anyway


def test_ai_review_button_calls_provider_once(monkeypatch):
    from test_ai_review import FakeReviewer

    reviewer = FakeReviewer()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("supplier_risk_agent.agents.ai_review.reviewer_from_env", lambda: reviewer)
    at = navigate(app(), "Lieferantendetail")
    assert not ai_button(at).disabled and reviewer.calls == []

    ai_button(at).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(reviewer.calls) == 1
    assert any("Management summary" in m.value for m in at.markdown)
    assert ai_button(at).disabled  # kept for this exact input; no second paid call

    at.run()  # plain rerun, e.g. after any widget interaction
    assert len(reviewer.calls) == 1


# --- explain & correct ------------------------------------------------------------------------


def select_supplier(at: AppTest, sid: str) -> AppTest:
    navigate(at, "Lieferantendetail")
    box = at.selectbox(key="ai_supplier")
    return box.select(sid).run()


def propose(at: AppTest, sid: str, field: str, value: str, reason: str) -> AppTest:
    at.selectbox(key=f"correction_field_{sid}").select(field)
    at.text_input(key=f"correction_value_{sid}").input(value)
    at.text_area(key=f"correction_reason_{sid}").input(reason)
    at.text_input(key=f"correction_name_{sid}").input("tester")
    return click(at, "Vorher/Nachher prüfen")


def risk_score(at: AppTest, sid: str) -> float:
    return state(at)["results"][sid].overall_score


def test_trace_is_shown_without_api_key():
    at = select_supplier(app(), "SUP-005")
    assert any("Sum of contributions: 19.5 = internal score 19.5" in c.value for c in at.caption)
    assert any("risk:rule:insolvency_signals" in m.value and "raised the class" in m.value for m in at.markdown)


def test_preview_does_not_apply_and_confirm_applies_and_records():
    at = select_supplier(app(), "SUP-003")
    at = propose(at, "SUP-003", "qualified_sources", "2", "Second source qualified (synthetic)")
    assert any("Vorschau — noch nicht übernommen" in m.value for m in at.markdown)
    assert risk_score(at, "SUP-003") == 84.0  # preview only
    row = next(r for r in at.session_state.rows if r["supplier_id"] == "SUP-003")
    assert row["qualified_sources"] == 1

    click(at, "Korrektur bestätigen")
    assert risk_score(at, "SUP-003") == pytest.approx(79.63, abs=0.01)
    history = Path(at.session_state["history_dir"]) / "corrections.jsonl"
    entry = json.loads(history.read_text().splitlines()[-1])
    assert entry["changes"][0]["old_value"] == 1 and entry["changes"][0]["new_value"] == 2
    assert entry["entered_by"] == "tester" and entry["identity_verified"] is False


def test_correction_without_reason_is_refused():
    at = select_supplier(app(), "SUP-003")
    at = propose(at, "SUP-003", "qualified_sources", "2", "")
    assert any("reason" in e.value for e in at.error)
    assert "pending_correction" not in at.session_state


def test_ai_explanation_is_marked_outdated_after_a_correction(monkeypatch):
    from test_ai_review import FakeReviewer

    reviewer = FakeReviewer()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("supplier_risk_agent.agents.ai_review.reviewer_from_env", lambda: reviewer)
    at = select_supplier(app(), "SUP-003")
    ai_button(at).click().run()
    assert len(reviewer.calls) == 1 and not at.error

    at = propose(at, "SUP-003", "qualified_sources", "2", "Second source qualified (synthetic)")
    click(at, "Korrektur bestätigen")
    assert any(e.value.startswith("Outdated:") for e in at.error)
    assert not ai_button(at).disabled and len(reviewer.calls) == 1  # no automatic new call


def test_objection_is_recorded_without_changing_the_score():
    at = select_supplier(app(), "SUP-003")
    form_areas = [t for t in at.text_area if t.label.startswith("Why is the assessment wrong")]
    form_areas[0].input("Country index looks outdated (synthetic)")
    click(at, "Record objection")
    assert any("Objection recorded" in s.value for s in at.success)
    assert risk_score(at, "SUP-003") == 84.0
    lines = (Path(at.session_state["history_dir"]) / "objections.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["status"] == "open"


def test_literal_search_empty_state_and_reset():
    at = app()
    at.text_input(key="portfolio_search").input("[").run()
    assert not at.exception
    assert any("Keine Lieferanten gefunden" in x.value for x in at.info)
    click(at, "Filter zurücksetzen")
    assert at.text_input(key="portfolio_search").value == ""
    assert len(at.dataframe[0].value) == 6


def test_filter_and_open_supplier():
    at = app()
    at.multiselect(key="portfolio_classes").select("critical").run()
    assert set(at.dataframe[0].value.supplier_id) == {"SUP-003", "SUP-005"}
    at.selectbox(key="portfolio_supplier").select("SUP-005").run()
    click(at, "Bewertung öffnen")
    assert at.selectbox(key="ai_supplier").value == "SUP-005"
    assert len(at.metric) == 2


def test_demo_reload_discards_pending_correction():
    at = propose(select_supplier(app(), "SUP-003"), "SUP-003", "qualified_sources", "2", "Synthetic reason")
    assert "pending_correction" in at.session_state
    navigate(at, "Start")
    click(at, "Demo ausprobieren")
    assert "pending_correction" not in at.session_state
    assert risk_score(at, "SUP-003") == 84


def test_discard_preview_does_not_apply():
    at = propose(select_supplier(app(), "SUP-004"), "SUP-004", "compliance_status", "minor_findings", "Synthetic audit")
    click(at, "Vorschau verwerfen")
    assert risk_score(at, "SUP-004") == 41.75
    assert not (Path(at.session_state.history_dir) / "corrections.jsonl").exists()


def test_correction_preserves_approved_session_weights():
    at = load_calibration_demo(app())
    click(at, "Calibrate")
    navigate(at, "Freigaben")
    next(c for c in at.checkbox if c.label == "Approve proposed weights").check()
    reviewer(at, "calibration reviewer")
    click(at, "Submit decision")
    weights = state(at)["active_weights"]
    sid = next(iter(state(at)["results"]))
    at = select_supplier(at, sid)
    row = next(r for r in at.session_state.rows if r["supplier_id"] == sid)
    new_value = "2" if row.get("qualified_sources") != 2 else "3"
    propose(at, sid, "qualified_sources", new_value, "Synthetic second source")
    expected = at.session_state.pending_correction["comparison"]["risk"]["score"][1]
    click(at, "Korrektur bestätigen")
    assert state(at)["active_weights"] == weights
    assert risk_score(at, sid) == pytest.approx(expected, abs=0.01)
