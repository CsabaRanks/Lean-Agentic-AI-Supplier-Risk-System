# GitHub references

Open-source projects reviewed while designing this repository. Facts were checked against the
source code and the GitHub API in October 2026; star counts and dates change over time.

> We reuse **ideas and patterns**, not code. Several of the repositories below have no license
> (all rights reserved by default) or a copyleft license, so no source was copied.

---

## 1. aniket-work/supply-chain-risk-intelligence

- **URL:** https://github.com/aniket-work/supply-chain-risk-intelligence
- **What it is:** Companion demo for an article on a LangGraph multi-agent system that turns
  geopolitical and market signals into logistics impact, stock-out risk and an executive
  recommendation.
- **Stack:** LangGraph only; CLI via `main.py`. No LLM calls in the active code path — the agent
  nodes return fixed, simulated text.
- **Architecture:** linear `StateGraph` MarketAnalyst → LogisticsCoordinator → InventoryStrategist →
  ExecutiveOrchestrator, with a `TypedDict` state and an `Annotated[list, operator.add]` history.
- **License:** README states MIT; no LICENSE file in the repo.
- **Why relevant:** The cleanest minimal illustration of the *directed multi-agent graph with a
  shared typed state* pattern — our primary architectural blueprint.
- **Limitations:** No scoring logic, no real data, no tests.

## 2. Bhardwaj-Saurabh/OmniSupply-AI-Multi-Agent-Supply-Chain-Intelligence-Platform

- **URL:** https://github.com/Bhardwaj-Saurabh/OmniSupply-AI-Multi-Agent-Supply-Chain-Intelligence-Platform
- **What it is:** Supply-chain intelligence platform where a supervisor routes user questions to
  specialised agents (data analysis, risk, finance, reporting) over order/inventory/finance data.
- **Stack:** LangGraph + LangChain, OpenAI, Pydantic structured outputs, SQL + vector store,
  Opik tracing, `uv` packaging.
- **Architecture:** supervisor pipeline (parse → plan → select agents → execute → aggregate →
  report); each agent is a `BaseAgent` subclass with its own sub-graph.
- **Scoring:** deterministic weighted risk sub-scores with severity thresholds; the LLM writes the
  narrative and the code **overrides** any LLM-produced numbers.
- **License:** GPL-3.0.
- **Why relevant:** Best reference for *“compute numbers in code, let the LLM explain”* and for a
  supervisor with typed structured outputs.
- **Limitations:** operational, portfolio-level risk rather than per-supplier evaluation;
  hard-coded weights; no tests.

## 3. chinmaynadgir/supplychain-ai-agent

- **URL:** https://github.com/chinmaynadgir/supplychain-ai-agent
- **What it is:** “Supply Chain Risk Intelligence Assistant” — classifies suppliers into risk
  tiers, assesses disruption impact and produces narrative reports with charts.
- **Stack:** custom orchestrator with plain LLM calls (Gemini / Hugging Face), pandas,
  Streamlit UI.
- **Scoring:** LLM-judged tiers (Low / Medium / High / Critical) from financial health,
  compliance, dependency, on-time rate and quality; no explicit weights.
- **License:** README states MIT and refers to a LICENSE file that is not in the repo (checked at commit `0d91a53`, 2026-10-12).
- **Why relevant:** Useful supplier data model and a business-friendly UI idea.
- **Limitations:** results are not reproducible or explainable; no typed state.

## 4. poshalanavateja/Vendor-Bid-Evaluation-Ai

- **URL:** https://github.com/poshalanavateja/Vendor-Bid-Evaluation-Ai
- **What it is:** Evaluates vendor proposals (PDF) against an RFP: clause extraction, compliance
  check, risk and fairness flags, scoring, ranking and report.
- **Stack:** LangGraph + LangChain, OpenAI, FastAPI (SSE), React frontend, prompts in YAML.
- **Architecture:** LLM supervisor loop with conditional edges to worker agents; nested
  `TypedDict` state; human-review exit.
- **Scoring:** deterministic three tiers — hard compliance gate, weighted comparative score,
  capped risk penalty — with a transparent score breakdown.
- **License:** none.
- **Why relevant:** Strongest overall design of the set: supervisor + typed state + deterministic,
  explainable scoring + human-in-the-loop. Inspired our escalation rules and review exit.
- **Limitations:** built for one-off bid evaluation, not ongoing supplier risk; hard-coded
  weights; no tests.

## 5. vendor-evaluator (awesome-openclaw-agents)

- **URL:** https://github.com/mergisi/awesome-openclaw-agents/tree/main/agents/supply-chain/vendor-evaluator
- **What it is:** A prompt / persona definition for a single agent that scores and ranks vendors
  on quality, price, delivery and responsiveness and recommends procurement actions.
- **Stack:** no code — Markdown persona for the OpenClaw agent runtime.
- **Scoring:** LLM-judged, illustrated with example weights; the example arithmetic in the persona
  is inconsistent, which illustrates the risk of letting an LLM do the math.
- **License:** MIT.
- **Why relevant:** Good checklist for output format and procurement practice: state the
  methodology, show strengths/weaknesses, flag single sourcing, set review frequency by risk tier.

---

## Further reading (concepts, not code)

- Weighted-sum scorecards and min-max normalisation — standard multi-criteria decision analysis.
- Public governance and political-stability indicators (e.g. World Bank Worldwide Governance
  Indicators) as an input for country risk.
- LangGraph documentation — `StateGraph`, conditional edges, reducers, `interrupt()` for
  human-in-the-loop.
