import json
import subprocess
import sys
from pathlib import Path

import pytest

from supplier_risk_agent.tools import aggregate, score_factors
from supplier_risk_agent.tools.synthetic import (
    hidden_weights,
    label_noise_floor,
    synthetic_portfolio,
)

ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_is_deterministic_per_seed(model):
    a = synthetic_portfolio(10, seed=7, model=model)
    b = synthetic_portfolio(10, seed=7, model=model)
    assert [p.model_dump() for p in a] == [p.model_dump() for p in b]
    assert [p.model_dump() for p in a] != [p.model_dump() for p in synthetic_portfolio(10, 8, model)]


def test_noise_free_labels_equal_hidden_scores(model):
    for p in synthetic_portfolio(15, seed=3, model=model, noise_sd=0.0, label_step=0):
        true = aggregate(score_factors(p, model, hidden_weights()), model).overall_score
        assert p.expert_risk_score == pytest.approx(true)


def test_reference_dataset_matches_generator(model):
    """data/calibration_portfolio.json is reproducible from the generator (seed 42)."""
    stored = json.loads((ROOT / "data" / "calibration_portfolio.json").read_text())
    regenerated = synthetic_portfolio(len(stored), seed=42, model=model)
    for record, profile in zip(stored[:-4], regenerated):
        assert record["expert_risk_score"] == profile.expert_risk_score
    assert all("expert_risk_score" not in r for r in stored[-4:])


def test_noise_floor():
    assert label_noise_floor(4.0, 5.0) == pytest.approx(16 + 25 / 12)


def test_validation_script_quick_run(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_calibration.py"), "--quick", "--out", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads((tmp_path / "summary.json").read_text())
    cv = summary["cv_reference_portfolio"]["at_default_lambda"]
    assert cv["cv_mse_calibrated"] < cv["cv_mse_default"]
    for name in ("e1_cv_summary", "e2_sample_size_summary", "e3_stability_summary"):
        assert (tmp_path / f"{name}.csv").exists()

    # figures 4-6 from the same results (matplotlib is an optional extra)
    pytest.importorskip("matplotlib")
    figures = tmp_path / "figures"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "plot_calibration_validation.py"),
         "--results", str(tmp_path), "--out", str(figures)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    for name in ("fig04_lambda_curve", "fig05_learning_curve", "fig06_weight_stability"):
        assert (figures / f"{name}.png").stat().st_size > 10_000
        assert (figures / f"{name}.svg").exists()


def test_robustness_script_quick_run(tmp_path):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "robustness_calibration.py"), "--quick", "--out", str(tmp_path)],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads((tmp_path / "summary.json").read_text())["summary"]
    by_policy = {r["policy"]: r for r in rows}
    assert {"linear", "interaction", "knockout", "worst_factor", "level_shift", "two_experts"} <= set(by_policy)
    # sanity: a linear policy is exactly representable, non-linear ones are not
    assert by_policy["linear"]["linear_floor_mse"] == pytest.approx(0.0, abs=1e-3)
    assert by_policy["knockout"]["linear_floor_mse"] > 10
