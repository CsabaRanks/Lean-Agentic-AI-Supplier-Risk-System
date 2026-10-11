"""Supply chain risk (political stability), change complexity (time to exit), action framework,
external providers, reporting and history."""

import pytest
from conftest import DATA_DIR

from supplier_risk_agent import SupplierProfile, SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.providers import (
    CsvIndicatorProvider,
    ErpDeliveryProvider,
    WorldBankWgiProvider,
    enrich,
)
from supplier_risk_agent.tools import HistoryStore, JsonFileSource, rate_factor
from supplier_risk_agent.tools.reporting import (
    ALL_GROUPS,
    action_plan,
    factor_contributions,
    group_summary,
    top_risks,
)


def profile(**indicators):
    return SupplierProfile(supplier_id="X", name="X", country="Region C", indicators=indicators)


@pytest.mark.parametrize("percentile,rating", [(95, 1), (80, 1), (79, 2), (50, 3), (25, 4), (5, 5)])
def test_political_stability_maps_wgi_percentile(percentile, rating):
    r, why = rate_factor(profile(wgi_political_stability=percentile), "country_risk", "political_stability")
    assert r == rating and "WGI" in why


def test_political_stability_falls_back_to_country_index():
    r, why = rate_factor(profile(country_risk_index=72), "country_risk", "political_stability")
    assert r == 4 and "country risk index" in why


@pytest.mark.parametrize("months,rating", [(2, 1), (3, 1), (6, 2), (12, 3), (18, 4), (36, 5)])
def test_change_complexity_from_time_to_exit(months, rating):
    assert rate_factor(profile(time_to_exit_months=months), "switching_complexity", "time_to_exit")[0] == rating


def test_expert_rating_still_overrides_time_to_exit():
    p = profile(time_to_exit_months=36)
    p.expert_ratings["switching_complexity"] = 2
    assert rate_factor(p, "switching_complexity", "time_to_exit") == (2, "expert rating")


def test_supply_chain_sub_score_combines_its_three_factors(model):
    a = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "sample_suppliers.json")).assess("SUP-003")
    dim = next(d for d in a.dimension_scores if d.dimension == "supply_chain")
    factors = {f.factor for f in a.factor_scores if f.dimension == "supply_chain"}
    assert factors == {"country_risk", "sourcing_strategy", "transport_dependency"}
    assert dim.score == pytest.approx(90.0)


def test_wgi_mock_provider_fills_and_records_provenance():
    source = JsonFileSource(DATA_DIR / "sample_suppliers.json")
    profiles = [source.get_supplier(i) for i in source.list_supplier_ids()]
    enriched, _ = enrich(profiles, [WorldBankWgiProvider.mock()])
    p = next(x for x in enriched if x.supplier_id == "SUP-003")  # Region C
    assert p.indicators["wgi_political_stability"] == 24
    assert "MOCK" in p.indicator_sources["wgi_political_stability"]
    assert "wgi_political_stability" not in profiles[0].indicators  # inputs untouched


def test_provider_never_overwrites_manual_values_and_placeholders_report_not_connected():
    p = profile(wgi_political_stability=99)
    enriched, messages = enrich([p], [WorldBankWgiProvider.mock(), ErpDeliveryProvider()])
    assert enriched[0].indicators["wgi_political_stability"] == 99
    assert any("not connected" in m for m in messages)
    with pytest.raises(NotImplementedError):
        WorldBankWgiProvider.from_api()


def test_csv_provider_reads_a_system_export(tmp_path):
    export = tmp_path / "erp.csv"
    export.write_text("Supplier;OTD %;PPM\nSUP-001;91,5;300\n", encoding="utf-8")
    provider = CsvIndicatorProvider(export, "erp export", {"OTD %": "on_time_rate", "PPM": "quality_ppm"},
                                    key_column="Supplier", as_of="2026-09")
    p = SupplierProfile(supplier_id="SUP-001", name="A")
    enriched, _ = enrich([p], [provider])
    assert enriched[0].indicators == {"on_time_rate": 91.5, "quality_ppm": 300.0}
    assert enriched[0].indicator_sources["on_time_rate"] == "erp export (2026-09)"


def test_evaluator_applies_providers_before_scoring():
    plain = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "sample_suppliers.json")).assess("SUP-001")
    with_wgi = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "sample_suppliers.json"),
                                     providers=[WorldBankWgiProvider.mock()]).assess("SUP-001")
    rationale = lambda a: next(f.rationale for f in a.factor_scores if f.factor == "country_risk")
    assert "country risk index" in rationale(plain) and "WGI" in rationale(with_wgi)


def test_action_framework_per_factor_and_level(model):
    a = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "sample_suppliers.json")).assess("SUP-003")
    factor_actions = {r.factor: r for r in a.recommendations if r.priority == "factor"}
    # availability rated 5 -> the level-5 entry, not the level-4 one
    assert "Start qualifying" in factor_actions["availability"].action
    assert factor_actions["sourcing_strategy"].owner == "category manager"
    assert "credit_risk" in factor_actions and "insolvency_signals" not in factor_actions  # rated 3


def test_unknown_factor_in_action_framework_is_rejected():
    from supplier_risk_agent.models.config import RiskModelConfig

    raw = load_risk_model().model_dump()
    raw["factor_actions"] = [{"factor": "nope", "min_rating": 4, "action": "x"}]
    with pytest.raises(ValueError, match="unknown factor"):
        RiskModelConfig.model_validate(raw)


def test_reporting_group_summary_top_risks_and_plan(model):
    assessments = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "calibration_portfolio.json")).assess_all()
    summary = {r["material_group"]: r for r in group_summary(assessments, model)}
    assert summary[ALL_GROUPS]["suppliers"] == 36
    assert sum(summary[g]["suppliers"] for g in ("plastics", "metal_parts", "electronics")) == 36
    top = top_risks(assessments, model, n=3)
    assert len(top) == 3 and top[0]["risk_class"] == "critical" and top[0]["main_drivers"]
    worst = next(a for a in assessments if a.supplier_id == top[0]["supplier_id"])
    total = sum(points for _, points in factor_contributions(worst, model))
    assert total == pytest.approx(worst.overall_score, abs=0.1)  # contributions add up (complete data)
    plan = action_plan(assessments)
    assert plan and {"supplier_id", "action", "owner", "level"} <= set(plan[0])


def test_history_records_snapshots_and_trends(tmp_path, model):
    store = HistoryStore(tmp_path)
    ev = SupplierRiskEvaluator(JsonFileSource(DATA_DIR / "sample_suppliers.json"))
    store.record(ev.assess_all(), model, note="first", recorded_at="2026-01-01T00:00:00+00:00")
    store.record(ev.assess_all(), model, approved_by="alice", recorded_at="2026-07-01T00:00:00+00:00")
    assert store.snapshots("risk") == ["2026-01-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00"]
    timeline = store.load("risk", supplier_id="SUP-003")
    assert [r["score"] for r in timeline] == [84.0, 84.0] and timeline[1]["approved_by"] == "alice"
    trend = store.group_trend("risk", material_group="chemicals")
    assert len(trend) == 2 and trend[0]["classes"] == {"critical": 1}
    assert store.load("performance") == []  # one file per view
