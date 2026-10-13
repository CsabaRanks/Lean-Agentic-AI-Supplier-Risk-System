"""Locale rendering does not change domain values or translate authored content."""

import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import pandas as pd
from pydantic import ValidationError

from supplier_risk_agent import load_risk_model
from supplier_risk_agent.tools.corrections import CorrectionRequest

spec = importlib.util.spec_from_file_location(
    "ui_i18n_test", Path(__file__).parents[1] / "ui/i18n.py"
)
i18n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("de-DE", "de"),
        ("de", "de"),
        ("DE-at", "de"),
        ("en-US", "en"),
        ("fr-FR", "en"),
        (None, "en"),
        ("", "en"),
    ],
)
def test_browser_language(locale, expected):
    assert i18n.browser_language(locale) == expected


@pytest.mark.parametrize(
    ("lang", "number", "date"),
    [
        ("de", "1.234,50", "13.10.2026 09:30:00 UTC+0000"),
        ("en", "1,234.50", "10/13/2026 09:30:00 UTC+0000"),
    ],
)
def test_localized_display_preserves_values(monkeypatch, lang, number, date):
    monkeypatch.setattr(i18n, "language", lambda: lang)
    data = pd.DataFrame(
        {"score": [1234.5], "reason": ["Risk"], "recorded_at": ["2026-10-13T09:30:00+00:00"]}
    )
    original = data.copy(deep=True)
    styled = i18n.table(data)
    assert i18n.number(1234.5) == number
    assert i18n.date(data.recorded_at[0]) == date
    assert styled._display_funcs[(0, 0)](1234.5) == number
    assert styled._display_funcs[(0, 1)]("Risk") == "Risk"
    pd.testing.assert_frame_equal(data, original)


def test_translated_validation_and_generated_rules(monkeypatch):
    monkeypatch.setattr(i18n, "language", lambda: "de")
    with pytest.raises(ValidationError) as exc:
        CorrectionRequest(
            supplier_id="SUP-003",
            changes=[{"field": "qualified_sources", "kind": "data_correction"}],
            reason="",
        )
    assert "Begründung" in i18n.error_text(exc.value)
    assert (
        i18n.message("raised the class from 'medium' to at least 'high'")
        == "Klasse von „Mittel“ auf mindestens „Hoch“ erhöht"
    )
    assert i18n.parse_input("41,75") == "41.75"
    assert i18n.parse_input("minor_findings") == "minor_findings"


def test_catalog_covers_bundled_criteria_and_recommendations():
    catalog = i18n.catalog()
    for view in ("risk", "performance"):
        model = load_risk_model(view=view)
        for dimension in model.dimensions:
            assert dimension.label in catalog
            for factor in dimension.factors:
                assert factor.key in catalog and factor.label in catalog
        # All user-facing action prose in the bundled model is translated centrally.
        import yaml

        path = (
            Path(__file__).parents[1] / f"src/supplier_risk_agent/config/default_{view}_model.yaml"
        )
        data = yaml.safe_load(path.read_text())
        for definition in data["actions"].values():
            for action in definition["actions"]:
                assert action in catalog
        for definition in data.get("factor_actions", []) + data.get("dimension_triggers", []):
            assert definition["action"] in catalog
    for key, translations in catalog.items():
        assert set(translations) == {"de", "en"}, key
        import string

        fields = lambda text: {field for _, field, _, _ in string.Formatter().parse(text) if field}
        assert fields(translations["de"]) == fields(translations["en"]), key
    # This is a checked-in catalog, not a runtime translation service.
    json.dumps(catalog, ensure_ascii=False)
