"""Summaries for dashboards: per material group, top risks with their drivers, action plan.

Pure functions over finished assessments. Nothing is re-scored here; the
numbers come from the scoring engine and are only grouped and ranked.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

from ..models.config import RiskModelConfig
from ..models.domain import RiskAssessment

ALL_GROUPS = "All material groups"


def factor_contributions(a: RiskAssessment, model: RiskModelConfig) -> list[tuple[str, float]]:
    """Points each factor adds to the internal 0..100 score, largest first.

    contribution_f = weight_f * (rating_f - min) / (max - min) * 100, using the
    effective weights of the assessment. With complete data the contributions
    add up to the internal score.
    """
    lo, hi = model.rating_scale.min, model.rating_scale.max
    labels = {f.key: f.label for d in model.dimensions for f in d.factors}
    contributions = [
        (labels.get(f.factor, f.factor), f.weight * (f.rating - lo) / (hi - lo) * 100)
        for f in a.factor_scores if f.rating is not None
    ]
    return sorted(contributions, key=lambda c: c[1], reverse=True)


def drivers_text(a: RiskAssessment, model: RiskModelConfig, n: int = 2) -> str:
    return ", ".join(f"{label} ({points:.0f})" for label, points in factor_contributions(a, model)[:n])


def group_summary(assessments: list[RiskAssessment], model: RiskModelConfig) -> list[dict[str, Any]]:
    """One row per material group plus a total row: size, mean score, class counts, review and escalations."""
    classes = [c.key for c in model.risk_classes]
    groups: dict[str, list[RiskAssessment]] = {ALL_GROUPS: list(assessments)}
    for a in assessments:
        groups.setdefault(a.material_group or "(none)", []).append(a)

    rows = []
    for group, items in groups.items():
        scored = [a for a in items if a.overall_score is not None]
        counts = Counter(a.risk_class for a in items)
        worst = max(scored, key=lambda a: a.overall_score, default=None)
        rows.append({
            "material_group": group,
            "suppliers": len(items),
            "mean_score": round(mean(model.to_display(a.overall_score) for a in scored), 1) if scored else None,
            **{f"class_{c}": counts.get(c, 0) for c in classes},
            "share_top_two_classes": round(sum(counts.get(c, 0) for c in classes[-2:]) / len(items), 3)
            if items else 0.0,
            "needs_review": sum(a.requires_human_review for a in items),
            "escalated": sum(bool(a.escalations) for a in items),
            "most_concerning": worst.supplier_name if worst else None,
        })
    return rows


def top_risks(assessments: list[RiskAssessment], model: RiskModelConfig, n: int = 5) -> list[dict[str, Any]]:
    """The n most concerning suppliers (by class, then internal score) with their main drivers."""
    rank = {c.key: i for i, c in enumerate(model.risk_classes)}
    ordered = sorted(
        (a for a in assessments if a.overall_score is not None),
        key=lambda a: (rank.get(a.risk_class, -1), a.overall_score), reverse=True,
    )
    return [{
        "supplier_id": a.supplier_id,
        "name": a.supplier_name,
        "material_group": a.material_group,
        "score": model.to_display(a.overall_score),
        "risk_class": a.risk_class,
        "main_drivers": drivers_text(a, model),
        "escalated": bool(a.escalations),
    } for a in ordered[:n]]


def action_plan(assessments: list[RiskAssessment]) -> list[dict[str, Any]]:
    """All recommended actions as rows: one line per supplier and action."""
    rows = []
    for a in assessments:
        for r in a.recommendations:
            rows.append({
                "supplier_id": a.supplier_id,
                "name": a.supplier_name,
                "material_group": a.material_group,
                "risk_class": a.risk_class,
                "level": r.priority,
                "factor": r.factor,
                "action": r.action,
                "owner": r.owner or None,
                "review_cycle": r.review_cycle,
                "trigger": r.trigger,
            })
    return rows
