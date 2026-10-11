# Proprietary SaaS references (public information only)

Two commercial supplier-risk platforms serve as **examples** for the "proprietary SaaS" profile in
[comparison-matrix.md](comparison-matrix.md).

**Basis and caveats**

- Everything here is drawn from **publicly available** sources, checked in October 2026: vendor
  websites, help-centre articles, press releases and vendor-commissioned studies.
- This is **not a product test**. No hands-on access, no customer interviews.
- Vendor statements are reported as **vendor claims**.
- Third-party aggregator content (e.g. AI-generated comparison sites) is used only as a weak
  indication and is marked as such.
- Review sites (G2, Capterra) could not be accessed.
- Anything not found publicly is marked **"not found publicly"**. That means it is not documented
  in public sources, not that the capability is absent.

---

## Prewave

| Topic | Public information | Source |
|---|---|---|
| Scope | Risk intelligence (monitoring, alerts, supplier scoring, multi-tier visibility); compliance & due diligence (LkSG, CSDDD, EUDR, forced-labour regulations); resilience/impact quantification | prewave.com |
| Signals | Vendor claims ~4.5M signals/day in hundreds of languages, merged into events; other pages give different figures (3M+/day, 400+ languages) | prewave.com; erpresearch.com |
| Tier-N | Mapping claimed "without supplier surveys", based on AI and trade/bill-of-lading data | prewave.com; SoftwareOne listing |
| **Score method** | **Published composition.** Score 1–100 (100 = least risk detected), with component weights: peer score 30 % (country 15 %, industry 7.5 %, commodity 7.5 %), alert score 40 %, assessment score 20 %, external data 10 %, Tier-N 0 % by default. Described as a "non-linear and weighted algorithm"; negative signals weigh more | help.prewave.com/en/articles/237277 |
| Configurability | "Event types and their weighting can be adjusted", customised "perspectives"; details via customer success | same |
| Source weighting / NLP | Not found publicly (weak indication from an aggregator: "not publicly transparent") | rfp.wiki (AI-assisted, low confidence) |
| Workflows | Alerts to actions, supplier assessments/questionnaires, supplier network (free for suppliers) | prewave.com; help centre |
| Integrations | SAP Ariba documented (scores written back via API); procurement-suite partners listed; REST API | help.prewave.com/en/articles/250973 |
| Pricing | **Not public**; quote-based subscription by supplier count and modules | erpresearch.com; gartner.com reviews page |
| ROI | Vendor-commissioned TEI study (composite organisation) reports high ROI; no licence price | tei.forrester.com/go/prewave/… |
| Scale | Vendor claims 150–200+ enterprise customers and >1M suppliers assessed; self-announced Leader in a 2026 analyst evaluation | prewave.com; wp.prewave.com |
| Open source | No | — |

## Sphera Supply Chain Risk Management (formerly riskmethods)

| Topic | Public information | Source |
|---|---|---|
| Scope | Supplier 360 intelligence, multi-/N-tier mapping, early warnings, supplier engagement campaigns, risk response & resolution, compliance incident management; earlier module names: Risk Radar, Impact Analyzer, Action Planner | sphera.com/solutions/supply-chain-risk-management |
| Due diligence | LkSG bundle (risk analysis, documentation of preventive/remedial measures, indicator scorecard, supplier questionnaire), 2023 | sphera.com white paper and brochure (2023) |
| Signals | AI/NLP/ML-based monitoring (press release 2023); risk types include natural disasters, insolvencies, geopolitics. Source count and languages: not found publicly | sphera.com press release; secondary review site |
| **Score method** | **Not found publicly.** "AI-scoring ties each risk to business impact"; indicator scorecards mentioned. Weights and their configurability not found publicly | sphera.com |
| Workflows | Response playbooks with ownership and tracked closure; incident management; questionnaires | sphera.com; TrustRadius listing |
| Integrations | Embedding into procurement/GRC/ERP workflows stated; specific connectors and public API docs not found publicly | sphera.com |
| Pricing | **Not public** (an unverified review-site snippet mentions a per-user monthly price) | — |
| Scale | Sphera overall claims 7,000+ customers (2023); no SCRM-specific figure found | sphera.com press release |
| Open source | No | — |

## Comparable vendors (brief, for context)

- **Resilinc:** a supplier resilience score with five fixed components against "universal
  standards". Customer-adjustable weights not found publicly.
- **EcoVadis** (ESG ratings): publishes its criteria and themes. Weights vary by industry, size and
  country and are described qualitatively; buyers cannot set them (assumption).
- **Everstream, Interos:** scoring methodology not found publicly.

## Takeaways for the comparison

- **Transparency varies a lot within "SaaS".** Prewave publishes its score composition. Sphera
  publishes almost nothing about scoring. The SaaS profile is therefore given as a **range**
  where vendors differ.
- **No vendor publishes pricing.** Both are enterprise subscriptions.
- **Neither offers calibration against the customer's own expert judgement** as a documented
  feature (not found publicly). Weight adjustment exists (Prewave), but as manual configuration.
- **Clear SaaS strengths:**
  - data coverage (external signals, Tier-N)
  - regulatory documentation
  - scale
  - operational maturity
