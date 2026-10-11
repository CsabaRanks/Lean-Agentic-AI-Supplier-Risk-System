import pytest

from supplier_risk_agent import SupplierRiskEvaluator
from supplier_risk_agent.tools import InMemorySource, JsonFileSource
from supplier_risk_agent.tools.tabular import (
    assessment_to_row,
    from_csv,
    profile_to_row,
    rows_to_profiles,
    to_csv,
)


def test_csv_round_trip_gives_identical_assessments(model):
    from conftest import DATA_DIR

    source = JsonFileSource(DATA_DIR / "sample_suppliers.json")
    profiles = [source.get_supplier(i) for i in source.list_supplier_ids()]
    text = to_csv([profile_to_row(p, model) for p in profiles])
    restored, errors = rows_to_profiles(from_csv(text), model)
    assert not errors
    assert [p.model_dump() for p in restored] == [p.model_dump() for p in profiles]

    original = {r.supplier_id: r for r in SupplierRiskEvaluator(source, model).assess_all()}
    again = {r.supplier_id: r for r in SupplierRiskEvaluator(InMemorySource(restored), model).assess_all()}
    assert {k: (v.overall_score, v.risk_class) for k, v in again.items()} == \
           {k: (v.overall_score, v.risk_class) for k, v in original.items()}


def test_semicolon_csv_and_cell_types(model):
    text = "supplier_id;name;business_impact;credit_score;intercontinental;transport_mode;expert_risk_score\n" \
           "S1;Acme;4;71;ja;sea;55\n;;;;;;\n"
    profiles, errors = rows_to_profiles(from_csv(text), model)
    assert not errors and len(profiles) == 1  # the empty row is skipped
    p = profiles[0]
    assert p.expert_ratings == {"business_impact": 4}
    assert p.indicators == {"credit_score": 71, "intercontinental": True, "transport_mode": "sea"}
    assert p.expert_risk_score == 55.0


def test_row_errors_are_reported_not_raised(model):
    rows = [{"supplier_id": "S1", "business_impact": "3.5"}, {"name": "no id"},
            {"supplier_id": "S2"}, {"supplier_id": "S2"}]
    profiles, errors = rows_to_profiles(rows, model)
    assert [p.supplier_id for p in profiles] == ["S2"]
    assert len(errors) == 3
    assert any("whole number" in e for e in errors)
    assert any("needs a supplier_id" in e for e in errors)
    assert any("duplicate" in e for e in errors)


def test_factor_named_text_column_is_an_indicator(model):
    profiles, _ = rows_to_profiles([{"supplier_id": "S1", "compliance_status": "major_findings"},
                                    {"supplier_id": "S2", "compliance_status": "5"}], model)
    assert profiles[0].indicators == {"compliance_status": "major_findings"} and not profiles[0].expert_ratings
    assert profiles[1].expert_ratings == {"compliance_status": 5}  # numeric = expert override


def test_assessment_row_has_spreadsheet_columns(evaluator):
    row = assessment_to_row(evaluator.assess("SUP-004"))
    assert row["risk_class"] == "high" and row["calculated_class"] == "medium" and row["escalated"]
    assert {"dim_severity", "dim_financial", "dim_supply_chain", "dim_esg_compliance"} <= set(row)
    assert row["score"] == pytest.approx(41.75)


@pytest.mark.parametrize("view", ["risk", "performance"])
def test_one_sheet_serves_every_view(view):
    """Rows written once are read identically for each view (shared criteria, view-independent parsing)."""
    from conftest import DATA_DIR

    from supplier_risk_agent import load_risk_model

    model = load_risk_model(view=view)
    source = JsonFileSource(DATA_DIR / "sample_suppliers.json")
    profiles = [source.get_supplier(i) for i in source.list_supplier_ids()]
    rows = from_csv(to_csv([profile_to_row(p, load_risk_model()) for p in profiles]))
    restored, errors = rows_to_profiles(rows, model)
    assert not errors

    def scores(src):
        return {a.supplier_id: (a.overall_score, a.risk_class) for a in SupplierRiskEvaluator(src, model).assess_all()}

    assert scores(InMemorySource(restored)) == scores(source)


def test_criterion_keys_do_not_shadow_numeric_indicators():
    """A number under a criterion's name is read as an expert rating, so no numeric indicator may share it."""
    from supplier_risk_agent.models.config import criteria_catalogue

    catalogue = criteria_catalogue()
    text_indicators = {"compliance_status", "transport_mode"}
    sources = {c["source"] for c in catalogue.values()} - {"expert_assessment"} - text_indicators
    assert not set(catalogue) & sources
