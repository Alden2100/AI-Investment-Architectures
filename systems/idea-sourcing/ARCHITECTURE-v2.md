# Idea Sourcing v2 — Multi-Agent Architecture

**Status:** Design (pre-build). Supersedes the single-orchestrator `orchestrator.py`.
**Scope:** Standalone idea-sourcing system. Keyless / free-data only.
**Decisions baked in (from review):**

| Decision | Choice |
|---|---|
| Model strategy | **Full ladder** — local qwen → Sonnet → Opus, auto-escalate on low confidence |
| Trust layer | **Audit log** + **data-quality flags** (no Report-Contract envelope, no hard composite anchor) |
| Reuse | **Pragmatic** — keep whatever fits the multi-agent design; rebuild the orchestration/agent layer |
| Scope | **Keyless** free-data; **standalone** (no cross-system handoff); **no investment thesis** (evidence + ranking explanation only) |

### Agent naming

The **`idea-sourcing-orchestrator`** is the single entry point and controller — when invoked (by a user, a schedule, or an event), it runs the entire system end to end. It is named for its system. Every other agent is named for **exactly what it does**, not by a generic stage role, so names stay unambiguous as agents are added for other systems (valuation, due-diligence, etc.).

| Role in funnel | Agent name | Old generic name |
|---|---|---|
| Entry point / controller | **`idea-sourcing-orchestrator`** | Funnel Orchestrator Agent |
| Stage 0 — interpret the mandate | **`mandate-interpreter`** | Mandate Interpretation Agent |
| Stage 1 — non-LLM funnel pre-filter | **`opportunity-engine`** (deterministic, not an agent) | Opportunity Engine |
| Stage 3 — validate/standardize securities | **`universe-validator`** | Universe Agent |
| Stage 4 — quantitative scoring | **`quantitative-screener`** | Screening Agent |
| Stage 5 — detect catalysts/changes | **`catalyst-detector`** | Signal Agent |
| Stage 6 — qualitative business evidence | **`qualitative-researcher`** | Research Agent |
| Stage 7 — aggregate + rank + explain | **`opportunity-ranker`** | Ranking Agent |

---

## 1. Objective & non-goals

Continuously interpret an arbitrary user mandate, search the investable universe, run a progressively deeper funnel, and emit a **ranked opportunity list with supporting evidence** for an analyst to investigate further.

The system **does not** make buy/sell calls, write memos, build full valuation models, set price targets, or replace diligence. It produces an evidence-backed shortlist and the reasoning for the ordering — nothing that reads as a recommendation.

## 2. Governing principles

1. **Separate search from reasoning.** Traditional software filters, ranks, queries, computes, and does vector search over thousands of names. The model only reasons over a small candidate set. (Carries the old invariant: *code for what's exact, model for what's judged*.)
2. **Progressive funnel.** Each stage does more work on fewer names: ~8,000 → ~300 → ~75 → ~25 → ranked.
3. **Hierarchical agents, deterministic skills.** Agents decide; skills do bounded deterministic work and emit one JSON object. Agents never call APIs or parse documents directly.
4. **Mandate-driven.** Nothing assumes one definition of a good investment. The structured mandate is an input to every downstream stage and configures filters, factor weights, and ranking.
5. **Modular & replaceable.** The orchestrator knows contracts, not implementations. Agents communicate through structured outputs. Skills are versioned and pinned per system via a manifest.
6. **Keyless by default.** Every fact comes from a free source with a fallback chain. No paid API is required to run end-to-end.

## 3. High-level architecture

The `idea-sourcing-orchestrator` is the **single entry point and controller**. A user, schedule, or event invokes it with a mandate; it then drives every stage, parallelizes per company, caches, retries, and logs. No stage runs except through the orchestrator.

```
   User / schedule / event   ──(mandate: text / PDF / DOCX / MD)──┐
                                                                   ▼
                                              ┌─────────────────────────────────────┐
                                              │     idea-sourcing-orchestrator        │
                                              │  (single entry point / controller —   │
                                              │   runs stages, parallelizes, caches,  │
                                              │   retries, logs every model decision) │
                                              └─────────────────────────────────────┘
                                                                   │ runs, in order:
      ┌──────────────┬───────────────┬───────────────┬────────────┴───┬───────────────┬───────────────┐
      ▼              ▼               ▼               ▼                 ▼               ▼               ▼
 mandate-       opportunity-    universe-      quantitative-      catalyst-       qualitative-    opportunity-
 interpreter    engine          validator      screener           detector        researcher      ranker
 (Stage 0)      (Stage 1,LLM-   (Stage 3)      (Stage 4)          (Stage 5)       (Stage 6)       (Stage 7)
  mandate→       free funnel     validate &     quant scores       catalysts &     qual business   aggregate,
  profile        → 100–300       standardize    & elimination      changes         evidence        rank, explain
                 candidates)
                                 └──────────────── parallel per company ───────────────┘
                                                                   │
                                                                   ▼
                                          Ranked Opportunity List (+ expandable evidence per name)

  Cross-cutting:  Evidence Store · HTTP/stage cache · Model Router · Audit Log · Data-Quality Flags
```

Every external operation is a skill. Every model call is routed and logged. Every company is analyzed independently, so the orchestrator runs stages 3–7 concurrently per name. Within the two judgment stages, an **adversarial debate overlay** runs opposing agents at the same time — `confirming`/`disconfirming` evidence in Stage 6, a selective `ranking-challenger` in Stage 7 (see §7).

---

## 4. What we reuse vs. build

The old system already contains most of the deterministic spine. The rebuild is concentrated in the **agent/orchestration layer** and in splitting one monolithic scoring step into discrete, mandate-configurable skills.

### Reuse wholesale (the spine)

| Old asset | Role in v2 |
|---|---|
| `imdata/store.py` (SQLite + TTL HTTP cache) | Evidence Store + cache foundation (extended with new tables) |
| `imdata/screener.py` (`company_metrics` snapshot) | Core of the Opportunity Engine — instant universe filter |
| `imdata/universe.py`, `entities.py`, `edgar.py` | `universe-validator` data |
| `imdata/prices.py` (yfinance→Yahoo→Stooq) | Prices, ADV/liquidity |
| `imdata/estimates.py` | Consensus, `data_quality()` cross-validation |
| `imdata/ownership.py` | Insider (Form 4) signal |
| `imdata/news.py`, `articles.py` | News + body extraction |
| `imdata/macro.py`, `valinputs.py` | Risk-free / WACC inputs (Treasury, Damodaran) |
| `imdata/filing_rag.py` | Seed for semantic/vector search (filing-text RAG today) |
| `imrouter/` engine + `orchestration.py` | Model router, `synthesize()`, `persona()`, `routing_ledger()`, `audit()` |
| `imdata/skillkit.py` (`call_skill`, `run`) | Skill subprocess contract |
| Manifest + `link.py` symlink materialization | Per-system skill pinning |

### Reuse as skills (map onto the new stages)

| Agent (stage) | Existing skills reused |
|---|---|
| `opportunity-engine` (1) | `universe-screener`, `stock-screener-builder` |
| `universe-validator` (3) | `universe-screener` (metadata/liquidity view) |
| `quantitative-screener` (4) | `fundamentals-fetcher`, `comps-builder`, `dcf-valuation`, `analyst-estimate-monitor` |
| `catalyst-detector` (5) | `catalyst-flagger`, `news-fetcher`, `regulatory-filing-monitor`, `filing-change-detector`, `insider-trading-monitor`, `earnings-call-summarizer` |
| `qualitative-researcher` (6) | `business-model-analyzer`, `moat-analyzer`, `industry-structure-analyzer`, `management-quality-evaluator`, `peer-identifier`, `footnote-analyzer`, `kpi-extractor`, `management-sentiment-analyzer` |

### Build new

- **`mandate-interpreter`** — mandate parser + structured-mandate builder (PDF/DOCX/MD/text → profile). Reuse the `pdf` skill for extraction.
- **`opportunity-engine`** — mandate-configurable factor pre-rank; company-similarity vector search (extends `filing_rag`).
- **`idea-sourcing-orchestrator`** — the single entry-point multi-agent controller (parallelism, per-stage caching, retry, incremental re-runs).
- **`quantitative-screener`** — split the old monolithic `score_candidates()` into discrete skills: Valuation, Growth, Quality, Profitability, Capital-Allocation, Momentum, Financial-Health, Custom-Formula.
- **`qualitative-researcher`** — revenue-driver, customer-analysis, supplier-analysis, risk-identification, evidence-extraction skills, plus the `confirming-evidence` / `disconfirming-evidence` adversarial pair (debate overlay).
- **`opportunity-ranker`** — evidence-aggregation, normalize-scores, peer-comparison, opportunity-ranking, risk-adjustment, confidence-assessment, explainability skills, plus the `ranking-challenger` (selective debate overlay).

**Reused as evidence (not thesis writers):** `bull-case-generator` → `confirming-evidence`, `bear-case-generator` → `disconfirming-evidence`. They run as the Stage-6 adversarial pair and emit tagged evidence objects, never a case/recommendation narrative.

**Explicitly excluded** (conflict with "no thesis"): `thesis-recorder`, `memo-writer`, `valuation-summary-writer`. No thesis/recommendation text is produced anywhere in the system.

---

## 5. Stage specifications

Each agent declares a **contract only** (input/output). Wiring is the orchestrator's job. All numbers are skill-computed; agents quote, never invent.

### Stage 0 — `mandate-interpreter`
**Purpose:** any mandate → structured profile. Understands intent, not keywords.
**Skills:** document-parser, pdf-extract, text-clean, philosophy-extract, objective-extract, constraint-extract, industry-preference, metric-preference, factor-weight-extract, risk-tolerance, time-horizon, example-company-extract, clarification, structured-mandate-builder.
**Output — `MandateProfile`:**
```json
{
  "style": "quality | value | growth | deep-value | founder-led | ...",
  "quality_pref": "...", "valuation_pref": "...", "growth_pref": "...",
  "preferred_industries": [], "excluded_industries": [],
  "market_cap": {"min": null, "max": null},
  "risk_tolerance": "...", "time_horizon": "...",
  "preferred_metrics": [], "factor_weights": {"value":0.3,"growth":0.25,"quality":0.25,"catalyst":0.1,"momentum":0.1},
  "example_companies": [], "special_instructions": "...",
  "mandate_hash": "sha256(...)"     // cache key + audit handle
}
```
**Routing:** extraction/classification → qwen; the final intent synthesis → Sonnet.

### Stage 1 — `opportunity-engine` (NON-LLM)
**Purpose:** reduce the universe to 100–300 candidates before any model runs.
**Components (all deterministic):** financial screening, mandate-configured factor model, event detection, news/estimate-revision/insider monitoring, custom filters, and vector/semantic/similarity search (seeded by example companies in the mandate).
**Input:** full universe (the `company_metrics` snapshot). **Output:** candidate tickers + the deterministic factor pre-rank that seeds Stage 7. The `MandateProfile` configures filters, factor weights, and ranking formula — nothing hardcoded.

### Stage 2 — `idea-sourcing-orchestrator`
**Purpose:** the single entry point and controller for the whole system; contains almost no business logic of its own.
**Invocation:** invoked by a user, a schedule, or an event with a mandate. Nothing else starts a run — the orchestrator runs Stage 0 first (interpret the mandate), then Stage 1 (opportunity-engine), then drives Stages 3–7.
**Responsibilities:** run stages in order, pass survivors forward, drop weak candidates at each gate, **parallelize per company** across Stages 3–7, retry failed jobs, cache outputs, skip unchanged work via the Evidence Store, and log every model decision. Built on the old `imrouter/orchestration.py` helpers.

### Stage 3 — `universe-validator`
**Purpose:** validate and standardize candidates.
**Skills:** security-universe, exchange-filter, company-metadata, market-cap, sector/industry classification, liquidity screen, geography, watchlist.
**Output:** clean, validated company metadata ready for analysis; drops invalid/illiquid names.

### Stage 4 — `quantitative-screener`
**Purpose:** evaluate structured financials; apply mandate-weighted quantitative scoring.
**Skills:** valuation, growth, quality, profitability, capital-allocation, momentum, financial-health, estimate-revision, relative-performance, custom-formula.
**Output:** per-name quantitative sub-scores + structured evidence; eliminates weak candidates. (This is the old `score_candidates()` decomposed into auditable skills.)

### Stage 5 — `catalyst-detector`
**Purpose:** detect what recently changed.
**Skills:** sec-filing, earnings-call, news, insider-trading, patent, product-release, M&A, macro-exposure, regulatory-event, alt-data, event-detection.
**Output:** structured catalysts/inflections per name `{type, date, source, confidence, hard_event, rationale}`.

### Stage 6 — `qualitative-researcher`
**Purpose:** structured **qualitative evidence** — no thesis.
**Skills:** business-model, revenue-driver, competitive-position, industry-structure, customer-analysis, supplier-analysis, management-quality, capital-allocation, financial-statement-analysis, risk-identification, catalyst-identification, evidence-extraction.
**Adversarial evidence pair (debate overlay).** For each surviving name, two sub-agents run **concurrently**: a `confirming-evidence` agent marshals the case-for, a `disconfirming-evidence` agent marshals the case-against and risks. One bounded round — each sees the other's points once and may rebut — then the researcher records **both sides** as structured evidence. This produces the "conflicting evidence" the ranking needs and stays inside the no-thesis rule (evidence for and against, never a recommendation). It revives the old `bull-case-generator` / `bear-case-generator` as evidence generators. Routing: the two sides run on a cheap rung (qwen/Sonnet); only the reconciliation, if needed, escalates.
**Output:** evidence objects with citations per name, each tagged `confirming` | `disconfirming`. Everything evidence-based; no recommendation language.

### Stage 7 — `opportunity-ranker`
**Purpose:** combine all evidence into the final ranking + explanations.
**Skills:** evidence-aggregation, normalize-scores, peer-comparison, opportunity-ranking, risk-adjustment, confidence-assessment, explainability, (optional) portfolio-fit.
**Method:** deterministic skills produce normalized quant/qual/catalyst/risk/mandate-fit scores and one composite **Opportunity Score**. The `opportunity-ranker` (model) orders the list and writes a concise *explanation* of why each name ranks where it does — it consumes the deterministic scores as strong evidence (not a hard anchor) and must cite a specific figure when it deviates. Low-confidence rankings escalate one model rung.
**Selective challenger (debate overlay).** Only for *contested* names — those whose scores cluster within a tolerance of a cutoff, or where the quant score and the Stage-6 qualitative evidence disagree — run one bounded `ranking-challenger` pass that argues the placement is wrong, then a reconciliation. This is not a separate mechanism but a richer form of the confidence-guard escalation already approved: instead of merely escalating to a bigger model, the escalation *is* propose → challenge → reconcile. Routing: challenger on a cheaper rung, referee/reconciler on the higher rung. Names that aren't contested skip the challenger entirely, so debate stays gated to the few rows that justify the cost.
**Output — final list rows:**
```json
{"rank":1,"ticker":"...","company":"...","opportunity_score":0,"confidence":"high|med|low",
 "mandate_fit":0,"primary_catalysts":[],"primary_risks":[],
 "why_ranked":"explanation citing specific figures/events (NOT a buy/sell thesis)",
 "data_flags":[], "evidence_ref":"evidence-store id"}
```
Each row expands to quant metrics, qualitative evidence, recent events, extracted reasoning, and citations.

---

## 6. Model router (full ladder)

One router *engine* (`imrouter`), one *policy* per agent. Policy maps task type → rung; the engine's confidence guard promotes a low-confidence or schema-invalid result one rung automatically. Keyless fallbacks both directions (Ollama down → step up to Claude; no API key → fall back to qwen), each logged with a reason.

| Task type (per agent) | Rung |
|---|---|
| extraction, classification, screening, summarization | **qwen3.5:9b** (local, free) |
| synthesis, reasoning (mandate intent, ranking) | **Sonnet** |
| hard/low-confidence judgment | **Opus** (auto-escalated) |

`model_routing` is reported on every run as proof the ladder engaged (a single model across all tasks means judgment leaked out of the router).

## 7. Cross-cutting

**Evidence Store** — extend `imdata/store.py` with tables: `runs` (mandate_hash, started_at, model_routing), `evidence` (company, stage, skill, json, citations, computed_at), `scores` (company, factor, value, run_id), `events` (company, type, date, source, confidence). Every agent writes structured output here, enabling incremental updates — if only a news article changed, re-run Signal + downstream, not the whole funnel.

**Caching** — reuse the TTL HTTP cache; add a per-stage output cache keyed by `(company, mandate_hash, inputs_hash)`. Unchanged inputs → cache hit, no recompute.

**Audit log** — reuse `store.append_audit` + the router ledger. Every model-made decision (agent, task, rung, model, result, reason) is logged to a replayable trail. *(Selected.)*

**Data-quality flags** — reuse `estimates.data_quality()` + the screener's market-cap reconciliation + business-model caveats (banks/REITs where EV/EBITDA & DCF mislead). Suspect numbers are flagged on the name, surfaced in `data_flags`, and lower the `opportunity-ranker`'s confidence. *(Selected.)*

**Parallelization** — two kinds. (1) *Horizontal:* stages 3–7 run per company concurrently (bounded worker pool); the old per-candidate sequential loop is replaced. Skills stay process-isolated via `call_skill`. (2) *Adversarial (debate overlay):* at the narrow end of the funnel only, opposing agents work the same judgment at once — the Stage-6 `confirming`/`disconfirming` evidence pair (always, per surviving name) and the Stage-7 `ranking-challenger` (selectively, on contested names). Debate is confined to judgment-only stages — never the deterministic ones (`opportunity-engine`, `universe-validator`, `quantitative-screener`), where code already computes the right answer — and is bounded to one propose→challenge→reconcile round to cap cost and drift.

**Explainability** — every score traces to its skill + inputs; every rank carries why-ranked, supporting evidence, confidence, and conflicting evidence via the Evidence Store.

**Extensibility** — adding an agent, skill, or data source is additive: drop a versioned skill in the library, pin it in the manifest, declare the agent contract. No equity/single-philosophy assumptions are baked in.

## 8. Proposed layout

```
systems/idea-sourcing/
├── ARCHITECTURE-v2.md            # this doc
├── manifest.yaml                 # pinned skills + agents (extended)
├── router-policy.yaml            # per-task rungs (ladder)
├── orchestrator.py               # Stage 2 funnel orchestrator (rebuilt)
├── agents/                       # contracts: mandate-interpreter, universe-validator, quantitative-screener,
│                                 #   catalyst-detector, qualitative-researcher (+ confirming/disconfirming),
│                                 #   opportunity-ranker (+ ranking-challenger)
└── stages/                       # thin per-stage drivers the orchestrator composes

skills-library/
├── _shared/                      # imdata, imrouter, branding, web-search  (reused)
├── mandate/  opportunity/        # new drawers (Stage 0 / Stage 1)
└── research/ filings/ market/ valuation/ ...  (existing skills reused + new ones added)
```

## 9. Phased build plan

1. **Evidence Store + contracts.** Extend `store.py`; define the 6 agent I/O JSON schemas and the `MandateProfile`. Unit-test the schemas.
2. **Stage 0 + Stage 1.** Mandate parser → profile; wire the Opportunity Engine on the existing snapshot with a mandate-configurable factor pre-rank. End-to-end: mandate → candidate list.
3. **`idea-sourcing-orchestrator`.** The single entry-point controller: parallel per-company funnel, caching, retry, audit, routing ledger. Run with stub stages.
4. **Stages 3–5.** Universe validation, Screening (decompose `score_candidates`), Signal. Mostly wrapping existing skills.
5. **Stages 6–7 + debate overlay.** Research evidence skills with the `confirming`/`disconfirming` adversarial pair; Ranking aggregation/explainability with the selective `ranking-challenger`. Bound debate to one round; enforce no-thesis output.
6. **Verification.** Smoke test (keyless via qwen), `link.py --check` manifest validation, data-quality flag tests, and a routing-ledger assertion that the ladder engaged.

## 10. Open items to confirm before build

- **Universe source & size** for Stage 1 (SEC-derived US universe vs. adding Finviz breadth) — affects the 8,000→300 funnel realism.
- **Vector search corpus** — what text to embed for company similarity (business descriptions, 10-K Item 1) and where to store vectors keylessly.
- **Funnel gate thresholds** — fixed defaults vs. mandate-derived per stage.
