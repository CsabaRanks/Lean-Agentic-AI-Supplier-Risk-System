# Comparison of reference projects

How the reviewed projects (see [github-references.md](github-references.md)) compare, and which
ideas this repository adopts — and why.

## Overview

| | supply-chain-risk-intelligence | OmniSupply-AI | supplychain-ai-agent | Vendor-Bid-Evaluation-Ai | vendor-evaluator | **this repo** |
|---|---|---|---|---|---|---|
| Focus | geopolitical → logistics impact | supply-chain analytics Q&A | supplier tiering & reports | RFP bid evaluation | vendor scorecard prompt | **per-supplier risk evaluation** |
| Framework | LangGraph | LangGraph + LangChain | custom + LLM | LangGraph + LangChain | prompt only | **LangGraph** |
| Orchestration | linear graph | LLM supervisor pipeline | LLM-generated plan | LLM supervisor loop | single agent | **rule-based supervisor (hub & spoke)** |
| State | TypedDict | TypedDict + Pydantic | untyped | nested TypedDict | — | **TypedDict + Pydantic domain objects** |
| Scoring | none (simulated) | deterministic, hard-coded weights | LLM-judged | deterministic tiers, hard-coded | LLM-judged | **deterministic, config-driven** |
| Weights configurable | — | no | — | no | in prompt | **yes (YAML, per material group)** |
| Weights calibrated against experts | — | no | no | no | no | **yes — Calibration Agent** |
| Escalation / hard gates | — | thresholds | — | hard compliance gate | — | **escalation rules (class floors)** |
| Missing-data handling | — | — | — | defaults to 0.5 | — | **re-weighting + completeness flag** |
| Human review | — | — | — | yes | — | **yes (exit node; interrupt planned)** |
| Audit trail | history list | tracing | — | messages | — | **append-only typed audit trail** |
| Tests / CI | no | no | ad-hoc scripts | no | no | **pytest suite** |
| License | MIT (stated) | GPL-3.0 | none | none | MIT | **MIT** |

## Common ground

- All code-based projects split the problem into **specialised agents** with a shared state.
- LangGraph `StateGraph` with `TypedDict` state and list reducers is the de-facto pattern.
- Mature designs (OmniSupply, Vendor-Bid-Evaluation) converge on **deterministic scoring + LLM for
  language**, while LLM-judged scoring (supplychain-ai-agent, vendor-evaluator) is hard to
  reproduce and, as the vendor-evaluator example shows, error-prone even in simple arithmetic.
- None of the projects ships an automated test suite.

## What we adopt — and why

| Idea | Source | How it appears here |
|---|---|---|
| Directed multi-agent graph with shared typed state | supply-chain-risk-intelligence | `graph/builder.py`, `models/state.py` |
| Supervisor that routes to workers and gets control back | OmniSupply, Vendor-Bid-Evaluation | `agents/supervisor.py` — rule-based for determinism, one method to swap in an LLM |
| Numbers in code, LLM only for language | OmniSupply | `tools/scoring.py` is pure; LLM explanations are on the roadmap |
| Hard gates that a weighted average cannot hide | Vendor-Bid-Evaluation | `escalation_rules` (class floors) |
| Human-review exit | Vendor-Bid-Evaluation | `human_review` node; triggered by low data completeness or proposed weights |
| Review frequency by risk tier, flag single sourcing | vendor-evaluator | `actions.<class>.review_cycle`, `sourcing_strategy` factor |
| Rich supplier data model | supplychain-ai-agent | `SupplierProfile` with expert ratings + raw indicators |

## What we deliberately do differently

### 1. Calibration against expert judgement (key differentiator)

**None of the reviewed projects validates its weights.** Weights are either hard-coded
(OmniSupply, Vendor-Bid-Evaluation), written into a prompt (vendor-evaluator) or absent because an
LLM decides (supplychain-ai-agent).

This repository adds a dedicated **Calibration Agent**:

- takes computed scores and holistic **expert labels from category managers**,
- fits the factor weights by **minimising the MSE** between model score and expert label,
- respects **constraints** (weights ≥ minimum, sum = 1) and a regularisation towards the
  configured defaults, so it refines the methodology instead of replacing it,
- **re-triggers the Scoring Agent** when new weights are accepted (bounded feedback loop),
- **logs old vs. new weights and MSE before/after** in the state and the audit trail,
- supports a **global** scope and **per-material-group** scopes, because one weighting rarely fits
  all commodities.

Why it matters: it makes the system **learn from the people who know the suppliers best**, turns
a static scorecard into a model that improves with every review cycle, and gives category managers
a transparent, auditable reason for each weight — something neither spreadsheets nor black-box
SaaS scores offer.

### 2. Configuration over code
Criteria, weights, thresholds, rules and actions are one YAML file, validated by Pydantic. A
procurement team can adapt the model without touching Python.

### 3. Explicit handling of missing data
Re-normalised weights plus a `data_completeness` metric and review flag, instead of silently
assuming a neutral value.

### 4. Tested
Unit tests for scoring, weights and calibration (including recovery of known weights from
synthetic labels) and integration tests for the graph flow.

## What we do *not* adopt (for now)

- **LLM supervisor loop** — costly and non-deterministic for a workflow whose order is known;
  kept as an optional extension point.
- **LLM-judged scores** — not reproducible, not auditable.
- **Heavy platform scope** (SQL warehouse, vector store, web UI) — out of scope for the core; a UI
  and data connectors are on the roadmap.
