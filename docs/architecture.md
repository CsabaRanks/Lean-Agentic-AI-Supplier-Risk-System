# Architecture

## Design principles

1. **Deterministic numbers, explainable results.** Every score is computed by pure Python functions
   (`tools/scoring.py`). Given the same data, model and weights, the result is identical. LLMs are
   *planned* for data extraction and narrative explanations, but they never compute or change a score.
2. **Configuration over code.** Criteria, default weights, class thresholds, escalation rules, actions
   and calibration settings live in one YAML file (`RiskModelConfig`). Swapping the model does not
   touch the agents.
3. **Weights are a first-class object.** The scoring engine consumes a `WeightSet` (effective factor
   weights summing to 1). Configured defaults, material-group defaults and calibrated weights are
   interchangeable.
4. **Agents with a single responsibility, coordinated by a supervisor.** The graph is a hub-and-spoke
   LangGraph `StateGraph`; each worker returns a partial state update and hands control back.
5. **Governance built in.** Append-only audit trail, data-completeness checks, escalation rules that
   cannot be averaged away, human review with `interrupt()`, and versioned weight files.

## Graph

```mermaid
flowchart TD
    START([start]) --> SUP{Supervisor}
    SUP -->|no data yet| DC[Data Collection Agent]
    SUP -->|no scores yet| SC[Scoring Agent]
    SUP -->|calibration enabled,<br/>not yet run| CA[Calibration Agent]
    SUP -->|weights applied,<br/>round 1 only| SC
    SUP -->|scores final| RA[Action & Recommendation Agent]
    SUP -->|flagged| HR[Human Review<br/>interrupt]
    SUP -->|done| END([end])
    DC --> SUP
    SC --> SUP
    CA --> SUP
    RA --> SUP
    HR -->|decision| SUP
    CA -. auto-applied .-> WS[(Weight store)]
    HR -. approved .-> WS
```

The routing rules live in one method, `Supervisor.route()`:

| Condition (checked in order) | Next step |
|---|---|
| `suppliers` not in state | `collect_data` |
| no suppliers loaded | `end` |
| `results` not in state | `score` |
| calibration enabled and not yet performed | `calibrate` |
| calibration applied (auto or approved) and `scoring_round < 2` | `score` (feedback loop) |
| recommendations not yet created (or invalidated by a review decision) | `recommend` |
| `requires_human_review` and no `review_status` yet | `human_review` |
| otherwise | `end` |

The loops are bounded by construction: calibration runs at most once, re-scoring happens at most
once, and human review happens at most once per run.

## Human-in-the-loop

`human_review` calls LangGraph's `interrupt()` with a review request:

- flagged suppliers and their reasons
- proposed weights with old/new values and MSE
- the allowed classes

The graph is compiled with a checkpointer. The paused run is stored under its `run_id` (the
LangGraph thread id) and continues with `SupplierRiskEvaluator.resume(run_id, ReviewDecision(...))`:

| Decision | Effect |
|---|---|
| `approve_weights=True` | proposed weights become active and are stored (with reviewer); the portfolio is re-scored and recommendations rebuilt |
| `overrides={id: {risk_class, comment}}` | manual class per supplier (`manual_override=True`), kept across re-scoring; recommendations rebuilt |
| `defer=True` | the run closes without decisions, and flagged items stay open |

Invalid decisions (unknown supplier or class, approval without pending weights) are reported in
`errors` and ignored. The checkpointer only restores allow-listed types (`state_serializer()`).
Use the same serializer for a persistent checkpointer, e.g. to resume a run in another process.

## Agents

| Agent | Module | Responsibility |
|---|---|---|
| Supervisor | `agents/supervisor.py` | Rule-based routing; single extension point for an LLM supervisor. |
| Data Collection | `agents/data_collection.py` | Loads suppliers in scope (optionally one material group) and expert labels from a `SupplierDataSource`. |
| Scoring | `agents/scoring.py` | Resolves the weight set per supplier, computes factor ratings, dimension scores, overall score, class, escalations, completeness checks. |
| Calibration | `agents/calibration.py` | Fits weights to expert labels (min. MSE, constraints), logs old vs. new weights and MSE, applies (and stores) or proposes them. |
| Action & Recommendation | `agents/recommendation.py` | Maps class, elevated dimensions and escalations to actions and a review cycle. |
| Human Review | `agents/human_review.py` | Pauses the run with `interrupt()`; applies the reviewer's decision (approve weights, class overrides, defer). |

## State (`models/state.py`)

One `SupplierRiskState` (TypedDict) per run over a portfolio:

| Group | Fields |
|---|---|
| Input | `run_id`, `supplier_ids`, `material_group`, `calibrate` |
| Data | `suppliers`, `expert_labels` |
| Weights | `active_weights` (per scope: `global` or a material group), `calibrated_weights` |
| Scoring | `results` (supplier id → `RiskAssessment`), `scoring_round` |
| Calibration | `calibration_performed`, `calibration_applied`, `mse_before`, `mse_after`, `calibration_report` |
| Recommendation | `recommendations_done` (actions are stored on each `RiskAssessment`) |
| Governance | `next_step`, `requires_human_review`, `review_status`, `review_decision`, `manual_overrides`, `review_reasons`*, `errors`*, `audit_trail`* |

\* append-only (`Annotated[list, operator.add]`): LangGraph concatenates updates from all nodes.

### Why portfolio scope?

Calibration needs many expert-labelled suppliers at once, and class distributions are only
meaningful across a portfolio. A single supplier is assessed by running the same graph with
`supplier_ids=[id]`.

## Weight resolution

For each supplier the Scoring Agent picks the most specific weight set:

Active weights come from the weight store (latest version per scope) when one is configured,
and are updated by calibration within a run.

1. active (e.g. calibrated) weights for the supplier's material group
2. configured defaults for that material group (`material_group_weights`)
3. active global weights (e.g. globally calibrated)
4. configured global defaults

## Module map

```
src/supplier_risk_agent/
├── agents/          # one class per agent, each a LangGraph node (callable)
├── graph/           # StateGraph construction + SupplierRiskEvaluator facade
├── models/          # config (RiskModelConfig, WeightSet), domain objects, state
├── tools/           # indicators -> ratings, scoring, calibration, data sources, weight store
├── config/          # bundled example risk model (YAML)
└── cli.py           # `supplier-risk` command
```

## Extension points

| You want to… | Change |
|---|---|
| use different criteria / weights / thresholds | copy the YAML, pass `--model` |
| add a data feed (credit API, ESG platform, news) | new `@register_source` function in `tools/indicators.py` and/or a new `SupplierDataSource` |
| add an agent (e.g. external risk monitoring) | new node in `graph/builder.py` + one rule in `Supervisor.route()` |
| use an LLM supervisor | replace `Supervisor.route()` |
| resume runs across processes | pass a persistent checkpointer with `serde=state_serializer()` |
