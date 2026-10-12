from pathlib import Path

import pytest

from supplier_risk_agent import SupplierRiskEvaluator, load_risk_model

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="session")
def model():
    return load_risk_model()


@pytest.fixture(scope="session")
def evaluator():
    return SupplierRiskEvaluator.from_json(DATA_DIR / "sample_suppliers.json")


@pytest.fixture(scope="session")
def calibration_evaluator():
    return SupplierRiskEvaluator.from_json(DATA_DIR / "calibration_portfolio.json")


@pytest.fixture(scope="session")
def auto_apply_evaluator(calibration_evaluator):
    """Calibration portfolio with auto_apply switched on (the bundled templates propose weights only)."""
    model = calibration_evaluator.model.model_copy(deep=True)
    model.calibration.auto_apply = True
    return SupplierRiskEvaluator(calibration_evaluator.source, model)
