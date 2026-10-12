"""Controlled corrections of one supplier's inputs: propose, preview, confirm.

Two kinds of change are kept apart:

* **data correction**: a wrong or missing input value is fixed, e.g. a credit
  score, an on-time rate, or the expert rating of a criterion whose source *is*
  an expert assessment (availability, business impact, ...);
* **expert override**: an expert rating replaces the rating a rule derived from
  input data, e.g. credit risk rated 3 although the credit score maps to 4.
  The scoring engine already gives an expert rating precedence
  (``tools.indicators.rate_factor``); the override only makes it explicit and
  documented.

Weights, class thresholds and rules cannot be changed here; they stay in the
calibration and approval process.

The flow is pure and deterministic: ``preview_correction`` applies the changes
to a copy of the rows, re-scores the supplier in every view with the same
engine and weights, and returns the before/after comparison. Nothing changes
until the caller adopts ``new_rows`` (after explicit confirmation) and records
the correction with ``HistoryStore.record_correction``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..models.config import RiskModelConfig, WeightSet
from ..models.domain import RiskAssessment, SupplierProfile
from ..providers.base import enrich
from .explain import scoring_trace
from .indicators import source_inputs
from .scoring import assess_profile, recommend, resolve_weights
from .tabular import _is_empty, _parse, label_view, rows_to_profiles

ChangeKind = Literal["data_correction", "expert_override"]
DATA, OVERRIDE = "data_correction", "expert_override"


class FieldChange(BaseModel):
    field: str
    kind: ChangeKind
    old_value: Any = None
    new_value: Any = None


class CorrectionRequest(BaseModel):
    supplier_id: str
    changes: list[FieldChange] = Field(min_length=1)
    reason: str
    entered_by: str | None = Field(default=None, description="Name as typed by the user; not a verified identity")

    @field_validator("reason")
    @classmethod
    def _reason_required(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("a reason for the change is required")
        return value.strip()


def parse_cell(text: Any) -> Any:
    """A value typed into a table cell: 'none' clears it; numbers and booleans are parsed as on CSV import."""
    if text is None or (isinstance(text, str) and text.strip().lower() in {"", "none", "null"}):
        return None
    return _parse(text)


def correctable_fields(models: list[RiskModelConfig]) -> dict[str, dict[str, Any]]:
    """Fields a correction may touch: field -> {kind, criteria (view:key), label}.

    Inputs of rating sources are data corrections, as are expert ratings of
    expert-assessed criteria. A criterion with a derived rating can receive an
    expert override, unless its input has the same name as the criterion (the
    row format could not hold both).
    """
    fields: dict[str, dict[str, Any]] = {}
    for model in models:
        for dim in model.dimensions:
            for fac in dim.factors:
                ref = f"{model.view}:{fac.key}"
                if fac.source == "expert_assessment":
                    entry = fields.setdefault(fac.key, {"kind": DATA, "criteria": [], "label": fac.label,
                                                        "expects": "expert rating 1..5"})
                    entry["criteria"].append(ref)
                    continue
                inputs = source_inputs(fac.source)
                for name in inputs:
                    entry = fields.setdefault(name, {"kind": DATA, "criteria": [], "label": name,
                                                     "expects": "input value"})
                    entry["criteria"].append(ref)
                if fac.key not in inputs:
                    entry = fields.setdefault(fac.key, {"kind": OVERRIDE, "criteria": [], "label": fac.label,
                                                        "expects": "expert rating 1..5 replacing the derived rating"})
                    entry["criteria"].append(ref)
    return fields


def field_spec(field: str, fields: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """How a field may be corrected; None if it cannot be corrected here.

    Criterion inputs and overrides follow ``correctable_fields``. Master data and other input columns
    are data corrections. The supplier id and expert labels (calibration) are not correctable here.
    """
    if field in fields:
        return fields[field]
    if not field or field == "supplier_id" or label_view(field):
        return None
    return {"kind": DATA, "criteria": [], "label": field, "expects": "input value", "known": False}


def _check_value(change: FieldChange, spec: dict[str, Any]) -> None:
    if change.new_value is None or spec["expects"] == "input value":
        return
    value = change.new_value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != int(value) \
            or not 1 <= int(value) <= 5:
        raise ValueError(f"'{change.field}' expects a whole number from 1 to 5, got {value!r}")


def apply_changes(rows: list[dict[str, Any]], request: CorrectionRequest,
                  models: list[RiskModelConfig]) -> list[dict[str, Any]]:
    """A copy of ``rows`` with the request applied to the supplier's row. Raises ValueError if invalid."""
    allowed = correctable_fields(models)
    new_rows = [dict(r) for r in rows]
    target = next((r for r in new_rows if str(r.get("supplier_id")) == request.supplier_id), None)
    if target is None:
        raise ValueError(f"unknown supplier '{request.supplier_id}'")
    for change in request.changes:
        spec = field_spec(change.field, allowed)
        if spec is not None and spec.get("known") is False and change.field not in target:
            spec = None  # neither a known input nor an existing column of this supplier
        if spec is None:
            raise ValueError(f"'{change.field}' cannot be corrected here (weights and rules go through calibration)")
        if change.kind != spec["kind"]:
            raise ValueError(f"'{change.field}' is a {spec['kind'].replace('_', ' ')}, not a "
                             f"{change.kind.replace('_', ' ')}")
        _check_value(change, spec)
        target[change.field] = change.new_value
    if all(target.get(c.field) == r.get(c.field) for c in request.changes
           for r in rows if str(r.get("supplier_id")) == request.supplier_id):
        raise ValueError("the proposed values equal the current values")
    return new_rows


def assess_supplier(rows: list[dict[str, Any]], supplier_id: str, models: list[RiskModelConfig],
                    active_weights: dict[str, dict[str, WeightSet]] | None = None,
                    providers=()) -> dict[str, tuple[RiskAssessment, SupplierProfile, WeightSet]]:
    """Deterministic assessment of one supplier in every view, with the same engine as a run."""
    out = {}
    for model in models:
        profiles, _ = rows_to_profiles(rows, model)
        profile = next((p for p in profiles if p.supplier_id == supplier_id), None)
        if profile is None:
            raise ValueError(f"unknown supplier '{supplier_id}'")
        if providers:
            profile = enrich([profile], list(providers))[0][0]
        weights = resolve_weights(profile.material_group, (active_weights or {}).get(model.view, {}), model)
        result = assess_profile(profile, model, weights)
        result = result.model_copy(update={"recommendations": recommend(result, model)})
        out[model.view] = (result, profile, weights)
    return out


def _fired(trace: dict[str, Any]) -> list[str]:
    return [r["id"] for r in trace["non_additive"] if r["fired"]]


def compare(before: dict, after: dict, models: list[RiskModelConfig]) -> dict[str, dict[str, Any]]:
    """Before/after per view: score, class, completeness, changed criteria and changed rules."""
    by_view = {m.view: m for m in models}
    out = {}
    for view, (a_before, p_before, w_before) in before.items():
        a_after, p_after, w_after = after[view]
        model = by_view[view]
        t_before = scoring_trace(a_before, p_before, model, w_before)
        t_after = scoring_trace(a_after, p_after, model, w_after)
        c_before = {c["key"]: c for c in t_before["criteria"]}
        changed = []
        for c in t_after["criteria"]:
            old = c_before[c["key"]]
            if (old["rating"], old["rating_origin"], old["contribution_points"]) != \
                    (c["rating"], c["rating_origin"], c["contribution_points"]):
                changed.append({
                    "criterion": c["key"],
                    "rating": [old["rating"], c["rating"]],
                    "origin": [old["rating_origin"], c["rating_origin"]],
                    "contribution_points": [old["contribution_points"], c["contribution_points"]],
                })
        fired_before, fired_after = set(_fired(t_before)), set(_fired(t_after))
        out[view] = {
            "score_label": model.score_label,
            "score": [t_before["score"]["value"], t_after["score"]["value"]],
            "class": [t_before["class"]["final"], t_after["class"]["final"]],
            "class_from_score": [t_before["class"]["from_score"], t_after["class"]["from_score"]],
            "data_completeness": [t_before["data_completeness"], t_after["data_completeness"]],
            "needs_review": [a_before.requires_human_review, a_after.requires_human_review],
            "changed_criteria": changed,
            "rules_now_triggered": sorted(fired_after - fired_before),
            "rules_no_longer_triggered": sorted(fired_before - fired_after),
            "model": t_after["model"],
            "weights": t_after["weights"],
        }
    return out


def preview_correction(rows: list[dict[str, Any]], request: CorrectionRequest, models: list[RiskModelConfig],
                       active_weights: dict[str, dict[str, WeightSet]] | None = None,
                       providers=()) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """(rows with the correction applied, before/after comparison). Does not modify ``rows``."""
    current = next((r for r in rows if str(r.get("supplier_id")) == request.supplier_id), {})
    for change in request.changes:
        change.old_value = current.get(change.field)
    new_rows = apply_changes(rows, request, models)
    before = assess_supplier(rows, request.supplier_id, models, active_weights, providers)
    after = assess_supplier(new_rows, request.supplier_id, models, active_weights, providers)
    return new_rows, compare(before, after, models)


def _same(a: Any, b: Any) -> bool:
    """Cell equality as a user sees it: empty == empty, 41 == 41.0, ' x ' == 'x'."""
    if _is_empty(a) or _is_empty(b):
        return _is_empty(a) and _is_empty(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or str(a).lower() == str(b).lower()
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def split_table_edits(rows: list[dict[str, Any]], edited: list[dict[str, Any]], assessed: set[str],
                      models: list[RiskModelConfig]) -> tuple[list[dict[str, Any]], dict[str, list[FieldChange]],
                                                              list[str]]:
    """Separate first data entry from changes to suppliers that already have a result.

    Returns (rows to keep, pending changes per assessed supplier, notes). Rows of suppliers without
    a result (new rows, rows not yet calculated) are taken as edited. For assessed suppliers the
    current values stay in place and every changed cell becomes a pending ``FieldChange``, to be
    previewed, justified and confirmed like any correction. Deleting an assessed supplier is not
    applied.
    """
    allowed = correctable_fields(models)
    before = {str(r.get("supplier_id")): r for r in rows if not _is_empty(r.get("supplier_id"))}
    kept, pending, notes, seen = [], {}, [], set()
    for row in edited:
        sid = None if _is_empty(row.get("supplier_id")) else str(row.get("supplier_id"))
        if sid is None or sid not in assessed or sid not in before:
            kept.append(row)
            if sid:
                seen.add(sid)
            continue
        seen.add(sid)
        old = before[sid]
        out = dict(old)
        for field in dict.fromkeys([*old, *row]):
            if _same(old.get(field), row.get(field)):
                continue
            spec = field_spec(field, allowed)
            if spec is None:
                notes.append(f"{sid}: '{field}' cannot be changed here")
                continue
            new_value = None if _is_empty(row.get(field)) else row.get(field)
            if spec["expects"] != "input value" and isinstance(new_value, float) and new_value.is_integer():
                new_value = int(new_value)
            pending.setdefault(sid, []).append(
                FieldChange(field=field, kind=spec["kind"], old_value=old.get(field), new_value=new_value))
        kept.append(out)
    for sid, old in before.items():
        if sid in assessed and sid not in seen:
            kept.append(dict(old))
            notes.append(f"{sid}: evaluated suppliers cannot be deleted in the table; the row was kept")
    return kept, pending, notes
