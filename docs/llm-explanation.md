# Optional LLM explanation

[Back to the product overview](../README.md) · [Architecture](architecture.md)

The **Supplier Review Agent** sends the calculation trace of one supplier (both views) to a language
model and returns a management summary, the main drivers, where risk and performance differ,
prioritised action proposals and open questions, each with references to trace entries.

| Deterministic evaluation | LLM explanation |
|---|---|
| Ratings, weights, scores, classes, escalation rules, completeness, rule-based actions, calibration, the trace | Summary, drivers, view differences, action proposals, open questions |
| Same input → same result | Wording can differ between calls |
| Always runs; needs no key | Only when you press **Generate AI Review** or use `--ai-review` |

Safeguards:

- **Explicit trigger and preview.** Nothing is sent until you press the button (or confirm in the
  CLI). The exact JSON is shown beforehand: the trace with inputs, sources, rules, ratings, weights,
  contributions and rule-based actions. Supplier name, country, spend and expert labels are not sent.
  Use synthetic or approved data only.
- **Results stay deterministic.** The agent writes only its explanation into the run; it cannot change
  a score, class or weight. Scores shown next to it come from the deterministic results.
- **Validated output, within limits.** The answer must match a fixed schema. The summary, every driver,
  view difference and action must cite trace entries that exist; criterion keys must exist; both views
  must be compared; missing data must produce at least one open question. Otherwise the whole answer
  is rejected.
- **What validation does not check.** The free text can still contain numbers, and a misquoted value
  is not detected. Validation checks *that* an existing trace entry is cited, not *whether* it supports
  the sentence, and not whether explanations and priorities are sensible or every gap is addressed.
  The prompt restricts the model to the trace and withholds the supplier's name, which reduces but
  does not rule out invented facts or reasons. Read it as a draft.
- **Proposals, not decisions.** Suggested actions are marked as proposals for human review.
- **Bounded cost and failure.** Timeout and retry limit are configurable. A result is kept per exact
  input, so app reruns never call the provider again; after a correction the old explanation is
  flagged as outdated, not silently replaced. Errors are shown as messages, and the deterministic
  workflow continues unchanged.

## Setup

After the [base installation](../README.md#try-the-demo), copy `.env.example` to `.env`
in the repository root and set `ANTHROPIC_API_KEY`; model, timeout and retries are optional settings.
Use `cp .env.example .env` on macOS/Linux or `Copy-Item .env.example .env` in Windows PowerShell.
Then install the separate extra and start the interface or CLI:

```bash
python -m pip install -e ".[llm]"
supplier-risk --data data/sample_suppliers.json --ai-review SUP-004     # shows the payload, asks before sending
streamlit run ui/app.py                                                 # Supplier detail → AI explanation · optional
```

## Historical validation notes

The following records the manual checks reported in the original README on 12 October 2026;
these are not a new evaluation or a guarantee of future output quality.

The LLM explanation is **experimental**. Automated tests use mocked responses; a real smoke test with
`claude-opus-5-5` passed on 12 October 2026. In manual spot checks of three fictional suppliers (one
with complete data, one with many gaps, one with an escalation rule), every number in the text was
found in the input or was a sum of input values, and data gaps became open questions. Three answers
are examples, not an evaluation. The first real call was rejected by validation (12 drivers, no
actions), which led to stating the limits explicitly in the prompt.

## Language and retained explanations

New explanations use the selected **DE | EN** language in the UI. Existing explanations and
user reasons stay in their original language. Switching languages never calls the provider.
To request a new explanation in another language, explicitly discard the existing explanation
and generate a new one. The input hash and deterministic results are unchanged by language.
