"""Scoring trace: how one supplier's score and class came about, step by step.

Pure and deterministic, derived from the same results the scoring engine
produced (``RiskAssessment``) plus the profile that went in. Available without
any API key; the optional LLM explanation only reads this trace.

Score contributions follow the engine's aggregation (``tools.scoring``):

    effective weight  e_f = theta_f / sum(theta of rated criteria in f's dimension)
                            * W_d / sum(W of dimensions with data)
    contribution      c_f = e_f * (r_f - r_min) / (r_max - r_min) * 100

The contributions of all rated criteria add up to the internal score
(0 = favourable ... 100 = unfavourable). Missing criteria have no effective
weight; their nominal weight is redistributed within the dimension, and the
weight of dimensions without any data across the other dimensions.

Rules that do not add points are listed separately (``non_additive``):
escalation rules (class floors), the data-completeness check, and a class set
by a reviewer.

Every entry has an ``id`` (``<view>:<criterion>``, ``<view>:dim:<key>``,
``<view>:rule:<criterion>``, ``<view>:completeness``, ``<view>:class``,
``<view>:score``) so that explanations can cite it.
"""

from __future__ import annotations

from typing import Any

from ..models.config import RiskModelConfig, WeightSet
from ..models.domain import RiskAssessment, SupplierProfile
from .indicators import describe_source, source_inputs

RATING_SCALE = "1 = favourable ... 5 = unfavourable (same direction in every view); null = no data"


def rating_origin(profile: SupplierProfile, factor_key: str, source: str, rating: int | None) -> str:
    """Where a criterion's rating came from."""
    if rating is None:
        return "missing"
    if factor_key in profile.expert_ratings:
        return "expert assessment" if source == "expert_assessment" else "expert override of a derived rating"
    return "derived from input data by rule"


def _inputs(profile: SupplierProfile, factor_key: str, source: str) -> list[dict[str, Any]]:
    rows = []
    if factor_key in profile.expert_ratings:
        rows.append({"input": factor_key, "value": profile.expert_ratings[factor_key],
                     "source": "expert rating (entered by hand)"})
    elif source == "expert_assessment":
        rows.append({"input": factor_key, "value": None, "source": "missing: expert rating not entered"})
    for name in source_inputs(source):
        value = profile.indicators.get(name)
        if value is None:
            origin = "missing: no value and no source"
        else:
            origin = profile.indicator_sources.get(name) or "entered by hand (no source or data date recorded)"
        rows.append({"input": name, "value": value, "source": origin})
    return rows


def scoring_trace(assessment: RiskAssessment, profile: SupplierProfile, model: RiskModelConfig,
                  weights: WeightSet | None = None) -> dict[str, Any]:
    """Structured, citable explanation of one supplier's result in one view."""
    view = model.view
    lo, hi = model.rating_scale.min, model.rating_scale.max
    labels = {f.key: (f.label, f.source) for d in model.dimensions for f in d.factors}
    dims = {d.dimension: d for d in assessment.dimension_scores}
    scored_dims = [d for d in assessment.dimension_scores if d.weighted_rating is not None and d.weight > 0]
    total_dim_weight = sum(d.weight for d in scored_dims)

    criteria, contributions = [], {}
    for f in assessment.factor_scores:
        label, source = labels.get(f.factor, (f.factor, f.source))
        dim = dims[f.dimension]
        rated_weight = sum(x.weight for x in assessment.factor_scores
                           if x.dimension == f.dimension and x.rating is not None)
        if f.rating is None or rated_weight == 0 or total_dim_weight == 0:
            effective, points = 0.0, None
        else:
            effective = f.weight / rated_weight * dim.weight / total_dim_weight
            points = effective * (f.rating - lo) / (hi - lo) * 100
            contributions[f.factor] = points
        criteria.append({
            "id": f"{view}:{f.factor}",
            "key": f.factor,
            "label": label,
            "dimension": f.dimension,
            "rating": f.rating,
            "rating_origin": rating_origin(profile, f.factor, source, f.rating),
            "rule": describe_source(source),
            "basis": f.rationale or f.source,
            "inputs": _inputs(profile, f.factor, source),
            "nominal_weight": round(f.weight, 4),
            "effective_weight": round(effective, 4),
            "contribution_points": round(points, 2) if points is not None else None,
        })

    dimensions = [{
        "id": f"{view}:dim:{d.dimension}",
        "key": d.dimension,
        "label": d.label,
        "nominal_weight": d.weight,
        "completeness": d.completeness,
        "score": model.to_display(d.score),
        "contribution_points": round(sum(contributions.get(f.factor, 0.0) for f in assessment.factor_scores
                                         if f.dimension == d.dimension), 2) if d.score is not None else None,
    } for d in assessment.dimension_scores]

    ratings = {f.factor: f.rating for f in assessment.factor_scores}
    rules = []
    for rule in model.escalation_rules:
        rating = ratings.get(rule.factor)
        fired = rating is not None and rating >= rule.min_rating
        raised = fired and model.class_rank(rule.floor_class) > model.class_rank(assessment.calculated_class or
                                                                               model.risk_classes[0].key)
        if rating is None:
            effect = "not evaluable: criterion has no data"
        elif not fired:
            effect = "not triggered"
        elif raised:
            effect = f"raised the class from '{assessment.calculated_class}' to at least '{rule.floor_class}'"
        else:
            effect = f"triggered, no effect: class '{assessment.calculated_class}' is already at or above the floor"
        rules.append({
            "id": f"{view}:rule:{rule.factor}",
            "type": "escalation rule (class floor, not additive)",
            "criterion": rule.factor,
            "condition": f"rating >= {rule.min_rating}",
            "rating": rating,
            "floor_class": rule.floor_class,
            "fired": fired,
            "effect": effect,
            "reason": rule.reason,
        })
    rules.append({
        "id": f"{view}:completeness",
        "type": "data completeness check (not additive)",
        "completeness": assessment.data_completeness,
        "minimum": model.min_data_completeness,
        "fired": assessment.data_completeness < model.min_data_completeness,
        "effect": ("flags the supplier for human review; the score uses only the rated criteria"
                   if assessment.data_completeness < model.min_data_completeness else "passed"),
    })
    if assessment.manual_override:
        rules.append({
            "id": f"{view}:override",
            "type": "class set by a reviewer (not additive)",
            "fired": True,
            "effect": f"class set to '{assessment.risk_class}'",
            "reason": assessment.review_comment or "",
        })

    internal = assessment.overall_score
    thresholds = [{"class": c.key, "from_score": c.min_score} for c in model.risk_classes]
    weights_label = f"{assessment.weights_scope}/{assessment.weights_origin}"
    if weights is not None and weights.version is not None:
        weights_label += f" v{weights.version}"
    return {
        "view": view,
        "question": model.view_question,
        "model": f"{model.name}@{model.version}",
        "weights": weights_label,
        "rating_scale": RATING_SCALE,
        "score": {
            "id": f"{view}:score",
            "label": model.score_label,
            "orientation": model.score_orientation,
            "value": model.to_display(internal),
            "internal_value": internal,
            "sum_of_contributions": round(sum(contributions.values()), 2) if contributions else None,
            "note": ("internal scale: 0 = favourable ... 100 = unfavourable; contributions are internal points"
                     + ("; the displayed performance score is 100 minus the internal score"
                        if model.score_orientation == "higher_is_better" else "")),
        },
        "class": {
            "id": f"{view}:class",
            "from_score": assessment.calculated_class,
            "final": assessment.risk_class,
            "thresholds_internal_scale": thresholds,
        },
        "data_completeness": assessment.data_completeness,
        "missing_criteria": [f.factor for f in assessment.factor_scores if f.rating is None],
        "criteria": criteria,
        "dimensions": dimensions,
        "non_additive": rules,
    }


def trace_ids(trace: dict[str, Any]) -> set[str]:
    """All citable entry ids of one view's trace."""
    ids = {trace["score"]["id"], trace["class"]["id"]}
    for section in ("criteria", "dimensions", "non_additive"):
        ids.update(entry["id"] for entry in trace[section])
    return ids
