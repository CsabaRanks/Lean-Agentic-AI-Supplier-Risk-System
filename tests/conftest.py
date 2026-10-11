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
