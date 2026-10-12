"""Optional LLM review: input preparation, output validation, graph integration and error handling.

All tests use synthetic suppliers and a fake or mocked provider; no network access.
The real provider is exercised only by ``test_real_provider_smoke`` when ANTHROPIC_API_KEY is set.
"""

import json
import os
from types import SimpleNamespace

import pytest
from conftest import DATA_DIR

from supplier_risk_agent import SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.graph import ai_review_payload
from supplier_risk_agent.llm import AnthropicReviewer, LLMReviewError, LLMSettings, load_env_file
from supplier_risk_agent.models import ReviewDecision
from supplier_risk_agent.models.ai_review import AIReviewDraft
from supplier_risk_agent.tools.ai_review import (
    data_gaps,
    payload_hash,
    payload_json,
    validate_review,
)
from supplier_risk_agent.tools.data_sources import JsonFileSource

SAMPLE = DATA_DIR / "sample_suppliers.json"


def draft(**changes) -> AIReviewDraft:
    """A valid answer for SUP-003 (all criterion keys exist in the sample payload)."""
    base = {
        "management_summary": "Critical supply risk despite strong delivery performance.",
        "summary_refs": ["risk:score", "performance:score"],
        "risk_drivers": [
            {"criterion": "sourcing_strategy", "view": "risk", "explanation": "Single source, rated 5.",
             "trace_refs": ["risk:sourcing_strategy"]},
            {"criterion": "country_risk", "view": "risk", "explanation": "Rated 4.", "trace_refs": ["risk:country_risk"]},
        ],
        "view_differences": [
            {"topic": "Good supplier, fragile supply", "explanation": "Delivery is rated well; dependency is not.",
             "criteria": ["on_time_delivery", "sourcing_strategy"],
             "trace_refs": ["performance:dim:delivery", "risk:dim:supply_chain"]},
        ],
        "suggested_actions": [
            {"priority": "low", "action": "Review payment terms.", "rationale": "Credit rated 4.",
             "criteria": ["credit_risk"], "trace_refs": ["risk:credit_risk"]},
            {"priority": "high", "action": "Qualify a second source.", "rationale": "Single source.",
             "criteria": ["sourcing_strategy"], "trace_refs": ["risk:sourcing_strategy"]},
        ],
        "open_questions": [],
    }
    return AIReviewDraft.model_validate({**base, **changes})


class FakeReviewer:
    """Stands in for the provider; counts calls and returns a fixed answer or raises."""

    def __init__(self, answer=None, error: Exception | None = None):
        self.settings = LLMSettings(api_key="test")
        self.answer, self.error, self.calls = answer, error, []

    def review(self, system, user):
        self.calls.append((system, user))
        if self.error:
            raise self.error
        return (self.answer or draft()), "fake-model"


@pytest.fixture()
def runs():
    """Risk and performance runs of the synthetic sample portfolio, sharing one fake reviewer."""
    reviewer = FakeReviewer()
    source = JsonFileSource(SAMPLE)
    risk = SupplierRiskEvaluator(source, load_risk_model(view="risk"), ai_reviewer=reviewer)
    perf = SupplierRiskEvaluator(source, load_risk_model(view="performance"), ai_reviewer=reviewer)
    return SimpleNamespace(risk=risk, perf=perf, risk_state=risk.run(), perf_state=perf.run(), reviewer=reviewer)


def payload_for(runs, sid="SUP-003"):
    return ai_review_payload(sid, (runs.risk, runs.risk_state), (runs.perf, runs.perf_state))


# --- input preparation -----------------------------------------------------------------------


def test_payload_contains_both_views_and_only_structured_results(runs):
    payload = payload_for(runs)
    assert payload["supplier"] == {"id": "SUP-003", "material_group": "chemicals"}
    assert list(payload["views"]) == ["risk", "performance"]
    risk = payload["views"]["risk"]
    assert risk["score"]["value"] == 84.0 and risk["class"]["final"] == "critical"
    assert {c["key"] for c in risk["criteria"]} == set(load_risk_model(view="risk").factor_keys())
    assert all({"id", "rating", "nominal_weight", "contribution_points", "inputs", "rule"} <= set(c)
               for c in risk["criteria"])
    assert payload["views"]["performance"]["score"]["orientation"] == "higher_is_better"

    text = payload_json(payload)
    for withheld in ("Cobalt", "annual_spend", "country\"", "expert_risk_score"):
        assert withheld not in text, withheld


def test_payload_marks_missing_data_and_fired_rules(runs):
    gaps = payload_for(runs, "SUP-006")
    assert "risk: credit_risk" in data_gaps(gaps)
    assert gaps["views"]["risk"]["flagged_for_human_review"]
    rules = [r for r in payload_for(runs, "SUP-005")["views"]["risk"]["non_additive"] if r["fired"]]
    assert [r["id"] for r in rules] == ["risk:rule:insolvency_signals"]


def test_payload_is_deterministic(runs):
    assert payload_hash(payload_for(runs)) == payload_hash(payload_for(runs))
    assert payload_json(payload_for(runs)) == payload_json(payload_for(runs))


def test_payload_requires_the_supplier_in_every_view(runs):
    with pytest.raises(LookupError):
        payload_for(runs, "SUP-999")


# --- output validation -------------------------------------------------------------------------


def test_valid_answer_passes(runs):
    assert validate_review(draft(), payload_for(runs)) == []


@pytest.mark.parametrize("changes, expected", [
    ({"management_summary": "  "}, "summary is empty"),
    ({"management_summary": "x" * 2000}, "longer than"),
    ({"risk_drivers": []}, "risk drivers"),
    ({"risk_drivers": [{"criterion": "brand_reputation", "view": "risk", "explanation": "x", "trace_refs": ["risk:score"]}]},
     "unknown criterion 'brand_reputation'"),
    ({"risk_drivers": [{"criterion": "on_time_delivery", "view": "risk", "explanation": "x", "trace_refs": ["risk:score"]}]},
     "unknown criterion 'on_time_delivery' in view 'risk'"),
    ({"suggested_actions": []}, "suggested actions"),
    ({"view_differences": []}, "differences between the views"),
    ({"open_questions": [{"question": "Who owns it?", "criteria": ["ownership"]}]}, "unknown criterion 'ownership'"),
    ({"summary_refs": []}, "summary cites no trace entry"),
    ({"risk_drivers": [{"criterion": "country_risk", "view": "risk", "explanation": "x", "trace_refs": []}]},
     "a risk driver cites no trace entry"),
    ({"risk_drivers": [{"criterion": "country_risk", "view": "risk", "explanation": "x",
                        "trace_refs": ["risk:market_news"]}]}, "unknown trace entry 'risk:market_news'"),
])
def test_invalid_answers_are_rejected(runs, changes, expected):
    problems = validate_review(draft(**changes), payload_for(runs))
    assert any(expected in p for p in problems), problems


def test_missing_data_requires_open_questions(runs):
    payload = payload_for(runs, "SUP-006")
    answer = draft(risk_drivers=[{"criterion": "business_impact", "view": "risk", "explanation": "Rated 4.",
                                  "trace_refs": ["risk:business_impact"]}])
    assert any("missing data" in p for p in validate_review(answer, payload))
    answer = draft(risk_drivers=answer.model_dump()["risk_drivers"],
                   open_questions=[{"question": "What is the credit rating?", "criteria": ["credit_risk"]}])
    assert validate_review(answer, payload) == []


def test_schema_has_no_numeric_fields():
    """No structured score, class or weight fields; numbers inside the free text are not checked."""
    schema = json.dumps(AIReviewDraft.model_json_schema())
    assert '"number"' not in schema and '"integer"' not in schema


# --- graph integration ---------------------------------------------------------------------------


def test_review_is_a_follow_up_step_and_changes_no_numbers(runs):
    before = runs.risk_state["results"]
    state = runs.risk.ai_review(runs.risk_state["run_id"], payload_for(runs))

    result = state["ai_reviews"]["SUP-003"]
    assert result.scores["risk"] == {"score": 84.0, "score_label": "Risk score", "class": "critical",
                                     "data_completeness": 1.0}
    assert [a.priority for a in result.review.suggested_actions] == ["high", "low"]  # prioritised by code
    assert result.model == "fake-model" and result.payload_sha256 == payload_hash(payload_for(runs))
    assert {k: (r.overall_score, r.risk_class) for k, r in state["results"].items()} == \
        {k: (r.overall_score, r.risk_class) for k, r in before.items()}
    assert state["audit_trail"][-2].agent == "ai_review" and state["audit_trail"][-2].event == "ai_review_created"
    assert state["ai_review_request"] is None

    # exactly the previewed payload was sent
    system, user = runs.reviewer.calls[0]
    assert "Do not add facts" in system and payload_json(payload_for(runs)) in user


def test_pending_human_review_stays_pending(runs):
    run_id = runs.risk_state["run_id"]
    assert runs.risk.pending_review(runs.risk_state)
    state = runs.risk.ai_review(run_id, payload_for(runs))
    assert runs.risk.pending_review(state) is not None
    resumed = runs.risk.resume(run_id, ReviewDecision(reviewer="tester", defer=True))
    assert resumed["review_status"] == "deferred" and "SUP-003" in resumed["ai_reviews"]


def test_review_runs_only_on_request(runs):
    assert runs.reviewer.calls == []
    runs.risk.ai_review(runs.risk_state["run_id"], payload_for(runs))
    runs.risk.resume(runs.risk_state["run_id"], ReviewDecision(reviewer="tester", defer=True))
    assert len(runs.reviewer.calls) == 1  # resuming does not trigger another call


def test_stale_preview_is_not_sent(runs):
    payload = payload_for(runs)
    payload["views"]["risk"]["score"] = 12.0
    state = runs.risk.ai_review(runs.risk_state["run_id"], payload)
    assert "no longer matches" in state["ai_review_errors"]["SUP-003"]
    assert runs.reviewer.calls == []


@pytest.mark.parametrize("reviewer, expected", [
    (FakeReviewer(error=LLMReviewError("The provider did not answer within 90 s")), "did not answer"),
    (FakeReviewer(answer=draft(risk_drivers=[{"criterion": "x", "view": "risk", "explanation": "y", "trace_refs": ["risk:score"]}])),
     "failed validation"),
])
def test_failures_are_reported_and_keep_the_run_usable(reviewer, expected):
    source = JsonFileSource(SAMPLE)
    risk = SupplierRiskEvaluator(source, load_risk_model(view="risk"), ai_reviewer=reviewer)
    perf = SupplierRiskEvaluator(source, load_risk_model(view="performance"))
    rs, ps = risk.run(), perf.run()
    state = risk.ai_review(rs["run_id"], ai_review_payload("SUP-003", (risk, rs), (perf, ps)))
    assert expected in state["ai_review_errors"]["SUP-003"]
    assert "SUP-003" not in state.get("ai_reviews", {})
    assert state["results"]["SUP-003"].risk_class == "critical"
    assert state["audit_trail"][-2].event == "ai_review_failed"


def test_without_api_key_the_review_is_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    source = JsonFileSource(SAMPLE)
    risk = SupplierRiskEvaluator(source, load_risk_model(view="risk"))  # provider from the environment
    perf = SupplierRiskEvaluator(source, load_risk_model(view="performance"))
    rs, ps = risk.run(), perf.run()
    state = risk.ai_review(rs["run_id"], ai_review_payload("SUP-003", (risk, rs), (perf, ps)))
    assert "ANTHROPIC_API_KEY" in state["ai_review_errors"]["SUP-003"]


# --- configuration ------------------------------------------------------------------------------


def test_settings_from_env_defaults_and_errors():
    s = LLMSettings.from_env({})
    assert (s.provider, s.model, s.api_key) == ("anthropic", "claude-opus-5-5", None)
    assert "ANTHROPIC_API_KEY" in s.unavailable_reason
    s = LLMSettings.from_env({"ANTHROPIC_API_KEY": "sk-secret-123", "SRA_LLM_TIMEOUT_SECONDS": "30",
                              "SRA_LLM_MAX_RETRIES": "1"})
    assert s.unavailable_reason is None and s.timeout_seconds == 30 and s.max_retries == 1
    assert "sk-secret-123" not in repr(s)  # the key never shows up in logs
    assert "not supported" in LLMSettings.from_env({"SRA_LLM_PROVIDER": "other", "ANTHROPIC_API_KEY": "k"}
                                                   ).unavailable_reason
    with pytest.raises(LLMReviewError, match="must be a number"):
        LLMSettings.from_env({"SRA_LLM_TIMEOUT_SECONDS": "soon"})


def test_env_file_does_not_override_existing_variables(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nSRA_LLM_MODEL=from-file\nexport SRA_LLM_MAX_TOKENS='123'\n")
    monkeypatch.setenv("SRA_LLM_MODEL", "from-env")
    monkeypatch.delenv("SRA_LLM_MAX_TOKENS", raising=False)
    assert load_env_file(env)
    assert os.environ["SRA_LLM_MODEL"] == "from-env" and os.environ["SRA_LLM_MAX_TOKENS"] == "123"
    assert not load_env_file(tmp_path / "missing.env")


# --- provider adapter with a mocked SDK client -------------------------------------------------------


def sdk():
    return pytest.importorskip("anthropic")


class MockMessages:
    def __init__(self, outcome):
        self.outcome, self.kwargs = outcome, None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def mock_client(outcome):
    messages = MockMessages(outcome)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages)), messages


def response(stop_reason="end_turn", parsed=None, model="claude-opus-5-5"):
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, model=model)


def test_adapter_requests_structured_output_with_fallback():
    sdk()
    client, messages = mock_client(response(parsed=draft()))
    answer, served_by = AnthropicReviewer(LLMSettings(api_key="k"), client).review("system", "user")
    assert answer == draft() and served_by == "claude-opus-5-5"
    assert messages.kwargs["output_format"] is AIReviewDraft
    assert messages.kwargs["fallbacks"] == "default" and messages.kwargs["model"] == "claude-opus-5-5"

    client, messages = mock_client(response(parsed=draft(), model="claude-haiku-5-5"))
    AnthropicReviewer(LLMSettings(api_key="k", model="claude-haiku-5-5"), client).review("s", "u")
    assert "fallbacks" not in messages.kwargs


def _status_error(cls, status):
    import httpx2

    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize("make_error, expected", [
    (lambda a, req: a.APITimeoutError(request=req), "did not answer within 90 s (tried 3 time(s))"),
    (lambda a, req: a.APIConnectionError(request=req), "Could not reach the provider"),
    (lambda a, req: _status_error(a.AuthenticationError, 401), "API key was rejected"),
    (lambda a, req: _status_error(a.NotFoundError, 404), "Model 'claude-opus-5-5' was not found"),
    (lambda a, req: _status_error(a.RateLimitError, 429), "Rate limit reached"),
    (lambda a, req: _status_error(a.InternalServerError, 500), "HTTP 500"),
])
def test_adapter_turns_sdk_errors_into_readable_messages(make_error, expected):
    a = sdk()
    import httpx2

    error = make_error(a, httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    client, _ = mock_client(error)
    with pytest.raises(LLMReviewError, match=expected.replace("(", r"\(").replace(")", r"\)")):
        AnthropicReviewer(LLMSettings(api_key="k"), client).review("s", "u")


@pytest.mark.parametrize("outcome, expected", [
    (response(stop_reason="refusal"), "declined"),
    (response(stop_reason="max_tokens"), "cut off"),
    (response(parsed=None), "no structured answer"),
    (ValueError("not json"), "did not match the expected review format"),
])
def test_adapter_rejects_unusable_answers(outcome, expected):
    sdk()
    client, _ = mock_client(outcome)
    with pytest.raises(LLMReviewError, match=expected):
        AnthropicReviewer(LLMSettings(api_key="k"), client).review("s", "u")


# --- real provider (only with an API key) -----------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="real smoke test needs ANTHROPIC_API_KEY")
def test_real_provider_smoke():
    """One paid call on synthetic data: the answer must pass the same validation as above."""
    sdk()
    source = JsonFileSource(SAMPLE)
    risk = SupplierRiskEvaluator(source, load_risk_model(view="risk"))
    perf = SupplierRiskEvaluator(source, load_risk_model(view="performance"))
    rs, ps = risk.run(), perf.run()
    state = risk.ai_review(rs["run_id"], ai_review_payload("SUP-003", (risk, rs), (perf, ps)))
    assert state.get("ai_review_errors", {}) == {}, state.get("ai_review_errors")
    assert state["ai_reviews"]["SUP-003"].review.management_summary
