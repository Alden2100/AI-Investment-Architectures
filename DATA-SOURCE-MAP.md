# Data-source map — 7 systems + the shared layer

*Reconciles `avenoth_free_data_sources.html` with what's wired today and the audit gaps. Source of the decision rule: your own architecture (all fetching funnels through `_shared/data-fetch/imdata` + its cache).*

## The decision rule (use this for ANY new source)

1. **Used by ≥2 systems, or foundational?** (universe/identifiers, the store/cache, prices, macro) → **Shared** (`imdata`). Put the *fetch + cache* here.
2. **Exactly one system + bespoke parsing no one else reuses?** → **System-local** (only the parser; the raw fetch+cache can still live in shared).
3. **Unsure?** → Default Shared. Duplicated fetchers are exactly what the architecture exists to prevent.
4. **Always** route the outbound call through the shared store with a `fetched_at` TTL before hitting the network (the Avenoth doc's caching architecture = your `http_cache` pattern).

Tiers below: **[wired]** = already in `imdata` today · **[keyless]** = free, no key · **[key]** = free but needs a free API key.

---

## Shared layer (`_shared/data-fetch/imdata`) — the spine everyone reuses

| Source | Tier | What it provides | Gap it closes |
|---|---|---|---|
| SEC EDGAR submissions + XBRL companyfacts | [wired] | filing history, all tagged financials | core fundamentals |
| EDGAR full-text search (EFTS) + RSS/Atom | [wired] | filing discovery, real-time 8-K/4/13D alerts | filings/catalysts |
| Prices: yfinance → Yahoo → Stooq fallback | [wired] | OHLCV, splits, dividends | prices/vol |
| News fetch + **body extraction** (trafilatura) | [keyless] | full article text, not titles | #3 thin news (in progress) |
| **FRED** (risk-free rate, CPI, yield curve, spreads) | [key] | macro backbone for every system | no macro context |
| **US Treasury yield curve** (XML) | [keyless] | official risk-free rate for DCF | hardcoded WACC inputs |
| **Damodaran datasets** (sector WACC, beta, ERP, margins) | [keyless] | derived discount-rate inputs | **#4 hardcoded 9% WACC** |
| **Estimates/consensus** (stockanalysis.com scrape, or FMP) | [keyless/key] | forward EPS/revenue, analyst count | **#3 no forward numbers** |
| SQLite + DuckDB/Parquet cache | [wired] | dedup + free-tier stretch | quota safety |
| Universe/screen (EDGAR + Finviz/`finvizfinance`) | [keyless] | investable universe | screening |

The bolded shared additions (Damodaran, Treasury/FRED, consensus) are the highest-leverage because they directly fix audit causes #3 and #4 — they're shared precisely because valuation, reporting, idea-sourcing and portfolio all draw on them.

---

## Per-system map

**01 · Due Diligence** — Shared: EDGAR XBRL, prices, FRED. System-local: **S-1 / Form D** parsing (pre-IPO & private context) `[keyless]`, **segment KPIs via `edgartools`** (XBRL dimensional) `[keyless]`, Macrotrends long-history sanity check `[keyless]`.

**02 · Idea Sourcing** — Shared: universe/screen, XBRL fundamentals, prices, EDGAR 8-K RSS catalysts, FRED. System-local: **13F holdings** (smart-money replication) `[keyless]`, **FINRA short interest** `[keyless]`, FMP peer financials/growth `[key]`.

**03 · Governance Audit** — Shared: EDGAR filings + DEF 14A fetch. System-local: **Form 4 insider XML** `[keyless]`, **13D/13G beneficial ownership** `[keyless]`, **OpenSanctions** PEP/sanctions `[key]`, CEO pay-ratio from proxy + XBRL.

**04 · Portfolio Monitoring** — Shared: prices (returns/vol), FRED (rates), EDGAR RSS holding alerts, news. System-local: **CBOE VIX** (vol overlay) `[keyless]`, **CFTC COT** positioning/crowding `[keyless]`, **FINRA short interest** `[keyless]`, Alpha Vantage indicators `[key, 25/day]`.

**05 · Reporting** — Shared only (it consumes upstream outputs): XBRL fundamentals, prices, FRED, Damodaran, consensus estimates. No system-local sources — if Reporting wants a new number, add it to shared.

**06 · Valuation** — Shared: XBRL fundamentals, prices, **Treasury/FRED risk-free rate**, **Damodaran sector WACC/beta/ERP**. System-local: **consensus estimates** for forward FCF `[keyless/key]`, **segments** for sum-of-parts `[keyless]`.

**07 · Filing Intelligence** — Shared: EFTS full-text search, EDGAR RSS, filing-text fetch. System-local: **earnings-call transcripts (8-K EX-99.1)** feeding `earnings-call-summarizer` `[keyless]`.

**Orchestration / all systems** — Ollama local + Claude Code (Max-plan model step) + the SQLite/DuckDB/Parquet cache. All shared.

---

## How to apply this (the procedure)

For each system, list the questions it must answer, then for each fact: (a) check if a **shared** fetcher already produces it → use it; (b) if not, run the decision rule above to decide shared vs. system-local; (c) wire the *fetch+cache* into `imdata`, expose it as a skill, and have the system's orchestrator select it. A source appears under multiple systems only as a *shared* fetcher each calls — never copied into two systems.

**Start order (max value, least effort):** Damodaran + Treasury/FRED (fixes WACC, shared) → consensus estimates (fixes forward numbers, shared) → 8-K EX-99.1 transcripts (management commentary, filing-intel) → segment KPIs via edgartools (moat/SOTP). Insider/13F/13D/G/OpenSanctions come online with the two scaffolded systems (governance-audit, due-diligence).
