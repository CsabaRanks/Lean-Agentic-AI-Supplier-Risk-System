"""Supplier Risk Agent — spreadsheet-style front end ("wolf in sheep's clothing").

It looks and feels like a spreadsheet: suppliers in rows, criteria, scores and
classes in columns, filters, sorting, traffic-light colours, direct input,
CSV import and export. A switch at the top changes the view between
**Performance** ("How well does this supplier deliver?") and **Risk**
("How exposed are we if it fails?"). The views share criteria such as credit
risk, ESG and compliance, and each has its own weights, classes and actions.

Underneath runs the full workflow of the package: deterministic scoring,
expert calibration with safeguards, human review via graph interrupt,
versioned weights and an audit trail, separately for each view.

This file only collects input and displays results. Every number comes from
`SupplierRiskEvaluator` and the package's tools; nothing is recomputed here.

    pip install -e ".[ui]"
    streamlit run ui/app.py
"""

from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from supplier_risk_agent import SupplierRiskEvaluator, load_risk_model
from supplier_risk_agent.models import ClassOverride, ReviewDecision
from supplier_risk_agent.models.config import available_views
from supplier_risk_agent.providers import WorldBankWgiProvider
from supplier_risk_agent.tools import HistoryStore, InMemorySource, JsonFileSource, WeightStore
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
STATUS = [("#0ca30c", "🟢"), ("#fab219", "🟡"), ("#ec835a", "🟠"), ("#d03b3b", "🔴")]
# categorical slots 1 and 2 of the validated reference palette
CURRENT_COLOR, PROPOSED_COLOR = "#2a78d6", "#eb6834"
NUMERIC_INPUTS = {"annual_spend", "credit_score", "distress_signals", "country_risk_index", "qualified_sources",
                  "esg_score", "on_time_rate", "quality_ppm"}

st.set_page_config(page_title="Supplier Risk Agent", page_icon="📋", layout="wide")


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


def run(calibrate: bool, material_group: str | None) -> None:
    profiles, errors = rows_to_profiles(st.session_state.rows, model())
    st.session_state.input_errors = errors
    info = run_info()
    info.clear()
    if not profiles:
        return
    evaluator = SupplierRiskEvaluator(InMemorySource(profiles), model(), weight_store(), providers=providers())
    info.update(
        evaluator=evaluator,
        state=evaluator.run(material_group=material_group, calibrate=calibrate),
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
    return f"background-color: {styles[key][0]}; color: {'#ffffff' if worst else '#0b0b0b'}; font-weight: 600"


if "view" not in st.session_state:
    st.session_state.view = "risk"
if "rows" not in st.session_state:
    set_rows(load_rows(next(iter(DATASETS.values()))), next(iter(DATASETS)))


# --- sidebar: data in and out -------------------------------------------------------------

with st.sidebar:
    st.header("Data")
    choice = st.selectbox("Example data", list(DATASETS), key="dataset_choice")
    if st.button("Load example", width="stretch"):
        set_rows(load_rows(DATASETS[choice]), choice)
        st.rerun()

    upload = st.file_uploader("Import CSV (one supplier per row)", type=["csv"], key="input_csv")
    if upload is not None and st.session_state.get("imported") != upload.file_id:
        st.session_state.imported = upload.file_id
        set_rows(from_csv(upload.getvalue().decode("utf-8-sig")), upload.name)
        st.rerun()

    st.download_button("Export input CSV", to_csv(st.session_state.rows), file_name="suppliers.csv",
                       mime="text/csv", width="stretch")
    st.download_button("Empty template CSV", ",".join(all_view_columns()) + "\n", file_name="template.csv",
                       mime="text/csv", width="stretch")
    st.caption(f"Current data: {st.session_state.origin} · {len(st.session_state.rows)} rows")

    with st.expander("Advanced"):
        st.checkbox("Store approved weights (versioned)", key="use_store",
                    help="Approved weights are saved as a new version per view and used as the starting "
                         "point of later runs.")
        st.text_input("Weight store folder", value="data/weights", key="store_dir")
        st.checkbox("Political stability from World Bank WGI (MOCK)", key="use_wgi_mock",
                    help="Placeholder provider with FICTIONAL values for the sample regions. For real data, "
                         "download WGI and use WorldBankWgiProvider.from_csv() (see docs/data-providers.md). "
                         "Recalculate after switching.")
        st.text_input("History folder", value="data/history", key="history_dir")
        st.caption(f"Model: {model().name} v{model().version}")


# --- header and view switch ------------------------------------------------------------------

st.title("Supplier Risk Agent")
views = available_views()
top_left, top_right = st.columns([3, 1])
top_left.radio("View", views, key="view", horizontal=True, format_func=lambda v: ui_model(v).view_label)
if top_right.button("🔄 Recalculate now", type="primary", width="stretch",
                    help="Scores are recalculated on demand from the current data, weights and providers."):
    run(calibrate=False, material_group=None)
    st.toast("Recalculated")
if not run_info():  # first time this view is shown: score it
    run(calibrate=False, material_group=None)
st.caption(
    f"**{model().view_label}** — {model().view_question} Works like a spreadsheet: change data, press "
    "**Recalculate now**, and every score, class and action is updated at once. Underneath: deterministic "
    "scoring, expert calibration with safeguards, human review and versioned weights."
)
for error in st.session_state.get("input_errors", []):
    st.error(f"Input: {error}")

tab_portfolio, tab_dash, tab_actions, tab_history, tab_run, tab_cal, tab_review = st.tabs(
    ["📋 Portfolio", "📊 Dashboard", "🛠 Actions", "🕓 History", "▶️ Scoring run", "🎯 Calibration",
     "✅ Review & approval"]
)


# --- tab: dashboard ---------------------------------------------------------------------------

with tab_dash:
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


# --- tab: actions ------------------------------------------------------------------------------

with tab_actions:
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


# --- tab: history ---------------------------------------------------------------------------

with tab_history:
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


# --- tab: scoring run --------------------------------------------------------------------

with tab_run:
    st.subheader("Supplier inputs")
    st.caption(
        "One sheet for both views: shared criteria appear once. Edit cells directly, add rows at the bottom, "
        "or import a CSV in the sidebar, then press **Recalculate**. Expert ratings: 1 (favourable) – "
        "5 (unfavourable). Empty cells mean “no data”."
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
    st.session_state.rows = [
        {**{k: v for k, v in previous.get(row.get("supplier_id"), {}).items() if label_view(k)}, **row}
        for row in edited.astype(object).where(edited.notna(), None).to_dict("records")
    ]

    c1, c2, _ = st.columns([2, 1, 3])
    group = c1.selectbox("Scope", ["All material groups", *material_groups()], key="run_scope")
    if c2.button("▶️ Recalculate", type="primary", width="stretch"):
        run(calibrate=False, material_group=None if group.startswith("All") else group)
        st.rerun()
    if run_info().get("run_kind") and run_info().get("rows_at_run") != st.session_state.rows:
        st.info("Inputs changed since the last run — recalculate to update the results.")


# --- tab: portfolio -----------------------------------------------------------------------

with tab_portfolio:
    df = results_frame()
    if df.empty:
        st.info("No results. Add suppliers in **▶️ Scoring run** or import a CSV in the sidebar.")
    else:
        order = [c.key for c in model().risk_classes]
        styles = class_styles()
        m = st.columns(5)
        m[0].metric("Suppliers", len(df))
        for col, key in zip(m[1:3], reversed(order[-2:])):
            col.metric(f"{styles[key][1]} {key}", int((df.risk_class == key).sum()))
        m[3].metric("Need review", int(df.needs_review.sum()))
        m[4].metric("Raised by escalation rule", int(df.escalated.sum()))

        f = st.columns([2, 2, 1, 2])
        groups = f[0].multiselect("Material group", sorted(df.material_group.dropna().unique()))
        classes = f[1].multiselect("Class", order)
        only_review = f[2].checkbox("Needs review")
        search = f[3].text_input("Search supplier", placeholder="ID or name")
        view = df
        if groups:
            view = view[view.material_group.isin(groups)]
        if classes:
            view = view[view.risk_class.isin(classes)]
        if only_review:
            view = view[view.needs_review]
        if search:
            hit = view.supplier_id.str.contains(search, case=False) | view.name.str.contains(search, case=False)
            view = view[hit]

        dims = [c for c in view.columns if c.startswith("dim_")]
        shown = with_numeric(view.copy(), ["score", "data_completeness", *dims]).assign(
            risk_class=view.risk_class.map(class_label),
            data_completeness=lambda d: d.data_completeness * 100,
        )
        direction = "higher = better" if model().score_orientation == "higher_is_better" else "higher = riskier"
        dim_labels = {f"dim_{d.key}": d.label for d in model().dimensions}
        st.dataframe(
            shown.style.map(style_class, subset=["risk_class"])
            .format(precision=1, na_rep="", subset=["score"])
            .format(precision=0, na_rep="", subset=["data_completeness", *dims]),
            width="stretch", hide_index=True,
            column_order=["supplier_id", "name", "material_group", "score", "risk_class", "escalated",
                          "manual_override", "needs_review", "review_cycle", "data_completeness", *dims,
                          "weights"],
            column_config={
                "supplier_id": "ID", "name": "Supplier", "material_group": "Material group",
                "score": f"{model().score_label} ({direction})", "risk_class": "Class",
                "escalated": st.column_config.CheckboxColumn("Escalated"),
                "manual_override": st.column_config.CheckboxColumn("Manual class"),
                "needs_review": st.column_config.CheckboxColumn("Review"),
                "review_cycle": "Review cycle", "data_completeness": "Data %",
                **{d: dim_labels.get(d, d[4:]) for d in dims}, "weights": "Weights",
            },
        )
        st.download_button("Export results CSV", to_csv(view.to_dict("records")),
                           file_name=f"{model().view}_assessment.csv", mime="text/csv")

        counts = df.risk_class.value_counts().reindex(order, fill_value=0).reset_index()
        counts.columns = ["class", "suppliers"]
        chart = alt.Chart(counts).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
            y=alt.Y("class:N", sort=order, title=None),
            x=alt.X("suppliers:Q", title="Suppliers", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("class:N", scale=alt.Scale(domain=order, range=[styles[c][0] for c in order]),
                            legend=None),
            tooltip=["class", "suppliers"],
        )
        labels = chart.mark_text(align="left", dx=4).encode(text="suppliers:Q", color=alt.value("#52514e"))
        st.altair_chart((chart + labels).properties(height=alt.Step(30), title="Suppliers per class"),
                        width="stretch")

        state = run_info()["state"]
        with st.expander("🔍 Supplier details"):
            sid = st.selectbox("Supplier", list(view.supplier_id), key="detail_supplier")
            if sid:
                a = state["results"][sid]
                st.markdown(f"**{a.supplier_name}** · {class_label(a.risk_class)} · {model().score_label.lower()} "
                            f"{model().to_display(a.overall_score)} · weights {a.weights_scope}/{a.weights_origin}")
                st.dataframe(pd.DataFrame([f.model_dump() for f in a.factor_scores]),
                             width="stretch", hide_index=True,
                             column_order=["dimension", "factor", "rating", "weight", "rationale"],
                             column_config={"weight": st.column_config.NumberColumn("weight", format="%.3f")})
                for r in a.recommendations:
                    cycle = f" · review {r.review_cycle}" if r.review_cycle else ""
                    st.markdown(f"- **{r.priority}**: {r.action}{cycle}")
                for e in a.escalations:
                    st.warning(f"Escalation on {e.rule_factor}: {e.reason}")
                for reason in a.review_reasons:
                    st.info(f"Review: {reason}")
                if a.review_comment:
                    st.caption(f"Reviewer comment: {a.review_comment}")

        with st.expander("🧾 Audit trail of this run"):
            st.dataframe(pd.DataFrame([{"time": e.timestamp, "agent": e.agent, "event": e.event}
                                       for e in state["audit_trail"]]), width="stretch", hide_index=True)


# --- tab: calibration -----------------------------------------------------------------------

with tab_cal:
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


# --- tab: review & approval -----------------------------------------------------------------

with tab_review:
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
