"""Supplier Risk Agent — spreadsheet-style front end ("wolf in sheep's clothing").

It looks and feels like a spreadsheet: suppliers in rows, criteria, scores and
classes in columns, filters, sorting, traffic-light colours, direct input,
CSV import and export.

Underneath runs the full workflow of the package: deterministic scoring,
expert calibration with safeguards, human review via graph interrupt,
versioned weights and an audit trail.

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
from supplier_risk_agent.tools import InMemorySource, JsonFileSource, WeightStore
from supplier_risk_agent.tools.tabular import (
    LABEL_COLUMN,
    assessment_to_row,
    from_csv,
    input_columns,
    profile_to_row,
    rows_to_profiles,
    to_csv,
)

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "Sample portfolio (6 suppliers)": ROOT / "data" / "sample_suppliers.json",
    "Calibration demo (36 suppliers, synthetic expert labels)": ROOT / "data" / "calibration_portfolio.json",
}
CLASS_ORDER = ["low", "medium", "high", "critical"]
# status palette (fixed roles) — always shown together with the class label, never colour alone
CLASS_COLOR = {"low": "#0ca30c", "medium": "#fab219", "high": "#ec835a", "critical": "#d03b3b"}
CLASS_ICON = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
# categorical slots 1 and 2 of the validated reference palette
CURRENT_COLOR, PROPOSED_COLOR = "#2a78d6", "#eb6834"

st.set_page_config(page_title="Supplier Risk Agent", page_icon="📋", layout="wide")


# --- model, data and runs ------------------------------------------------------------


@st.cache_resource
def ui_model():
    """Bundled risk model. In the UI, calibrated weights always go through the Review tab."""
    model = load_risk_model()
    model.calibration.auto_apply = False
    return model


def load_rows(path: Path) -> list[dict]:
    model = ui_model()
    source = JsonFileSource(path)
    return [profile_to_row(source.get_supplier(i), model) for i in source.list_supplier_ids()]


def set_rows(rows: list[dict], origin: str) -> None:
    """Replace the data and score it straight away, like a spreadsheet that is always calculated."""
    st.session_state.rows = rows
    st.session_state.origin = origin
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    for key in ("evaluator", "state", "run_kind"):
        st.session_state.pop(key, None)
    run(calibrate=False, material_group=None)


def weight_store() -> WeightStore | None:
    if st.session_state.get("use_store"):
        return WeightStore(ROOT / st.session_state.get("store_dir", "data/weights"))
    return None


def run(calibrate: bool, material_group: str | None) -> None:
    profiles, errors = rows_to_profiles(st.session_state.rows, ui_model())
    st.session_state.input_errors = errors
    if not profiles:
        st.session_state.pop("state", None)
        return
    evaluator = SupplierRiskEvaluator(InMemorySource(profiles), ui_model(), weight_store())
    st.session_state.evaluator = evaluator
    st.session_state.state = evaluator.run(material_group=material_group, calibrate=calibrate)
    st.session_state.run_kind = "calibration" if calibrate else "scoring"
    st.session_state.rows_at_run = [dict(r) for r in st.session_state.rows]


def results_frame() -> pd.DataFrame:
    state = st.session_state.get("state") or {}
    rows = [assessment_to_row(a) for a in state.get("results", {}).values()]
    return pd.DataFrame(rows).sort_values("score", ascending=False, na_position="last") if rows else pd.DataFrame()


def material_groups() -> list[str]:
    return sorted({str(r["material_group"]) for r in st.session_state.rows if r.get("material_group")})


NUMERIC_INPUTS = {"annual_spend", "credit_score", "distress_signals", "country_risk_index", "qualified_sources",
                  "esg_score", LABEL_COLUMN}


def with_numeric(df: pd.DataFrame, columns) -> pd.DataFrame:
    """Numeric dtype for number columns, so that empty cells stay empty instead of showing 'None'."""
    for c in columns:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def class_label(value) -> str:
    return f"{CLASS_ICON.get(value, '⚪')} {value}" if isinstance(value, str) else "⚪ n/a"


def style_class(value: str) -> str:
    key = str(value).split(" ")[-1]
    if key not in CLASS_COLOR:
        return ""
    text = "#ffffff" if key == "critical" else "#0b0b0b"
    return f"background-color: {CLASS_COLOR[key]}; color: {text}; font-weight: 600"


if "rows" not in st.session_state:
    set_rows(load_rows(next(iter(DATASETS.values()))), next(iter(DATASETS)))


# --- sidebar: data in and out --------------------------------------------------------

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

    st.download_button(
        "Export input CSV", to_csv(st.session_state.rows), file_name="suppliers.csv",
        mime="text/csv", width="stretch",
    )
    st.download_button(
        "Empty template CSV", ",".join(input_columns(ui_model())) + "\n", file_name="template.csv",
        mime="text/csv", width="stretch",
    )
    st.caption(f"Current data: {st.session_state.origin} · {len(st.session_state.rows)} rows")

    with st.expander("Advanced"):
        st.checkbox("Store approved weights (versioned)", key="use_store",
                    help="Approved weights are saved as a new version and used as the starting point of later runs.")
        st.text_input("Weight store folder", value="data/weights", key="store_dir")
        model = ui_model()
        st.caption(f"Risk model: {model.name} v{model.version}")


# --- header ----------------------------------------------------------------------------

st.title("Supplier Risk Agent")
st.caption(
    "Works like a spreadsheet. Underneath: deterministic scoring, expert calibration with "
    "safeguards, human review and versioned weights. Details appear only where you need them."
)
for error in st.session_state.get("input_errors", []):
    st.error(f"Input: {error}")

tab_portfolio, tab_run, tab_cal, tab_review = st.tabs(
    ["📋 Portfolio", "▶️ Scoring run", "🎯 Calibration", "✅ Review & approval"]
)


# --- tab: scoring run ----------------------------------------------------------------

with tab_run:
    st.subheader("Supplier inputs")
    st.caption(
        "Edit cells directly, add rows at the bottom, or import a CSV in the sidebar, then press "
        "**Recalculate**. Expert ratings: 1 (low risk) – 5 (high risk). Empty cells mean “no data”."
    )
    model = ui_model()
    # expert labels are edited only in the Calibration tab, so that two editors never compete for a cell
    columns = [c for c in dict.fromkeys(input_columns(model) + [k for r in st.session_state.rows for k in r])
               if c != LABEL_COLUMN]
    expert_cols = [c for c in columns if c in model.factor_keys() and c != "compliance_status"]
    config = {
        "supplier_id": st.column_config.TextColumn("Supplier ID", required=True),
        "material_group": st.column_config.TextColumn("Material group"),
        "annual_spend": st.column_config.NumberColumn("Annual spend", format="%.0f"),
        "transport_mode": st.column_config.SelectboxColumn("Transport", options=["road", "rail", "air", "sea"]),
        "intercontinental": st.column_config.CheckboxColumn("Intercontinental"),
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
    previous_labels = {r.get("supplier_id"): r.get(LABEL_COLUMN) for r in st.session_state.rows}
    st.session_state.rows = [
        {**row, LABEL_COLUMN: previous_labels.get(row.get("supplier_id"))}
        for row in edited.astype(object).where(edited.notna(), None).to_dict("records")
    ]

    c1, c2, _ = st.columns([2, 1, 3])
    group = c1.selectbox("Scope", ["All material groups", *material_groups()], key="run_scope")
    if c2.button("▶️ Recalculate", type="primary", width="stretch"):
        run(calibrate=False, material_group=None if group.startswith("All") else group)
        st.rerun()
    if st.session_state.get("run_kind") and st.session_state.get("rows_at_run") != st.session_state.rows:
        st.info("Inputs changed since the last run — run again to update the results.")


# --- tab: portfolio --------------------------------------------------------------------

with tab_portfolio:
    df = results_frame()
    if df.empty:
        st.info("No results. Add suppliers in **▶️ Scoring run** or import a CSV in the sidebar.")
    else:
        m = st.columns(5)
        m[0].metric("Suppliers", len(df))
        m[1].metric("🔴 Critical", int((df.risk_class == "critical").sum()))
        m[2].metric("🟠 High", int((df.risk_class == "high").sum()))
        m[3].metric("Need review", int(df.needs_review.sum()))
        m[4].metric("Raised by escalation rule", int(df.escalated.sum()))

        f = st.columns([2, 2, 1, 2])
        groups = f[0].multiselect("Material group", sorted(df.material_group.dropna().unique()))
        classes = f[1].multiselect("Class", CLASS_ORDER)
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
                "score": "Score (0–100)",
                "risk_class": "Class",
                "escalated": st.column_config.CheckboxColumn("Escalated"),
                "manual_override": st.column_config.CheckboxColumn("Manual class"),
                "needs_review": st.column_config.CheckboxColumn("Review"),
                "review_cycle": "Review cycle",
                "data_completeness": "Data %",
                **{d: d[4:].replace("_", " ").title() for d in dims},
                "weights": "Weights",
            },
        )
        st.download_button("Export results CSV", to_csv(view.to_dict("records")),
                           file_name="risk_assessment.csv", mime="text/csv")

        counts = df.risk_class.value_counts().reindex(CLASS_ORDER, fill_value=0).reset_index()
        counts.columns = ["class", "suppliers"]
        chart = alt.Chart(counts).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
            y=alt.Y("class:N", sort=CLASS_ORDER, title=None),
            x=alt.X("suppliers:Q", title="Suppliers", axis=alt.Axis(tickMinStep=1)),
            color=alt.Color("class:N", scale=alt.Scale(domain=CLASS_ORDER, range=[CLASS_COLOR[c] for c in CLASS_ORDER]),
                            legend=None),
            tooltip=["class", "suppliers"],
        )
        labels = chart.mark_text(align="left", dx=4, color="#52514e").encode(text="suppliers:Q", color=alt.value("#52514e"))
        st.altair_chart((chart + labels).properties(height=alt.Step(30), title="Suppliers per risk class"),
                        width="stretch")

        with st.expander("🔍 Supplier details"):
            state = st.session_state.state
            sid = st.selectbox("Supplier", list(view.supplier_id), key="detail_supplier")
            if sid:
                a = state["results"][sid]
                st.markdown(f"**{a.supplier_name}** · {class_label(a.risk_class)} · score {a.overall_score} · "
                            f"weights {a.weights_scope}/{a.weights_origin}")
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
                                       for e in st.session_state.state["audit_trail"]]),
                         width="stretch", hide_index=True)


# --- tab: calibration ------------------------------------------------------------------

with tab_cal:
    st.subheader("Expert labels")
    st.caption(
        "Give a holistic risk score (0–100) for suppliers you know well — ideally before looking at the "
        "model score. Calibration fits the weights to these labels; safeguards decide whether the result "
        "is trustworthy. Approval happens in **✅ Review & approval**."
    )
    labels = pd.DataFrame([{k: r.get(k) for k in ("supplier_id", "name", "material_group", LABEL_COLUMN)}
                           for r in st.session_state.rows])
    scores = results_frame()
    if not scores.empty:
        labels = labels.merge(scores[["supplier_id", "score"]], on="supplier_id", how="left")
    labels = with_numeric(labels, [LABEL_COLUMN, "score"])
    edited_labels = st.data_editor(
        labels, width="stretch", hide_index=True, key=f"label_editor_{st.session_state.editor_version}",
        disabled=[c for c in labels.columns if c != LABEL_COLUMN],
        column_config={
            LABEL_COLUMN: st.column_config.NumberColumn("Expert label (0–100)", min_value=0, max_value=100, step=5),
            "score": st.column_config.NumberColumn("Model score", format="%.1f"),
        },
    )
    new_labels = dict(zip(edited_labels.supplier_id, edited_labels[LABEL_COLUMN]))
    for row in st.session_state.rows:
        value = new_labels.get(row.get("supplier_id"))
        row[LABEL_COLUMN] = None if pd.isna(value) else float(value)

    label_upload = st.file_uploader("Import labels CSV (columns supplier_id, expert_risk_score)", type=["csv"],
                                    key="label_csv")
    if label_upload is not None and st.session_state.get("imported_labels") != label_upload.file_id:
        st.session_state.imported_labels = label_upload.file_id
        imported = {r["supplier_id"]: r.get(LABEL_COLUMN) for r in from_csv(label_upload.getvalue().decode("utf-8-sig"))}
        for row in st.session_state.rows:
            if row.get("supplier_id") in imported and imported[row["supplier_id"]] not in (None, ""):
                row[LABEL_COLUMN] = float(imported[row["supplier_id"]])
        st.session_state.editor_version += 1
        st.rerun()

    n_labels = sum(1 for r in st.session_state.rows if r.get(LABEL_COLUMN) is not None)
    c1, c2, _ = st.columns([2, 1, 3])
    scope = c1.selectbox("Calibrate for", ["All material groups (global)", *material_groups()], key="cal_scope")
    if c2.button("🎯 Calibrate", type="primary", width="stretch", disabled=n_labels == 0):
        run(calibrate=True, material_group=None if scope.startswith("All") else scope)
        st.rerun()
    st.caption(f"{n_labels} supplier(s) labelled. Roughly 30 or more consistent labels per scope are needed "
               "before calibration is usually accepted.")

    report = (st.session_state.get("state") or {}).get("calibration_report")
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
            k[4].metric("Mean label − score", f"{report.level_offset:+.1f}")
        (st.success if report.accepted else st.info)(report.message)
        for warning in report.warnings:
            st.warning(warning)

        if report.new_weights:
            comparison = pd.DataFrame([
                {"factor": f, "weights": "current", "weight": report.old_weights[f] * 100}
                for f in report.old_weights
            ] + [
                {"factor": f, "weights": "proposed", "weight": report.new_weights[f] * 100}
                for f in report.new_weights
            ])
            bars = alt.Chart(comparison).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4).encode(
                y=alt.Y("factor:N", title=None, sort=list(report.old_weights), axis=alt.Axis(labelLimit=220)),
                yOffset=alt.YOffset("weights:N", sort=["current", "proposed"]),
                x=alt.X("weight:Q", title="Weight (%)"),
                color=alt.Color("weights:N", scale=alt.Scale(domain=["current", "proposed"],
                                                             range=[CURRENT_COLOR, PROPOSED_COLOR]),
                                legend=alt.Legend(title=None, orient="top")),
                tooltip=["factor", "weights", alt.Tooltip("weight:Q", format=".1f", title="weight %")],
            )
            st.altair_chart(bars.properties(height=460, title="Current vs. proposed weights"),
                            width="stretch")
            table = pd.DataFrame({"current %": {f: v * 100 for f, v in report.old_weights.items()},
                                  "proposed %": {f: v * 100 for f, v in report.new_weights.items()}})
            table["change"] = table["proposed %"] - table["current %"]
            with st.expander("Weights as a table"):
                st.dataframe(table.round(1), width="stretch")
                st.download_button("Export weights CSV", table.round(4).to_csv(), file_name="weights.csv",
                                   mime="text/csv")


# --- tab: review & approval ------------------------------------------------------------

with tab_review:
    state = st.session_state.get("state")
    evaluator = st.session_state.get("evaluator")
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
        st.subheader("Waiting for your decision")
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
            st.session_state.state = evaluator.resume(state["run_id"], decision)
            st.rerun()

    if state and state.get("errors"):
        with st.expander("Messages"):
            for error in state["errors"]:
                st.warning(error)
