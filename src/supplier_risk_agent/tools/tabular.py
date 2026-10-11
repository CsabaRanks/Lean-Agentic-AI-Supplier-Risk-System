"""Flat, spreadsheet-style rows <-> domain objects.

Spreadsheets and CSV files hold one supplier per row. This module converts
between such rows and :class:`SupplierProfile` / :class:`RiskAssessment`
objects. It contains no scoring logic. Column roles are derived from the risk
model, so a changed model changes the expected columns automatically:

* meta columns: ``supplier_id, name, material_group, country, annual_spend``
* ``expert_<view>_score`` (e.g. ``expert_risk_score``, ``expert_performance_score``): holistic
  expert label (0..100) per view, used for calibration
* a column named like a risk factor with a numeric value (e.g. ``business_impact = 4``):
  expert rating 1..5
* any other column: a raw indicator (e.g. ``credit_score``, ``transport_mode``). This includes
  factor-named columns with text values: ``compliance_status = compliant`` is the raw
  indicator that the compliance factor's rating source reads

Empty cells mean "no data".
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections.abc import Iterable
from typing import Any

from ..models.config import RiskModelConfig, criteria_catalogue
from ..models.domain import RiskAssessment, SupplierProfile
from .indicators import source_inputs

META_COLUMNS = ["supplier_id", "name", "material_group", "country", "annual_spend"]
LABEL_COLUMN = "expert_risk_score"  # label column of the risk view
_LABEL_RE = re.compile(r"^expert_(?P<view>[a-z0-9_]+)_score$")


def label_view(column: str) -> str | None:
    """'expert_performance_score' -> 'performance'; None if the column is not a label column."""
    match = _LABEL_RE.match(column)
    return match["view"] if match else None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and value.strip() == ""


def _parse(value: Any) -> Any:
    """Turn spreadsheet cell text into bool / int / float / str."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in {"true", "yes", "ja"}:
        return True
    if text.lower() in {"false", "no", "nein"}:
        return False
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def _as_int(value: Any) -> int:
    number = float(value)
    if not number.is_integer():
        raise ValueError(f"expected a whole number, got {value!r}")
    return int(number)


def input_columns(models: RiskModelConfig | Iterable[RiskModelConfig]) -> list[str]:
    """Suggested column order for an input sheet covering one or several views.

    meta, expert ratings, raw indicators (derived from the criteria's rating
    sources), then one expert-label column per view.
    """
    models = [models] if isinstance(models, RiskModelConfig) else list(models)
    factors = [f for m in models for d in m.dimensions for f in d.factors]
    expert = [f.key for f in factors if f.source == "expert_assessment"]
    indicators = [name for f in factors for name in source_inputs(f.source)]
    labels = [m.label_column for m in models]
    return list(dict.fromkeys(META_COLUMNS + expert + indicators + labels))


def all_view_columns() -> list[str]:
    """Input columns for every bundled view (shared criteria appear once)."""
    from ..models.config import available_views, load_risk_model

    return input_columns([load_risk_model(view=v) for v in available_views()])


def row_to_profile(row: dict[str, Any], model: RiskModelConfig) -> SupplierProfile:
    # Rows are read independently of the view: every criterion of the shared catalogue
    # (plus any the model defines itself) counts, so one sheet serves all views.
    factor_keys = set(criteria_catalogue()) | set(model.factor_keys())
    values = {k: _parse(v) for k, v in row.items() if k and not _is_empty(v)}
    if "supplier_id" not in values:
        raise ValueError("every row needs a supplier_id")
    numeric = {k: v for k, v in values.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    expert_ratings = {k: _as_int(v) for k, v in numeric.items() if k in factor_keys}
    labels = {label_view(k): float(v) for k, v in values.items() if label_view(k)}
    indicators = {
        k: v for k, v in values.items()
        if k not in expert_ratings and k not in META_COLUMNS and not label_view(k)
    }
    return SupplierProfile(
        supplier_id=str(values["supplier_id"]),
        name=str(values.get("name", values["supplier_id"])),
        material_group=str(values["material_group"]) if "material_group" in values else None,
        country=str(values.get("country", "")),
        annual_spend=float(values["annual_spend"]) if "annual_spend" in values else None,
        expert_ratings=expert_ratings,
        indicators=indicators,
        expert_risk_score=labels.pop("risk", None),
        expert_scores=labels,
    )


def rows_to_profiles(rows: list[dict[str, Any]], model: RiskModelConfig) -> tuple[list[SupplierProfile], list[str]]:
    """Convert rows; returns (profiles, errors). Rows without any content are skipped."""
    profiles, errors, seen = [], [], set()
    for i, row in enumerate(rows, start=1):
        if all(_is_empty(v) for v in row.values()):
            continue
        try:
            profile = row_to_profile(row, model)
        except (ValueError, TypeError) as exc:
            errors.append(f"row {i}: {exc}")
            continue
        if profile.supplier_id in seen:
            errors.append(f"row {i}: duplicate supplier_id '{profile.supplier_id}'")
            continue
        seen.add(profile.supplier_id)
        profiles.append(profile)
    return profiles, errors


def profile_to_row(profile: SupplierProfile, model: RiskModelConfig) -> dict[str, Any]:
    row: dict[str, Any] = {c: None for c in input_columns(model)}
    row.update({
        "supplier_id": profile.supplier_id,
        "name": profile.name,
        "material_group": profile.material_group,
        "country": profile.country or None,
        "annual_spend": profile.annual_spend,
        LABEL_COLUMN: profile.expert_risk_score,
    })
    row.update(profile.expert_ratings)
    row.update(profile.indicators)
    row.update({f"expert_{view}_score": value for view, value in profile.expert_scores.items()})
    return row


def assessment_to_row(a: RiskAssessment, model: RiskModelConfig | None = None) -> dict[str, Any]:
    """One result row per supplier, as shown in the portfolio table and exported to CSV.

    With ``model``, scores are given in the view's reading direction (e.g. performance:
    higher is better); without it, on the internal scale (0 = favourable).
    """
    shown = model.to_display if model else (lambda v: v)
    first_action = next((r for r in a.recommendations if r.review_cycle), None)
    row: dict[str, Any] = {
        "supplier_id": a.supplier_id,
        "name": a.supplier_name,
        "material_group": a.material_group,
        "view": a.view,
        "score": shown(a.overall_score),
        "risk_class": a.risk_class,
        "calculated_class": a.calculated_class,
        "escalated": bool(a.escalations),
        "manual_override": a.manual_override,
        "data_completeness": a.data_completeness,
        "needs_review": a.requires_human_review,
        "review_cycle": first_action.review_cycle if first_action else None,
        "weights": f"{a.weights_scope}/{a.weights_origin}",
    }
    for d in a.dimension_scores:
        row[f"dim_{d.dimension}"] = shown(d.score)
    row["review_reasons"] = "; ".join(a.review_reasons) or None
    row["review_comment"] = a.review_comment
    return row


def to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    columns = list(dict.fromkeys(k for row in rows for k in row))
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if _is_empty(row.get(k)) else row.get(k)) for k in columns})
    return buffer.getvalue()


def from_csv(text: str) -> list[dict[str, Any]]:
    """Read CSV text; accepts comma- or semicolon-separated files (common in European Excel exports)."""
    sample = text[:2048]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter))
