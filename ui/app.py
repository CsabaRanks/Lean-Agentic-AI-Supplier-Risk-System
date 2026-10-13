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
    "Calibration demo (36 suppliers, synthetic expert labels)": ROOT / "data" / "calibration_portfolio.json",
}
# status palette (fixed roles), from favourable to unfavourable — always shown with the class label
STATUS = [("#e8f3ed", "🟢"), ("#fcf3dc", "🟡"), ("#fff0e5", "🟠"), ("#fbe9e7", "🔴")]
# categorical slots 1 and 2 of the validated reference palette
CURRENT_COLOR, PROPOSED_COLOR = "#2a78d6", "#eb6834"
NUMERIC_INPUTS = {"annual_spend", "credit_score", "distress_signals", "country_risk_index", "qualified_sources",
                  "esg_score", "on_time_rate", "quality_ppm"}

st.set_page_config(page_title="Supplier Workspace", page_icon=":material/view_quilt:", layout="wide")
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
    return {sid for info in st.session_state.get("runs", {}).values()
            for sid in ((info or {}).get("state") or {}).get("results", {})}


def show_comparison(comparison: dict) -> None:
    """Before/after of a proposed correction, per view and per changed criterion."""
    for col, (view, values) in zip(st.columns(len(comparison)), comparison.items()):
        with col.container(border=True):
            st.markdown("**Risiko**" if view == "risk" else "**Performance**")
            before, after = values["score"]
            st.metric("Vorher → Nachher", f"{before} → {after}")
            st.write(f"{risk_name(values['class'][0])} → {risk_name(values['class'][1])}")
            if values["rules_no_longer_triggered"]:
                st.caption("Regel entfällt: " + ", ".join(values["rules_no_longer_triggered"]))
            if values["rules_now_triggered"]:
                st.caption("Neue Regel: " + ", ".join(values["rules_now_triggered"]))
    with st.expander("Alle Auswirkungen der Korrektur"):
        comparison_table(comparison)


def comparison_table(comparison: dict) -> None:
    st.dataframe(pd.DataFrame([{
        "view": ui_model(v).view_label, "score": f"{c['score'][0]} → {c['score'][1]}",
        "class": f"{c['class'][0]} → {c['class'][1]}",
        "data": f"{c['data_completeness'][0]:.0%} → {c['data_completeness'][1]:.0%}",
        "needs review": f"{c['needs_review'][0]} → {c['needs_review'][1]}",
        "rules now triggered": ", ".join(c["rules_now_triggered"]) or "—",
        "rules no longer triggered": ", ".join(c["rules_no_longer_triggered"]) or "—",
    } for v, c in comparison.items()]), hide_index=True, width="stretch")
    changed = [{"view": v, "criterion": x["criterion"], "rating": f"{x['rating'][0]} → {x['rating'][1]}",
                "origin": f"{x['origin'][0]} → {x['origin'][1]}",
                "points": f"{x['contribution_points'][0]} → {x['contribution_points'][1]}"}
               for v, c in comparison.items() for x in c["changed_criteria"]]
    if changed:
        st.dataframe(pd.DataFrame(changed), hide_index=True, width="stretch")
    else:
        st.caption("No criterion rating changes.")


def apply_corrections(items: list[tuple], new_rows: list[dict]) -> None:
    """Adopt confirmed corrections: record each in the history, replace the data, recalculate."""
    for request, comparison in items:
        entry = history().record_correction(request, comparison)
        if request.supplier_id in st.session_state.get("ai_explanations", {}):
            st.session_state.setdefault("ai_outdated", {})[request.supplier_id] = (
                f"the correction of {entry['recorded_at']} ({request.reason})")
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
    evaluator = SupplierRiskEvaluator(InMemorySource(profiles), view_model, weight_store(), providers=providers())
    info.update(
        evaluator=evaluator,
        state=evaluator.run(material_group=material_group, calibrate=calibrate,
                            active_weights=approved_weights),
        run_kind="calibration" if calibrate else "scoring",
        rows_at_run=[dict(r) for r in st.session_state.rows],
    )


def results_frame() -> pd.DataFrame:
    """Result rows in the view's reading direction, most concerning supplier first."""
    state = run_info().get("state") or {}
    ranked = sorted(state.get("results", {}).values(),
                    key=lambda a: a.overall_score if a.overall_score is not None else -1, reverse=True)
    return pd.DataFrame([assessment_to_row(a, model()) for a in ranked])


def material_groups() -> list[str]:
    return sorted({str(r["material_group"]) for r in st.session_state.rows if r.get("material_group")})


def with_numeric(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Numeric dtype for number columns, so that empty cells stay empty instead of showing 'None'."""
    for c in columns:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def class_label(value) -> str:
    icon = class_styles().get(value, ("", "⚪"))[1]
    return f"{icon} {value}" if isinstance(value, str) else "⚪ n/a"


def style_class(value: str) -> str:
    key = str(value).split(" ")[-1]
    styles = class_styles()
    if key not in styles:
        return ""
    worst = key == list(styles)[-1]
    return f"background-color: {styles[key][0]}; color: {'#a33636' if worst else '#243247'}; font-weight: 600"




def dashboard_page():
    items = assessments()
    if not items:
        st.info("No results yet.")
    else:
        order = [c.key for c in model().risk_classes]
        styles = class_styles()
        summary = pd.DataFrame(group_summary(items, model()))
        group = st.selectbox("Material group", summary.material_group.tolist(), key="dash_group")
        row = summary.set_index("material_group").loc[group]
        selected = items if group == ALL_GROUPS else [a for a in items if (a.material_group or "(none)") == group]

        k = st.columns(5)
        k[0].metric("Suppliers", int(row.suppliers))
        k[1].metric(f"Mean {model().score_label.lower()}", f"{row.mean_score:.1f}" if pd.notna(row.mean_score) else "–")
        k[2].metric(f"Share {' / '.join(order[-2:])}", f"{row.share_top_two_classes:.0%}")
        k[3].metric("Need review", int(row.needs_review))
        k[4].metric("Raised by escalation rule", int(row.escalated))

        left, right = st.columns([3, 2])
        with left:
            class_columns = [f"class_{c}" for c in order]
            per_group = summary.loc[summary.material_group != ALL_GROUPS, ["material_group", *class_columns]].melt(
                id_vars="material_group", value_vars=class_columns, var_name="class", value_name="suppliers")
            per_group["class"] = per_group["class"].str.removeprefix("class_")
            stacked = alt.Chart(per_group).mark_bar(stroke="white", strokeWidth=2).encode(
                y=alt.Y("material_group:N", title=None),
                x=alt.X("suppliers:Q", title="Suppliers", axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("class:N", scale=alt.Scale(domain=order, range=[styles[c][0] for c in order]),
                                legend=alt.Legend(title=None, orient="top")),
                order=alt.Order("class_rank:Q"),
                tooltip=["material_group", "class", "suppliers"],
            ).transform_calculate(class_rank=f"indexof({order}, datum.class)")
            st.altair_chart(stacked.properties(height=alt.Step(34), title="Classes per material group"),
                            width="stretch")
        with right:
            st.markdown(f"**Top risks — {group}**")
            top = pd.DataFrame(top_risks(selected, model(), n=5))
            if not top.empty:
                top["risk_class"] = top.risk_class.map(class_label)
                st.dataframe(top[["name", "score", "risk_class", "main_drivers"]], hide_index=True, width="stretch",
                             column_config={"name": "Supplier", "score": st.column_config.NumberColumn(
                                 model().score_label, format="%.1f"), "risk_class": "Class",
                                 "main_drivers": "Main drivers (points)"})
        st.markdown("**All material groups**")
        st.dataframe(summary, hide_index=True, width="stretch", column_config={
            "material_group": "Material group", "suppliers": "Suppliers",
            "mean_score": st.column_config.NumberColumn(f"Mean {model().score_label.lower()}", format="%.1f"),
            "share_top_two_classes": st.column_config.NumberColumn(f"Share {' / '.join(order[-2:])}",
                                                                   format="percent"),
            **{f"class_{c}": f"{styles[c][1]} {c}" for c in order},
            "needs_review": "Review", "escalated": "Escalated", "most_concerning": "Most concerning"})


# --- page: actions ------------------------------------------------------------------------------



def actions_page():
    plan = pd.DataFrame(action_plan(assessments()))
    if plan.empty:
        st.info("No actions.")
    else:
        st.caption("Action framework: measures per risk class, per elevated dimension and per factor level. "
                   "Defined in the view's YAML (`actions`, `dimension_triggers`, `factor_actions`).")
        f = st.columns([2, 2, 2, 2])
        groups = f[0].multiselect("Material group", sorted(plan.material_group.dropna().unique()), key="act_group")
        classes = f[1].multiselect("Class", [c.key for c in model().risk_classes], key="act_class")
        levels = f[2].multiselect("Level", sorted(plan.level.unique()), key="act_level")
        owners = f[3].multiselect("Owner", sorted(plan.owner.dropna().unique()), key="act_owner")
        view_plan = plan
        for column, chosen in (("material_group", groups), ("risk_class", classes), ("level", levels),
                               ("owner", owners)):
            if chosen:
                view_plan = view_plan[view_plan[column].isin(chosen)]
        st.dataframe(view_plan.assign(risk_class=view_plan.risk_class.map(class_label)), hide_index=True,
                     width="stretch", column_config={"supplier_id": "ID", "name": "Supplier", "risk_class": "Class",
                                                    "material_group": "Material group", "level": "Level",
                                                    "factor": "Factor", "action": "Action", "owner": "Owner",
                                                    "review_cycle": "Review cycle", "trigger": "Why"})
        st.download_button("Export action plan CSV", to_csv(view_plan.to_dict("records")),
                           file_name=f"{model().view}_action_plan.csv", mime="text/csv")


# --- page: history ---------------------------------------------------------------------------



def history_page():
    c1, c2 = st.columns([1, 3])
    note = c2.text_input("Note for this snapshot", placeholder="e.g. annual review 2026", key="snap_note")
    if c1.button("📌 Save snapshot", width="stretch", disabled=not assessments()):
        n = history().record(assessments(), model(), run_id=(run_info().get("state") or {}).get("run_id"),
                             note=note)
        st.success(f"Saved {n} rows to {st.session_state.get('history_dir', 'data/history')}/{model().view}.jsonl")
    rows = pd.DataFrame(history().load(model().view))
    if rows.empty:
        st.info("No snapshots yet for this view. Save one above; approved reviews are saved automatically.")
    else:
        rows["recorded_at"] = pd.to_datetime(rows.recorded_at)
        st.caption(f"{rows.recorded_at.nunique()} snapshot(s) for the {model().view_label.lower()} view.")
        left, right = st.columns(2)
        with left:
            names = dict(zip(rows.supplier_id, rows.name))
            sid = st.selectbox("Supplier", sorted(names), format_func=lambda s: f"{s} · {names[s]}", key="hist_sup")
            mine = rows[rows.supplier_id == sid]
            line = alt.Chart(mine).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2,
                                             color=CURRENT_COLOR).encode(
                x=alt.X("recorded_at:T", title=None, axis=alt.Axis(format="%d %b %Y", labelAngle=0, tickCount=6)),
                y=alt.Y("score:Q", title=model().score_label, scale=alt.Scale(domain=[0, 100])),
                tooltip=[alt.Tooltip("recorded_at:T", title="snapshot"), "score", "risk_class", "note"],
            )
            st.altair_chart(line.properties(height=260, title=f"{names[sid]} over time"), width="stretch")
            st.dataframe(mine[["recorded_at", "score", "risk_class", "weights", "approved_by", "note"]],
                         hide_index=True, width="stretch")
        with right:
            groups = sorted(rows.material_group.dropna().unique())
            g = st.selectbox("Material group", groups, key="hist_group")
            trend = pd.DataFrame(history().group_trend(model().view, material_group=g))
            trend["recorded_at"] = pd.to_datetime(trend.recorded_at)
            line = alt.Chart(trend).mark_line(point=alt.OverlayMarkDef(size=60, filled=True), strokeWidth=2,
                                              color=CURRENT_COLOR).encode(
                x=alt.X("recorded_at:T", title=None, axis=alt.Axis(format="%d %b %Y", labelAngle=0, tickCount=6)),
                y=alt.Y("mean_score:Q", title=f"Mean {model().score_label.lower()}", scale=alt.Scale(domain=[0, 100])),
                tooltip=[alt.Tooltip("recorded_at:T", title="snapshot"), "mean_score", "suppliers"],
            )
            st.altair_chart(line.properties(height=260, title=f"{g}: mean score over time"), width="stretch")
            st.dataframe(trend.assign(classes=trend.classes.map(lambda c: ", ".join(f"{k}: {v}" for k, v in c.items()))),
                         hide_index=True, width="stretch")


# --- page: scoring run --------------------------------------------------------------------



def scoring_page():
    st.subheader("Supplier inputs")
    st.caption(
        "One sheet for both views: shared criteria appear once. Add new suppliers at the bottom (or import a "
        "CSV in the sidebar) and press **Recalculate**. Changes to suppliers that already have a result are "
        "not applied directly: they need a reason, a preview and your confirmation, and are recorded in the "
        "history. Expert ratings: 1 (favourable) – 5 (unfavourable). Empty cells mean “no data”."
    )
    all_factors = {f.key for v in views for d in ui_model(v).dimensions for f in d.factors}
    # expert labels are edited only in the Calibration tab, so that two editors never compete for a cell
    columns = [c for c in dict.fromkeys(all_view_columns() + [k for r in st.session_state.rows for k in r])
               if not label_view(c)]
    expert_cols = [c for c in columns if c in all_factors and c != "compliance_status"]
    config = {
        "supplier_id": st.column_config.TextColumn("Supplier ID", required=True),
        "material_group": st.column_config.TextColumn("Material group"),
        "annual_spend": st.column_config.NumberColumn("Annual spend", format="%.0f"),
        "transport_mode": st.column_config.SelectboxColumn("Transport", options=["road", "rail", "air", "sea"]),
        "intercontinental": st.column_config.CheckboxColumn("Intercontinental"),
        "on_time_rate": st.column_config.NumberColumn("On-time %", min_value=0, max_value=100),
        "quality_ppm": st.column_config.NumberColumn("PPM", min_value=0),
        "compliance_status": st.column_config.SelectboxColumn(
            "Compliance", options=["compliant", "minor_findings", "open_findings", "major_findings",
                                   "critical_findings"]),
        **{c: st.column_config.NumberColumn(c.replace("_", " "), min_value=1, max_value=5, step=1)
           for c in expert_cols},
    }
    numeric_cols = [c for c in columns if c in NUMERIC_INPUTS or c in expert_cols]
    edited = st.data_editor(
        with_numeric(pd.DataFrame(st.session_state.rows, columns=columns), numeric_cols),
        num_rows="dynamic", width="stretch", hide_index=True, column_config=config,
        key=f"input_editor_{st.session_state.editor_version}",
    )
    previous = {r.get("supplier_id"): r for r in st.session_state.rows}
    edited_rows = [
        {**{k: v for k, v in previous.get(row.get("supplier_id"), {}).items() if label_view(k)}, **row}
        for row in edited.astype(object).where(edited.notna(), None).to_dict("records")
    ]
    # First data entry stays direct; changes to suppliers that already have a result become corrections.
    view_models = [ui_model("risk"), ui_model("performance")]
    st.session_state.rows, table_changes, table_notes = split_table_edits(
        st.session_state.rows, edited_rows, assessed_ids(), view_models)
    for note in table_notes:
        st.warning(note)
    if table_changes:
        st.warning("Changes to suppliers that already have a result are **not applied yet**. Give a reason, "
                   "preview the effect in both views and confirm; the correction is then recorded in the history. "
                   "New suppliers can still be entered directly.", icon="✋")
        st.dataframe(pd.DataFrame([{"supplier": sid, "field": c.field, "kind": c.kind.replace("_", " "),
                                    "current": c.old_value, "proposed": c.new_value}
                                   for sid, changes in table_changes.items() for c in changes]).astype(str),
                     hide_index=True, width="stretch")
        digest = json.dumps({sid: [(c.field, c.new_value) for c in cs] for sid, cs in table_changes.items()},
                            sort_keys=True, default=str)
        with st.form("table_correction_form"):
            t_reason = st.text_area("Reason for the change (required)", key="table_reason")
            t_name = st.text_input("Your name (optional, not verified)", key="table_name")
            t_preview = st.form_submit_button("Preview table changes")
        if t_preview:
            try:
                items, rows_now = [], st.session_state.rows
                active = {v: ((st.session_state.get("runs", {}).get(v) or {}).get("state") or {}).get(
                    "active_weights") or {} for v in ("risk", "performance")}
                for sid, changes in table_changes.items():
                    req = CorrectionRequest(supplier_id=sid, changes=changes, reason=t_reason,
                                            entered_by=t_name.strip() or None)
                    rows_now, comparison = preview_correction(rows_now, req, view_models, active, providers())
                    items.append((req, comparison))
                st.session_state.table_preview = {"digest": digest, "items": items, "new_rows": rows_now}
            except (ValidationError, ValueError) as exc:
                st.session_state.pop("table_preview", None)
                st.error(f"Correction not possible: {exc}")
        preview = st.session_state.get("table_preview")
        if preview and preview["digest"] == digest:
            st.markdown("**Preview — nothing is applied yet**")
            for req, comparison in preview["items"]:
                st.markdown(f"`{req.supplier_id}`")
                show_comparison(comparison)
            b1, b2 = st.columns(2)
            if b1.button("✅ Confirm table changes", type="primary", width="stretch"):
                apply_corrections(preview["items"], preview["new_rows"])
                st.session_state.pop("table_preview", None)
                st.toast("Changes applied and recorded")
                st.rerun()
            if b2.button("Discard table changes", width="stretch"):
                st.session_state.pop("table_preview", None)
                st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
                st.rerun()

    c1, c2, _ = st.columns([2, 1, 3])
    group = c1.selectbox("Scope", ["All material groups", *material_groups()], key="run_scope")
    if c2.button("▶️ Recalculate", type="primary", width="stretch"):
        run(calibrate=False, material_group=None if group.startswith("All") else group)
        st.rerun()
    if run_info().get("run_kind") and run_info().get("rows_at_run") != st.session_state.rows:
        st.info("Inputs changed since the last run — recalculate to update the results.")


# --- page: portfolio -----------------------------------------------------------------------



def calibration_page():
    label_col = model().label_column
    direction = "higher = better" if model().score_orientation == "higher_is_better" else "higher = riskier"
    st.subheader(f"Expert labels — {model().view_label} view")
    st.caption(
        f"Give a holistic {model().score_label.lower()} (0–100, {direction}) for suppliers you know well — ideally "
        "before looking at the model score. Calibration fits this view's weights to these labels; safeguards decide "
        "whether the result is trustworthy. Approval happens in **✅ Review & approval**."
    )
    labels = pd.DataFrame([{**{k: r.get(k) for k in ("supplier_id", "name", "material_group")},
                            label_col: r.get(label_col)} for r in st.session_state.rows])
    scores = results_frame()
    if not scores.empty:
        labels = labels.merge(scores[["supplier_id", "score"]], on="supplier_id", how="left")
    labels = with_numeric(labels, [label_col, "score"])
    edited_labels = st.data_editor(
        labels, width="stretch", hide_index=True,
        key=f"label_editor_{model().view}_{st.session_state.editor_version}",
        disabled=[c for c in labels.columns if c != label_col],
        column_config={
            label_col: st.column_config.NumberColumn(f"Expert label (0–100, {direction})",
                                                     min_value=0, max_value=100, step=5),
            "score": st.column_config.NumberColumn(f"Model {model().score_label.lower()}", format="%.1f"),
        },
    )
    new_labels = dict(zip(edited_labels.supplier_id, edited_labels[label_col]))
    for row in st.session_state.rows:
        value = new_labels.get(row.get("supplier_id"))
        row[label_col] = None if pd.isna(value) else float(value)

    label_upload = st.file_uploader(f"Import labels CSV (columns supplier_id, {label_col})", type=["csv"],
                                    key=f"label_csv_{model().view}")
    if label_upload is not None and st.session_state.get("imported_labels") != label_upload.file_id:
        st.session_state.imported_labels = label_upload.file_id
        imported = {r["supplier_id"]: r.get(label_col) for r in from_csv(label_upload.getvalue().decode("utf-8-sig"))}
        for row in st.session_state.rows:
            if row.get("supplier_id") in imported and imported[row["supplier_id"]] not in (None, ""):
                row[label_col] = float(imported[row["supplier_id"]])
        st.session_state.editor_version += 1
        st.rerun()

    n_labels = sum(1 for r in st.session_state.rows if r.get(label_col) is not None)
    c1, c2, _ = st.columns([2, 1, 3])
    scope = c1.selectbox("Calibrate for", ["All material groups (global)", *material_groups()], key="cal_scope")
    if c2.button("🎯 Calibrate", type="primary", width="stretch", disabled=n_labels == 0):
        run(calibrate=True, material_group=None if scope.startswith("All") else scope)
        st.rerun()
    st.caption(f"{n_labels} supplier(s) labelled for this view. Roughly 30 or more consistent labels per scope are "
               "needed before calibration is usually accepted.")

    report = (run_info().get("state") or {}).get("calibration_report")
    if report:
        st.divider()
        st.subheader("Result")
        k = st.columns(5)
        k[0].metric("Labels used", report.n_samples)
        if report.cv_mse_before is not None:
            k[1].metric("Error before → after (cross-validated)",
                        f"{report.cv_mse_before:.1f} → {report.cv_mse_after:.1f}")
            k[2].metric("Clarity z (≥ 2 needed)", f"{report.cv_improvement_z:.1f}")
        if report.regularization_used is not None:
            k[3].metric("Regularisation λ", f"{report.regularization_used:.3g}")
        if report.level_offset is not None:
            k[4].metric("Mean label − model (internal scale)", f"{report.level_offset:+.1f}")
        (st.success if report.accepted else st.info)(report.message)
        for warning in report.warnings:
            st.warning(warning)

        if report.new_weights:
            comparison = pd.DataFrame(
                [{"factor": f, "weights": "current", "weight": v * 100} for f, v in report.old_weights.items()]
                + [{"factor": f, "weights": "proposed", "weight": v * 100} for f, v in report.new_weights.items()]
            )
            bars = alt.Chart(comparison).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                y=alt.Y("factor:N", title=None, sort=list(report.old_weights), axis=alt.Axis(labelLimit=220)),
                yOffset=alt.YOffset("weights:N", sort=["current", "proposed"]),
                x=alt.X("weight:Q", title="Weight (%)"),
                color=alt.Color("weights:N", scale=alt.Scale(domain=["current", "proposed"],
                                                             range=[CURRENT_COLOR, PROPOSED_COLOR]),
                                legend=alt.Legend(title=None, orient="top")),
                tooltip=["factor", "weights", alt.Tooltip("weight:Q", format=".1f", title="weight %")],
            )
            st.altair_chart(bars.properties(height=46 * len(report.old_weights),
                                            title="Current vs. proposed weights"), width="stretch")
            table = pd.DataFrame({"current %": {f: v * 100 for f, v in report.old_weights.items()},
                                  "proposed %": {f: v * 100 for f, v in report.new_weights.items()}})
            table["change"] = table["proposed %"] - table["current %"]
            with st.expander("Weights as a table"):
                st.dataframe(table.round(1), width="stretch")
                st.download_button("Export weights CSV", table.round(4).to_csv(),
                                   file_name=f"{model().view}_weights.csv", mime="text/csv")


# --- page: review & approval -----------------------------------------------------------------



def review_page():
    state = run_info().get("state")
    evaluator = run_info().get("evaluator")
    request = evaluator.pending_review(state) if state and evaluator else None
    if not request:
        if state and state.get("review_decision"):
            d = state["review_decision"]
            st.success(f"Review {state.get('review_status')} by {d.reviewer}.")
            report = state.get("calibration_report")
            if report and report.stored_as:
                st.caption(f"Approved weights stored as `{report.stored_as}`")
        else:
            st.info("Nothing to review. Runs pause here when data is insufficient or calibrated weights are proposed.")
    else:
        st.subheader(f"Waiting for your decision — {model().view_label} view")
        proposed = request.get("proposed_weights")
        if proposed:
            st.markdown(f"**Proposed weights** for scope *{proposed['scope']}* from {proposed['n_samples']} labels — "
                        f"cross-validated error {proposed['cv_mse_before']:.1f} → {proposed['cv_mse_after']:.1f} "
                        f"(z = {proposed['cv_improvement_z']:.1f}). Details in **🎯 Calibration**.")
            for warning in proposed.get("warnings", []):
                st.warning(warning)
        for reason in request.get("portfolio_reasons", []):
            st.info(reason)

        flagged = pd.DataFrame(request["flagged_suppliers"])
        overrides = None
        if not flagged.empty:
            st.markdown("**Suppliers flagged for review** — optionally set a class manually (with a comment).")
            flagged = flagged.assign(
                current=flagged.risk_class.map(class_label), new_class="", comment="",
                reasons=flagged.reasons.map("; ".join),
            )
            overrides = st.data_editor(
                flagged[["supplier_id", "name", "current", "reasons", "new_class", "comment"]],
                width="stretch", hide_index=True, key=f"override_editor_{state['run_id']}",
                disabled=["supplier_id", "name", "current", "reasons"],
                column_config={"new_class": st.column_config.SelectboxColumn(
                    "New class", options=["", *request["allowed_classes"]])},
            )

        with st.form("decision"):
            reviewer = st.text_input("Reviewer", placeholder="Your name")
            approve = st.checkbox("Approve proposed weights", disabled=not proposed)
            c1, c2 = st.columns(2)
            submit = c1.form_submit_button("✅ Submit decision", type="primary", width="stretch")
            defer = c2.form_submit_button("Defer", width="stretch")
        if submit or defer:
            chosen = {}
            if overrides is not None:
                for row in overrides.to_dict("records"):
                    if row["new_class"]:
                        chosen[row["supplier_id"]] = ClassOverride(risk_class=row["new_class"],
                                                                   comment=row["comment"] or "")
            decision = ReviewDecision(reviewer=reviewer or "unknown", approve_weights=bool(approve and proposed),
                                      overrides=chosen, defer=defer)
            new_state = evaluator.resume(state["run_id"], decision)
            run_info()["state"] = new_state
            if not defer:  # an approved assessment is worth keeping: snapshot to history
                history().record(list(new_state["results"].values()), model(), run_id=new_state["run_id"],
                                 note="after review", approved_by=decision.reviewer)
            st.rerun()

    if state and state.get("errors"):
        with st.expander("Messages"):
            for error in state["errors"]:
                st.warning(error)


# --- page: explain & correct ----------------------------------------------------------------




def show_ai_review(result: AIReviewResult, outdated_note: str | None) -> None:
    if outdated_note:
        st.error(f"Outdated: this AI explanation was generated before {outdated_note}. The numbers above are "
                 "current; generate a new explanation to match them.", icon="⚠️")
    st.warning(result.disclaimer, icon="🤖")
    r = result.review
    st.markdown("**Management summary**")
    st.write(r.management_summary)
    st.caption("Based on: " + ", ".join(f"`{x}`" for x in r.summary_refs))
    st.markdown("**Main drivers**")
    st.dataframe(pd.DataFrame([{**d.model_dump(), "trace_refs": ", ".join(d.trace_refs)} for d in r.risk_drivers]),
                 hide_index=True, width="stretch",
                 column_config={"criterion": "Criterion", "view": "View", "explanation": "Why it matters",
                                "trace_refs": "Trace entries"})
    if r.view_differences:
        st.markdown("**Risk vs. performance**")
        for d in r.view_differences:
            st.markdown(f"- **{d.topic}** — {d.explanation} `{', '.join(d.trace_refs)}`")
    st.markdown("**Suggested actions** — proposals for human review, not decisions")
    st.dataframe(pd.DataFrame([{**a.model_dump(), "criteria": ", ".join(a.criteria),
                                "trace_refs": ", ".join(a.trace_refs)} for a in r.suggested_actions]),
                 hide_index=True, width="stretch",
                 column_config={"priority": "Priority", "action": "Action", "rationale": "Rationale",
                                "criteria": "Criteria", "trace_refs": "Trace entries"})
    if r.open_questions or result.data_gaps:
        st.markdown("**Open questions**")
        for q in r.open_questions:
            st.markdown(f"- {q.question} `{', '.join(q.criteria)}`")
        if result.data_gaps:
            st.caption("Missing data in the input (determined by the tool, not by the LLM): "
                       + ", ".join(result.data_gaps))
    st.caption(f"{result.provider} / {result.model} · {result.created_at} · input SHA-256 {result.payload_sha256[:12]}…")


def inputs_text(inputs: list[dict]) -> str:
    return "; ".join(f"{i['input']} = {'—' if i['value'] is None else i['value']} [{i['source']}]" for i in inputs)


def show_trace(t: dict) -> None:
    s = t["score"]
    st.markdown(f"**{ui_model(t['view']).view_label}** · {s['label']} **{s['value']}** · class "
                f"**{class_label(t['class']['final']) if t['view'] == model().view else t['class']['final']}** · "
                f"data {t['data_completeness']:.0%} · model `{t['model']}` · weights `{t['weights']}`")
    st.caption(s["note"] + f". Sum of contributions: {s['sum_of_contributions']} = internal score "
               f"{s['internal_value']}.")
    frame = pd.DataFrame([{  # numbers first, long texts last, so the contributions stay visible
        "id": c["id"], "criterion": c["label"], "rating": c["rating"], "points": c["contribution_points"],
        "weight": c["nominal_weight"], "effective weight": c["effective_weight"], "origin": c["rating_origin"],
        "inputs (source)": inputs_text(c["inputs"]), "rule": c["rule"],
    } for c in sorted(t["criteria"], key=lambda c: -(c["contribution_points"] or 0))])
    st.dataframe(frame, hide_index=True, width="stretch", column_config={
        "weight": st.column_config.NumberColumn("Weight", format="%.3f"),
        "effective weight": st.column_config.NumberColumn("Effective weight", format="%.3f"),
        "points": st.column_config.NumberColumn("Points", format="%.2f")})
    rules = [r for r in t["non_additive"] if r["fired"] or r.get("rating") is None and "rule" in r["id"]]
    st.markdown("Rules that do not add points: " + ("; ".join(
        f"`{r['id']}` {r['effect']}" for r in rules) if rules else "none triggered."))




def detail_page():
    ensure_both_views()
    link(portfolio_page, "Zurück zum Portfolio", ":material/arrow_back:")
    st.caption("SUPPLIER WORKSPACE / LIEFERANTENDETAIL")
    current = list(st.session_state.runs.get("risk", {}).get("state", {}).get("results", {}).values())
    if not current:
        st.info("Noch keine Bewertungen. Starten Sie die Demo oder importieren Sie Lieferantendaten.")
    else:
        names = {a.supplier_id: a.supplier_name for a in current}
        if st.session_state.get("selected_supplier") in names:
            st.session_state.ai_supplier = st.session_state.pop("selected_supplier")
        sid = st.selectbox("Lieferant", sorted(names), format_func=lambda i: f"{names[i]} · {i}", key="ai_supplier")
        st.title(names[sid])
        row = next(r for r in st.session_state.rows if str(r.get("supplier_id")) == sid)
        st.caption(f"{sid} · {row.get('material_group') or 'Ohne Warengruppe'} · {row.get('country') or 'Land nicht angegeben'}")
        if st.session_state.get("correction_success") == sid:
            st.success("Korrektur bestätigt. Beide Bewertungen wurden aktualisiert und die Änderung protokolliert.")

        runs = st.session_state.setdefault("runs", {})
        for view in ("risk", "performance"):
            if not (runs.get(view) or {}).get("state"):
                run(calibrate=False, material_group=None, view=view)
        try:
            payload = ai_review_payload(sid, *((runs[v]["evaluator"], runs[v]["state"])
                                               for v in ("risk", "performance")))
        except (KeyError, LookupError) as exc:
            payload = None
            st.warning(f"Both views are needed: {exc}")

        if payload is not None:
            # 1 · deterministic explanation --------------------------------------------------------
            for col, (view, t) in zip(st.columns(2), payload["views"].items()):
                with col.container(border=True):
                    st.markdown("**RISIKO**" if view == "risk" else "**PERFORMANCE**")
                    st.metric("Risiko bei Ausfall" if view == "risk" else "Leistung des Lieferanten",
                              "—" if t['score']['value'] is None else f"{t['score']['value']:.1f} / 100")
                    final_class = t['class']['final']
                    color = {"low": "green", "medium": "orange", "high": "orange", "critical": "red",
                             "A": "green", "B": "orange", "C": "red"}.get(final_class, "gray")
                    st.badge(risk_name(final_class), color=color)
                    st.caption("Niedriger ist besser" if view == "risk" else "Höher ist besser")
                    st.caption(f"Datenbasis: {t['data_completeness']:.0%}")
                    if t['class']['final'] != t['class']['from_score']:
                        st.warning(f"Klasse aus Score: {risk_name(t['class']['from_score'])}. "
                                   "Eine Eskalation oder Freigabe verändert die endgültige Klasse.")
            gaps = [v for v, t in payload["views"].items() if t['data_completeness'] < ui_model(v).min_data_completeness]
            if gaps:
                st.warning("Unvollständige Datenbasis: Diese Bewertung erfordert eine fachliche Prüfung.")
            st.write("")
            st.subheader("Bewertung nachvollziehen & korrigieren")
            st.caption("1  Verstehen   →   2  Korrektur begründen   →   3  Wirkung prüfen   →   4  Bestätigen")
            with st.expander("Warum diese Bewertung?", expanded=True):
                for col, (v, t) in zip(st.columns(2), payload["views"].items()):
                    with col:
                        st.markdown("**Risiko: wichtigste Beiträge**" if v == "risk" else "**Performance: größte Abzüge**")
                        ranked = sorted(t["criteria"], key=lambda c: -(c["contribution_points"] or 0))[:3]
                        for c in ranked:
                            st.write(f"{c['label']} · {c['contribution_points'] or 0:.2f} Punkte")
                        if v == "performance":
                            st.caption("Performance = 100 − interne Belastungspunkte.")
                        for rule in t["non_additive"]:
                            if rule["fired"]:
                                st.info(f"{rule['effect']} ({rule['id']})")
                for v, t in payload["views"].items():
                    with st.expander("Daten, Quellen & Berechnung · " + ("Risiko" if v == "risk" else "Performance")):
                        show_trace(t)
            with st.expander("Empfohlene Maßnahmen"):
                for v in ("risk", "performance"):
                    a = runs[v]["state"]["results"].get(sid)
                    if a:
                        st.markdown("**" + ("Risiko" if v == "risk" else "Performance") + "**")
                        for recommendation in a.recommendations:
                            st.write(f"{recommendation.priority} · {recommendation.action}")
            # 3 · controlled correction ---------------------------------------------------------------------
            st.subheader("Korrektur begründen")
            st.caption("Korrigieren Sie einen Eingabewert oder ersetzen Sie eine abgeleitete Bewertung "
                       "durch ein Expertenurteil (1–5). Begründen Sie die Änderung. "
                       "Gewichte und Regeln werden separat kalibriert und freigegeben.")
            fields = correctable_fields([ui_model("risk"), ui_model("performance")])
            row = next(r for r in st.session_state.rows if str(r.get("supplier_id")) == sid)
            with st.expander("Alle korrigierbaren Felder und aktuellen Werte"):
                st.dataframe(pd.DataFrame([{
                    "field": f, "kind": spec["kind"].replace("_", " "), "used by": ", ".join(spec["criteria"]),
                    "expects": spec["expects"], "current": None if row.get(f) is None else str(row.get(f)),
                } for f, spec in fields.items()]), hide_index=True, width="stretch")
            with st.form(f"correction_form_{sid}"):
                f1, f2 = st.columns([2, 1])
                c_field = f1.selectbox(
                    "Feld", list(fields), key=f"correction_field_{sid}",
                    format_func=lambda f: f"{fields[f]['label'].replace('_', ' ')} · {f} · aktuell: "
                                          f"{'—' if row.get(f) is None else row.get(f)}")
                c_value = f2.text_input("Neuer Wert ('none' leert das Feld)", key=f"correction_value_{sid}")
                reason = st.text_area("Begründung (erforderlich)", key=f"correction_reason_{sid}")
                entered_by = st.text_input("Ihr Name (optional, ungeprüft)", key=f"correction_name_{sid}")
                preview_clicked = st.form_submit_button("Vorher/Nachher prüfen")
            if preview_clicked:
                try:
                    request = CorrectionRequest(
                        supplier_id=sid, reason=reason, entered_by=entered_by.strip() or None,
                        changes=[FieldChange(field=c_field, kind=fields[c_field]["kind"], new_value=parse_cell(c_value))])
                    active = {v: (runs[v]["state"] or {}).get("active_weights") or {} for v in ("risk", "performance")}
                    new_rows, comparison = preview_correction(st.session_state.rows, request,
                                                              [ui_model("risk"), ui_model("performance")],
                                                              active, providers())
                    st.session_state.pending_correction = {"sid": sid, "request": request, "new_rows": new_rows,
                                                           "comparison": comparison}
                except (ValidationError, ValueError) as exc:
                    st.session_state.pop("pending_correction", None)
                    st.error(f"Korrektur nicht möglich: {exc}")
            pending = st.session_state.get("pending_correction")
            if pending and pending["sid"] == sid:
                st.markdown("**Vorschau — noch nicht übernommen**")
                request = pending["request"]
                st.write("**Begründung dieser Vorschau:** " + request.reason)
                for change in request.changes:
                    st.write(f"{change.field}: {change.old_value} → {change.new_value}")
                comparison = pending["comparison"]
                show_comparison(comparison)
                a1, a2 = st.columns(2)
                if a1.button("Korrektur bestätigen", type="primary", width="stretch"):
                    apply_corrections([(pending["request"], comparison)], pending["new_rows"])
                    st.session_state.pop("pending_correction", None)
                    st.session_state.correction_success = sid
                    st.toast("Korrektur gespeichert")
                    st.rerun()
                if a2.button("Vorschau verwerfen", width="stretch"):
                    st.session_state.pop("pending_correction", None)
                    st.rerun()
            log = history().corrections(sid)
            if log:
                with st.expander(f"Korrekturhistorie ({len(log)})"):
                    st.dataframe(pd.DataFrame([{
                        "time": e["recorded_at"], "changes": "; ".join(
                            f"{c['field']} ({c['kind'].replace('_', ' ')}): {c['old_value']} → {c['new_value']}"
                            for c in e["changes"]),
                        "reason": e["reason"], "entered by (not verified)": e["entered_by"],
                        "risk": f"{e['views']['risk']['score'][0]} → {e['views']['risk']['score'][1]}",
                        "performance": f"{e['views']['performance']['score'][0]} → "
                                       f"{e['views']['performance']['score'][1]}",
                    } for e in log]), hide_index=True, width="stretch")

            with st.expander("KI-Erklärung · optional"):
                # 2 · AI explanation -----------------------------------------------------------------------
                try:
                    llm_settings = LLMSettings.from_env()
                    unavailable = llm_settings.unavailable_reason
                except LLMReviewError as exc:
                    llm_settings, unavailable = None, str(exc)
                if unavailable:
                    st.info(f"AI explanation not available: {unavailable} The calculation above is complete without it.")
                else:
                    st.caption(f"Provider: **{llm_settings.describe()}** · timeout {llm_settings.timeout_seconds:g} s "
                               f"per attempt · up to {llm_settings.max_retries} retries")
                digest = payload_hash(payload)
                with st.expander("Data sent to the provider (exactly this JSON)"):
                    st.caption("The scoring trace of both views. Not sent: supplier name, country, annual spend and "
                               "expert labels. Use synthetic or approved data only.")
                    st.code(payload_json(payload), language="json")
                explanations = st.session_state.setdefault("ai_explanations", {})  # supplier -> AIReviewResult
                outdated_notes = st.session_state.setdefault("ai_outdated", {})  # supplier -> note
                failures = st.session_state.setdefault("ai_review_failures", {})
                existing = explanations.get(sid)
                current_ok = existing is not None and review_is_current(existing, payload)
                c1, c2 = st.columns(2)
                clicked = c1.button("Generate AI Review", type="primary", width="stretch",
                                    disabled=bool(unavailable) or current_ok,
                                    help="One paid API call. The result is kept for this exact input; reruns of the "
                                         "app do not call the provider again.")
                if existing is not None:
                    c2.button("Discard explanation", width="stretch",
                              on_click=lambda s=sid: (explanations.pop(s, None), outdated_notes.pop(s, None)))
                if clicked and not current_ok:  # explicit trigger only; guarded against double clicks
                    risk_run = runs["risk"]
                    with st.spinner(f"Waiting for {llm_settings.describe()} …"):
                        new_state = risk_run["evaluator"].ai_review(risk_run["state"]["run_id"], payload)
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
                    st.error(f"AI explanation failed: {failures[digest]}")
                if existing is not None:
                    show_ai_review(existing, None if current_ok else outdated_notes.get(sid, "the data changed"))


            with st.expander("Bewertung beanstanden"):
                # 4 · dispute --------------------------------------------------------------------------------------
                st.caption("Records that you disagree with a criterion. It changes no score and does not train weights; "
                           "it is a note for the next review.")
                with st.form(f"dispute_form_{sid}"):
                    d1, d2 = st.columns(2)
                    d_view = d1.selectbox("View", ["risk", "performance"], format_func=lambda v: ui_model(v).view_label)
                    criteria = sorted({c["key"] for t in payload["views"].values() for c in t["criteria"]})
                    d_criterion = d2.selectbox("Criterion", criteria)
                    d_reason = st.text_area("Why is the assessment wrong? (required)")
                    d_name = st.text_input("Ihr Name (optional, ungeprüft)", key=f"dispute_name_{sid}")
                    if st.form_submit_button("Record objection"):
                        entry_view = payload["views"].get(d_view, {})
                        rated = next((c for c in entry_view.get("criteria", []) if c["key"] == d_criterion), None)
                        try:
                            history().record_objection(sid, d_view, d_criterion, d_reason, d_name.strip() or None,
                                                       context={"rating": rated["rating"] if rated else None,
                                                                "score": entry_view.get("score", {}).get("value")})
                            st.success("Objection recorded. Scores are unchanged.")
                        except ValueError as exc:
                            st.error(str(exc))
                objections = history().objections(sid)
                if objections:
                    with st.expander(f"Objections ({len(objections)})"):
                        st.dataframe(pd.DataFrame([{k: o[k] for k in ("recorded_at", "view", "criterion", "reason",
                                                                      "entered_by", "status")} for o in objections]),
                                     hide_index=True, width="stretch")


def home_page():
    st.caption("SUPPLIER WORKSPACE / WILLKOMMEN")
    st.title("Gute Entscheidungen beginnen\nmit einem klaren Überblick.")
    st.markdown("Risiken erkennen. Leistung verstehen. Bewertungen gemeinsam verbessern.")
    st.write("")
    with st.container(border=True):
        st.subheader("Ihr Lieferantenportfolio. Zwei Perspektiven.")
        st.write("Erkunden Sie sechs fiktive Lieferanten und sehen Sie, warum gute Performance "
                 "nicht automatisch geringes Risiko bedeutet.")
        if st.button("Demo ausprobieren", type="primary", icon=":material/play_arrow:"):
            with st.spinner("Demo wird vorbereitet …"):
                set_rows(load_rows(next(iter(DATASETS.values()))), next(iter(DATASETS)))
                st.session_state.demo_mode = True
            navigate(portfolio_page)
        st.caption("Synthetische Daten · Kein API-Key nötig · Keine automatische KI-Anfrage")
    for col, title, body in zip(st.columns(3),
            ["01  Überblick gewinnen", "02  Bewertung verstehen", "03  Begründet korrigieren"],
            ["Risiko und Performance in einer gemeinsamen Tabelle vergleichen.",
             "Von der Bewertung bis zu Daten, Regeln und Quellen navigieren.",
             "Die Wirkung prüfen und Änderungen bewusst bestätigen."]):
        with col:
            st.markdown(f"**{title}**")
            st.write(body)
    st.divider()
    link(data_page, label="Mit eigenen Daten starten", icon=":material/upload_file:")
    st.caption("CSV importieren oder Lieferanten erfassen. Bewertungen werden auf Anfrage berechnet.")


def ensure_both_views():
    for v in ("risk", "performance"):
        if not st.session_state.get("runs", {}).get(v, {}).get("state"):
            with st.spinner("Risiko und Performance werden berechnet …"):
                run(calibrate=False, material_group=None, view=v)


def portfolio_page():
    ensure_both_views()
    st.caption("SUPPLIER WORKSPACE / PORTFOLIO")
    left, right = st.columns([4, 1], vertical_alignment="bottom")
    left.title("Lieferantenportfolio")
    left.write("Risiko und Performance. Alle Lieferanten im Blick.")
    if right.button("Neu berechnen", icon=":material/refresh:", width="stretch"):
        for v in ("risk", "performance"):
            run(False, None, v)
        st.rerun()
    risks = st.session_state.runs.get("risk", {}).get("state", {}).get("results", {})
    perfs = st.session_state.runs.get("performance", {}).get("state", {}).get("results", {})
    if not risks:
        st.info("Noch keine Bewertungen. Importieren Sie eine CSV oder starten Sie die Demo.")
        link(home_page, label="Zur Demo", icon=":material/play_arrow:")
        link(data_page, label="Daten erfassen", icon=":material/upload_file:")
        return
    records = []
    for sid, a in risks.items():
        b = perfs.get(sid)
        records.append({"supplier_id": sid, "name": a.supplier_name,
            "material_group": a.material_group or "Ohne Warengruppe",
            "risk": ui_model("risk").to_display(a.overall_score), "risk_class": a.risk_class,
            "performance": ui_model("performance").to_display(b.overall_score) if b else None,
            "performance_class": b.risk_class if b else None,
            "review": a.requires_human_review or bool(b and b.requires_human_review),
            "data": min(a.data_completeness, b.data_completeness if b else 0) * 100,
            "escalated": bool(a.escalations) or bool(b and b.escalations)})
    df = pd.DataFrame(records)
    # Class severity comes before score: a class floor must never disappear in a ranking.
    df["rank"] = df.risk_class.map({"critical": 0, "high": 1, "medium": 2, "low": 3}).fillna(4)
    df = df.sort_values(["rank", "risk"], ascending=[True, False]).drop(columns="rank")
    for col, label, value, note in zip(st.columns(4),
            ["Lieferanten", "Erhöhtes Risiko", "Performance A", "Prüfung erforderlich"],
            [len(df), int(df.risk_class.isin(["high", "critical"]).sum()),
             int((df.performance_class == "A").sum()), int(df.review.sum())],
            ["im Portfolio", "hoch oder kritisch", "leistungsstarke Partner", "Daten oder Bewertung prüfen"]):
        with col.container(border=True):
            st.metric(label, value)
            st.caption(note)
    with st.container(border=True):
        search = st.text_input("Lieferanten suchen", placeholder="Name oder Lieferanten-ID …",
                               key="portfolio_search", icon=":material/search:")
        f = st.columns(3)
        groups = f[0].multiselect("Warengruppe", sorted(df.material_group.unique()), key="portfolio_groups")
        classes = f[1].multiselect("Risikoklasse", ["low", "medium", "high", "critical"],
                                   format_func=risk_name, key="portfolio_classes")
        perf = f[2].multiselect("Performance", ["A", "B", "C"], key="portfolio_perf")
        only_review = st.checkbox("Nur Lieferanten mit Prüfbedarf", key="portfolio_review")
        visible = df
        if search:
            visible = visible[visible.name.str.contains(search, case=False, regex=False)
                              | visible.supplier_id.str.contains(search, case=False, regex=False)]
        for column, chosen in (("material_group", groups), ("risk_class", classes), ("performance_class", perf)):
            if chosen:
                visible = visible[visible[column].isin(chosen)]
        if only_review:
            visible = visible[visible.review]
        st.caption(f"{len(visible)} von {len(df)} Lieferanten · Zeile auswählen, um die Bewertung zu öffnen")
        if visible.empty:
            st.info("Keine Lieferanten gefunden. Passen Sie den Suchbegriff oder die Filter an.")
            st.button("Filter zurücksetzen", on_click=reset_filters)
            return
        shown = visible.assign(risk_class=visible.risk_class.map(risk_name),
                               performance_class=visible.performance_class.fillna("Nicht bewertet"),
                               review=visible.review.map({True: "Prüfen", False: "—"}))
        event = st.dataframe(shown.style.map(status_cell, subset=["risk_class", "performance_class"]),
            hide_index=True, width="stretch", row_height=48,
            column_order=["name", "risk_class", "risk", "performance_class", "performance", "review",
                          "material_group", "data", "supplier_id"],
            column_config={"name": st.column_config.TextColumn("Lieferant", width="medium"),
                "risk_class": "Risiko", "risk": st.column_config.NumberColumn("Risk ↓", format="%.1f"),
                "performance_class": "Klasse", "performance": st.column_config.NumberColumn("Performance ↑", format="%.1f"),
                "review": "Prüfbedarf", "material_group": "Warengruppe", "supplier_id": "ID",
                "data": st.column_config.ProgressColumn("Datenbasis", min_value=0, max_value=100, format="%.0f %%")},
            on_select="rerun", selection_mode="single-row",
            key=f"portfolio_table_{st.session_state.get('portfolio_version', 0)}")
        if event.selection.rows:
            open_supplier(str(visible.iloc[event.selection.rows[0]].supplier_id))
        st.caption("Risk: niedriger ist besser · Performance: höher ist besser · Skala 0–100. "
                   "Eskalationsregeln können die Klasse unabhängig vom Score erhöhen.")
        # Accessible alternative to the canvas table, especially on narrow screens.
        with st.expander("Lieferanten direkt öffnen"):
            sid = st.selectbox("Lieferant auswählen", list(visible.supplier_id),
                format_func=lambda s: f"{risks[s].supplier_name} · {s}", key="portfolio_supplier")
            if st.button("Bewertung öffnen", type="primary"):
                open_supplier(sid)
        st.download_button("Tabelle exportieren", to_csv(visible.to_dict("records")),
                           file_name="supplier_portfolio.csv", mime="text/csv", icon=":material/download:")


def risk_name(value):
    return {"low": "Niedrig", "medium": "Mittel", "high": "Hoch", "critical": "Kritisch"}.get(value, value or "Nicht bewertet")


def status_cell(value):
    color, background = {
        "Niedrig": ("#22634b", "#e8f3ed"), "A": ("#22634b", "#e8f3ed"),
        "Mittel": ("#805b15", "#fcf3dc"), "B": ("#805b15", "#fcf3dc"),
        "Hoch": ("#94562b", "#fff0e5"), "Kritisch": ("#a33636", "#fbe9e7"),
        "C": ("#a33636", "#fbe9e7")}.get(value, ("#526175", "#f1f4f8"))
    return f"color: {color}; background-color: {background}; font-weight: 600"


def reset_filters():
    for key in ("portfolio_groups", "portfolio_classes", "portfolio_perf"):
        st.session_state[key] = []
    st.session_state.portfolio_search = ""
    st.session_state.portfolio_review = False


def open_supplier(sid):
    st.session_state.selected_supplier = sid
    st.session_state.portfolio_version = st.session_state.get("portfolio_version", 0) + 1
    st.session_state.pop("pending_correction", None)
    navigate(detail_page)


def data_page():
    st.title("Daten & Import")
    st.caption("Lieferanten erfassen, Beispieldaten laden oder eine eigene CSV importieren.")
    choice = st.selectbox("Beispieldaten", list(DATASETS), key="dataset_choice")
    if st.button("Beispieldaten laden"):
        set_rows(load_rows(DATASETS[choice]), choice)
        st.session_state.demo_mode = True
        st.rerun()
    upload = st.file_uploader("CSV importieren", type=["csv"], key="input_csv")
    if upload is not None and st.session_state.get("imported") != upload.file_id:
        try:
            rows = from_csv(upload.getvalue().decode("utf-8-sig"))
            profiles, errors = rows_to_profiles(rows, model())
            if errors or not profiles:
                raise ValueError("; ".join(errors) or "Die Datei enthält keine Lieferanten.")
            set_rows(rows, upload.name)
            st.session_state.imported = upload.file_id
            st.session_state.demo_mode = False
            st.rerun()
        except (ValueError, UnicodeError, KeyError) as exc:
            st.error(f"Import nicht möglich: {exc}. Prüfen Sie die CSV-Vorlage und versuchen Sie es erneut.")
    a, b = st.columns(2)
    a.download_button("Eingabedaten exportieren", to_csv(st.session_state.rows), file_name="suppliers.csv", mime="text/csv")
    b.download_button("CSV-Vorlage herunterladen", ",".join(all_view_columns()) + "\n", file_name="template.csv", mime="text/csv")
    if st.session_state.rows:
        scoring_page()
    else:
        st.info("Laden Sie Beispieldaten oder importieren Sie zunächst eine CSV-Vorlage.")


def settings_page():
    st.title("Einstellungen")
    st.checkbox("Store approved weights (versioned)", key="use_store")
    st.text_input("Weight store folder", key="store_dir")
    st.checkbox("Political stability from World Bank WGI (MOCK)", key="use_wgi_mock")
    st.text_input("History folder", key="history_dir")
    st.caption("Mock-Daten sind fiktiv. Nach Änderungen im Portfolio neu berechnen.")
    st.caption("Die optionale KI-Erklärung wird nur im Lieferantendetail ausdrücklich angefordert. "
               "API-Zugang über die lokale .env-Datei konfigurieren.")




PAGES = {
    "Start": home_page, "Portfolio": portfolio_page, "Lieferantendetail": detail_page,
    "Dashboard": dashboard_page, "Maßnahmen": actions_page, "Historie": history_page,
    "Daten & Import": data_page, "Kalibrierung": calibration_page,
    "Freigaben": review_page, "Einstellungen": settings_page,
}


def navigate(page):
    st.session_state.next_page = next(name for name, fn in PAGES.items() if fn == page)
    st.rerun()


def link(page, label, icon=None):
    if st.button(label, icon=icon):
        navigate(page)


st.session_state.setdefault("view", "risk")
st.session_state.setdefault("rows", [])
st.session_state.setdefault("runs", {})
st.session_state.setdefault("origin", "Noch keine Daten geladen")
st.session_state.setdefault("editor_version", 0)
st.session_state.setdefault("store_dir", "data/weights")
st.session_state.setdefault("history_dir", "data/history")
# Settings and view widgets are conditional; retain their values between pages.
for setting in ("view", "store_dir", "history_dir", "use_store", "use_wgi_mock", "ai_supplier",
                "portfolio_search", "portfolio_groups", "portfolio_classes", "portfolio_perf", "portfolio_review"):
    if setting in st.session_state:
        st.session_state[setting] = st.session_state[setting]
if "next_page" in st.session_state:
    st.session_state.navigation = st.session_state.pop("next_page")
with st.sidebar:
    st.markdown("### :material/view_quilt: Supplier Workspace")
    st.caption("PROCUREMENT · RISK & PERFORMANCE")
    page = st.session_state.setdefault("navigation", "Start")
    st.caption("ARBEITSBEREICH")
    primary_pages = {"Start": "home", "Portfolio": "table_view",
                     "Lieferantendetail": "domain", "Maßnahmen": "task_alt"}
    for name, icon in primary_pages.items():
        if st.button(name, key=f"nav_{name}", icon=f":material/{icon}:",
                     type="primary" if page == name else "tertiary", width="stretch"):
            navigate(PAGES[name])
    with st.expander("Verwaltung & Analyse", expanded=page not in primary_pages):
        for name in ("Dashboard", "Historie", "Daten & Import", "Kalibrierung", "Freigaben", "Einstellungen"):
            if st.button(name, key=f"nav_{name}", type="primary" if page == name else "tertiary", width="stretch"):
                navigate(PAGES[name])
    st.divider()
    if st.session_state.get("demo_mode"):
        st.badge("Demo · synthetische Daten", color="blue")
    else:
        st.caption(st.session_state.origin)
    st.caption(f"{len(st.session_state.rows)} Lieferanten · lokal")
    st.caption("Nachvollziehbare Bewertungen. Entscheidungen bleiben bei Ihnen.")
views = available_views()
if page in {"Dashboard", "Maßnahmen", "Historie", "Daten & Import", "Kalibrierung", "Freigaben"}:
    st.radio("Bewertungsperspektive", views, key="view", horizontal=True,
             format_func=lambda v: "Risiko" if v == "risk" else "Performance")
    if st.session_state.rows and not run_info():
        run(False, None)
for error in st.session_state.get("input_errors", []):
    st.error(f"Eingabedaten prüfen: {error}")
if page in {"Kalibrierung", "Freigaben"} and not st.session_state.rows:
    st.info("Laden Sie zunächst Lieferantendaten oder starten Sie die Demo.")
    link(home_page, "Zum Einstieg")
else:
    PAGES[page]()
