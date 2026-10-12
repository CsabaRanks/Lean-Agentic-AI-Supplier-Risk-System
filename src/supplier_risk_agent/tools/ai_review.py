"""Input preparation and output validation for the optional LLM explanation.

Pure functions only. The payload is the deterministic scoring trace
(``tools.explain``) of one supplier in each view: inputs with source and data
date, rating rules, ratings, nominal and effective weights, score
contributions, non-additive rules (escalation, completeness check), plus the
rule-based actions. It deliberately omits the supplier name, country, spend
and expert labels: the model needs none of them to explain the scores, and
without a name it cannot mix in outside "knowledge" about a real company.

``validate_review`` checks the model's answer against the payload: every
referenced criterion and trace entry must exist in the input, the summary,
each driver, each view difference and each action must cite trace entries,
both views must be compared, and data gaps must lead to at least one open
question. A failed check rejects the whole answer. Not checked: numbers quoted
in the free text, whether a cited entry actually supports the sentence, the
quality of explanations and priorities, and whether every single data gap is
addressed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ..models.ai_review import AIReviewDraft, AIReviewResult
from ..models.config import RiskModelConfig, WeightSet
from ..models.domain import RiskAssessment, SupplierProfile
from .explain import scoring_trace, trace_ids
from .scoring import resolve_weights

MAX_SUMMARY_CHARS = 1500
MAX_DRIVERS = 6
MAX_ACTIONS = 8
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

SYSTEM_PROMPT = """\
You explain the results of a deterministic supplier evaluation to a category manager.

You receive the scoring trace of one supplier from up to two views of the same criteria catalogue:
"risk" (how exposed the buyer is if the supplier fails) and "performance" (how well the supplier
delivers). The trace shows inputs and their sources, rating rules, ratings, weights, each
criterion's contribution in score points, and rules that are not additive (escalation rules that
set a class floor, the data-completeness check). Scores, classes and weights are final.

Rules:
- Use only the trace. You do not know who the supplier is. Do not add facts about the company, its
  country, market, news, finances or history, and do not add reasons for the rating that are not
  in the trace.
- Do not compute, change or propose scores, classes or weights. You may quote values from the trace.
- Cite trace entries by their exact "id" (for example "risk:credit_risk", "risk:rule:compliance_status",
  "performance:dim:delivery") in every "trace_refs" and "summary_refs" field. Refer to criteria by
  their exact "key" in the "criteria" and "criterion" fields.
- Explain the largest contributions first. Explain escalation rules and the completeness check
  separately: they change the class or trigger a review, not the score.
- Ratings run from 1 (favourable) to 5 (unfavourable). A rating of null means no data. Name missing
  data and missing sources explicitly, never guess a value, and turn each gap into an open question.
- Explain where the two views differ and why, based on criteria, weights and contributions.
- Suggested actions are proposals for a human reviewer. Build on the rule-based actions in the
  trace where they fit, and prioritise them (high, medium, low).
- Be concise and factual. Write in English for a procurement audience."""

USER_TEMPLATE = f"""\
Explain this supplier's evaluation and fill every field of the answer format:
- management_summary: at most {MAX_SUMMARY_CHARS} characters; summary_refs: the trace ids it relies on.
- risk_drivers: the 1 to {MAX_DRIVERS} most important drivers only, each with a criterion key, its view and
  trace_refs.
- view_differences: at least one entry if the trace contains both views, each with trace_refs.
- suggested_actions: 1 to {MAX_ACTIONS} prioritised proposals (high, medium, low) for a human reviewer, each
  with trace_refs.
- open_questions: one question per missing or unclear piece of information; at least one if any
  criterion is missing. Use an empty list only if nothing is missing or unclear.

Trace:
{{payload}}"""


def view_section(assessment: RiskAssessment, profile: SupplierProfile, model: RiskModelConfig,
                 weights: WeightSet | None = None) -> dict[str, Any]:
    """Scoring trace of one supplier in one view plus rule-based actions, as sent to the provider."""
    section = scoring_trace(assessment, profile, model, weights)
    actions, seen = [], set()
    for rec in assessment.recommendations:
        if rec.action not in seen:
            seen.add(rec.action)
            actions.append({"level": rec.priority, "action": rec.action, "criterion": rec.factor})
    section["flagged_for_human_review"] = assessment.requires_human_review
    section["review_reasons"] = list(assessment.review_reasons)
    section["rule_based_actions"] = actions
    return section


def section_from_state(state: dict, supplier_id: str, model: RiskModelConfig) -> dict[str, Any]:
    """``view_section`` for a supplier of a finished (or paused) run."""
    result = state.get("results", {}).get(supplier_id)
    profile = state.get("suppliers", {}).get(supplier_id)
    if result is None or profile is None:
        raise LookupError(f"supplier '{supplier_id}' has no result in the {model.view} view")
    weights = resolve_weights(result.material_group, state.get("active_weights") or {}, model)
    return view_section(result, profile, model, weights)


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


def review_is_current(result: AIReviewResult, payload: dict[str, Any]) -> bool:
    """False once the input changed (e.g. after a correction): the explanation is outdated."""
    return result.payload_sha256 == payload_hash(payload)


def data_gaps(payload: dict[str, Any]) -> list[str]:
    return [f"{view}: {key}" for view, s in payload["views"].items() for key in s["missing_criteria"]]


def score_summary(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        view: {"score": s["score"]["value"], "score_label": s["score"]["label"], "class": s["class"]["final"],
               "data_completeness": s["data_completeness"]}
        for view, s in payload["views"].items()
    }


def validate_review(draft: AIReviewDraft, payload: dict[str, Any]) -> list[str]:
    """Problems that make the answer unusable (empty list = valid)."""
    views = payload["views"]
    keys_by_view = {view: {c["key"] for c in s["criteria"]} for view, s in views.items()}
    all_keys = set().union(*keys_by_view.values()) if keys_by_view else set()
    all_ids = set().union(*(trace_ids(s) for s in views.values())) if views else set()
    problems: list[str] = []

    summary = draft.management_summary.strip()
    if not summary:
        problems.append("management summary is empty")
    elif len(summary) > MAX_SUMMARY_CHARS:
        problems.append(f"management summary longer than {MAX_SUMMARY_CHARS} characters")
    if not draft.summary_refs:
        problems.append("management summary cites no trace entry")

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

    for kind, items in (("risk driver", draft.risk_drivers), ("view difference", draft.view_differences),
                        ("suggested action", draft.suggested_actions)):
        if any(not item.trace_refs for item in items):
            problems.append(f"a {kind} cites no trace entry")

    referenced = [
        *(k for d in draft.view_differences for k in d.criteria),
        *(k for a in draft.suggested_actions for k in a.criteria),
        *(k for q in draft.open_questions for k in q.criteria),
    ]
    for key in sorted(set(referenced) - all_keys):
        problems.append(f"unknown criterion '{key}' referenced")

    cited = [
        *draft.summary_refs,
        *(r for d in draft.risk_drivers for r in d.trace_refs),
        *(r for d in draft.view_differences for r in d.trace_refs),
        *(r for a in draft.suggested_actions for r in a.trace_refs),
    ]
    for ref in sorted(set(cited) - all_ids):
        problems.append(f"unknown trace entry '{ref}' cited")

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
