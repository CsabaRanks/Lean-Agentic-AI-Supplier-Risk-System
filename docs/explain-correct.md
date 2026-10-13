# Explain & correct

[Back to the product overview](../README.md) · [English demo walkthrough](demo-guide.md)

A category manager looks at a supplier, wants to know why it is rated the way it is, spots a wrong
input, and corrects it in a controlled way. The **Supplier detail** view provides the calculation, correction and optional explanation:

1. **How the score is calculated.** A trace generated from the scoring engine's own results, without
   any API key. It shows per criterion the inputs with source and data date (or "missing"), the rating
   rule, the rating and where it came from, the nominal and effective weight, and the contribution in
   points; the contributions add up exactly to the score. Rules that do not add points are listed
   separately: escalation rules that set a class floor, the data-completeness check, a reviewer's
   class override.
2. **AI explanation (optional).** A language model explains the trace for both views. Every summary,
   driver, view difference and action must cite trace entries (e.g. `risk:rule:compliance_status`);
   answers citing unknown entries are rejected. See [optional LLM explanation](llm-explanation.md).
3. **Correct data or ratings.** A *data correction* fixes an input (e.g. a compliance status or a
   credit score). An *expert override* replaces a rating that a rule derived from data. A reason is
   required. Both views are recomputed deterministically and shown before and after: scores,
   classes, changed criteria and rules. Nothing changes until you confirm. Weights and rules are not
   editable here; they stay in calibration and approval.
4. **Dispute assessment.** Records that you disagree with a criterion. It changes no score and does
   not train weights.

The same rule applies to the input table in **Data & import**: new suppliers are entered directly, but
a changed cell of a supplier that already has a result is held back as a pending correction and
applied only after a reason, the before/after preview and your confirmation. Deleting such a
supplier in the table is not applied.

Confirmed corrections are written to `corrections.jsonl` in the history folder: old and new value,
kind, reason, time, model and weight version, before and after per view, and the name you typed,
marked as not verified. An existing AI explanation is then marked **Outdated**.

**Example (fictional supplier SUP-004).** The risk score is 41.75, which would be "medium", but the
class is "high": a critical compliance finding triggers an escalation rule. The trace shows this
separately from the points (ESG rating 12.0 points, compliance status 8.0, …). A re-audit closed the
finding, so the category manager corrects `compliance_status` from `critical_findings` to
`minor_findings` with that reason. The preview shows risk 41.75 → 35.75, class high → medium, the
escalation rule no longer triggered; performance 38.75 → 40.62, class C unchanged. After confirmation
the correction is recorded and the earlier AI explanation is flagged as outdated.

## Validation boundary

Automated tests cover contribution additivity, escalation effects, previews without adoption,
confirmed corrections and history, disputes, and outdated explanations. This is technical
verification, not evidence of explanation quality, correction accuracy or fewer false alarms.
No category-manager field study or real supplier data has validated this workflow.
