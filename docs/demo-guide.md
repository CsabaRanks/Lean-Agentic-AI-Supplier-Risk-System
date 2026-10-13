# Try the procurement workspace

[Back to the product overview](../README.md) · [Installation](../README.md#try-the-demo)

The local demo uses six synthetic suppliers and needs no API key. Start with **Try the demo**
on **Home**. Select **EN** using **DE | EN** at the top of the sidebar to follow these labels.
On a narrow screen, open the sidebar first. Language changes preserve filters, supplier selection,
entered reasons and open previews; existing AI explanations and user text remain in their original language.

## First walkthrough

1. In **Portfolio**, compare Risk (lower is better) and Performance (higher is better), both on
   a 0–100 scale. Search for `Delta`.
2. Select the **Delta Fibre Media** row. Alternatively, expand **Open a supplier directly**
   and select **Open assessment**.
3. In **Supplier detail**, read both assessment cards and **Why this assessment?**.
   The main contributions explain the scores; a critical compliance finding raises the risk
   class to High even though the numeric score falls in Medium.
4. Under **Explain the correction**, select **Compliance status** (`compliance_status`).
   Set **New value ('none' clears the field)** to `minor_findings` and enter a reason, for example:
   “Synthetic audit: the critical finding has been resolved.”
5. Select **Preview before/after**. Risk changes from **41.75 to 35.75**, High to Medium;
   Performance changes from **38.75 to 40.62**, remaining C. The compliance escalation no longer applies.
6. Select **Confirm correction** to apply and record it, or **Discard preview** to leave the
   assessment unchanged. Expand **Correction history** to inspect a confirmed change.

Scores on the main cards use one decimal place; the preview shows two. These are illustrative
results from the bundled data and default weights, not findings about real suppliers.
Sources and the full calculation are available in the **Data, sources & calculation** expanders.
[Explain & correct](explain-correct.md) details the trace and correction history.

## Find the other tools

**Actions** contains the rule-based action plan. **Administration & analysis** contains
Dashboard, History, Data & import, Calibration, Approvals and Settings. CSV templates are
available in **Data & import**. Calibration proposes weights for human approval.

The collapsed **AI explanation · optional** section in Supplier detail offers a separate,
explicit provider request after [LLM setup](llm-explanation.md#setup). The deterministic
calculation trace and correction workflow work without it.

## Screenshots and interface limits

The [README screenshots](../README.md#see-it-in-action) show the actual English interface.
The portfolio image comes from the DE/EN browser check; the detail and correction images were
captured on 13 October 2026 at 1440 × 1100 with synthetic data and no LLM request.
Historical UI screenshots remain in the [UI audit](professional-ui.md); they are not the current product tour.

Streamlit's own upload controls, table menus, keyboard hints and framework errors may remain
English. Narrow tables scroll horizontally, and individual suppliers do not have dedicated URLs.
See the [UI documentation](professional-ui.md) for desktop/mobile checks and localisation limits.
