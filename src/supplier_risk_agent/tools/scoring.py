"""Deterministic scoring engine.

Pure functions only — no LLM, no I/O. Given the same profile, model and
weights, the result is always identical, which keeps scores reproducible and
auditable. Agents call these functions; an LLM may later *explain* results,
but never computes them.

Calculation (theta_f = effective weight of factor f from a WeightSet)
--------------------------------------------------------------------
1. Every factor gets a rating r_f in [1, 5] (or None if data is missing).
2. Dimension weight   W_d = sum(theta_f for f in d)
   Dimension rating   R_d = sum(theta_f * r_f) / sum(theta_f)   over available f in d
3. Weighted rating    R   = sum(W_d * R_d) / sum(W_d)            over dimensions with data
   (with complete data this is simply sum(theta_f * r_f))
4. Normalised score   S   = (R - 1) / (5 - 1) * 100               -> 0..100
5. Risk class         = highest class whose ``min_score`` <= S
6. Escalation rules may raise (never lower) the class.

Missing factors are excluded and the remaining weights re-normalised inside
their dimension. The share of weight actually backed by data is reported as
``data_completeness``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.config import GLOBAL_SCOPE, RiskModelConfig, WeightSet
from ..models.domain import (
    ActionRecommendation,
    ClassOverride,
    DimensionScore,
    Escalation,
    FactorScore,
    RiskAssessment,
    SupplierProfile,
)
from .indicators import rate_factor


@dataclass(frozen=True)
class AggregateResult:
    dimension_scores: list[DimensionScore]
    weighted_rating: float | None
    overall_score: float | None
    data_completeness: float


def normalise(rating: float, model: RiskModelConfig) -> float:
    lo, hi = model.rating_scale.min, model.rating_scale.max
    return round((rating - lo) / (hi - lo) * 100, 2)


def resolve_weights(
    material_group: str | None, active: dict[str, WeightSet], model: RiskModelConfig
) -> WeightSet:
    """Pick the most specific weight set for a supplier.

    Order: active set for its material group -> configured material group
    default -> active global set -> configured global default.
    """
    if material_group and material_group in active:
        return active[material_group]
    if material_group and material_group in model.material_group_weights:
        return model.default_weights(material_group)
    return active.get(GLOBAL_SCOPE) or model.default_weights()


def score_factors(profile: SupplierProfile, model: RiskModelConfig, weights: WeightSet) -> list[FactorScore]:
    scores: list[FactorScore] = []
    for dim in model.dimensions:
        for fac in dim.factors:
            rating, rationale = rate_factor(profile, fac.key, fac.source)
            scores.append(
                FactorScore(
                    factor=fac.key,
                    dimension=dim.key,
                    rating=rating,
                    weight=weights.factor_weights.get(fac.key, 0.0),
                    source=fac.source,
                    rationale=rationale,
                )
            )
    return scores


def aggregate(factor_scores: list[FactorScore], model: RiskModelConfig) -> AggregateResult:
    dims: list[DimensionScore] = []
    for dim in model.dimensions:
        own = [f for f in factor_scores if f.dimension == dim.key]
        avail = [f for f in own if f.rating is not None]
        w_dim = sum(f.weight for f in own)
        w_avail = sum(f.weight for f in avail)
        rating = sum(f.weight * f.rating for f in avail) / w_avail if w_avail > 0 else None
        dims.append(
            DimensionScore(
                dimension=dim.key,
                label=dim.label,
                weight=round(w_dim, 4),
                weighted_rating=round(rating, 4) if rating is not None else None,
                score=normalise(rating, model) if rating is not None else None,
                completeness=round(w_avail / w_dim, 4) if w_dim > 0 else 0.0,
            )
        )

    completeness = round(sum(f.weight for f in factor_scores if f.rating is not None), 4)
    scored = [d for d in dims if d.weighted_rating is not None and d.weight > 0]
    if not scored:
        return AggregateResult(dims, None, None, completeness)

    w_total = sum(d.weight for d in scored)
    overall = sum(d.weight * d.weighted_rating for d in scored) / w_total
    return AggregateResult(dims, round(overall, 4), normalise(overall, model), completeness)


def classify(score: float, model: RiskModelConfig) -> str:
    current = model.risk_classes[0].key
    for cls in model.risk_classes:  # sorted ascending by min_score
        if score >= cls.min_score:
            current = cls.key
    return current


def apply_escalations(
    risk_class: str, factor_scores: list[FactorScore], model: RiskModelConfig
) -> tuple[str, list[Escalation]]:
    ratings = {f.factor: f.rating for f in factor_scores}
    fired: list[Escalation] = []
    final = risk_class
    for rule in model.escalation_rules:
        rating = ratings.get(rule.factor)
        if rating is not None and rating >= rule.min_rating:
            fired.append(Escalation(rule_factor=rule.factor, floor_class=rule.floor_class, reason=rule.reason))
            if model.class_rank(rule.floor_class) > model.class_rank(final):
                final = rule.floor_class
    return final, fired


def assess_profile(profile: SupplierProfile, model: RiskModelConfig, weights: WeightSet) -> RiskAssessment:
    """Full deterministic assessment of one supplier (without recommendations)."""
    factors = score_factors(profile, model, weights)
    agg = aggregate(factors, model)

    calculated = final = None
    escalations: list[Escalation] = []
    reasons: list[str] = []
    if agg.overall_score is None:
        reasons.append("no factor could be rated — score cannot be computed")
    else:
        calculated = classify(agg.overall_score, model)
        final, escalations = apply_escalations(calculated, factors, model)

    if agg.data_completeness < model.min_data_completeness:
        missing = [f.factor for f in factors if f.rating is None]
        reasons.append(
            f"data completeness {agg.data_completeness:.0%} below "
            f"{model.min_data_completeness:.0%} (missing: {', '.join(missing)})"
        )

    return RiskAssessment(
        supplier_id=profile.supplier_id,
        supplier_name=profile.name,
        material_group=profile.material_group,
        model_name=model.name,
        model_version=model.version,
        view=model.view,
        weights_scope=weights.scope,
        weights_origin=weights.origin,
        overall_score=agg.overall_score,
        weighted_rating=agg.weighted_rating,
        risk_class=final,
        calculated_class=calculated,
        data_completeness=agg.data_completeness,
        factor_scores=factors,
        dimension_scores=agg.dimension_scores,
        escalations=escalations,
        requires_human_review=bool(reasons),
        review_reasons=reasons,
    )


def apply_override(assessment: RiskAssessment, override: ClassOverride, reviewer: str) -> RiskAssessment:
    """Set a reviewer's risk class. Scores stay untouched; the change is flagged."""
    comment = f"{reviewer}: {override.comment}" if override.comment else f"class set by {reviewer}"
    return assessment.model_copy(
        update={
            "risk_class": override.risk_class,
            "manual_override": True,
            "review_comment": comment,
            "requires_human_review": False,
        }
    )


def recommend(assessment: RiskAssessment, model: RiskModelConfig) -> list[ActionRecommendation]:
    risk_class = assessment.risk_class
    if risk_class is None:
        return []

    recs: list[ActionRecommendation] = []
    class_actions = model.actions.get(risk_class)
    if class_actions:
        for action in class_actions.actions:
            recs.append(
                ActionRecommendation(
                    priority=risk_class,
                    action=action,
                    trigger=f"overall risk class '{risk_class}'",
                    review_cycle=class_actions.review_cycle,
                )
            )

    by_dim = {d.dimension: d for d in assessment.dimension_scores}
    for trig in model.dimension_triggers:
        dim = by_dim.get(trig.dimension)
        if dim and dim.score is not None and dim.score >= trig.min_score:
            recs.append(
                ActionRecommendation(
                    priority="targeted",
                    action=trig.action,
                    trigger=f"{dim.label} score {dim.score:.0f} >= {trig.min_score:.0f}",
                )
            )

    # action framework: the most specific entry per factor whose level is reached
    rules: dict[str, list] = {}
    for fa in model.factor_actions:
        rules.setdefault(fa.factor, []).append(fa)
    for f in assessment.factor_scores:
        if f.rating is None or f.factor not in rules:
            continue
        reached = [fa for fa in rules[f.factor] if f.rating >= fa.min_rating]
        if reached:
            fa = max(reached, key=lambda r: r.min_rating)
            recs.append(
                ActionRecommendation(
                    priority="factor",
                    action=fa.action,
                    trigger=f"{f.factor} rated {f.rating} ({f.rationale})",
                    factor=f.factor,
                    owner=fa.owner,
                )
            )

    for esc in assessment.escalations:
        recs.append(
            ActionRecommendation(
                priority=esc.floor_class,
                action=f"Investigate escalation on '{esc.rule_factor}': {esc.reason}",
                trigger=f"escalation rule on factor '{esc.rule_factor}'",
            )
        )
    return recs
