# Idea-Sourcing Stress Tests — for Claude Code

**Audience:** Claude Code working in `AI Investment Architectures/`.
**Companion to:** `CLAUDE-CODE-testing-guide.md` (the 6-layer pyramid, env switches, seeded-cache fixture).
**Scope:** the idea-sourcing system only — `systems/idea-sourcing/orchestrator.py` and the skills/data it fans out to (`universe-screener`, `fundamentals-fetcher`, `catalyst-flagger`, `news-fetcher`, `dcf-valuation`, `comps-builder`, and the shared `imdata` layer).

## Goal

Source *any* company — every industry, every size band, US and foreign, clean and messy filers — and prove the screen→enrich→rank pipeline returns the right names with sane, honestly-flagged numbers. Each test below is a mandate to run plus a pass criterion. Run them, record results in the triage table (Appendix C), fix the root cause, re-run.

This suite deliberately targets the failure classes already found in testing: a sector screen that returned **zero**, a market cap **10× too low** (Coca-Cola Consolidated, split/share mismatch), names **silently dropped** when share-count lookup failed (Boston Beer dual-class, Molson Coors), and DCF/comps that **returned nulls** on dual-class and newly-merged names. The current code claims to fix all four (snapshot screen, `_market_cap` vendor cross-check at >3× disagreement, dual-class share summing, graceful nulls). **These tests verify those fixes hold and push into the next layer of edge cases.**

---

## How to run

Shorthands used in every command below:

```bash
ORCH=".venv/bin/python systems/idea-sourcing/orchestrator.py"
SCR=".venv/bin/python skills-library/research/universe-screener/run.py"
# warms the company_metrics snapshot. `imdata` lives in the shared layer and isn't
# installed as a package, so put it on the path (the repo guides show the bare
# `python -m imdata.screener` but it only resolves from the data-fetch dir):
SNAP="PYTHONPATH=skills-library/_shared/data-fetch .venv/bin/python -m imdata.screener"
```

> Note: `$SCR` and `$ORCH` set their own `sys.path` internally, so they run from the repo root as-is. Only `$SNAP` needs the `PYTHONPATH` prefix above (or `cd skills-library/_shared/data-fetch` first). Because of the env-var prefix, invoke `$SNAP` via `env`/`bash -c` or just paste the full command rather than relying on shell variable expansion.

Run modes:

- **Deterministic core (Layers 1–2)** — run `$SCR` and the leaf skills directly; assert numbers/shape. No model, no live network when run on a seeded cache (Appendix A).
- **System smoke (Layer 3)** — run `$ORCH` keyless with `IM_ALLOW_DEGRADED=1` so qwen narrates the single ranking step. Assert *structural* fields, not prose.
- **Always isolate the cache.** Point `TOOLBOX_DB_PATH` and `TOOLBOX_CACHE_DIR` at a fresh tempdir per test (the `tests/data_sources_test.py` / `tests/screener_snapshot_test.py` pattern) so a test never pollutes the dev cache.

Warm the snapshot before any live sector/size screen (otherwise you test a cold-cache path):

```bash
$SNAP --refresh --max-names 1500     # repeat to page coverage through the universe
$SNAP                                  # prints snapshot_coverage / universe counts
```

### Pass-criterion types (use the one named per test)

- **[assert]** — a hard, deterministic invariant. Must pass every run. Build it offline on the seeded cache where possible.
- **[golden]** — a pinned value (e.g. a specific market cap). Don't invent the number: **capture-and-lock** (Appendix B) — record the live value on a trusted first run into `tests/fixtures/`, then assert future runs stay within tolerance. Refresh deliberately, not on every run.
- **[diagnostic]** — no hard pass/fail; emit the observation for human review. Used where the *correct* behavior is still a product decision (e.g. how to treat foreign issuers) or where recall is a judgment call (sector-term coverage).

For network-dependent reads, follow the repo rule: deterministic logic is **hard**, a live fetch is **soft** (a transient `None` must not fail the build).

---

## A. Sector / industry coverage

The screen matches a **substring of the SIC description** (`--sic-contains`) or an exact SIC code (`--sic`). The risk is **recall**: SIC descriptions are idiosyncratic ("national commercial banks", "pharmaceutical preparations", "semiconductors & related devices", "real estate investment trusts"), so an intuitive sector word can silently miss most of a sector. One test per major sector, plus taxonomy edge cases.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| SEC-01 | `$SCR --sic-contains software --min-mcap 2e9 --max-mcap 1e10` | tech/software recall | **[assert]** ≥3 matches; every `sic_description` contains "software"/"computer". **[diagnostic]** spot-check a few known mid-cap software names are present. |
| SEC-02 | `$SCR --sic-contains semiconductor --min-mcap 2e9 --max-mcap 5e11` | semis | **[assert]** ≥3 matches, all sector-consistent. |
| SEC-03 | `$SCR --sic-contains bank --min-mcap 2e9 --max-mcap 5e10` | financials/banks | **[diagnostic]** does "bank" catch national + state commercial banks *and* savings institutions/thrifts? Record what SIC descriptions appear vs. what's missed. |
| SEC-04 | `$SCR --sic-contains insurance --min-mcap 2e9 --max-mcap 1e11` | insurers | **[assert]** ≥3, sector-consistent. |
| SEC-05 | `$SCR --sic-contains pharmaceutical` then `$SCR --sic-contains biological` | pharma vs. biotech taxonomy | **[diagnostic]** compare the two result sets — "biotech" as a word is not a SIC description; confirm whether biotech names hide under "pharmaceutical preparations" / "biological products" / "commercial physical & biological research". Document the canonical terms. |
| SEC-06 | `$SCR --sic-contains "crude petroleum"` and `$SCR --sic-contains oil` | energy / oil & gas | **[diagnostic]** which term has better recall; note overlap with "oil & gas field services". |
| SEC-07 | `$SCR --sic-contains electric --min-mcap 2e9 --max-mcap 1e11` | utilities | **[assert]** ≥3, sector-consistent. |
| SEC-08 | `$SCR --sic-contains "real estate" --min-mcap 2e9 --max-mcap 5e10` | REITs / real estate | **[diagnostic]** are REITs (SIC 6798 "real estate investment trusts") captured by "real estate"? Confirm. |
| SEC-09 | `$SCR --sic-contains retail --min-mcap 2e9 --max-mcap 5e10` | consumer/retail | **[assert]** ≥3, sector-consistent. |
| SEC-10 | `$SCR --sic-contains machinery --min-mcap 2e9 --max-mcap 5e10` | industrials | **[assert]** ≥3, sector-consistent. |
| SEC-11 | `$SCR --sic-contains aircraft` | aerospace/defense | **[assert]** ≥1, sector-consistent. |
| SEC-12 | `$SCR --sic-contains gold` / `--sic-contains mining` | materials/mining | **[diagnostic]** recall across metal mining SICs. |
| SEC-13 | `$SCR --sic-contains telephone` | telecom | **[assert]** ≥1, sector-consistent. |
| SEC-14 | `$SCR --sic 2834 --min-mcap 2e9 --max-mcap 1e12` | exact SIC code path | **[assert]** every match has `sic == 2834`. |
| SEC-15 | `$SCR --sic-contains zzznotasector` | empty-sector handling | **[assert]** `count == 0`, clean summary, exit 0, no traceback. |
| SEC-16 | run SEC-01..SEC-13, tally matches per term | cross-sector recall map | **[diagnostic]** build a "sector word → SIC descriptions hit / count" table; flag any sector where an obvious word returns 0 or misses a known sub-industry. Output: a canonical sector→term mapping the orchestrator/docs should adopt (or a synonym layer). |

**Likely fix if these surface gaps:** add a sector→SIC-code/synonym map (so "biotech", "REIT", "defense", "thrift" resolve to the right SIC set) rather than relying on raw description substrings.

---

## B. Size bands

Market cap = the snapshot's `market_cap`. The band filter must be correct at every size, order results largest-first, and never let a `null` cap satisfy a band.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| SIZE-01 | `$SCR --min-mcap 2e11` | mega-cap | **[assert]** every match cap ≥ 200B. **[diagnostic]** mega names (AAPL/MSFT/NVDA-class) present. |
| SIZE-02 | `$SCR --min-mcap 1e10 --max-mcap 2e11` | large-cap | **[assert]** every match 10B ≤ cap ≤ 200B. |
| SIZE-03 | `$SCR --min-mcap 2e9 --max-mcap 1e10` | mid-cap (the original bug) | **[assert]** ≥5 matches; every cap in band; `truncated == False` on the snapshot path. |
| SIZE-04 | `$SCR --min-mcap 3e8 --max-mcap 2e9` | small-cap | **[assert]** every match in band. |
| SIZE-05 | `$SCR --max-mcap 3e8` | micro-cap | **[assert]** every match cap ≤ 300M. |
| SIZE-06 | seeded: name at exactly 2e9 with `--min-mcap 2e9` | inclusive boundary | **[assert]** boundary name included (filter is `< min` excludes, so `== min` is kept); document the convention. |
| SIZE-07 | `$SCR --min-mcap 1e10 --max-mcap 2e9` | inverted band | **[assert]** `count == 0`, no crash. |
| SIZE-08 | `$SCR --min-mcap 0 --max-mcap 1e10` | falsy-zero floor | **[assert]** confirm whether `--min-mcap 0` is treated as "no floor" (current `if args.min_mcap` makes `0` falsy). Document; if unintended, fix to `is not None`. |
| SIZE-09 | `$SCR --sic-contains beverage --min-mcap 2e9 --max-mcap 1e10` | size order | **[assert]** results sorted by market cap descending. |
| SIZE-10 | seeded universe with a `null`-cap name in-sector | null exclusion | **[assert]** null-cap name never appears in any banded result (extends `screener_snapshot_test.py`). |
| SIZE-11 | SIZE-03 results | band membership truth-check | **[golden]** capture each returned name's true cap (vendor) and lock; assert all stay within band ±5% on re-run. |

---

## C. Market-cap / share-count accuracy

The bug class that motivated this suite. `imdata/screener.py::_market_cap` cross-checks SEC `shares×price` against the vendor market cap and prefers the vendor when they disagree by >3× (`_MCAP_DISAGREE`); `_latest_shares` sums share classes reported in the same period (dual-class). Verify both, and the `estimates.data_quality` flags.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| MCAP-01 | `$SNAP --tickers COKE` then inspect its metrics row | split / share-price mismatch (the 10× bug) | **[golden]** COKE market cap within ±15% of true (~tens of $B, not ~$1B). **[assert]** when SEC vs vendor disagree >3×, row `source == "vendor"` and `note` explains the mismatch. |
| MCAP-02 | `$SNAP --tickers SAM` | dual-class (A+B) summing | **[assert]** market cap is non-null and order-of-magnitude correct (~$2B-class, not 10× off); `source` in {sec, vendor}. **[assert]** SAM appears when screened in a band containing its true cap. |
| MCAP-03 | `$SNAP --tickers GOOGL GOOG` | dual-class mega, double-count risk | **[assert]** neither is ~2× a sane total; caps internally consistent. |
| MCAP-04 | `$SNAP --tickers BRK.B BF.B LEN.B` | dotted dual-class tickers | **[assert]** ticker parsing works (dot not mangled); caps non-null and sane. |
| MCAP-05 | `$SNAP --tickers PRMB` | recent merger (Primo Water + BlueTriton) | **[assert]** market cap present and sane even though DCF later fails on FCF history. |
| MCAP-06 | `$SNAP --tickers <a 2025 IPO>` | thin share/price history | **[assert]** returns a value or `(None,'none',reason)` — never a crash, never a silent drop. |
| MCAP-07 | `$ORCH --ticker-in COKE SAM PRMB --max-candidates 3` (keyless) | flag propagation | **[assert]** any name with a mismatch produces non-empty `candidate.data_flags`, and those flags appear in `report.risks`. |
| MCAP-08 | `$SNAP --tickers TSM BABA ASML` | non-USD quote | **[assert]** `data_quality` emits a "non-USD … FX not applied" flag; **[diagnostic]** is the resulting market cap usable or should it be suppressed until FX is applied? |
| MCAP-09 | a name where Yahoo and Stooq diverge | independent corroboration | **[diagnostic/soft]** `data_quality` raises the "not corroborated by independent feed" flag when feeds disagree. |
| MCAP-10 | re-run MCAP-01..03 twice on a warm snapshot | stability | **[assert]** market caps stable run-to-run (no random source flapping). |

**Likely fix if these surface gaps:** apply FX conversion for non-USD quotes (or suppress + flag the cap), and add a unit test on `_market_cap` with synthetic SEC/vendor pairs covering agree / >3× disagree / SEC-missing.

---

## D. Valuation & business-model edge cases

DCF (single-stage FCF) and EV/EBITDA comps are inappropriate for some business models. The orchestrator already warns the ranking model that `dcf_upside` is unreliable for hyper-growth, but the *numbers* themselves can be misleading for financials/REITs. Test that the pipeline degrades honestly (nulls/flags) rather than emitting a confident wrong number.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| VAL-01 | `$ORCH --ticker-in <mid-cap bank> --max-candidates 1` | bank: EV/EBITDA meaningless | **[diagnostic]** does comps emit an EV/EBITDA for a bank? It shouldn't be treated as "cheap/rich". Expected target: skip EV/EBITDA for SIC 60xx and use P/B or P/E, or attach a "metric N/A for financials" caveat. |
| VAL-02 | `$ORCH --ticker-in <mid-cap insurer> --max-candidates 1` | insurer | **[diagnostic]** same as VAL-01. |
| VAL-03 | `$ORCH --ticker-in <equity REIT> --max-candidates 1` | REIT: DCF/EPS inappropriate (FFO) | **[diagnostic]** `dcf_upside` and `pe` are misleading for a REIT; confirm they're flagged or suppressed rather than ranked on. |
| VAL-04 | `$ORCH --ticker-in <pre-profit biotech> --max-candidates 1` | negative earnings | **[assert]** `pe` null/negative is handled (no crash); ranking still produces a row; thesis doesn't call a negative P/E "cheap". |
| VAL-05 | seeded comps row with negative EBITDA | negative EBITDA | **[assert]** `ev_ebitda` for a negative-EBITDA name is null or not presented as a low ("cheap") multiple. |
| VAL-06 | `$ORCH --ticker-in PRMB --max-candidates 1` | no derivable base FCF | **[assert]** `dcf_upside == null` returned gracefully; pipeline completes; name still ranked with a "DCF n/a" note. |
| VAL-07 | `$ORCH --ticker-in CELH --max-candidates 1` | hyper-growth deep-negative DCF | **[assert]** `dcf_upside` present (negative ok); **[diagnostic]** ranking/verdict not driven solely to "pass" by the DCF (the relative/PEG/growth guidance should dominate). |
| VAL-08 | comps over a mixed set (bank + software + REIT) | median robustness | **[assert]** `comps_median` is computed over finite values only (Nones ignored), not skewed/NaN. |
| VAL-09 | `$ORCH --ticker-in <conglomerate/holdco> --max-candidates 1` | mixed-segment business | **[diagnostic]** fundamentals/comps sane; note any segment-driven distortion. |
| VAL-10 | `$ORCH --ticker-in <non-Dec fiscal-year name> --max-candidates 1` | off-calendar fiscal year | **[assert]** fundamentals pick the correct latest annual period (not a stale/partial one). |

**Likely fix if these surface gaps:** a business-model-aware comps/DCF selector keyed on SIC (financials → P/B + P/E, no EV/EBITDA; REITs → P/FFO, no FCF-DCF), and a `valuation_method` field on each candidate so the report states which lens was used.

---

## E. Geography & currency

The universe is SEC filers, which **includes foreign private issuers** (20-F filers) and ADRs. There is currently **no country/geography filter** on the screen. A "US-based" mandate therefore can't be expressed today — a real gap to surface and close.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| GEO-01 | `$SCR --sic-contains semiconductor --min-mcap 2e10 --max-mcap 1e12` | foreign issuers leak into a "US" screen | **[diagnostic]** are ADRs (e.g. TSM, ASML) returned? With no country filter they will be. Decide & implement a `--country US` / `--us-only` flag (filter on EDGAR business-address state / country of incorporation). |
| GEO-02 | `$ORCH --ticker-in TSM BABA ASML SAP --max-candidates 4` | ADR enrichment | **[assert]** non-USD quotes flagged by `data_quality`; **[diagnostic]** market caps either FX-correct or suppressed-and-flagged, never silently wrong. |
| GEO-03 | `$ORCH --ticker-in <a 20-F filer> --max-candidates 1` | 20-F vs 10-K fundamentals | **[diagnostic]** does `fundamentals-fetcher` resolve revenue/income for a 20-F filer, or only 10-K filers? Document coverage. |
| GEO-04 | after `--us-only` exists: `$SCR --sic-contains semiconductor --us-only` | regression once built | **[assert]** known foreign ADRs excluded; known US names retained. |

**Likely fix:** add a country/incorporation filter sourced from EDGAR `company_meta` (state/country) into the snapshot row and the screener; apply FX from a keyless rate for non-USD quotes used in valuation.

---

## F. Robustness, scale & error handling

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| ROB-01 | `$ORCH --ticker-in XXXX --max-candidates 1` | invalid ticker | **[assert]** no crash; name skipped or returned empty with a clear note; exit 0. |
| ROB-02 | `$ORCH --ticker-in <recently delisted> --max-candidates 1` | delisted name | **[assert]** graceful (no traceback). |
| ROB-03 | `$SCR --min-mcap 1e13` | impossible band → empty | **[assert]** `count == 0`, clean summary, exit 0. |
| ROB-04 | `$ORCH` (no flags) | missing mandate | **[assert]** raises the documented `ValueError("Provide a mandate…")`. |
| ROB-05 | `$ORCH --ticker-in <50 mixed tickers> --max-candidates 50` | scale / partial failure | **[assert]** completes; a single name's fetch failure doesn't abort the run; all names attempted. **[diagnostic]** wall-clock + any rate-limit warnings. |
| ROB-06 | `$ORCH --ticker-in msft MSFT  msft --max-candidates 3` | case/dupe/whitespace | **[assert]** normalized & deduped (no duplicate rows, no empty-string ticker). |
| ROB-07 | empty snapshot, then `$SCR --sic-contains beverage --min-mcap 2e9 --max-mcap 1e10` | cold snapshot | **[assert]** triggers a bounded warm; `snapshot_coverage` reported (partial coverage disclosed); does **not** silently return only the largest names. |
| ROB-08 | warm snapshot to a small `--max-names`, then screen a band whose member you know is *not yet* warmed | coverage completeness (false negatives) | **[assert/diagnostic]** the un-warmed in-band name is currently missed; the result must *disclose* partial coverage so a miss isn't read as "no such name". Fix target: full-universe warm or a live fallback for snapshot misses. |
| ROB-09 | `$SCR --sic-contains beverage --min-mcap 2e9 --max-mcap 1e10 --no-snapshot` | live path | **[assert]** still returns matches; `truncated == True` only when base set > `--max-fetch` with an expensive filter. |
| ROB-10 | ROB-05 with SEC RPS instrumented | rate-limit discipline | **[diagnostic]** stays under `config.SEC_MAX_RPS`; backoff on 429s. |
| ROB-11 | every test | cache isolation | **[assert]** `TOOLBOX_DB_PATH`/`TOOLBOX_CACHE_DIR` point to a tempdir; dev cache untouched after the suite. |

---

## G. Ranking & output contract (deterministic, keyless)

Run with `IM_ALLOW_DEGRADED=1` so qwen handles the one ranking step; assert structure and the deterministic backfill/attachment logic, not prose.

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| RANK-01 | `$ORCH --ticker-in COKE FIZZ CELH PRMB SAM --max-candidates 5` | every name represented | **[assert]** `len(shortlist) == len(candidates)`; the model-dropped names are backfilled. |
| RANK-02 | same run | rank integrity | **[assert]** ranks are unique and contiguous `1..n`. |
| RANK-03 | same run | verdict enum | **[assert]** every `verdict ∈ {pursue, watch, pass}`. |
| RANK-04 | run incl. a null-DCF name (PRMB/SAM) | null tolerance | **[assert]** null `dcf_upside`/`ev_ebitda` don't drop the row or crash ranking. |
| RANK-05 | run incl. a flagged name (COKE) | flag→risk wiring | **[assert]** `data_flags` non-empty propagates into `report.risks` and the BLUF data-quality note. |
| RANK-06 | same run | report envelope | **[assert]** `report` has `bluf`, `assumptions`/funnel, `provenance`, `commentary`, `risks`, `falsifiers`. |
| RANK-07 | run the same seeded mandate twice | determinism | **[assert]** identical candidate set & order both runs (the ranking prose may vary; the sourced names must not). |
| RANK-08 | same run | advice disclaimer | **[assert]** classification/BLUF states "not investment advice" / "prototype screen". |
| RANK-09 | same run | numbers on rows | **[assert]** each shortlist row carries `dcf_upside, ev_ebitda, pe, ps, current_price, market_cap` (for the table/PDF), filled from the candidate. |
| RANK-10 | `$ORCH --sic-contains beverage --min-mcap 2e9 --max-mcap 1e10 --theme "value" --max-candidates 5` | theme tilt | **[diagnostic/soft]** theses reference the value tilt. |

---

## H. Catalysts & news (soft / network)

| ID | Command | Stresses | Criterion |
|----|---------|----------|-----------|
| CAT-01 | `$ORCH --ticker-in <active 8-K filer> --max-candidates 1` | filings detected | **[soft]** `catalyst_signals.filings > 0` when filings exist. |
| CAT-02 | `$ORCH --ticker-in <quiet small-cap> --max-candidates 1` | no-news graceful | **[assert]** empty headlines/catalysts list, no crash. |
| CAT-03 | same as CAT-01 | catalyst object shape | **[assert]** `catalysts` entries are objects with `type/date/confidence/rationale`, not bare counts. |
| CAT-04 | CAT-01 run | insider signal | **[soft]** `insider_signal` present or `None` (no crash). |
| CAT-05 | CAT-01 run | consensus | **[soft]** `target_mean`/`recommendation` present or `None`. |

---

## Appendix A — Synthetic seed universe (offline determinism)

Extend `tests/screener_snapshot_test.py`'s `UNIVERSE` so the deterministic Layer-1 tests cover every sector, size band, and edge case **without the network**. Seed both `companies` and `company_metrics`, then assert the band/sector filters over the whole synthetic universe. Add a new file `tests/screener_coverage_test.py` modeled on the existing one:

```python
# ticker -> (title, sic_description, market_cap, currency)
UNIVERSE = {
    # --- size bands, one clean sector (software) ---
    "MEGA":  ("Mega Soft",      "prepackaged software",            3.0e11, "USD"),
    "LARGE": ("Large Soft",     "prepackaged software",            5.0e10, "USD"),
    "MID":   ("Mid Soft",       "prepackaged software",            6.0e9,  "USD"),
    "SMALL": ("Small Soft",     "prepackaged software",            1.0e9,  "USD"),
    "MICRO": ("Micro Soft Co",  "prepackaged software",            2.0e8,  "USD"),
    "EDGE":  ("Edge Soft",      "prepackaged software",            2.0e9,  "USD"),  # exactly at 2e9 floor
    "NOCAP": ("No Cap Soft",    "prepackaged software",            None,   "USD"),  # null cap never matches a band
    # --- sector coverage (all mid-cap, in-band) ---
    "BANK":  ("Midcap Bank",    "national commercial banks",       6.0e9,  "USD"),
    "INSUR": ("Midcap Insurer", "fire, marine & casualty insurance",6.0e9, "USD"),
    "PHARM": ("Midcap Pharma",  "pharmaceutical preparations",     6.0e9,  "USD"),
    "BIOTC": ("Midcap Biotech", "biological products",             6.0e9,  "USD"),
    "OILGS": ("Midcap Oil",     "crude petroleum & natural gas",   6.0e9,  "USD"),
    "UTIL":  ("Midcap Utility", "electric services",               6.0e9,  "USD"),
    "REIT":  ("Midcap REIT",    "real estate investment trusts",   6.0e9,  "USD"),
    "RETL":  ("Midcap Retail",  "retail stores, nec",              6.0e9,  "USD"),
    "INDST": ("Midcap Machine", "industrial machinery & equipment",6.0e9,  "USD"),
    "MINE":  ("Midcap Miner",   "gold mining",                     6.0e9,  "USD"),
    # --- edge cases ---
    "FORGN": ("Foreign ADR",    "semiconductors & related devices",6.0e9,  "EUR"),  # non-USD: should be flagged / filtered by --us-only
    "NEGEB": ("Negative EBITDA","prepackaged software",            6.0e9,  "USD"),  # pair with a comps fixture: ev_ebitda<0 not "cheap"
}
```

Assertions to add (all **[assert]**, no network, no model):

- Each size band (`SIZE-01..05`) returns exactly the expected synthetic tickers.
- `EDGE` (cap == `min_mcap`) is included; `NOCAP` is excluded from every band.
- `--sic-contains bank|insurance|pharmaceutical|biological|"real estate"|electric` each return their one synthetic name and **exclude** the others (sector isolation).
- A "biotech" word search returns `BIOTC` only if a synonym map exists — otherwise document the miss (this is the SEC-05/SEC-16 finding in deterministic form).
- `FORGN` is returned by a sector screen today (no country filter) and excluded once `--us-only` lands (GEO-01/GEO-04 regression).

Pair a small synthetic **comps** fixture (negative-EBITDA and negative-EPS rows) for VAL-05/VAL-08 so median robustness is tested offline.

## Appendix B — Golden values: capture-and-lock

Never hand-write expected numbers. Procedure for every **[golden]** test:

1. On a trusted run (network up, sane output), record the live value into `tests/fixtures/golden_idea_sourcing.json` with the ticker, field, value, and `captured_at` date.
2. The test asserts the current run is within tolerance of the locked value (suggested: market cap ±15%, band membership exact, share count ±2%).
3. Refresh the lock **deliberately** (a dated commit) when a real corporate action (split, buyback, raise) moves the true value — not automatically.
4. Keep the committed **fixture cache** (`tests/fixtures/cache.db`, per the testing guide) covering MSFT, AAPL, KO, COKE, SAM, PRMB, one REIT, one bank, one ADR so Layers 1–4 run offline and identically.

## Appendix C — Results triage template

Record every run here (or as `tests/idea_sourcing_stress_results.md`). Fix root causes, not symptoms; re-run until green.

| Test ID | Status (pass/fail/diag) | Observed | Suspected root cause | File to fix | Fix / PR | Re-run |
|---------|------------------------|----------|----------------------|-------------|----------|--------|
| SEC-05  |                        |          |                      | `universe-screener/run.py` / sector map |          |        |
| MCAP-08 |                        |          |                      | `imdata/estimates.py`, `imdata/screener.py` |     |        |
| VAL-01  |                        |          |                      | `valuation/comps-builder`, `dcf-valuation` |      |        |
| GEO-01  |                        |          |                      | `imdata/screener.py` (+ snapshot row), screener flags | |    |
| ROB-08  |                        |          |                      | `imdata/screener.py` warm/coverage path |        |        |

## Appendix D — Hypothesized gap → fix map

Where the suite is most likely to bite, and where to look first:

- **Sector recall (SEC-03/05/06/08/12/16)** → SIC-description substring is lossy. Add a sector→SIC-code synonym map; expose canonical sector names.
- **Foreign issuers / FX (GEO-01/02, MCAP-08)** → no country filter; non-USD caps flagged but not converted. Add `--us-only` (EDGAR state/country) and FX conversion (or suppress non-USD caps).
- **Business-model valuation (VAL-01/02/03)** → EV/EBITDA & FCF-DCF emitted for banks/insurers/REITs. Add a SIC-keyed valuation-method selector (P/B, P/E, P/FFO) and a `valuation_method` field.
- **Snapshot coverage (ROB-07/08)** → results depend on what's been warmed; an un-warmed name reads as "doesn't exist". Ensure full-universe warm or a live fallback for misses, and always disclose coverage.
- **Falsy-zero band (SIZE-08)** → `if args.min_mcap` treats `0` as no-floor. Switch to explicit `is not None` if `0` should be a real floor.
- **Confirm the already-claimed fixes hold (MCAP-01/02/03, SIZE-03)** → these are regressions guarding the COKE 10× / dual-class / mid-cap-screen bugs; keep them in the every-commit set.

---

*Run order suggestion:* the deterministic core (Appendix A synthetic tests + SIZE + SEC-14/15 + RANK on a seeded cache) on every change, free and offline; the live `$SNAP`-warmed sector/size/MCAP/GEO/VAL screens before commit; the soft catalyst/consensus checks and the paid ranking rung deliberately and rarely.
