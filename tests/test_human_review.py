"""Human-in-the-loop: pause with interrupt(), resume with a ReviewDecision."""

import pytest

from supplier_risk_agent import SupplierRiskEvaluator
from supplier_risk_agent.models import ReviewDecision
from supplier_risk_agent.tools import WeightStore


@pytest.fixture
def proposing_evaluator(calibration_evaluator, tmp_path):
    """Calibration proposes weights instead of applying them; store in tmp dir."""
    model = calibration_evaluator.model.model_copy(deep=True)
    model.calibration.auto_apply = False
    return SupplierRiskEvaluator(calibration_evaluator.source, model, WeightStore(tmp_path))


def agents(state):
    return [e.agent for e in state["audit_trail"] if e.agent != "supervisor"]


def test_run_pauses_until_resumed(evaluator):
    paused = evaluator.run(["SUP-006"], run_id="r-defer")
    assert evaluator.pending_review(paused) is not None

    done = evaluator.resume("r-defer", ReviewDecision(reviewer="alice", defer=True))
    assert evaluator.pending_review(done) is None
    assert done["review_status"] == "deferred"
    assert done["results"]["SUP-006"].requires_human_review  # still open
    assert agents(done)[-1] == "human_review"


def test_class_override_survives_and_regenerates_recommendations(evaluator):
    evaluator.run(["SUP-006"], run_id="r-override")
    done = evaluator.resume(
        "r-override",
        {"reviewer": "alice", "overrides": {"SUP-006": {"risk_class": "critical", "comment": "known issue"}}},
    )
    r = done["results"]["SUP-006"]
    assert r.risk_class == "critical" and r.manual_override
    assert r.review_comment == "alice: known issue"
    assert not r.requires_human_review
    assert all(a.priority != "high" for a in r.recommendations)  # rebuilt for the new class
    assert any(a.review_cycle == "monthly" for a in r.recommendations)
    assert agents(done)[-2:] == ["human_review", "recommendation"]
    assert done["review_status"] == "completed"


def test_invalid_override_is_reported_not_applied(evaluator):
    evaluator.run(["SUP-006"], run_id="r-invalid")
    done = evaluator.resume("r-invalid", {"overrides": {"SUP-006": {"risk_class": "catastrophic"}}})
    assert done["results"]["SUP-006"].risk_class == "high"
    assert any("unknown class" in e for e in done["errors"])


def test_weight_approval_applies_persists_and_rescores(proposing_evaluator, tmp_path):
    paused = proposing_evaluator.run(calibrate=True, run_id="r-approve")
    request = proposing_evaluator.pending_review(paused)
    assert request["proposed_weights"]["mse_after"] < request["proposed_weights"]["mse_before"]
    assert not (tmp_path / "risk").exists()  # nothing persisted before approval

    done = proposing_evaluator.resume("r-approve", ReviewDecision(reviewer="bob", approve_weights=True))

    assert done["calibration_applied"] and done["scoring_round"] == 2
    assert agents(done)[-3:] == ["human_review", "scoring", "recommendation"]
    assert all(r.weights_origin == "calibrated" for r in done["results"].values())
    stored = sorted(p.name for p in (tmp_path / "risk").iterdir())  # one folder per view
    assert stored == ["global_v001.yaml"]
    assert done["calibration_report"].stored_as.endswith("global_v001.yaml")


def test_rejecting_weights_keeps_defaults(proposing_evaluator, tmp_path):
    proposing_evaluator.run(calibrate=True, run_id="r-reject")
    done = proposing_evaluator.resume("r-reject", ReviewDecision(reviewer="bob", approve_weights=False))
    assert not done["calibration_applied"] and done["scoring_round"] == 1
    assert all(r.weights_origin == "default" for r in done["results"].values())
    assert not (tmp_path / "risk").exists()


def test_approval_without_pending_weights_is_reported(evaluator):
    evaluator.run(["SUP-006"], run_id="r-noweights")
    done = evaluator.resume("r-noweights", {"approve_weights": True})
    assert any("no proposed weights" in e for e in done["errors"])


def test_cli_interactive_review(monkeypatch, capsys):
    from conftest import DATA_DIR

    from supplier_risk_agent import cli

    answers = iter(["SUP-006=critical", "carol"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    code = cli.main(["--data", str(DATA_DIR / "sample_suppliers.json"), "--supplier", "SUP-006",
                     "--review", "interactive"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Human review required" in out
    assert "class: critical" in out


def test_state_types_are_allow_listed_for_checkpoints(evaluator, caplog):
    """Resuming must not rely on deserializing unregistered types (blocked in future LangGraph)."""
    import logging

    caplog.set_level(logging.WARNING)
    evaluator.run(["SUP-006"], run_id="r-serde")
    evaluator.resume("r-serde", {"defer": True})
    assert not [r for r in caplog.records if "unregistered type" in r.getMessage()]
