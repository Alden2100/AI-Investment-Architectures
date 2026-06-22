# Guide for Claude Code — integrate the Avenoth free data sources into the existing architecture

*Goal: wire the ~40 sources from `avenoth_free_data_sources.html` into `_shared/data-fetch/imdata`, following the patterns already in this repo. Nothing is dropped — commercial-license risk is captured as a per-source flag, not an exclusion. Read this whole file before starting.*

## 0. What already exists (extend, don't rebuild)

`imdata/` currently has: `config.py`, `store.py`, `skillkit.py`, `edgar.py`, `prices.py`, `news.py`, `universe.py`, `filing_rag.py`, **`articles.py`** (trafilatura article-body extraction, kv-cached, concurrent, best-effort), **`estimates.py`** (yfinance consensus EPS/revenue, price targets, recommendations, ownership, short interest — kv-cached, best-effort). So "news bodies" and "consensus/ownership" are already in place via Yahoo. Your job is to broaden coverage, add the government/primary sources, and make provenance + license tier first-class.

## 1. Integration principles — reuse these 6 patterns for every source

1. **All fetching goes through `imdata`.** Systems never fetch directly; they call a shared module → skill → orchestrator. A source used by ≥2 systems or that is foundational (macro, prices, identifiers, cache) is shared; only bespoke single-system parsing is system-local.
2. **Cache everything, three tiers (already in `store.py`):**
   - Raw HTTP → `store.cached_get(url, ttl=, headers=, timeout=, data=)` / `store.cached_get_json(...)`.
   - Derived/parsed objects → `store.kv_get(key, ttl=)` / `store.kv_put(key, value)` (this is what `articles.py` and `estimates.py` use).
   - First-class entities with their own queries → a dedicated table + upsert helper (like `companies/filings/facts/prices/news`).
   Pick kv for most new sources; add a table only when you need to query across rows.
3. **Keyless by default, keyed upgrade when a key is present** — copy the existing precedent: `web-search` uses DuckDuckGo unless `BRAVE_API_KEY`; `prices` falls back yfinance→Yahoo→Stooq. Same shape: `if os.environ.get("X_API_KEY"): keyed_path() else: keyless_path()`.
4. **Best-effort, never raise.** Every accessor degrades to `None`/`[]`/`""` on missing fields, timeouts, schema drift, paywalls — exactly as `articles.py`/`estimates.py` do. A dead source must not crash a skill.
5. **Config centralization.** New TTLs and the SEC-style User-Agent go in `config.py`; new API keys are read from the environment and loaded from `.env` via the existing `os.environ.setdefault` loader in `ask.py`/orchestrators. Add each new key to `.env.example`.
6. **Respect rate limits in code.** SEC stays under `config.SEC_MAX_RPS`; per-source soft limits (yfinance ~2k/day, FMP 250/day, NewsAPI 100/day, Alpha Vantage 25/day) get a small sleep + the cache does the rest. Document the limit in the module docstring.

## 2. Make provenance + commercial-license tier first-class (the licensing solution)

Add a tiny **source registry** `imdata/sources.py`: one entry per source with `{name, module, tier, requires_key, attribution}` where `tier ∈ {public, keyless_unofficial, free_key_noncommercial, free_key_eval}`.

- `public` = government/public-domain, safe to resell (SEC, FRED-gov-series, Treasury, BLS, CFTC, FINRA, World Bank, Damodaran-with-attribution).
- `keyless_unofficial` = scrapes/unofficial endpoints, dev-only for client work (yfinance, Finviz, Macrotrends, stockanalysis, pytrends, Nitter).
- `free_key_noncommercial` = free key but NC license (OpenSanctions).
- `free_key_eval` = free key, eval/dev only, commercial needs paid agreement (FMP, NewsAPI, GNews, Alpha Vantage, Polygon, IEX, Simfin).

Then: (a) every skill output already carries `provenance`; extend it to name the **source + tier** for each number so a memo can footnote where data came from; (b) add an `IM_COMMERCIAL_MODE` env flag — when set, fetchers in non-`public` tiers are skipped (or swapped for their public equivalent) so a client-facing run uses only resellable data. This keeps all sources available for dev while making the commercial edge clean — nothing is eliminated, it's gated.

## 3. Module plan — where each source lands

Existing modules extended, new modules added. `[tier]` per §2.

### Filings & ownership — `edgar.py` (extend) + new `ownership.py`
| Source | Target | Cache | Tier | Closes gap |
|---|---|---|---|---|
| EDGAR submissions / XBRL companyfacts / EFTS full-text / RSS | `edgar.py` (wired) | table/http | public | core |
| EDGAR bulk data (num/tag/sub TSV → DuckDB/Parquet) | new `bulk.py` | files | public | offline bootstrap |
| Form 4 insider (XML) | new `ownership.py` | kv | public | insider signal (governance/catalyst) |
| 13D/13G beneficial ownership | `ownership.py` | kv | public | activist/governance |
| 13F institutional holdings | `ownership.py` | kv | public | smart-money idea sourcing |
| 8-K EX-99.1 earnings transcripts | `edgar.py` (`find_transcript()`) | table | public | **mgmt commentary (#3)** |
| Form D / S-1 (private/pre-IPO) | new `forms.py` | kv | public | due-diligence context |

### Market data — `prices.py` (extend provider chain) + new `volatility.py`
| Source | Target | Cache | Tier | Note |
|---|---|---|---|---|
| yfinance (primary) | `prices.py` (wired) | table | keyless_unofficial | dev-only for client work |
| Stooq (fallback) | `prices.py` (wired) | table | keyless_unofficial | |
| Polygon.io free | `prices.py` keyed branch | http | free_key_eval | EOD + ticker reference |
| Alpha Vantage | `prices.py` keyed branch | http | free_key_eval | indicators only (25/day) |
| IEX sandbox | skip (fake data) | — | free_key_eval | prototyping patterns only |
| CBOE VIX (CSV) | new `volatility.py` | http | public | vol overlay (portfolio) |
| FINRA short interest (CSV) | `ownership.py` | http | public | authoritative short % float |

### Fundamentals & valuation inputs — new `valinputs.py` + extend `universe.py`/`estimates.py`
| Source | Target | Cache | Tier | Closes gap |
|---|---|---|---|---|
| SEC XBRL facts | `edgar.py`/`fundamentals` (wired) | table | public | core financials |
| **Damodaran** WACC/beta/ERP/margins (XLS) | new `valinputs.py` | kv | public | **derived WACC (#4 hardcoded 9%)** |
| Segment KPIs (XBRL dimensional / `edgartools`) | new `segments.py` | kv | public | moat/SOTP (#4) |
| Consensus estimates (yfinance) | `estimates.py` (built) | kv | keyless_unofficial | **forward numbers (#3)** |
| stockanalysis.com estimates | `estimates.py` keyed/scrape branch | http | keyless_unofficial | forward EPS fallback |
| FMP (IS/BS/CF/ratios/comps) | new `fmp.py` | http | free_key_eval | rich comps; dev-only commercially |
| Simfin standardized statements | `fmp.py` sibling | http | free_key_eval | clean schema |
| Finviz screener / key stats | `universe.py` (extend, `finvizfinance`) | kv | keyless_unofficial | screening |
| Macrotrends long-history | `valinputs.py` scrape branch | http | keyless_unofficial | sanity-check old periods |

### Macro — new `macro.py`
| Source | Target | Cache | Tier |
|---|---|---|---|
| FRED (rates, CPI, yield curve, spreads) | `macro.py` (`fredapi`) | http | public (avoid 3rd-party S&P series) |
| US Treasury yield curve (XML) | `macro.py` | http | public |
| BLS (CPI/PPI/employment) | `macro.py` | http | public (free registration) |
| World Bank (`wbgapi`) | `macro.py` | http | public |
| ECB SDW (`pandasdmx`) | `macro.py` | http | public |
| CFTC COT positioning | `macro.py` | http | public |

### News & alt-data — `news.py` (extend providers) + new `altdata.py`
| Source | Target | Cache | Tier |
|---|---|---|---|
| Google News RSS + article bodies | `news.py` + `articles.py` (built) | table/kv | keyless_unofficial |
| NewsAPI / GNews | `news.py` keyed branch | http | free_key_eval (content copyrighted) |
| Reddit (PRAW) | new `altdata.py` | kv | free_key_eval (NC-ish) |
| Google Trends (`pytrends`) | `altdata.py` | kv | keyless_unofficial |
| Twitter/X, Nitter | `altdata.py` | kv | keyless_unofficial (targeted only) |

### Governance — new `sanctions.py`
| Source | Target | Cache | Tier |
|---|---|---|---|
| **Primary lists: OFAC SDN, EU, UN, UK** | `sanctions.py` (default) | http | public (resellable) |
| OpenSanctions aggregated API | `sanctions.py` keyed branch | http | free_key_noncommercial (gate behind `IM_COMMERCIAL_MODE`) |

Design `sanctions.py` to default to the **primary government lists** (commercial-safe) and only use OpenSanctions when a key is present and `IM_COMMERCIAL_MODE` is off.

## 4. Conventions (do it this way)

- **New env key:** read with `os.environ.get("FRED_API_KEY")`; add a commented line to `.env.example`; never hardcode. Gate the keyed path on its presence.
- **New TTL:** add `TTL_MACRO`, `TTL_DAMODARAN` (annual), `TTL_OWNERSHIP`, `TTL_SANCTIONS`, etc. to `config.py` with env overrides, mirroring the existing `TTL_*` block.
- **Provider fallback:** follow `prices.py` — try preferred, `except` → next, log which provider served the row in provenance.
- **New table vs kv:** add a table + upsert helper in `store.py` only if you'll query across rows (e.g. insider transactions you want to aggregate); otherwise `kv_put`/`kv_get` a JSON blob keyed like `f"damodaran:wacc:{sector}"`.
- **Skill exposure:** each new capability gets a skill folder (`SKILL.md` frontmatter `name/version/description` + `run.py` calling `skillkit.run(main, parser)`, emitting the standard JSON envelope with a `summary`). Keep skills lean; heavy parsing lives in the `imdata` module.
- **Rate limits:** document the source's limit in the module docstring; add `time.sleep()` in loops; rely on cache for the rest.
- **requirements.txt:** add only what's needed, pinned, lazy-imported inside functions (as `estimates.py` imports yfinance lazily): `fredapi`, `edgartools`, `finvizfinance`, `pandas_datareader`, `wbgapi`, `pandasdmx`, `praw`, `pytrends`, `duckdb`. Mark which are heavier deps.
- **Tests:** add a smoke test per new module under the relevant `systems/*/tests/` or a shared `tests/` that asserts the fetch returns the right shape and that a forced cache hit avoids the network. Keep them keyless where possible so CI runs offline.
- **Provenance:** every fetcher returns its `source` + `tier`; orchestrators must surface these so client deliverables can footnote sourcing and `IM_COMMERCIAL_MODE` can filter.

## 5. Per-system wiring (which shared fetchers each system selects)

- **01 Due Diligence** → edgar(XBRL) · prices · macro(FRED) · segments · forms(S-1/Form D) · valinputs(Macrotrends).
- **02 Idea Sourcing** → universe(Finviz) · edgar(XBRL, 8-K RSS) · prices · ownership(13F, short interest) · estimates · fmp(dev) · macro(FRED).
- **03 Governance Audit** → edgar(DEF 14A) · ownership(Form 4, 13D/G) · sanctions(primary lists) · XBRL pay-ratio.
- **04 Portfolio Monitoring** → prices · estimates(ownership/short) · macro(FRED rates) · volatility(VIX) · macro(CFTC COT) · news.
- **05 Reporting** → consumes upstream; pulls only shared (XBRL · prices · macro · valinputs · estimates).
- **06 Valuation** → edgar(XBRL) · prices · macro(Treasury/FRED risk-free) · **valinputs(Damodaran WACC/beta/ERP)** · estimates(forward FCF) · segments.
- **07 Filing Intelligence** → edgar(EFTS, RSS, filing text) · edgar transcripts(8-K EX-99.1).
- **Orchestration/all** → store cache (SQLite + DuckDB/Parquet for bulk) · router (Claude Code model step per the other handoff).

## 6. Phased rollout (max value first, aligned to the audit gaps)

1. **Valuation inputs (public, fixes #4):** `valinputs.py` Damodaran + `macro.py` Treasury/FRED risk-free → kill the hardcoded 9% WACC. Wire into valuation + scenario skills.
2. **Forward + commentary (fixes #3):** confirm `estimates.py` is wired into memos/valuation; add `edgar.find_transcript()` for 8-K EX-99.1 → earnings-call-summarizer on real transcripts; add `segments.py`.
3. **Macro context (public):** finish `macro.py` (FRED series, CFTC, World Bank) → portfolio + reporting overlays.
4. **Governance + idea-sourcing primary data (public):** `ownership.py` (Form 4, 13D/G, 13F, FINRA short) + `sanctions.py` (primary lists) → unblocks the two scaffolded systems.
5. **Keyed/eval upgrades (dev-only, gated):** `fmp.py`, NewsAPI/GNews in `news.py`, Polygon/Alpha Vantage in `prices.py`, OpenSanctions branch — all behind `requires_key` + `IM_COMMERCIAL_MODE`.
6. **Alt-data overlays (lowest priority):** `altdata.py` (Reddit, pytrends) as sentiment overlays, never decision-grade.

## 7. Acceptance criteria

- Every new source is reachable only through an `imdata` module, cached, and degrades to empty/None on failure (no new crash paths).
- `imdata/sources.py` registry exists; each fetcher reports `source`+`tier`; `IM_COMMERCIAL_MODE=1` produces a run that touches only `public`-tier sources and still completes.
- Valuation's WACC is derived from Damodaran/Treasury, not the 9% constant; a memo can footnote its data sources from provenance.
- New deps are pinned in `requirements.txt`, lazy-imported; new env keys are in `.env.example`; each new module has a keyless-capable smoke test.
- No source from the Avenoth file is missing from either an `imdata` module or `sources.py` (even if only stubbed with its tier) — coverage is complete, gating is explicit.

---
*Out of scope here (covered in `CLAUDE-CODE-handoff.md`): the model-routing fix (Claude Code on the Max plan) and the synthesis/templating fixes. This guide is the data layer only — but step 1–2 above directly feed those quality fixes.*
