# Supplier Risk Agent

**Transparent, configurable and self-calibrating supplier risk evaluation, built as a LangGraph multi-agent workflow.**

![python](https://img.shields.io/badge/python-3.10%2B-blue)
![langgraph](https://img.shields.io/badge/LangGraph-multi--agent-purple)
![license](https://img.shields.io/badge/license-MIT-green)

---

## The problem

Supplier risk evaluation usually falls into one of two camps:

| | Spreadsheet scorecards | Enterprise SCRM / SaaS platforms |
|---|---|---|
| Cost | ✅ free | ❌ expensive licences |
| Transparency | ✅ formulas visible | ❌ black-box scores |
| Consistency | ❌ copy-paste errors, drifting versions | ✅ |
| Governance | ❌ no audit trail, weights set once and never validated | ⚠️ varies |
| Extensibility | ❌ hard to add data feeds or automation | ⚠️ vendor roadmap |

**Supplier Risk Agent sits in the gap.** You get the transparency of a scorecard, the structure of
a real system and an architecture ready for automation and AI. It is open source and
runs locally.

## Where this approach sits

![Radar chart profiling Excel, proprietary SaaS, open-source repos and this Lean Agentic approach on 15 success factors](docs/images/spider-diagram.png)

The chart compares four approaches to supplier risk management and performance evaluation:

- spreadsheet practice
- proprietary SCRM platforms (Prewave and Sphera as examples)
- open-source agent repos
- this project

It shows each approach's **relative position**, factor by factor:

- **Platforms** lead on external signals, data coverage, scale, regulatory evidence and
  operational maturity.
- **This project** leads where the *method* matters:
  - **integration of risk management and performance evaluation** on one criteria catalogue
  - **expert calibration**
  - **configurable, material-group-specific weights**
  - **agentic orchestration**: specialised agents over a shared state, including a calibration
    agent and a review pause in the graph
  - reproducibility and methodological transparency

  Calibration, the two views and configurable weights are deliberate differentiators, described below.
  In practice, organisations often license a risk platform but keep supplier performance evaluation
  in spreadsheets; this project evaluates both on one basis.
- **External signals** are covered in part: a provider interface reads open data and system
  exports; live APIs are still placeholders, and the agent architecture is designed to take more
  sources. This project is designed to *complement* a signal source, not to replace one.

> Values are **illustrative and justified, not measured**.
>
> - **Basis:** public information and code review (October 2026).
> - **Rationale and confidence:** see [research/comparison-matrix.md](research/comparison-matrix.md).
> - **Generation:** the chart is generated from
>   [research/comparison-matrix.yaml](research/comparison-matrix.yaml) by `scripts/generate_spider.py`.
> - **No aggregation:** no weighting, total or ranking is derived.
> - **Factor model and positioning:** [research/success-factors.md](research/success-factors.md),
>   [research/lean-agentic-positioning.md](research/lean-agentic-positioning.md).

## What it does

- **Two views: performance and risk.** The same suppliers and shared criteria, evaluated with two configurable profiles, each with its own weights, classes and actions (see below).
- **Structured scoring.** Multi-dimensional, weighted scoring with 1–5 factor ratings and min-max normalisation to 0–100.
- **Configurable model.** Criteria are defined once in a shared catalogue. **Default weights**, thresholds, escalation rules and actions live in one YAML file per view. Nothing is hard-coded.
- **Calibration against expert judgement.** A dedicated agent learns weights from category managers' holistic assessments (see below).
- **Material-group aware.** Weights can differ per commodity or material group instead of one-size-fits-all.
- **Governance built in.**
  - Escalation rules: one severe finding cannot be averaged away.
  - Data-completeness checks.
  - Human review that **pauses the run** (LangGraph `interrupt()`) until a reviewer approves or corrects.
  - **Versioned weight files**: every approved weight set is stored with timestamp and approver.
  - An append-only audit trail.
- **Actionable output.** Each supplier gets a class with a review cycle and concrete actions. They come from an **action framework** per risk class, per elevated dimension and per factor level, each with a typical owner.
- **Supply chain risk and change complexity.** Supply chain risk is a sub-score of political stability (World Bank WGI percentile mapped to 1–5), sourcing strategy and transport dependency. Change complexity can be derived from the **time to exit** in months (bands 1–5).
- **External data providers.** A slim provider interface fills missing indicators and records where each value came from. Bundled: a World Bank WGI provider (fictional mock table, or your own WGI download as CSV), a generic CSV provider for ERP / ESG / credit exports, and documented placeholders for API integrations. See [docs/data-providers.md](docs/data-providers.md).
- **Dashboards and history.** Per material group: class distribution, key figures and top risks with their drivers. Timestamped snapshots per view follow suppliers and material groups over time.
- **Recalculate at any time.** Scores are never stale: change data, weights or providers and press **🔄 Recalculate now** (or rerun the CLI). Every score, class and action is recomputed deterministically.
- **Deterministic and tested.** Same input always gives the same score, backed by a pytest suite.

> ⚠️ **The bundled criteria, weights and thresholds are illustrative examples.** They are a
> template to start from. Adapt them to your categories and calibrate them on your own supplier
> base before using the results for decisions.

## Two views: supplier performance and supplier risk

In practice, procurement runs two related evaluations that are easy to mix up:

| | **Supplier performance evaluation** | **Supplier risk management** |
|---|---|---|
| Question | How well does this supplier deliver? | How exposed are we if this supplier fails? |
| Typical criteria | on-time delivery, quality (PPM), price, cooperation | replaceability, business consequence, financial stability, country / sourcing / transport, ESG & compliance |
| Classes in the template | A / B / C (A = preferred) | low / medium / high / critical |
| Typical consequence | supplier development, business allocation | mitigation: second source, safety stock, monitoring |

The two views **share criteria**, such as credit risk, ESG rating and compliance status. A
shared criterion is defined once in a catalogue (`config/criteria.yaml`), so it has the same
meaning and data source in both views. Each view gives it **its own weight**, classes, escalation
rules and actions (`config/default_risk_model.yaml`, `config/default_performance_model.yaml`).

Everything else works for both views alike:
- calibration against expert labels, with a separate label per view
- material-group weights
- human review
- versioned weights, stored per view

The sample data shows why both are needed. Cobalt Specialty Chemicals and Evergreen Packaging
are **critical** in the risk view, because of single sourcing and acute insolvency signals. Both
are **A suppliers** in the performance view, because they deliver on time and in quality.

```bash
supplier-risk --data data/sample_suppliers.json --view performance
```

Further views can be added as new YAML files that pick criteria from the catalogue, for example
a sustainability view.

## ⭐ Differentiator: calibration against expert judgement

Most supplier-risk scorecards and open-source supply-chain agents use weights that are hard-coded
or decided by an LLM. Nobody checks them against reality. This project adds a
**Calibration Agent** that closes the loop:

1. **Input.** Category managers give a holistic risk label for some suppliers, e.g. during the annual review. Labels are **0–100 scores** on the model's scale. The expert's class is derived from the label with the same thresholds.
2. **Fit.** The agent adjusts the factor weights to **minimise the mean squared error** between model score and expert label.
3. **Constraints.** Weights stay ≥ a minimum and sum to 1, with regularisation towards the configured defaults. Calibration *refines* the methodology. It does not replace it.
4. **Feedback loop.** If the improvement is significant, the new weights are applied and the **Scoring Agent re-runs**. They are applied either automatically or after a reviewer approves them at the human-review pause.
5. **Safeguards.**
   - Acceptance is tested out of sample (cross-validation). The improvement must also be clear
     relative to its own uncertainty, so fits that only memorise label noise, or that rest on
     inconsistent labels, are rejected.
   - A level-offset check stops weights from being distorted when experts are systematically
     stricter or more lenient than the model's scale. Such cases go to review.
   - Fit diagnostics flag what weights cannot express: a high unexplained residual, and
     knock-out candidates that belong in an escalation rule.
6. **Logging and persistence.** Old vs. new weights, MSE and class agreement before/after are logged. Applied weights are saved as a new version in the weight store (`data/weights/global_v002.yaml`, …).
7. **Scope.** Calibration runs **globally** or **per material group**.

```
Calibration [global] — 32 labelled supplier(s): accepted: MSE 37.8 -> 13.3 (64.9% better)
  MSE 37.77 -> 13.265  |  class agreement 84% -> 88%  |  applied: True
  factor                     old     new  delta
  business_impact          14.0%   18.1%  +4.1%
  sourcing_strategy         8.8%   14.6%  +5.8%
  esg_rating               12.0%    7.5%  -4.5%
  ...
```

This makes the system **able to learn** and brings it **closer to how category managers actually
judge risk**, while every weight stays explainable. Details: [docs/calibration.md](docs/calibration.md).

> The labels in `data/calibration_portfolio.json` are **synthetic**. They were generated from a hidden
> weighting plus noise to demonstrate the method. They are not real expert judgements.

## Architecture

```mermaid
flowchart TD
    START([start]) --> SUP{Supervisor}
    SUP --> DC[Data Collection Agent]
    SUP --> SC[Scoring Agent]
    SUP -. optional .-> CA[Calibration Agent]
    SUP --> RA[Action & Recommendation Agent]
    SUP -. if flagged .-> HR[Human Review · interrupt]
    DC --> SUP
    SC --> SUP
    CA -- new weights → re-score --> SUP
    RA --> SUP
    HR -- decision --> SUP
    SUP --> END([end])
    CA -. store .-> WS[(Weight store)]
    HR -. approved .-> WS
```

| Agent | Responsibility |
|---|---|
| **Supervisor** | Rule-based routing over the shared state. It is the single extension point for an LLM supervisor. |
| **Data Collection** | Loads suppliers in scope (optionally one material group), indicators and expert labels from a pluggable data source. |
| **Scoring** | Resolves weights per supplier, rates factors, aggregates dimensions, normalises, classifies, applies escalation rules and checks data completeness. |
| **Calibration** *(optional)* | Fits weights to expert labels (constrained least squares) and triggers re-scoring. |
| **Action & Recommendation** | Maps class, elevated dimensions and escalations to actions and review cycles. |
| **Human Review** | Pauses the run (`interrupt()`) for suppliers with too little data or for proposed weights. Resumes with the reviewer's decision: approve weights, override classes, or defer. |

The flow is `collect_data → score → [calibrate → score] → recommend → [human_review ⏸ → score? → recommend] → end`.
All agents share one typed `SupplierRiskState`. More in [docs/architecture.md](docs/architecture.md).

### Default scoring template

| Dimension | Default weight | Factors |
|---|---|---|
| Severity Index | 35 % | availability of alternatives · change complexity · business consequence |
| Financial Stability | 20 % | credit risk · insolvency signals |
| Supply Chain Risk | 25 % | country risk · sourcing strategy · transport dependency |
| ESG & Compliance | 20 % | ESG rating · compliance status |

`score = (weighted rating − 1) / 4 × 100`. The classes are Low < 30 ≤ Medium < 50 ≤ High < 70 ≤ Critical.

**Why this normalisation?** The 1–5 scale has no zero, so the best possible rating is 1. Min-max
normalisation maps the scale's real range onto 0–100: the best supplier scores 0, the scale
midpoint 50 and the worst 100. A naive `R / 5` would start at 20 and leave a fifth of the range
unused. The 0–100 scale is also the scale expert labels use for calibration. Because the
transformation is linear, rankings stay unchanged. See [docs/scoring-model.md](docs/scoring-model.md).

## Quick start

```bash
git clone <this-repo> && cd supplier-risk-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# assess the fictional sample portfolio (risk view; --view performance for the performance view)
supplier-risk --data data/sample_suppliers.json
supplier-risk --data data/sample_suppliers.json --view performance

# one supplier in detail
supplier-risk --data data/sample_suppliers.json --supplier SUP-003

# calibrate weights against expert labels (synthetic data) and store them as a new version
supplier-risk --data data/calibration_portfolio.json --calibrate --weights-dir data/weights
supplier-risk --data data/calibration_portfolio.json --material-group plastics --calibrate --weights-dir data/weights

# decide pending reviews in the terminal (approve weights, override classes)
supplier-risk --data data/sample_suppliers.json --review interactive

# political stability from the fictional WGI placeholder (or --wgi-csv your_download.csv);
# append a timestamped snapshot to the history
supplier-risk --data data/sample_suppliers.json --wgi-mock --history-dir data/history

# machine-readable output
supplier-risk --data data/sample_suppliers.json --json

pytest
```

```
ID        Supplier                      Score  Class      Data  Weights              Review
----------------------------------------------------------------------------------------------
SUP-003   Cobalt Specialty Chemicals     84.0  critical   100%  global/default
SUP-006   Foxglove Electronics           68.6  high        30%  global/default       yes
SUP-002   Borealis Polymers              47.1  medium     100%  global/default
SUP-004   Delta Fibre Media              41.8  high*      100%  global/default
SUP-005   Evergreen Packaging            19.5  critical*  100%  global/default
SUP-001   Alpha Precision Parts          12.2  low        100%  global/default

* class raised by an escalation rule
```

### Spreadsheet UI

The same workflow behind a familiar spreadsheet surface:
- **Rows and columns.** Suppliers in rows; criteria, scores and classes in columns.
- **Working the table.** Filters, sorting, traffic-light classes, direct cell editing.
- **CSV.** Import and export.

```bash
pip install -e ".[ui]"        # adds streamlit and pandas
streamlit run ui/app.py       # opens http://localhost:8501
```

| Tab | What you do there |
|---|---|
| **View switch** (top) | *Performance* or *Risk*: changes classes, weights, score direction and results. Each view keeps its own run, calibration and review. |
| **🔄 Recalculate now** (top) | Recompute every score, class and action from the current data, weights and providers, at any time. |
| **📋 Portfolio** | Ranked table with traffic-light classes, filters, supplier details, audit trail, CSV export |
| **📊 Dashboard** | Per material group: key figures, class distribution (stacked bars), top risks with their main drivers |
| **🛠 Actions** | Action plan from the action framework: one row per supplier and measure, filter by group, class, level and owner, CSV export |
| **🕓 History** | Save a timestamped snapshot; score over time per supplier and mean score per material group. Approved reviews are saved automatically. |
| **▶️ Scoring run** | Edit supplier inputs like a sheet (or import a CSV), then run the scoring. One sheet serves both views. |
| **🎯 Calibration** | Enter or import expert labels (0–100), calibrate, compare current vs. proposed weights, read the diagnostics |
| **✅ Review & approval** | Approve proposed weights, set classes manually with a comment, or defer |

**How the UI handles your data:**
- **Calculations.** All numbers come from the package (`SupplierRiskEvaluator`). The UI only
  collects input and shows results.
- **Approval.** Calibrated weights are never applied without approval in the UI.
- **CSV format.** One supplier per row. Columns named like a factor hold expert ratings 1–5; other
  columns hold raw indicators; `expert_risk_score` and `expert_performance_score` hold the
  labels of each view. Use **Empty template CSV** in
  the sidebar as a starting point. Semicolon-separated files from European Excel versions are
  accepted.
- **Placeholders.** *Advanced → Political stability from World Bank WGI (MOCK)* fills political
  stability from the bundled **fictional** table. It is a placeholder and not real data.
- **History files** (`data/history/<view>.jsonl`) are git-ignored, because they may contain real
  supplier data.

### Python API

```python
from supplier_risk_agent import SupplierRiskEvaluator

evaluator = SupplierRiskEvaluator.from_json("data/sample_suppliers.json")  # optional: model_path="my_model.yaml"

result = evaluator.assess("SUP-003")
print(result.overall_score, result.risk_class)
for action in result.recommendations:
    print(action.priority, action.action, action.review_cycle)

state = evaluator.run(calibrate=True)  # full state incl. calibration report and audit trail

# human-in-the-loop: the run pauses if a decision is needed
request = evaluator.pending_review(state)
if request:
    state = evaluator.resume(state["run_id"], {
        "reviewer": "jane.doe",
        "approve_weights": False,
        "overrides": {"SUP-006": {"risk_class": "high", "comment": "data requested from supplier"}},
    })
```

## Project structure

```
├── src/supplier_risk_agent/
│   ├── agents/        # Supervisor, Data Collection, Scoring, Calibration, Recommendation
│   ├── graph/         # LangGraph StateGraph + SupplierRiskEvaluator facade
│   ├── models/        # RiskModelConfig, WeightSet, domain objects, graph state
│   ├── providers/     # external data providers: World Bank WGI, CSV exports, API placeholders
│   ├── tools/         # rating sources, scoring, calibration, reporting, history, data sources
│   ├── config/        # default_risk_model.yaml (example template)
│   └── cli.py
├── data/              # fictional sample data; weights/ = versioned weight store
├── docs/              # architecture, scoring model, calibration, paper outline, images
├── examples/          # runnable scripts
├── research/          # success factors, comparison matrix (YAML = source), positioning, decision log
├── scripts/           # generate_spider.py: matrix Markdown + radar chart from the YAML
├── tests/
└── .github/workflows/ # CI: ruff + pytest
```

## Customising

| Goal | How |
|---|---|
| Change criteria, weights or thresholds | Copy `src/supplier_risk_agent/config/default_risk_model.yaml` and run with `--model my_model.yaml`. |
| Use different weights per material group | Set `material_group_weights` in the YAML, or run calibration with `--material-group`. |
| Connect your own data | Implement `SupplierDataSource` (`get_supplier`, `list_supplier_ids`). |
| Fill indicators from other systems | Pass `providers=[...]` to `SupplierRiskEvaluator`: `CsvIndicatorProvider` for exports, or your own `ExternalDataProvider` ([docs/data-providers.md](docs/data-providers.md)). |
| Change concrete actions | Edit `factor_actions` (per factor and level), `dimension_triggers` and `actions` in the view YAML. |
| Derive a rating from a new indicator | Add a function with `@register_source("my_source")` in `tools/indicators.py`. |
| Add an agent | Register a node in `graph/builder.py` and add one routing rule in `Supervisor.route()`. |

## Roadmap

- [x] Deterministic, configurable scoring with escalation rules and data-completeness checks
- [x] LangGraph supervisor workflow with audit trail
- [x] Calibration Agent (global and per material group)
- [x] Versioned weight store for approved weights
- [x] Human-in-the-loop with LangGraph `interrupt()` (approve weights, override classes)
- [ ] Persistent checkpointer (SQLite) to resume reviews across processes
- [ ] Cross-validated calibration report
- [ ] LLM explanation agent: narrative per supplier, without changing numbers
- [ ] LLM extraction agent: indicators from audit reports and questionnaires
- [ ] External risk monitoring agent: news, disasters, geopolitical alerts as a time-varying factor
- [x] Dashboard per material group, action plan, assessment history
- [x] External data provider interface (WGI as CSV / mock; generic CSV exports)
- [ ] API integrations for providers (WGI online, ESG platform, ERP, credit agency): placeholders today

## Background

This project builds on ideas from several open-source supply-chain agent projects. It extends
them with config-driven scoring, governance features and calibration against expert labels. See
[research/](research/) for the reviewed projects and the design decisions.

## License

MIT. See [LICENSE](LICENSE). All sample data is fictional.
