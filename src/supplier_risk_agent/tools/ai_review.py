"""Input preparation and output validation for the optional LLM review.

Pure functions only. The payload builder decides *what* leaves the machine:
the structured results of one supplier in each view (criterion ratings,
weights, scores, classes, fired escalation rules, data completeness and the
rule-based actions). Indicator values appear only inside the short "basis"
text of a rating (e.g. "credit score 41/100"). It deliberately omits the
supplier name, country, spend, the raw indicator record and expert labels:
the model needs none of them to interpret the scores, and without a name it
cannot mix in outside "knowledge" about a real company.

``validate_review`` checks the model's answer against the payload: every
referenced criterion must exist in the input, both views must be compared, and
data gaps must lead to at least one open question. A failed check rejects the
whole answer. Not checked: numbers quoted in the free text, whether statements
are supported by the payload, the quality of explanations and priorities, and
whether every single data gap is addressed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..models.ai_review import AIReviewDraft
from ..models.config import RiskModelConfig
from ..models.domain import RiskAssessment

RATING_SCALE = "1 = favourable ... 5 = unfavourable (same direction in every view); null = no data"
MAX_SUMMARY_CHARS = 1500
MAX_DRIVERS = 6
MAX_ACTIONS = 8
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

SYSTEM_PROMPT = """\
You review the results of a deterministic supplier evaluation for a procurement team.

You receive one supplier's structured results from up to two views of the same criteria catalogue:
"risk" (how exposed the buyer is if the supplier fails) and "performance" (how well the supplier
delivers). Scores, classes and weights were computed by a rule-based engine and are final.

Rules:
- Use only the data in the JSON payload. You do not know who the supplier is. Do not add facts about
  the company, its country, market, news, finances or history that are not in the payload.
- Do not compute, change or propose scores, classes or weights. You may quote values from the payload.
- Refer to criteria by their exact "key" from the payload, in the "criteria" and "criterion" fields.
- Ratings run from 1 (favourable) to 5 (unfavourable). A rating of null means no data. Name missing
  data explicitly, never guess a value for it, and turn each gap into an open question.
- Explain where the two views differ and why, based on the criteria and weights.
- Suggested actions are proposals for a human reviewer. Build on the rule-based actions in the
  payload where they fit, and prioritise them (high, medium, low).
- Be concise and factual. Write in English."""

USER_TEMPLATE = f"""\
Review this supplier and fill every field of the answer format:
- management_summary: at most {MAX_SUMMARY_CHARS} characters.
- risk_drivers: the 1 to {MAX_DRIVERS} most important drivers only, each with a criterion key and its view.
- view_differences: at least one entry if the payload contains both views.
- suggested_actions: 1 to {MAX_ACTIONS} prioritised proposals (high, medium, low) for a human reviewer.
- open_questions: one question per missing or unclear piece of information; at least one if any
  criterion is missing. Use an empty list only if nothing is missing or unclear.

Payload:
{{payload}}"""


def _labels(model: RiskModelConfig) -> tuple[dict[str, str], dict[str, str]]:
    factors = {f.key: f.label for d in model.dimensions for f in d.factors}
    dimensions = {d.key: d.label for d in model.dimensions}
    return factors, dimensions


def view_section(assessment: RiskAssessment, model: RiskModelConfig) -> dict[str, Any]:
    """Structured results of one supplier in one view, as sent to the provider."""
    factor_labels, dimension_labels = _labels(model)

    def shown(value: float | None) -> float | None:
        display = model.to_display(value)
        return round(display, 1) if display is not None else None

    actions, seen = [], set()
    for rec in assessment.recommendations:
        if rec.action not in seen:
            seen.add(rec.action)
            actions.append({"level": rec.priority, "action": rec.action, "criterion": rec.factor})
    return {
        "view": model.view,
        "question": model.view_question,
        "score_label": model.score_label,
        "score_orientation": model.score_orientation,
        "score": shown(assessment.overall_score),
        "class": assessment.risk_class,
        "class_before_escalation_rules": assessment.calculated_class,
        "class_set_by_reviewer": assessment.manual_override,
        "classes_favourable_to_unfavourable": [c.key for c in model.risk_classes],
        "data_completeness": round(assessment.data_completeness, 2),
        "minimum_data_completeness": model.min_data_completeness,
        "weights": f"{assessment.weights_scope}/{assessment.weights_origin}",
        "rating_scale": RATING_SCALE,
        "dimensions": [
            {"key": d.dimension, "label": dimension_labels.get(d.dimension, d.label),
             "weight": round(d.weight, 3), "score": shown(d.score)}
            for d in assessment.dimension_scores
        ],
        "criteria": [
            {"key": f.factor, "label": factor_labels.get(f.factor, f.factor), "dimension": f.dimension,
             "rating": f.rating, "weight": round(f.weight, 3), "basis": f.rationale or f.source}
            for f in assessment.factor_scores
        ],
        "missing_criteria": [f.factor for f in assessment.factor_scores if f.rating is None],
        "escalation_rules_fired": [
            {"criterion": e.rule_factor, "class_floor": e.floor_class, "reason": e.reason}
            for e in assessment.escalations
        ],
        "flagged_for_human_review": assessment.requires_human_review,
        "review_reasons": list(assessment.review_reasons),
        "rule_based_actions": actions,
    }


def build_review_payload(sections: list[dict[str, Any]], supplier_id: str,
                         material_group: str | None) -> dict[str, Any]:
    """Combine the view sections of one supplier (risk first) into the provider payload."""
    order = {"risk": 0, "performance": 1}
    views = {s["view"]: s for s in sorted(sections, key=lambda s: order.get(s["view"], 9))}
    return {
        "supplier": {"id": supplier_id, "material_group": material_group},
        "views": views,
    }


def payload_json(payload: dict[str, Any]) -> str:
    """Canonical JSON: what is shown to the user is byte-for-byte what is sent."""
    return json.dumps(payload, indent=2, ensure_ascii=False)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def data_gaps(payload: dict[str, Any]) -> list[str]:
    return [f"{view}: {key}" for view, s in payload["views"].items() for key in s["missing_criteria"]]


def score_summary(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        view: {"score": s["score"], "score_label": s["score_label"], "class": s["class"],
               "data_completeness": s["data_completeness"]}
        for view, s in payload["views"].items()
    }


def validate_review(draft: AIReviewDraft, payload: dict[str, Any]) -> list[str]:
    """Problems that make the answer unusable (empty list = valid)."""
    views = payload["views"]
    keys_by_view = {view: {c["key"] for c in s["criteria"]} for view, s in views.items()}
    all_keys = set().union(*keys_by_view.values()) if keys_by_view else set()
    problems: list[str] = []

    summary = draft.management_summary.strip()
    if not summary:
        problems.append("management summary is empty")
    elif len(summary) > MAX_SUMMARY_CHARS:
        problems.append(f"management summary longer than {MAX_SUMMARY_CHARS} characters")

    if not 1 <= len(draft.risk_drivers) <= MAX_DRIVERS:
        problems.append(f"expected 1 to {MAX_DRIVERS} risk drivers, got {len(draft.risk_drivers)}")
    for driver in draft.risk_drivers:
        if driver.view not in views:
            problems.append(f"risk driver refers to view '{driver.view}', which is not in the input")
        elif driver.criterion not in keys_by_view[driver.view]:
            problems.append(f"risk driver refers to unknown criterion '{driver.criterion}' in view '{driver.view}'")

    if not 1 <= len(draft.suggested_actions) <= MAX_ACTIONS:
        problems.append(f"expected 1 to {MAX_ACTIONS} suggested actions, got {len(draft.suggested_actions)}")
    if len(views) > 1 and not draft.view_differences:
        problems.append("no explanation of the differences between the views")
    if data_gaps(payload) and not draft.open_questions:
        problems.append("input has missing data but no open question was returned")

    referenced = [
        *(k for d in draft.view_differences for k in d.criteria),
        *(k for a in draft.suggested_actions for k in a.criteria),
        *(k for q in draft.open_questions for k in q.criteria),
    ]
    for key in sorted(set(referenced) - all_keys):
        problems.append(f"unknown criterion '{key}' referenced")

    texts = [
        *(d.explanation for d in draft.risk_drivers),
        *(t for d in draft.view_differences for t in (d.topic, d.explanation)),
        *(t for a in draft.suggested_actions for t in (a.action, a.rationale)),
        *(q.question for q in draft.open_questions),
    ]
    if any(not t.strip() for t in texts):
        problems.append("empty text field in the answer")
    return problems


def prioritised(draft: AIReviewDraft) -> AIReviewDraft:
    """Actions sorted high -> low (stable), so the order does not depend on the model."""
    actions = sorted(draft.suggested_actions, key=lambda a: PRIORITY_ORDER[a.priority])
    return draft.model_copy(update={"suggested_actions": actions})
