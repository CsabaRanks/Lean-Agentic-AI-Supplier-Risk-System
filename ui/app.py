"""Supplier Workspace: a native Streamlit procurement UI.

Start with synthetic data, compare risk and performance in one portfolio,
then explain and correct a supplier assessment with a reason and preview.
Scoring, calibration, approvals and optional AI reviews use the package.

    pip install -e ".[ui]"
    streamlit run ui/app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from i18n import (
    browser_language,
    data_editor,
    dataframe,
    date,
    date_axis,
    display_value,
    error_text,
    language,
    localized_chart,
    message,
    multiselect,
    number,
    option_labels,
    parse_input,
    selectbox,
    tr,
)
from pydantic import ValidationError

from supplier_risk_agent import SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.graph import ai_review_payload
from supplier_risk_agent.llm import LLMReviewError, LLMSettings, load_env_file
from supplier_risk_agent.models import ClassOverride, ReviewDecision
from supplier_risk_agent.models.ai_review import AIReviewResult
from supplier_risk_agent.models.config import available_views
from supplier_risk_agent.providers import WorldBankWgiProvider
from supplier_risk_agent.tools import HistoryStore, InMemorySource, JsonFileSource, WeightStore
from supplier_risk_agent.tools.ai_review import payload_hash, payload_json, review_is_current
from supplier_risk_agent.tools.corrections import (
    CorrectionRequest,
    FieldChange,
    correctable_fields,
    parse_cell,
    preview_correction,
    split_table_edits,
)
from supplier_risk_agent.tools.reporting import ALL_GROUPS, action_plan, group_summary, top_risks
from supplier_risk_agent.tools.tabular import (
    all_view_columns,
    assessment_to_row,
    from_csv,
    label_view,
    profile_to_row,
    rows_to_profiles,
    to_csv,
)

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "Sample portfolio (6 suppliers)": ROOT / "data" / "sample_suppliers.json",
    "Calibration demo (36 suppliers, synthetic expert labels)": ROOT
    / "data"
    / "calibration_portfolio.json",
}
# status palette (fixed roles), from favourable to unfavourable — always shown with the class label
STATUS = [("#e8f3ed", "🟢"), ("#fcf3dc", "🟡"), ("#fff0e5", "🟠"), ("#fbe9e7", "🔴")]
# categorical slots 1 and 2 of the validated reference palette
CURRENT_COLOR, PROPOSED_COLOR = "#2a78d6", "#eb6834"
NUMERIC_INPUTS = {
    "annual_spend",
    "credit_score",
    "distress_signals",
    "country_risk_index",
    "qualified_sources",
    "esg_score",
    "on_time_rate",
    "quality_ppm",
}

st.session_state.setdefault("language", browser_language(st.context.locale))

st.set_page_config(
    page_title="Supplier Workspace", page_icon=":material/view_quilt:", layout="wide"
)
load_env_file(ROOT / ".env")  # optional LLM settings; variables already set in the environment win


# --- views, data and runs --------------------------------------------------------------


@st.cache_resource
def ui_model(view: str):
    """Bundled model of a view. In the UI, calibrated weights always go through the Review tab."""
    model = load_risk_model(view=view)
    model.calibration.auto_apply = False
    return model


def model():
    return ui_model(st.session_state.get("view", "risk"))


def run_info() -> dict:
    """Run of the current view (evaluator, state, ...). Each view keeps its own run."""
    return st.session_state.setdefault("runs", {}).setdefault(model().view, {})


def class_styles() -> dict[str, tuple[str, str]]:
    """Class key -> (colour, icon), spread over the status palette from favourable to unfavourable."""
    keys = [c.key for c in model().risk_classes]
    last = len(STATUS) - 1
    return {k: STATUS[int(i * last / max(len(keys) - 1, 1))] for i, k in enumerate(keys)}


def load_rows(path: Path) -> list[dict]:
    source = JsonFileSource(path)
    return [profile_to_row(source.get_supplier(i), model()) for i in source.list_supplier_ids()]


def set_rows(rows: list[dict], origin: str) -> None:
    """Replace the data and score it straight away, like a spreadsheet that is always calculated."""
    st.session_state.pop("pending_correction", None)
    st.session_state.pop("table_preview", None)
    st.session_state.pop("selected_supplier", None)
    st.session_state.pop("correction_success", None)
    st.session_state.pop("editor_locale_drafts", None)
    st.session_state.rows = rows
    st.session_state.origin = origin
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    st.session_state.runs = {}
    run(calibrate=False, material_group=None)


def weight_store() -> WeightStore | None:
    if st.session_state.get("use_store"):
        return WeightStore(ROOT / st.session_state.get("store_dir", "data/weights"))
    return None


def providers() -> list:
    return [WorldBankWgiProvider.mock()] if st.session_state.get("use_wgi_mock") else []


def history() -> HistoryStore:
    return HistoryStore(ROOT / st.session_state.get("history_dir", "data/history"))


def assessments() -> list:
    return list((run_info().get("state") or {}).get("results", {}).values())


def assessed_ids() -> set[str]:
    """Suppliers that already have a result in any view: changes to them go through a correction."""
    return {
        sid
        for info in st.session_state.get("runs", {}).values()
        for sid in ((info or {}).get("state") or {}).get("results", {})
    }


def show_comparison(comparison: dict) -> None:
    """Before/after of a proposed correction, per view and per changed criterion."""
    for col, (view, values) in zip(st.columns(len(comparison)), comparison.items()):
        with col.container(border=True):
            st.markdown(tr("**Risiko**") if view == "risk" else tr("**Performance**"))
            before, after = values["score"]
            st.metric(tr("Vorher → Nachher"), f"{display_value(before)} → {display_value(after)}")
            st.write(
                tr(
                    "{v0} → {v1}",
                    v0=risk_name(values["class"][0]),
                    v1=risk_name(values["class"][1]),
                )
            )
            if values["rules_no_longer_triggered"]:
                st.caption(
                    tr("Regel entfällt: ") + tr(", ".join(values["rules_no_longer_triggered"]))
                )
            if values["rules_now_triggered"]:
                st.caption(tr("Neue Regel: ") + tr(", ".join(values["rules_now_triggered"])))
    with st.expander(tr("Alle Auswirkungen der Korrektur")):
        comparison_table(comparison)


def comparison_table(comparison: dict) -> None:
    dataframe(
        pd.DataFrame(
            [
                {
                    "view": tr(ui_model(v).view_label),
                    "score": f"{display_value(c['score'][0])} → {display_value(c['score'][1])}",
                    "class": f"{risk_name(c['class'][0])} → {risk_name(c['class'][1])}",
                    "data": f"{number(c['data_completeness'][0], '.0%')} → {number(c['data_completeness'][1], '.0%')}",
                    "needs review": f"{display_value(c['needs_review'][0])} → {display_value(c['needs_review'][1])}",
                    "rules now triggered": ", ".join(c["rules_now_triggered"]) or "—",
                    "rules no longer triggered": ", ".join(c["rules_no_longer_triggered"]) or "—",
                }
                for v, c in comparison.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    changed = [
        {
            "view": v,
            "criterion": x["criterion"],
            "rating": f"{x['rating'][0]} → {x['rating'][1]}",
            "origin": f"{tr(x['origin'][0])} → {tr(x['origin'][1])}",
            "points": f"{display_value(x['contribution_points'][0])} → {display_value(x['contribution_points'][1])}",
        }
        for v, c in comparison.items()
        for x in c["changed_criteria"]
    ]
    if changed:
        dataframe(pd.DataFrame(changed), hide_index=True, width="stretch")
    else:
        st.caption(tr("No criterion rating changes."))


def apply_corrections(items: list[tuple], new_rows: list[dict]) -> None:
    """Adopt confirmed corrections: record each in the history, replace the data, recalculate."""
    for request, comparison in items:
        entry = history().record_correction(request, comparison)
        if request.supplier_id in st.session_state.get("ai_explanations", {}):
            st.session_state.setdefault("ai_outdated", {})[request.supplier_id] = {
                "time": entry["recorded_at"],
                "reason": request.reason,
            }
    st.session_state.rows = new_rows
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    # Each view retains its approved session weights when the corrected data is scored.
    for view in ("risk", "performance"):
        run(calibrate=False, material_group=None, view=view)


def run(calibrate: bool, material_group: str | None, view: str | None = None) -> None:
    """Score the current data in the current view (or in ``view``)."""
    st.session_state.pop("pending_correction", None)
    st.session_state.pop("table_preview", None)
    view_model = ui_model(view) if view else model()
    profiles, errors = rows_to_profiles(st.session_state.rows, view_model)
    st.session_state.input_errors = errors
    info = st.session_state.setdefault("runs", {}).setdefault(view_model.view, {})
    approved_weights = (info.get("state") or {}).get("active_weights") or None
    info.clear()
    if not profiles:
        return
    evaluator = SupplierRiskEvaluator(
        InMemorySource(profiles), view_model, weight_store(), providers=providers()
    )
    info.update(
        evaluator=evaluator,
        state=evaluator.run(
            material_group=material_group, calibrate=calibrate, active_weights=approved_weights
        ),
        run_kind="calibration" if calibrate else "scoring",
        rows_at_run=[dict(r) for r in st.session_state.rows],
    )


def results_frame() -> pd.DataFrame:
    """Result rows in the view's reading direction, most concerning supplier first."""
    state = run_info().get("state") or {}
    ranked = sorted(
        state.get("results", {}).values(),
        key=lambda a: a.overall_score if a.overall_score is not None else -1,
        reverse=True,
    )
    return pd.DataFrame([assessment_to_row(a, model()) for a in ranked])


def material_groups() -> list[str]:
    return sorted(
        {str(r["material_group"]) for r in st.session_state.rows if r.get("material_group")}
    )


def with_numeric(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Numeric dtype for number columns, so that empty cells stay empty instead of showing 'None'."""
    for c in columns:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def class_label(value) -> str:
    icon = class_styles().get(value, ("", "⚪"))[1]
    return f"{icon} {tr(value)}" if isinstance(value, str) else "⚪ —"


def style_class(value: str) -> str:
    key = next((c for c in class_styles() if tr(c) == str(value).split(" ")[-1]), value)
    styles = class_styles()
    if key not in styles:
        return ""
    worst = key == list(styles)[-1]
    return f"background-color: {styles[key][0]}; color: {'#a33636' if worst else '#243247'}; font-weight: 600"


def dashboard_page():
    items = assessments()
    if not items:
        st.info(tr("No results yet."))
    else:
        order = [c.key for c in model().risk_classes]
        styles = class_styles()
        summary = pd.DataFrame(group_summary(items, model()))
        group = selectbox(
            tr("Material group"),
            summary.material_group.tolist(),
            key="dash_group",
            format_func=option_labels(summary.material_group.tolist(), tr),
            _parent=st,
        )
        row = summary.set_index("material_group").loc[group]
        selected = (
            items
            if group == ALL_GROUPS
            else [a for a in items if (a.material_group or "(none)") == group]
        )

        k = st.columns(5)
        k[0].metric(tr("Suppliers"), int(row.suppliers))
        k[1].metric(
            tr("Mean {v0}", v0=tr(model().score_label)),
            number(row.mean_score, ".1f") if pd.notna(row.mean_score) else "–",
        )
        k[2].metric(
            tr("Share {v0}", v0=" / ".join(risk_name(c) for c in order[-2:])),
            number(row.share_top_two_classes, ".0%"),
        )
        k[3].metric(tr("Need review"), int(row.needs_review))
        k[4].metric(tr("Raised by escalation rule"), int(row.escalated))

        left, right = st.columns([3, 2])
        with left:
            class_columns = [f"class_{c}" for c in order]
            per_group = summary.loc[
                summary.material_group != ALL_GROUPS, ["material_group", *class_columns]
            ].melt(
                id_vars="material_group",
                value_vars=class_columns,
                var_name="class",
                value_name="suppliers",
            )
            per_group["class"] = per_group["class"].str.removeprefix("class_").map(risk_name)
            stacked = (
                alt.Chart(per_group)
                .mark_bar(stroke="white", strokeWidth=2)
                .encode(
                    y=alt.Y("material_group:N", title=None),
                    x=alt.X("suppliers:Q", title=tr("Suppliers"), axis=alt.Axis(tickMinStep=1)),
                    color=alt.Color(
                        "class:N",
                        scale=alt.Scale(
                            domain=[risk_name(c) for c in order],
                            range=[styles[c][0] for c in order],
                        ),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    order=alt.Order("class_rank:Q"),
                    tooltip=[
                        alt.Tooltip("material_group:N", title=tr("material_group")),
                        alt.Tooltip("class:N", title=tr("class")),
                        alt.Tooltip("suppliers:Q", title=tr("suppliers")),
                    ],
                )
                .transform_calculate(
                    class_rank=f"indexof({[risk_name(c) for c in order]}, datum.class)"
                )
            )
            localized_chart(
                stacked.properties(height=alt.Step(34), title=tr("Classes per material group")),
                width="stretch",
            )
        with right:
            st.markdown(tr("**Top risks — {v0}**", v0=tr(group)))
            top = pd.DataFrame(top_risks(selected, model(), n=5))
            if not top.empty:
                top["risk_class"] = top.risk_class.map(class_label)
                dataframe(
                    top[["name", "score", "risk_class", "main_drivers"]],
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "name": "Supplier",
                        "score": st.column_config.NumberColumn(
                            tr(model().score_label), format="%.1f"
                        ),
                        "risk_class": "Class",
                        "main_drivers": "Main drivers (points)",
                    },
                )
        st.markdown(tr("**All material groups**"))
        dataframe(
            summary.assign(
                material_group=summary.material_group.map(
                    lambda group: tr(group) if group == ALL_GROUPS else group
                )
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "material_group": "Material group",
                "suppliers": "Suppliers",
                "mean_score": st.column_config.NumberColumn(
                    tr("Mean {v0}", v0=tr(model().score_label)), format="%.1f"
                ),
                "share_top_two_classes": st.column_config.NumberColumn(
                    tr("Share {v0}", v0=" / ".join(risk_name(c) for c in order[-2:])),
                    format="percent",
                ),
                **{f"class_{c}": f"{styles[c][1]} {risk_name(c)}" for c in order},
                "needs_review": "Review",
                "escalated": "Escalated",
                "most_concerning": "Most concerning",
            },
        )


# --- page: actions ------------------------------------------------------------------------------


def actions_page():
    plan = pd.DataFrame(action_plan(assessments()))
    if plan.empty:
        st.info(tr("No actions."))
    else:
        st.caption(
            tr(
                "Action framework: measures per risk class, per elevated dimension and per factor level. Defined in the view's YAML (`actions`, `dimension_triggers`, `factor_actions`)."
            )
        )
        f = st.columns([2, 2, 2, 2])
        groups = multiselect(
            tr("Material group"),
            sorted(plan.material_group.dropna().unique()),
            key="act_group",
            placeholder=tr("Choose options"),
            _parent=f[0],
        )
        classes = multiselect(
            tr("Class"),
            [c.key for c in model().risk_classes],
            key="act_class",
            format_func=option_labels([c.key for c in model().risk_classes], risk_name),
            placeholder=tr("Choose options"),
            _parent=f[1],
        )
        levels = multiselect(
            tr("Level"),
            sorted(plan.level.unique()),
            key="act_level",
            format_func=option_labels(sorted(plan.level.unique()), tr),
            placeholder=tr("Choose options"),
            _parent=f[2],
        )
        owners = multiselect(
            tr("Owner"),
            sorted(plan.owner.dropna().unique()),
            key="act_owner",
            format_func=option_labels(sorted(plan.owner.dropna().unique()), tr),
            placeholder=tr("Choose options"),
            _parent=f[3],
        )
        view_plan = plan
        for column, chosen in (
            ("material_group", groups),
            ("risk_class", classes),
            ("level", levels),
            ("owner", owners),
        ):
            if chosen:
                view_plan = view_plan[view_plan[column].isin(chosen)]
        dataframe(
            view_plan.assign(risk_class=view_plan.risk_class.map(class_label)),
            hide_index=True,
            width="stretch",
            column_config={
                "supplier_id": "ID",
                "name": "Supplier",
                "risk_class": "Class",
                "material_group": "Material group",
                "level": "Level",
                "factor": "Factor",
                "action": "Action",
                "owner": "Owner",
                "review_cycle": "Review cycle",
                "trigger": "Why",
            },
        )
        st.download_button(
            tr("Export action plan CSV"),
            to_csv(view_plan.to_dict("records")),
            file_name=f"{model().view}_action_plan.csv",
            mime="text/csv",
            key="control_324",
        )


# --- page: history ---------------------------------------------------------------------------


def history_page():
    c1, c2 = st.columns([1, 3])
    note = c2.text_input(
        tr("Note for this snapshot"), placeholder=tr("e.g. annual review 2026"), key="snap_note"
    )
    if c1.button(
        tr("📌 Save snapshot"), width="stretch", disabled=not assessments(), key="control_335"
    ):
        n = history().record(
            assessments(), model(), run_id=(run_info().get("state") or {}).get("run_id"), note=note
        )
        st.success(
            tr(
                "Saved {v0} rows to {v1}/{v2}.jsonl",
                v0=n,
                v1=st.session_state.get("history_dir", "data/history"),
                v2=model().view,
            )
        )
    rows = pd.DataFrame(history().load(model().view))
    if rows.empty:
        st.info(
            tr(
                "No snapshots yet for this view. Save one above; approved reviews are saved automatically."
            )
        )
    else:
        rows["recorded_at"] = pd.to_datetime(rows.recorded_at)
        st.caption(
            tr(
                "{v0} snapshot(s) for the {v1} view.",
                v0=rows.recorded_at.nunique(),
                v1=tr(model().view_label),
            )
        )
        left, right = st.columns(2)
        with left:
            names = dict(zip(rows.supplier_id, rows.name))
            sid = selectbox(
                tr("Supplier"),
                sorted(names),
                format_func=option_labels(sorted(names), lambda s: f"{s} · {names[s]}"),
                key="hist_sup",
                _parent=st,
            )
            mine = rows[rows.supplier_id == sid]
            line = (
                alt.Chart(mine.assign(risk_class=mine.risk_class.map(risk_name)))
                .mark_line(
                    point=alt.OverlayMarkDef(size=60, filled=True),
                    strokeWidth=2,
                    color=CURRENT_COLOR,
                )
                .encode(
                    x=alt.X(
                        "recorded_at:T",
                        title=None,
                        axis=alt.Axis(format=date_axis(), labelAngle=0, tickCount=6),
                    ),
                    y=alt.Y(
                        "score:Q", title=tr(model().score_label), scale=alt.Scale(domain=[0, 100])
                    ),
                    tooltip=[
                        alt.Tooltip("recorded_at:T", title=tr("snapshot"), format=date_axis()),
                        alt.Tooltip("score:Q", title=tr("score")),
                        alt.Tooltip("risk_class:N", title=tr("risk_class")),
                        alt.Tooltip("note:N", title=tr("note")),
                    ],
                )
            )
            localized_chart(
                line.properties(height=260, title=tr("{supplier} over time", supplier=names[sid])),
                width="stretch",
            )
            dataframe(
                mine[["recorded_at", "score", "risk_class", "weights", "approved_by", "note"]],
                hide_index=True,
                width="stretch",
            )
        with right:
            groups = sorted(rows.material_group.dropna().unique())
            g = selectbox(tr("Material group"), groups, key="hist_group", _parent=st)
            trend = pd.DataFrame(history().group_trend(model().view, material_group=g))
            trend["recorded_at"] = pd.to_datetime(trend.recorded_at)
            line = (
                alt.Chart(trend)
                .mark_line(
                    point=alt.OverlayMarkDef(size=60, filled=True),
                    strokeWidth=2,
                    color=CURRENT_COLOR,
                )
                .encode(
                    x=alt.X(
                        "recorded_at:T",
                        title=None,
                        axis=alt.Axis(format=date_axis(), labelAngle=0, tickCount=6),
                    ),
                    y=alt.Y(
                        "mean_score:Q",
                        title=tr("Mean {v0}", v0=tr(model().score_label)),
                        scale=alt.Scale(domain=[0, 100]),
                    ),
                    tooltip=[
                        alt.Tooltip("recorded_at:T", title=tr("snapshot"), format=date_axis()),
                        alt.Tooltip("mean_score:Q", title=tr("mean_score")),
                        alt.Tooltip("suppliers:Q", title=tr("suppliers")),
                    ],
                )
            )
            localized_chart(
                line.properties(height=260, title=tr("{group}: mean score over time", group=g)),
                width="stretch",
            )
            dataframe(
                trend.assign(
                    classes=trend.classes.map(
                        lambda c: ", ".join(f"{risk_name(k)}: {v}" for k, v in c.items())
                    )
                ),
                hide_index=True,
                width="stretch",
            )


# --- page: scoring run --------------------------------------------------------------------


def scoring_page():
    st.subheader(tr("Supplier inputs"))
    st.caption(
        tr(
            "One sheet for both views: shared criteria appear once. Add new suppliers at the bottom (or import a CSV in the sidebar) and press **Recalculate**. Changes to suppliers that already have a result are not applied directly: they need a reason, a preview and your confirmation, and are recorded in the history. Expert ratings: 1 (favourable) – 5 (unfavourable). Empty cells mean “no data”."
        )
    )
    all_factors = {f.key for v in views for d in ui_model(v).dimensions for f in d.factors}
    # expert labels are edited only in the Calibration tab, so that two editors never compete for a cell
    columns = [
        c
        for c in dict.fromkeys(all_view_columns() + [k for r in st.session_state.rows for k in r])
        if not label_view(c)
    ]
    expert_cols = [c for c in columns if c in all_factors and c != "compliance_status"]
    config = {
        "supplier_id": st.column_config.TextColumn(tr("Supplier ID"), required=True),
        "material_group": st.column_config.TextColumn(tr("Material group")),
        "annual_spend": st.column_config.NumberColumn(tr("Annual spend"), format="%.0f"),
        "transport_mode": st.column_config.SelectboxColumn(
            tr("Transport"), options=["road", "rail", "air", "sea"], format_func=tr
        ),
        "intercontinental": st.column_config.CheckboxColumn(tr("Intercontinental")),
        "on_time_rate": st.column_config.NumberColumn(tr("On-time %"), min_value=0, max_value=100),
        "quality_ppm": st.column_config.NumberColumn(tr("PPM"), min_value=0),
        "compliance_status": st.column_config.SelectboxColumn(
            tr("Compliance"),
            options=[
                "compliant",
                "minor_findings",
                "open_findings",
                "major_findings",
                "critical_findings",
            ],
            format_func=tr,
        ),
        **{
            c: st.column_config.NumberColumn(tr(c), min_value=1, max_value=5, step=1)
            for c in expert_cols
        },
    }
    numeric_cols = [c for c in columns if c in NUMERIC_INPUTS or c in expert_cols]
    edited = data_editor(
        with_numeric(pd.DataFrame(st.session_state.rows, columns=columns), numeric_cols),
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        column_config=config,
        key=f"input_editor_{st.session_state.editor_version}",
    )
    previous = {r.get("supplier_id"): r for r in st.session_state.rows}
    edited_rows = [
        {
            **{k: v for k, v in previous.get(row.get("supplier_id"), {}).items() if label_view(k)},
            **row,
        }
        for row in edited.astype(object).where(edited.notna(), None).to_dict("records")
    ]
    # First data entry stays direct; changes to suppliers that already have a result become corrections.
    view_models = [ui_model("risk"), ui_model("performance")]
    st.session_state.rows, table_changes, table_notes = split_table_edits(
        st.session_state.rows, edited_rows, assessed_ids(), view_models
    )
    for note in table_notes:
        st.warning(message(note))
    if table_changes:
        st.warning(
            tr(
                "Changes to suppliers that already have a result are **not applied yet**. Give a reason, preview the effect in both views and confirm; the correction is then recorded in the history. New suppliers can still be entered directly."
            ),
            icon="✋",
        )
        dataframe(
            pd.DataFrame(
                [
                    {
                        "supplier": sid,
                        "field": c.field,
                        "kind": c.kind.replace("_", " "),
                        "current": display_value(c.old_value),
                        "proposed": display_value(c.new_value),
                    }
                    for sid, changes in table_changes.items()
                    for c in changes
                ]
            ).astype(str),
            hide_index=True,
            width="stretch",
        )
        digest = json.dumps(
            {sid: [(c.field, c.new_value) for c in cs] for sid, cs in table_changes.items()},
            sort_keys=True,
            default=str,
        )
        with st.container(key="table_correction_form"):
            t_reason = st.text_area(tr("Reason for the change (required)"), key="table_reason")
            t_name = st.text_input(tr("Your name (optional, not verified)"), key="table_name")
            t_preview = st.button(tr("Preview table changes"), key="control_431")
        if t_preview:
            try:
                items, rows_now = [], st.session_state.rows
                active = {
                    v: ((st.session_state.get("runs", {}).get(v) or {}).get("state") or {}).get(
                        "active_weights"
                    )
                    or {}
                    for v in ("risk", "performance")
                }
                for sid, changes in table_changes.items():
                    req = CorrectionRequest(
                        supplier_id=sid,
                        changes=changes,
                        reason=t_reason,
                        entered_by=t_name.strip() or None,
                    )
                    rows_now, comparison = preview_correction(
                        rows_now, req, view_models, active, providers()
                    )
                    items.append((req, comparison))
                st.session_state.table_preview = {
                    "digest": digest,
                    "items": items,
                    "new_rows": rows_now,
                }
            except (ValidationError, ValueError) as exc:
                st.session_state.pop("table_preview", None)
                st.error(tr("Correction not possible: {v0}", v0=error_text(exc)))
        preview = st.session_state.get("table_preview")
        if preview and preview["digest"] == digest:
            st.markdown(tr("**Preview — nothing is applied yet**"))
            for req, comparison in preview["items"]:
                st.markdown(tr("`{v0}`", v0=req.supplier_id))
                show_comparison(comparison)
            b1, b2 = st.columns(2)
            if b1.button(
                tr("✅ Confirm table changes"), type="primary", width="stretch", key="control_453"
            ):
                apply_corrections(preview["items"], preview["new_rows"])
                st.session_state.pop("table_preview", None)
                st.toast(tr("Changes applied and recorded"))
                st.rerun()
            if b2.button(tr("Discard table changes"), width="stretch", key="control_458"):
                st.session_state.pop("table_preview", None)
                st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
                st.rerun()

    c1, c2, _ = st.columns([2, 1, 3])
    group = selectbox(
        tr("Scope"),
        ["All material groups", *material_groups()],
        key="run_scope",
        format_func=option_labels(["All material groups", *material_groups()], tr),
        _parent=c1,
    )
    if c2.button(tr("▶️ Recalculate"), type="primary", width="stretch", key="control_465"):
        run(calibrate=False, material_group=None if group.startswith("All") else group)
        st.rerun()
    if run_info().get("run_kind") and run_info().get("rows_at_run") != st.session_state.rows:
        st.info(tr("Inputs changed since the last run — recalculate to update the results."))


# --- page: portfolio -----------------------------------------------------------------------


def calibration_page():
    label_col = model().label_column
    direction = (
        "higher = better" if model().score_orientation == "higher_is_better" else "higher = riskier"
    )
    st.subheader(tr("Expert labels — {v0} view", v0=tr(model().view_label)))
    st.caption(
        tr(
            "Give a holistic {v0} (0–100, {v1}) for suppliers you know well — ideally before looking at the model score. Calibration fits this view's weights to these labels; safeguards decide whether the result is trustworthy. Approval happens in **✅ Review & approval**.",
            v0=tr(model().score_label),
            v1=tr(direction),
        )
    )
    labels = pd.DataFrame(
        [
            {
                **{k: r.get(k) for k in ("supplier_id", "name", "material_group")},
                label_col: r.get(label_col),
            }
            for r in st.session_state.rows
        ]
    )
    scores = results_frame()
    if not scores.empty:
        labels = labels.merge(scores[["supplier_id", "score"]], on="supplier_id", how="left")
    labels = with_numeric(labels, [label_col, "score"])
    edited_labels = data_editor(
        labels,
        width="stretch",
        hide_index=True,
        key=f"label_editor_{model().view}_{st.session_state.editor_version}",
        disabled=[c for c in labels.columns if c != label_col],
        column_config={
            label_col: st.column_config.NumberColumn(
                tr("Expert label (0–100, {v0})", v0=tr(direction)),
                min_value=0,
                max_value=100,
                step=5,
            ),
            "score": st.column_config.NumberColumn(
                tr("Model {v0}", v0=tr(model().score_label)), format="%.1f"
            ),
        },
    )
    new_labels = dict(zip(edited_labels.supplier_id, edited_labels[label_col]))
    for row in st.session_state.rows:
        value = new_labels.get(row.get("supplier_id"))
        row[label_col] = None if pd.isna(value) else float(value)

    label_upload = st.file_uploader(
        tr("Import labels CSV (columns supplier_id, {v0})", v0=label_col),
        type=["csv"],
        key=f"label_csv_{model().view}",
    )
    if label_upload is not None and st.session_state.get("imported_labels") != label_upload.file_id:
        st.session_state.imported_labels = label_upload.file_id
        imported = {
            r["supplier_id"]: r.get(label_col)
            for r in from_csv(label_upload.getdisplay_value().decode("utf-8-sig"))
        }
        for row in st.session_state.rows:
            if row.get("supplier_id") in imported and imported[row["supplier_id"]] not in (
                None,
                "",
            ):
                row[label_col] = float(imported[row["supplier_id"]])
        st.session_state.editor_version += 1
        st.rerun()

    n_labels = sum(1 for r in st.session_state.rows if r.get(label_col) is not None)
    c1, c2, _ = st.columns([2, 1, 3])
    scope = selectbox(
        tr("Calibrate for"),
        ["All material groups (global)", *material_groups()],
        key="cal_scope",
        format_func=option_labels(["All material groups (global)", *material_groups()], tr),
        _parent=c1,
    )
    if c2.button(
        tr("🎯 Calibrate"),
        type="primary",
        width="stretch",
        disabled=n_labels == 0,
        key="control_518",
    ):
        run(calibrate=True, material_group=None if scope.startswith("All") else scope)
        st.rerun()
    st.caption(
        tr(
            "{v0} supplier(s) labelled for this view. Roughly 30 or more consistent labels per scope are needed before calibration is usually accepted.",
            v0=n_labels,
        )
    )

    report = (run_info().get("state") or {}).get("calibration_report")
    if report:
        st.divider()
        st.subheader(tr("Result"))
        k = st.columns(5)
        k[0].metric(tr("Labels used"), report.n_samples)
        if report.cv_mse_before is not None:
            k[1].metric(
                tr("Error before → after (cross-validated)"),
                f"{number(report.cv_mse_before, '.1f')} → {number(report.cv_mse_after, '.1f')}",
            )
            k[2].metric(tr("Clarity z (≥ 2 needed)"), number(report.cv_improvement_z, ".1f"))
        if report.regularization_used is not None:
            k[3].metric(tr("Regularisation λ"), number(report.regularization_used, ".3g"))
        if report.level_offset is not None:
            k[4].metric(
                tr("Mean label − model (internal scale)"), number(report.level_offset, "+.1f")
            )
        (st.success if report.accepted else st.info)(report.message)
        for warning in report.warnings:
            st.warning(message(warning))

        if report.new_weights:
            comparison = pd.DataFrame(
                [
                    {"factor": tr(f), "weights": tr("current"), "weight": v * 100}
                    for f, v in report.old_weights.items()
                ]
                + [
                    {"factor": tr(f), "weights": tr("proposed"), "weight": v * 100}
                    for f, v in report.new_weights.items()
                ]
            )
            bars = (
                alt.Chart(comparison)
                .mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4)
                .encode(
                    y=alt.Y(
                        "factor:N",
                        title=None,
                        sort=[tr(f) for f in report.old_weights],
                        axis=alt.Axis(labelLimit=220),
                    ),
                    yOffset=alt.YOffset("weights:N", sort=[tr("current"), tr("proposed")]),
                    x=alt.X("weight:Q", title=tr("Weight (%)")),
                    color=alt.Color(
                        "weights:N",
                        scale=alt.Scale(
                            domain=[tr("current"), tr("proposed")],
                            range=[CURRENT_COLOR, PROPOSED_COLOR],
                        ),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=[
                        alt.Tooltip("factor:N", title=tr("factor")),
                        alt.Tooltip("weights:N", title=tr("weights")),
                        alt.Tooltip("weight:Q", format=".1f", title=tr("weight %")),
                    ],
                )
            )
            localized_chart(
                bars.properties(
                    height=46 * len(report.old_weights), title=tr("Current vs. proposed weights")
                ),
                width="stretch",
            )
            table = pd.DataFrame(
                {
                    "current %": {f: v * 100 for f, v in report.old_weights.items()},
                    "proposed %": {f: v * 100 for f, v in report.new_weights.items()},
                }
            )
            table["change"] = table["proposed %"] - table["current %"]
            with st.expander(tr("Weights as a table")):
                dataframe(table.round(1), width="stretch")
                st.download_button(
                    tr("Export weights CSV"),
                    table.round(4).to_csv(),
                    file_name=f"{model().view}_weights.csv",
                    mime="text/csv",
                    key="control_562",
                )


# --- page: review & approval -----------------------------------------------------------------


def review_page():
    state = run_info().get("state")
    evaluator = run_info().get("evaluator")
    request = evaluator.pending_review(state) if state and evaluator else None
    if not request:
        if state and state.get("review_decision"):
            d = state["review_decision"]
            st.success(tr("Review {v0} by {v1}.", v0=tr(state.get("review_status")), v1=d.reviewer))
            report = state.get("calibration_report")
            if report and report.stored_as:
                st.caption(tr("Approved weights stored as `{v0}`", v0=report.stored_as))
        else:
            st.info(
                tr(
                    "Nothing to review. Runs pause here when data is insufficient or calibrated weights are proposed."
                )
            )
    else:
        st.subheader(tr("Waiting for your decision — {v0} view", v0=tr(model().view_label)))
        proposed = request.get("proposed_weights")
        if proposed:
            st.markdown(
                tr(
                    "**Proposed weights** for scope *{v0}* from {v1} labels — cross-validated error {v2} → {v3} (z = {v4}). Details in **🎯 Calibration**.",
                    v0=proposed["scope"],
                    v1=proposed["n_samples"],
                    v2=number(proposed["cv_mse_before"], ".1f"),
                    v3=number(proposed["cv_mse_after"], ".1f"),
                    v4=number(proposed["cv_improvement_z"], ".1f"),
                )
            )
            for warning in proposed.get("warnings", []):
                st.warning(message(warning))
        for reason in request.get("portfolio_reasons", []):
            st.info(message(reason))

        flagged = pd.DataFrame(request["flagged_suppliers"])
        overrides = None
        if not flagged.empty:
            st.markdown(
                tr(
                    "**Suppliers flagged for review** — optionally set a class manually (with a comment)."
                )
            )
            flagged = flagged.assign(
                current=flagged.risk_class.map(class_label),
                new_class="",
                comment="",
                reasons=flagged.reasons.map("; ".join),
            )
            overrides = data_editor(
                flagged[["supplier_id", "name", "current", "reasons", "new_class", "comment"]],
                width="stretch",
                hide_index=True,
                key=f"override_editor_{state['run_id']}",
                disabled=["supplier_id", "name", "current", "reasons"],
                column_config={
                    "new_class": st.column_config.SelectboxColumn(
                        tr("New class"), options=["", *request["allowed_classes"]], format_func=tr
                    )
                },
            )

        with st.container(key="decision"):
            reviewer = st.text_input(tr("Reviewer"), placeholder=tr("Your name"), key="control_610")
            approve = st.checkbox(
                tr("Approve proposed weights"), disabled=not proposed, key="control_611"
            )
            c1, c2 = st.columns(2)
            submit = c1.button(
                tr("✅ Submit decision"), type="primary", width="stretch", key="control_613"
            )
            defer = c2.button(tr("Defer"), width="stretch", key="control_614")
        if submit or defer:
            chosen = {}
            if overrides is not None:
                for row in overrides.to_dict("records"):
                    if row["new_class"]:
                        chosen[row["supplier_id"]] = ClassOverride(
                            risk_class=row["new_class"], comment=row["comment"] or ""
                        )
            decision = ReviewDecision(
                reviewer=reviewer or "unknown",
                approve_weights=bool(approve and proposed),
                overrides=chosen,
                defer=defer,
            )
            new_state = evaluator.resume(state["run_id"], decision)
            run_info()["state"] = new_state
            if not defer:  # an approved assessment is worth keeping: snapshot to history
                history().record(
                    list(new_state["results"].values()),
                    model(),
                    run_id=new_state["run_id"],
                    note="after review",
                    approved_by=decision.reviewer,
                )
            st.rerun()

    if state and state.get("errors"):
        with st.expander(tr("Messages")):
            for error in state["errors"]:
                st.warning(message(error))


# --- page: explain & correct ----------------------------------------------------------------


def show_ai_review(result: AIReviewResult, outdated_note: str | dict | None) -> None:
    if outdated_note:
        if isinstance(outdated_note, dict):
            outdated_note = tr(
                "the correction of {time} ({reason})",
                time=date(outdated_note["time"]),
                reason=outdated_note["reason"],
            )
        st.error(
            tr(
                "Outdated: this AI explanation was generated before {v0}. The numbers above are current; generate a new explanation to match them.",
                v0=message(outdated_note),
            ),
            icon="⚠️",
        )
    st.warning(tr(result.disclaimer), icon="🤖")
    st.caption(
        tr(
            "Original explanation · {lang}. A language change does not request a new explanation.",
            lang=tr({"de": "German", "en": "English"}[result.language]),
        )
    )
    r = result.review
    st.markdown(tr("**Management summary**"))
    st.write(r.management_summary)
    st.caption(tr("Based on: ") + tr(", ".join(f"`{x}`" for x in r.summary_refs)))
    st.markdown(tr("**Main drivers**"))
    dataframe(
        pd.DataFrame(
            [{**d.model_dump(), "trace_refs": ", ".join(d.trace_refs)} for d in r.risk_drivers]
        ),
        original_text=True,
        hide_index=True,
        width="stretch",
        column_config={
            "criterion": "Criterion",
            "view": "View",
            "explanation": "Why it matters",
            "trace_refs": "Trace entries",
        },
    )
    if r.view_differences:
        st.markdown(tr("**Risk vs. performance**"))
        for d in r.view_differences:
            st.markdown(
                tr(
                    "- **{v0}** — {v1} `{v2}`",
                    v0=d.topic,
                    v1=d.explanation,
                    v2=", ".join(d.trace_refs),
                )
            )
    st.markdown(tr("**Suggested actions** — proposals for human review, not decisions"))
    dataframe(
        pd.DataFrame(
            [
                {
                    **a.model_dump(),
                    "criteria": ", ".join(a.criteria),
                    "trace_refs": ", ".join(a.trace_refs),
                }
                for a in r.suggested_actions
            ]
        ),
        original_text=True,
        hide_index=True,
        width="stretch",
        column_config={
            "priority": "Priority",
            "action": "Action",
            "rationale": "Rationale",
            "criteria": "Criteria",
            "trace_refs": "Trace entries",
        },
    )
    if r.open_questions or result.data_gaps:
        st.markdown(tr("**Open questions**"))
        for q in r.open_questions:
            st.markdown(tr("- {v0} `{v1}`", v0=q.question, v1=", ".join(q.criteria)))
        if result.data_gaps:
            st.caption(
                tr("Missing data in the input (determined by the tool, not by the LLM): ")
                + tr(", ".join(result.data_gaps))
            )
    st.caption(
        tr(
            "{v0} / {v1} · {v2} · input SHA-256 {v3}…",
            v0=result.provider,
            v1=result.model,
            v2=date(result.created_at),
            v3=result.payload_sha256[:12],
        )
    )


def inputs_text(inputs: list[dict]) -> str:
    return "; ".join(
        f"{tr(i['input'])} = {display_value(i['value'])} [{message(i['source'])}]" for i in inputs
    )


def show_trace(t: dict) -> None:
    s = t["score"]
    st.markdown(
        tr(
            "**{v0}** · {v1} **{v2}** · class **{v3}** · data {v4} · model `{v5}` · weights `{v6}`",
            v0=tr(ui_model(t["view"]).view_label),
            v1=tr(s["label"]),
            v2=display_value(s["value"]),
            v3=class_label(t["class"]["final"])
            if t["view"] == model().view
            else risk_name(t["class"]["final"]),
            v4=number(t["data_completeness"], ".0%"),
            v5=t["model"],
            v6=t["weights"],
        )
    )
    st.caption(
        message(s["note"])
        + tr(
            ". Sum of contributions: {v0} = internal score {v1}.",
            v0=display_value(s["sum_of_contributions"]),
            v1=display_value(s["internal_value"]),
        )
    )
    frame = pd.DataFrame(
        [
            {  # numbers first, long texts last, so the contributions stay visible
                "id": c["id"],
                "criterion": tr(c["label"]),
                "rating": c["rating"],
                "points": c["contribution_points"],
                "weight": c["nominal_weight"],
                "effective weight": c["effective_weight"],
                "origin": c["rating_origin"],
                "inputs (source)": inputs_text(c["inputs"]),
                "rule": c["rule"],
            }
            for c in sorted(t["criteria"], key=lambda c: -(c["contribution_points"] or 0))
        ]
    )
    dataframe(
        frame,
        hide_index=True,
        width="stretch",
        column_config={
            "weight": st.column_config.NumberColumn(tr("Weight"), format="%.3f"),
            "effective weight": st.column_config.NumberColumn(
                tr("Effective weight"), format="%.3f"
            ),
            "points": st.column_config.NumberColumn(tr("Points"), format="%.2f"),
        },
    )
    rules = [
        r for r in t["non_additive"] if r["fired"] or r.get("rating") is None and "rule" in r["id"]
    ]
    st.markdown(
        tr("Rules that do not add points: ")
        + (
            tr("; ".join(f"`{r['id']}` {message(r['effect'])}" for r in rules))
            if rules
            else tr("none triggered.")
        )
    )


def detail_page():
    ensure_both_views()
    link(portfolio_page, tr("Zurück zum Portfolio"), ":material/arrow_back:")
    st.caption(tr("SUPPLIER WORKSPACE / LIEFERANTENDETAIL"))
    current = list(
        st.session_state.runs.get("risk", {}).get("state", {}).get("results", {}).values()
    )
    if not current:
        st.info(
            tr(
                "Noch keine Bewertungen. Starten Sie die Demo oder importieren Sie Lieferantendaten."
            )
        )
    else:
        names = {a.supplier_id: a.supplier_name for a in current}
        if st.session_state.get("selected_supplier") in names:
            st.session_state.ai_supplier = st.session_state.pop("selected_supplier")
        sid = selectbox(
            tr("Lieferant"),
            sorted(names),
            format_func=option_labels(sorted(names), lambda i: f"{names[i]} · {i}"),
            key="ai_supplier",
            _parent=st,
        )
        st.title(tr(names[sid]))
        row = next(r for r in st.session_state.rows if str(r.get("supplier_id")) == sid)
        st.caption(
            tr(
                "{v0} · {v1} · {v2}",
                v0=sid,
                v1=row.get("material_group") or tr("Ohne Warengruppe"),
                v2=row.get("country") or tr("Land nicht angegeben"),
            )
        )
        if st.session_state.get("correction_success") == sid:
            st.success(
                tr(
                    "Korrektur bestätigt. Beide Bewertungen wurden aktualisiert und die Änderung protokolliert."
                )
            )

        runs = st.session_state.setdefault("runs", {})
        for view in ("risk", "performance"):
            if not (runs.get(view) or {}).get("state"):
                run(calibrate=False, material_group=None, view=view)
        try:
            payload = ai_review_payload(
                sid, *((runs[v]["evaluator"], runs[v]["state"]) for v in ("risk", "performance"))
            )
        except (KeyError, LookupError) as exc:
            payload = None
            st.warning(tr("Both views are needed: {v0}", v0=error_text(exc)))

        if payload is not None:
            # 1 · deterministic explanation --------------------------------------------------------
            for col, (view, t) in zip(st.columns(2), payload["views"].items()):
                with col.container(border=True):
                    st.markdown(tr("**RISIKO**") if view == "risk" else tr("**PERFORMANCE**"))
                    st.metric(
                        (
                            tr("Risiko bei Ausfall")
                            if view == "risk"
                            else tr("Leistung des Lieferanten")
                        ),
                        "—"
                        if t["score"]["value"] is None
                        else f"{number(t['score']['value'], '.1f')} / 100",
                    )
                    final_class = t["class"]["final"]
                    color = {
                        "low": "green",
                        "medium": "orange",
                        "high": "orange",
                        "critical": "red",
                        "A": "green",
                        "B": "orange",
                        "C": "red",
                    }.get(final_class, "gray")
                    st.badge(tr(risk_name(final_class)), color=color)
                    st.caption(
                        tr("Niedriger ist besser") if view == "risk" else tr("Höher ist besser")
                    )
                    st.caption(tr("Datenbasis: {v0}", v0=number(t["data_completeness"], ".0%")))
                    if t["class"]["final"] != t["class"]["from_score"]:
                        st.warning(
                            tr(
                                "Klasse aus Score: {v0}. Eine Eskalation oder Freigabe verändert die endgültige Klasse.",
                                v0=risk_name(t["class"]["from_score"]),
                            )
                        )
            gaps = [
                v
                for v, t in payload["views"].items()
                if t["data_completeness"] < ui_model(v).min_data_completeness
            ]
            if gaps:
                st.warning(
                    tr(
                        "Unvollständige Datenbasis: Diese Bewertung erfordert eine fachliche Prüfung."
                    )
                )
            st.write("")
            st.subheader(tr("Bewertung nachvollziehen & korrigieren"))
            st.caption(
                tr(
                    "1  Verstehen   →   2  Korrektur begründen   →   3  Wirkung prüfen   →   4  Bestätigen"
                )
            )
            with st.expander(tr("Warum diese Bewertung?"), expanded=True):
                for col, (v, t) in zip(st.columns(2), payload["views"].items()):
                    with col:
                        st.markdown(
                            tr("**Risiko: wichtigste Beiträge**")
                            if v == "risk"
                            else tr("**Performance: größte Abzüge**")
                        )
                        ranked = sorted(
                            t["criteria"], key=lambda c: -(c["contribution_points"] or 0)
                        )[:3]
                        for c in ranked:
                            st.write(
                                tr(
                                    "{v0} · {v1} Punkte",
                                    v0=tr(c["label"]),
                                    v1=number(c["contribution_points"] or 0, ".2f"),
                                )
                            )
                        if v == "performance":
                            st.caption(tr("Performance = 100 − interne Belastungspunkte."))
                        for rule in t["non_additive"]:
                            if rule["fired"]:
                                st.info(
                                    tr("{v0} ({v1})", v0=message(rule["effect"]), v1=rule["id"])
                                )
                for v, t in payload["views"].items():
                    with st.expander(
                        tr("Daten, Quellen & Berechnung · ")
                        + (tr("Risiko") if v == "risk" else tr("Performance"))
                    ):
                        show_trace(t)
            with st.expander(tr("Empfohlene Maßnahmen")):
                for v in ("risk", "performance"):
                    a = runs[v]["state"]["results"].get(sid)
                    if a:
                        st.markdown(
                            (tr("**") + (tr("Risiko") if v == "risk" else tr("Performance")))
                            + tr("**")
                        )
                        for recommendation in a.recommendations:
                            st.write(
                                tr(
                                    "{v0} · {v1}",
                                    v0=tr(recommendation.priority),
                                    v1=message(recommendation.action),
                                )
                            )
            # 3 · controlled correction ---------------------------------------------------------------------
            st.subheader(tr("Korrektur begründen"))
            st.caption(
                tr(
                    "Korrigieren Sie einen Eingabewert oder ersetzen Sie eine abgeleitete Bewertung durch ein Expertenurteil (1–5). Begründen Sie die Änderung. Gewichte und Regeln werden separat kalibriert und freigegeben."
                )
            )
            fields = correctable_fields([ui_model("risk"), ui_model("performance")])
            row = next(r for r in st.session_state.rows if str(r.get("supplier_id")) == sid)
            with st.expander(tr("Alle korrigierbaren Felder und aktuellen Werte")):
                dataframe(
                    pd.DataFrame(
                        [
                            {
                                "field": f,
                                "kind": spec["kind"].replace("_", " "),
                                "used by": ", ".join(spec["criteria"]),
                                "expects": spec["expects"],
                                "current": None
                                if row.get(f) is None
                                else display_value(row.get(f)),
                            }
                            for f, spec in fields.items()
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
            with st.container(key=f"correction_form_{sid}"):
                f1, f2 = st.columns([2, 1])
                c_field = selectbox(
                    tr("Feld"),
                    list(fields),
                    key=f"correction_field_{sid}",
                    format_func=option_labels(
                        list(fields),
                        lambda f: tr(
                            "{label} · {field} · current: {current}",
                            label=tr(fields[f]["label"]),
                            field=f,
                            current=display_value(row.get(f)),
                        ),
                    ),
                    _parent=f1,
                )
                c_value = f2.text_input(
                    tr("Neuer Wert ('none' leert das Feld)"), key=f"correction_value_{sid}"
                )
                reason = st.text_area(
                    tr("Begründung (erforderlich)"), key=f"correction_reason_{sid}"
                )
                entered_by = st.text_input(
                    tr("Ihr Name (optional, ungeprüft)"), key=f"correction_name_{sid}"
                )
                preview_clicked = st.button(tr("Vorher/Nachher prüfen"), key="control_789")
            if preview_clicked:
                try:
                    request = CorrectionRequest(
                        supplier_id=sid,
                        reason=reason,
                        entered_by=entered_by.strip() or None,
                        changes=[
                            FieldChange(
                                field=c_field,
                                kind=fields[c_field]["kind"],
                                new_value=parse_cell(parse_input(c_value)),
                            )
                        ],
                    )
                    active = {
                        v: (runs[v]["state"] or {}).get("active_weights") or {}
                        for v in ("risk", "performance")
                    }
                    new_rows, comparison = preview_correction(
                        st.session_state.rows,
                        request,
                        [ui_model("risk"), ui_model("performance")],
                        active,
                        providers(),
                    )
                    st.session_state.pending_correction = {
                        "sid": sid,
                        "request": request,
                        "new_rows": new_rows,
                        "comparison": comparison,
                    }
                except (ValidationError, ValueError) as exc:
                    st.session_state.pop("pending_correction", None)
                    st.error(tr("Korrektur nicht möglich: {v0}", v0=error_text(exc)))
            pending = st.session_state.get("pending_correction")
            if pending and pending["sid"] == sid:
                st.markdown(tr("**Vorschau — noch nicht übernommen**"))
                request = pending["request"]
                st.write(tr("**Begründung dieser Vorschau:** ") + request.reason)
                for change in request.changes:
                    st.write(
                        tr(
                            "{v0}: {v1} → {v2}",
                            v0=tr(change.field),
                            v1=display_value(change.old_value),
                            v2=display_value(change.new_value),
                        )
                    )
                comparison = pending["comparison"]
                show_comparison(comparison)
                a1, a2 = st.columns(2)
                if a1.button(
                    tr("Korrektur bestätigen"), type="primary", width="stretch", key="control_814"
                ):
                    apply_corrections([(pending["request"], comparison)], pending["new_rows"])
                    st.session_state.pop("pending_correction", None)
                    st.session_state.correction_success = sid
                    st.toast(tr("Korrektur gespeichert"))
                    st.rerun()
                if a2.button(tr("Vorschau verwerfen"), width="stretch", key="control_820"):
                    st.session_state.pop("pending_correction", None)
                    st.rerun()
            log = history().corrections(sid)
            if log:
                with st.expander(tr("Korrekturhistorie ({v0})", v0=len(log))):
                    dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "time": date(e["recorded_at"]),
                                    "changes": "; ".join(
                                        f"{tr(c['field'])} ({tr(c['kind'])}): {display_value(c['old_value'])} → {display_value(c['new_value'])}"
                                        for c in e["changes"]
                                    ),
                                    "reason": e["reason"],
                                    "entered by (not verified)": e["entered_by"],
                                    "risk": f"{display_value(e['views']['risk']['score'][0])} → {display_value(e['views']['risk']['score'][1])}",
                                    "performance": f"{display_value(e['views']['performance']['score'][0])} → "
                                    f"{display_value(e['views']['performance']['score'][1])}",
                                }
                                for e in log
                            ]
                        ),
                        hide_index=True,
                        width="stretch",
                    )

            with st.expander(tr("KI-Erklärung · optional")):
                # 2 · AI explanation -----------------------------------------------------------------------
                try:
                    llm_settings = LLMSettings.from_env()
                    unavailable = llm_settings.unavailable_reason
                except LLMReviewError as exc:
                    llm_settings, unavailable = None, str(exc)
                if unavailable:
                    st.info(
                        tr(
                            "AI explanation not available: {v0} The calculation above is complete without it.",
                            v0=error_text(unavailable),
                        )
                    )
                else:
                    st.caption(
                        tr(
                            "Provider: **{v0}** · timeout {v1} s per attempt · up to {v2} retries",
                            v0=llm_settings.describe(),
                            v1=number(llm_settings.timeout_seconds, "g"),
                            v2=llm_settings.max_retries,
                        )
                    )
                st.caption(
                    tr(
                        "New explanations are generated in {lang}.",
                        lang=tr({"de": "German", "en": "English"}[language()]),
                    )
                )
                digest = payload_hash(payload)
                with st.expander(tr("Data sent to the provider (exactly this JSON)")):
                    st.caption(
                        tr(
                            "The scoring trace of both views. Not sent: supplier name, country, annual spend and expert labels. Use synthetic or approved data only."
                        )
                    )
                    st.code(payload_json(payload), language="json")
                explanations = st.session_state.setdefault(
                    "ai_explanations", {}
                )  # supplier -> AIReviewResult
                outdated_notes = st.session_state.setdefault("ai_outdated", {})  # supplier -> note
                failures = st.session_state.setdefault("ai_review_failures", {})
                existing = explanations.get(sid)
                current_ok = existing is not None and review_is_current(existing, payload)
                c1, c2 = st.columns(2)
                clicked = c1.button(
                    tr("Generate AI Review"),
                    type="primary",
                    width="stretch",
                    disabled=bool(unavailable) or current_ok,
                    help=tr(
                        "One paid API call. The result is kept for this exact input; reruns of the app do not call the provider again."
                    ),
                    key="control_857",
                )
                if existing is not None:
                    c2.button(
                        tr("Discard explanation"),
                        width="stretch",
                        on_click=lambda s=sid: (
                            explanations.pop(s, None),
                            outdated_notes.pop(s, None),
                        ),
                        key="control_861",
                    )
                if (
                    clicked and not current_ok
                ):  # explicit trigger only; guarded against double clicks
                    risk_run = runs["risk"]
                    with st.spinner(tr("Waiting for {v0} …", v0=llm_settings.describe())):
                        new_state = risk_run["evaluator"].ai_review(
                            risk_run["state"]["run_id"], payload, language=language()
                        )
                    risk_run["state"] = new_state
                    error = new_state.get("ai_review_errors", {}).get(sid)
                    if error:
                        failures[digest] = error
                    else:
                        failures.pop(digest, None)
                        explanations[sid] = new_state["ai_reviews"][sid]
                        outdated_notes.pop(sid, None)
                    st.rerun()
                if digest in failures and not current_ok:
                    st.error(tr("AI explanation failed: {v0}", v0=error_text(failures[digest])))
                if existing is not None:
                    show_ai_review(
                        existing,
                        None if current_ok else outdated_notes.get(sid, "the data changed"),
                    )

            with st.expander(tr("Bewertung beanstanden")):
                # 4 · dispute --------------------------------------------------------------------------------------
                st.caption(
                    tr(
                        "Records that you disagree with a criterion. It changes no score and does not train weights; it is a note for the next review."
                    )
                )
                with st.container(key=f"dispute_form_{sid}"):
                    d1, d2 = st.columns(2)
                    d_view = selectbox(
                        tr("View"),
                        ["risk", "performance"],
                        format_func=option_labels(
                            ["risk", "performance"], lambda v: tr(ui_model(v).view_label)
                        ),
                        key=f"dispute_view_{sid}",
                        _parent=d1,
                    )
                    criteria = sorted(
                        {c["key"] for t in payload["views"].values() for c in t["criteria"]}
                    )
                    d_criterion = selectbox(
                        tr("Criterion"),
                        criteria,
                        format_func=option_labels(criteria, tr),
                        key=f"dispute_criterion_{sid}",
                        _parent=d2,
                    )
                    d_reason = st.text_area(
                        tr("Why is the assessment wrong? (required)"), key=f"dispute_reason_{sid}"
                    )
                    d_name = st.text_input(
                        tr("Ihr Name (optional, ungeprüft)"), key=f"dispute_name_{sid}"
                    )
                    if st.button(tr("Record objection"), key="control_892"):
                        entry_view = payload["views"].get(d_view, {})
                        rated = next(
                            (c for c in entry_view.get("criteria", []) if c["key"] == d_criterion),
                            None,
                        )
                        try:
                            history().record_objection(
                                sid,
                                d_view,
                                d_criterion,
                                d_reason,
                                d_name.strip() or None,
                                context={
                                    "rating": rated["rating"] if rated else None,
                                    "score": entry_view.get("score", {}).get("value"),
                                },
                            )
                            st.success(tr("Objection recorded. Scores are unchanged."))
                        except ValueError as exc:
                            st.error(error_text(exc))
                objections = history().objections(sid)
                if objections:
                    with st.expander(tr("Objections ({v0})", v0=len(objections))):
                        dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        k: o[k]
                                        for k in (
                                            "recorded_at",
                                            "view",
                                            "criterion",
                                            "reason",
                                            "entered_by",
                                            "status",
                                        )
                                    }
                                    for o in objections
                                ]
                            ),
                            hide_index=True,
                            width="stretch",
                        )


def home_page():
    st.caption(tr("SUPPLIER WORKSPACE / WILLKOMMEN"))
    st.title(tr("Gute Entscheidungen beginnen\nmit einem klaren Überblick."))
    st.markdown(tr("Risiken erkennen. Leistung verstehen. Bewertungen gemeinsam verbessern."))
    st.write("")
    with st.container(border=True):
        st.subheader(tr("Ihr Lieferantenportfolio. Zwei Perspektiven."))
        st.write(
            tr(
                "Erkunden Sie sechs fiktive Lieferanten und sehen Sie, warum gute Performance nicht automatisch geringes Risiko bedeutet."
            )
        )
        if st.button(
            tr("Demo ausprobieren"), type="primary", icon=":material/play_arrow:", key="control_918"
        ):
            with st.spinner(tr("Demo wird vorbereitet …")):
                set_rows(load_rows(next(iter(DATASETS.values()))), next(iter(DATASETS)))
                st.session_state.demo_mode = True
            navigate(portfolio_page)
        st.caption(tr("Synthetische Daten · Kein API-Key nötig · Keine automatische KI-Anfrage"))
    for col, title, body in zip(
        st.columns(3),
        ["01  Überblick gewinnen", "02  Bewertung verstehen", "03  Begründet korrigieren"],
        [
            "Risiko und Performance in einer gemeinsamen Tabelle vergleichen.",
            "Von der Bewertung bis zu Daten, Regeln und Quellen navigieren.",
            "Die Wirkung prüfen und Änderungen bewusst bestätigen.",
        ],
    ):
        with col:
            st.markdown(tr("**{v0}**", v0=tr(title)))
            st.write(tr(body))
    st.divider()
    link(data_page, label=tr("Mit eigenen Daten starten"), icon=":material/upload_file:")
    st.caption(
        tr("CSV importieren oder Lieferanten erfassen. Bewertungen werden auf Anfrage berechnet.")
    )


def ensure_both_views():
    for v in ("risk", "performance"):
        if not st.session_state.get("runs", {}).get(v, {}).get("state"):
            with st.spinner(tr("Risiko und Performance werden berechnet …")):
                run(calibrate=False, material_group=None, view=v)


def portfolio_page():
    ensure_both_views()
    st.caption(tr("SUPPLIER WORKSPACE / PORTFOLIO"))
    left, right = st.columns([4, 1], vertical_alignment="bottom")
    left.title(tr("Lieferantenportfolio"))
    left.write(tr("Risiko und Performance. Alle Lieferanten im Blick."))
    if right.button(
        tr("Neu berechnen"), icon=":material/refresh:", width="stretch", key="control_950"
    ):
        for v in ("risk", "performance"):
            run(False, None, v)
        st.rerun()
    risks = st.session_state.runs.get("risk", {}).get("state", {}).get("results", {})
    perfs = st.session_state.runs.get("performance", {}).get("state", {}).get("results", {})
    if not risks:
        st.info(tr("Noch keine Bewertungen. Importieren Sie eine CSV oder starten Sie die Demo."))
        link(home_page, label=tr("Zur Demo"), icon=":material/play_arrow:")
        link(data_page, label=tr("Daten erfassen"), icon=":material/upload_file:")
        return
    records = []
    for sid, a in risks.items():
        b = perfs.get(sid)
        records.append(
            {
                "supplier_id": sid,
                "name": a.supplier_name,
                "material_group": a.material_group or "Ohne Warengruppe",
                "risk": ui_model("risk").to_display(a.overall_score),
                "risk_class": a.risk_class,
                "performance": ui_model("performance").to_display(b.overall_score) if b else None,
                "performance_class": b.risk_class if b else None,
                "review": a.requires_human_review or bool(b and b.requires_human_review),
                "data": min(a.data_completeness, b.data_completeness if b else 0) * 100,
                "escalated": bool(a.escalations) or bool(b and b.escalations),
            }
        )
    df = pd.DataFrame(records)
    # Class severity comes before score: a class floor must never disappear in a ranking.
    df["rank"] = df.risk_class.map({"critical": 0, "high": 1, "medium": 2, "low": 3}).fillna(4)
    df = df.sort_values(["rank", "risk"], ascending=[True, False]).drop(columns="rank")
    for col, label, value, note in zip(
        st.columns(4),
        ["Lieferanten", "Erhöhtes Risiko", "Performance A", "Prüfung erforderlich"],
        [
            len(df),
            int(df.risk_class.isin(["high", "critical"]).sum()),
            int((df.performance_class == "A").sum()),
            int(df.review.sum()),
        ],
        [
            "im Portfolio",
            "hoch oder kritisch",
            "leistungsstarke Partner",
            "Daten oder Bewertung prüfen",
        ],
    ):
        with col.container(border=True):
            st.metric(tr(label), value)
            st.caption(message(note))
    with st.container(border=True):
        search = st.text_input(
            tr("Lieferanten suchen"),
            placeholder=tr("Name oder Lieferanten-ID …"),
            key="portfolio_search",
            icon=":material/search:",
        )
        f = st.columns(3)
        groups = multiselect(
            tr("Warengruppe"),
            sorted(df.material_group.unique()),
            key="portfolio_groups",
            placeholder=tr("Choose options"),
            _parent=f[0],
        )
        classes = multiselect(
            tr("Risikoklasse"),
            ["low", "medium", "high", "critical"],
            format_func=option_labels(["low", "medium", "high", "critical"], risk_name),
            key="portfolio_classes",
            placeholder=tr("Choose options"),
            _parent=f[1],
        )
        perf = multiselect(
            tr("Performance"),
            ["A", "B", "C"],
            key="portfolio_perf",
            placeholder=tr("Choose options"),
            _parent=f[2],
        )
        only_review = st.checkbox(tr("Nur Lieferanten mit Prüfbedarf"), key="portfolio_review")
        visible = df
        if search:
            visible = visible[
                visible.name.str.contains(search, case=False, regex=False)
                | visible.supplier_id.str.contains(search, case=False, regex=False)
            ]
        for column, chosen in (
            ("material_group", groups),
            ("risk_class", classes),
            ("performance_class", perf),
        ):
            if chosen:
                visible = visible[visible[column].isin(chosen)]
        if only_review:
            visible = visible[visible.review]
        st.caption(
            tr(
                "{v0} von {v1} Lieferanten · Zeile auswählen, um die Bewertung zu öffnen",
                v0=len(visible),
                v1=len(df),
            )
        )
        if visible.empty:
            st.info(
                tr("Keine Lieferanten gefunden. Passen Sie den Suchbegriff oder die Filter an.")
            )
            st.button(tr("Filter zurücksetzen"), on_click=reset_filters, key="control_1005")
            return
        shown = visible.assign(
            risk_class=visible.risk_class.map(risk_name),
            performance_class=visible.performance_class.fillna(tr("Nicht bewertet")),
            review=visible.review.map({True: tr("Prüfen"), False: "—"}),
        )
        event = dataframe(
            shown.style.map(status_cell, subset=["risk_class", "performance_class"]),
            hide_index=True,
            width="stretch",
            row_height=48,
            column_order=[
                "name",
                "risk_class",
                "risk",
                "performance_class",
                "performance",
                "review",
                "material_group",
                "data",
                "supplier_id",
            ],
            column_config={
                "name": st.column_config.TextColumn(tr("Lieferant"), width="medium"),
                "risk_class": "Risiko",
                "risk": st.column_config.NumberColumn(tr("Risk ↓"), format="%.1f"),
                "performance_class": "Klasse",
                "performance": st.column_config.NumberColumn(tr("Performance ↑"), format="%.1f"),
                "review": "Prüfbedarf",
                "material_group": "Warengruppe",
                "supplier_id": "ID",
                "data": st.column_config.ProgressColumn(
                    tr("Datenbasis"), min_value=0, max_value=100, format="%.0f %%"
                ),
            },
            on_select="rerun",
            selection_mode="single-row",
            key=f"portfolio_table_{st.session_state.get('portfolio_version', 0)}",
        )
        if event.selection.rows:
            open_supplier(str(visible.iloc[event.selection.rows[0]].supplier_id))
        st.caption(
            tr(
                "Risk: niedriger ist besser · Performance: höher ist besser · Skala 0–100. Eskalationsregeln können die Klasse unabhängig vom Score erhöhen."
            )
        )
        # Accessible alternative to the canvas table, especially on narrow screens.
        with st.expander(tr("Lieferanten direkt öffnen")):
            sid = selectbox(
                tr("Lieferant auswählen"),
                list(visible.supplier_id),
                format_func=option_labels(
                    list(visible.supplier_id), lambda s: f"{risks[s].supplier_name} · {s}"
                ),
                key="portfolio_supplier",
                _parent=st,
            )
            if st.button(tr("Bewertung öffnen"), type="primary", key="control_1028"):
                open_supplier(sid)
        st.download_button(
            tr("Tabelle exportieren"),
            to_csv(visible.to_dict("records")),
            file_name="supplier_portfolio.csv",
            mime="text/csv",
            icon=":material/download:",
            key="control_1030",
        )


def risk_name(value):
    return tr(value or "Nicht bewertet")


def status_cell(value):
    color, background = {
        tr("Niedrig"): ("#22634b", "#e8f3ed"),
        "A": ("#22634b", "#e8f3ed"),
        tr("Mittel"): ("#805b15", "#fcf3dc"),
        "B": ("#805b15", "#fcf3dc"),
        tr("Hoch"): ("#94562b", "#fff0e5"),
        tr("Kritisch"): ("#a33636", "#fbe9e7"),
        "C": ("#a33636", "#fbe9e7"),
    }.get(value, ("#526175", "#f1f4f8"))
    return f"color: {color}; background-color: {background}; font-weight: 600"


def reset_filters():
    for key in ("portfolio_groups", "portfolio_classes", "portfolio_perf"):
        st.session_state[key] = []
        for locale in ("de", "en"):
            st.session_state.pop(f"{key}__{locale}", None)
    st.session_state.portfolio_search = ""
    st.session_state.portfolio_review = False


def open_supplier(sid):
    st.session_state.selected_supplier = sid
    st.session_state.portfolio_version = st.session_state.get("portfolio_version", 0) + 1
    st.session_state.pop("pending_correction", None)
    navigate(detail_page)


def data_page():
    st.title(tr("Daten & Import"))
    st.caption(tr("Lieferanten erfassen, Beispieldaten laden oder eine eigene CSV importieren."))
    choice = selectbox(
        tr("Beispieldaten"),
        list(DATASETS),
        key="dataset_choice",
        format_func=option_labels(list(DATASETS), tr),
        _parent=st,
    )
    if st.button(tr("Beispieldaten laden"), key="control_1065"):
        set_rows(load_rows(DATASETS[choice]), choice)
        st.session_state.demo_mode = True
        st.rerun()
    upload = st.file_uploader(tr("CSV importieren"), type=["csv"], key="input_csv")
    if upload is not None and st.session_state.get("imported") != upload.file_id:
        try:
            rows = from_csv(upload.getdisplay_value().decode("utf-8-sig"))
            profiles, errors = rows_to_profiles(rows, model())
            if errors or not profiles:
                raise ValueError("; ".join(errors) or "Die Datei enthält keine Lieferanten.")
            set_rows(rows, upload.name)
            st.session_state.imported = upload.file_id
            st.session_state.demo_mode = False
            st.rerun()
        except (ValueError, UnicodeError, KeyError) as exc:
            st.error(
                tr(
                    "Import nicht möglich: {v0}. Prüfen Sie die CSV-Vorlage und versuchen Sie es erneut.",
                    v0=error_text(exc),
                )
            )
    a, b = st.columns(2)
    a.download_button(
        tr("Eingabedaten exportieren"),
        to_csv(st.session_state.rows),
        file_name="suppliers.csv",
        mime="text/csv",
        key="control_1083",
    )
    b.download_button(
        tr("CSV-Vorlage herunterladen"),
        ",".join(all_view_columns()) + "\n",
        file_name="template.csv",
        mime="text/csv",
        key="control_1084",
    )
    if st.session_state.rows:
        scoring_page()
    else:
        st.info(tr("Laden Sie Beispieldaten oder importieren Sie zunächst eine CSV-Vorlage."))


def settings_page():
    st.title(tr("Einstellungen"))
    st.checkbox(tr("Store approved weights (versioned)"), key="use_store")
    st.text_input(tr("Weight store folder"), key="store_dir")
    st.checkbox(tr("Political stability from World Bank WGI (MOCK)"), key="use_wgi_mock")
    st.text_input(tr("History folder"), key="history_dir")
    st.caption(tr("Mock-Daten sind fiktiv. Nach Änderungen im Portfolio neu berechnen."))
    st.caption(
        tr(
            "Die optionale KI-Erklärung wird nur im Lieferantendetail ausdrücklich angefordert. API-Zugang über die lokale .env-Datei konfigurieren."
        )
    )


PAGES = {
    "Start": home_page,
    "Portfolio": portfolio_page,
    "Lieferantendetail": detail_page,
    "Dashboard": dashboard_page,
    "Maßnahmen": actions_page,
    "Historie": history_page,
    "Daten & Import": data_page,
    "Kalibrierung": calibration_page,
    "Freigaben": review_page,
    "Einstellungen": settings_page,
}


def navigate(page):
    st.session_state.next_page = next(name for name, fn in PAGES.items() if fn == page)
    st.rerun()


def link(page, label, icon=None):
    if st.button(label, icon=icon, key=f"link_{page.__name__}"):
        navigate(page)


st.session_state.setdefault("view", "risk")
st.session_state.setdefault("rows", [])
st.session_state.setdefault("runs", {})
st.session_state.setdefault("origin", "Noch keine Daten geladen")
st.session_state.setdefault("editor_version", 0)
st.session_state.setdefault("store_dir", "data/weights")
st.session_state.setdefault("history_dir", "data/history")
# Settings and view widgets are conditional; retain their values between pages.
for setting in (
    "view",
    "store_dir",
    "history_dir",
    "use_store",
    "use_wgi_mock",
    "ai_supplier",
    "portfolio_supplier",
    "portfolio_search",
    "portfolio_groups",
    "portfolio_classes",
    "portfolio_perf",
    "portfolio_review",
):
    if setting in st.session_state:
        st.session_state[setting] = st.session_state[setting]
if "next_page" in st.session_state:
    st.session_state.navigation = st.session_state.pop("next_page")
with st.sidebar:
    st.segmented_control(
        "DE | EN",
        ["de", "en"],
        format_func=str.upper,
        key="language",
        selection_mode="single",
        required=True,
        width="stretch",
    )
    st.markdown(tr("### :material/view_quilt: Supplier Workspace"))
    st.caption(tr("PROCUREMENT · RISK & PERFORMANCE"))
    page = st.session_state.setdefault("navigation", "Start")
    st.caption(tr("ARBEITSBEREICH"))
    primary_pages = {
        "Start": "home",
        "Portfolio": "table_view",
        "Lieferantendetail": "domain",
        "Maßnahmen": "task_alt",
    }
    for name, icon in primary_pages.items():
        if st.button(
            tr(name),
            key=f"nav_{name}",
            icon=f":material/{icon}:",
            type="primary" if page == name else "tertiary",
            width="stretch",
        ):
            navigate(PAGES[name])
    with st.expander(tr("Verwaltung & Analyse"), expanded=page not in primary_pages):
        for name in (
            "Dashboard",
            "Historie",
            "Daten & Import",
            "Kalibrierung",
            "Freigaben",
            "Einstellungen",
        ):
            if st.button(
                tr(name),
                key=f"nav_{name}",
                type="primary" if page == name else "tertiary",
                width="stretch",
            ):
                navigate(PAGES[name])
    st.divider()
    if st.session_state.get("demo_mode"):
        st.badge(tr("Demo · synthetische Daten"), color="blue")
    else:
        st.caption(tr(st.session_state.origin))
    st.caption(tr("{v0} Lieferanten · lokal", v0=len(st.session_state.rows)))
    st.caption(tr("Nachvollziehbare Bewertungen. Entscheidungen bleiben bei Ihnen."))
views = available_views()
if page in {"Dashboard", "Maßnahmen", "Historie", "Daten & Import", "Kalibrierung", "Freigaben"}:
    st.radio(
        tr("Bewertungsperspektive"),
        views,
        key="view",
        horizontal=True,
        format_func=option_labels(views, lambda v: tr(v)),
    )
    if st.session_state.rows and not run_info():
        run(False, None)
for error in st.session_state.get("input_errors", []):
    st.error(tr("Eingabedaten prüfen: {v0}", v0=error_text(error)))
if page in {"Kalibrierung", "Freigaben"} and not st.session_state.rows:
    st.info(tr("Laden Sie zunächst Lieferantendaten oder starten Sie die Demo."))
    link(home_page, tr("Zum Einstieg"))
else:
    PAGES[page]()
