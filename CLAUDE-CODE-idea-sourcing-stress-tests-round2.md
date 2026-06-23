# Idea-Sourcing Stress Tests — Round 2 (regression-hardening)

**Audience:** Claude Code working in `AI Investment Architectures/`.
**Builds on:** `CLAUDE-CODE-idea-sourcing-stress-tests.md` (round 1) and its results in `tests/idea_sourcing_stress_results.md` (10 bugs fixed). **Conventions:** `CLAUDE-CODE-testing-guide.md`.
**Scope:** the *new* code paths introduced by round 1's fixes, plus the limitations left open.

## Premise

Round 1 found broad-category bugs. Fixing them added new logic — and new logic has new failure modes. The proof is already in your own results: the **dual-class summing** fix *created* the COKE duplicate-summing bug. Round 2 assumes every fix is a fresh suspect.

The current fix for that very bug — summing the **set of distinct share values** in the newest period — has a new failure mode of its own:

> **Two real share classes with identical counts collapse into one and undercount by 50%.** `{50M, 50M}` → `{50M}` → 50M, not 100M. And **near-duplicate facts** (the same class reported as `7,140,000` and `7,140,001` across two accessions) are *not* equal, so both survive → ~2× overcount.

That single observation is the spine of Bucket A. Most of Round 2 is **offline and deterministic** (pure functions + stubbed `get_concept`/`company_meta` + a seeded snapshot) — keeping with the testing guide's "models and network out of the fast loop."

### Code under test (verified symbols / paths)

| What | Where |
|------|-------|
| `_latest_shares` (distinct-set sum) | `imdata/screener.py` |
| `reconcile_mcap` (+ alias `_reconcile_mcap`), `_MCAP_DISAGREE = 3.0` | `imdata/screener.py` |
| `refresh_metrics` (`skipped_unknown`, country annotate) | `imdata/screener.py` |
| `SECTOR_SYNONYMS`, `_sic_match`, `_passes` (`is not None`, `us_only`) | `research/universe-screener/run.py` |
| `_shares_outstanding` (distinct-set + vendor re-derive), `_valuation_profile` | `valuation/comps-builder/run.py` |
| `_shares_outstanding` | `valuation/dcf-valuation/run.py` |
| `company_by_ticker` (`.`↔`-`), `_METRIC_COLS` incl. `country`, `_migrate` (additive ALTER, **no backfill**) | `imdata/store.py` |
| `company_meta` → `country`, `_US_STATES` | `imdata/edgar.py` |
| `valuation_caveat` → `data_flags` → `report.risks` | `systems/idea-sourcing/orchestrator.py` |

### Pass-criterion types

Same as round 1: **[assert]** hard/deterministic · **[golden]** capture-and-lock a live value · **[diagnostic]** observe, no hard fail · **[xfail]** a *known* limitation encoded as an expected-fail that must flip to a hard assert when fixed (Appendix C). Most Round-2 asserts are **[pure]** — no network, no model.

### Shorthands (as in round 1; isolate the cache per test)

```bash
ORCH=".venv/bin/python systems/idea-sourcing/orchestrator.py"
SCR=".venv/bin/python skills-library/research/universe-screener/run.py"
# pure/seeded tests extend tests/screener_coverage_test.py (already sets TOOLBOX_DB_PATH/CACHE_DIR to a tempdir)
```

`$ORCH` runs keyless with `IM_ALLOW_DEGRADED=1`. The pure/`[pure]` tests need no CLI — import the module and stub its data calls (Appendix A).

---

## Bucket A — Harden the 10 fixes

### A1. Distinct-share summing (the headline regression risk)

Drive the pure functions with a stubbed `get_concept` (Appendix A1 for the harness). Each row is `{"value": <shares>, "period_end": <iso>}`; `get_concept` returns newest-first.

| ID | Input (newest period, one tag) | Stresses | Criterion |
|----|--------------------------------|----------|-----------|
| HARD-01 | Class A `50_000_000`, Class B `50_000_000` (same period) | **identical-count collapse** | **[assert][pure]** `_latest_shares` should return `100_000_000`. **Fails today** (set collapses to `50M`). Mirror in comps & dcf `_shares_outstanding`. |
| HARD-02 | same class: `7_140_000` and `7_140_001` (two accessions, same period) | **near-duplicate overcount** | **[assert][pure]** should return `~7_140_000` (one class). **Fails today** (distinct set keeps both → `14_280_001`). |
| HARD-03 | live: GOOGL (A+C public, B private) | 3-class real name | **[golden]** `_latest_shares` × price reconciles to vendor within 3×; lock the share total. |
| HARD-04 | rows out of order / mixed `period_end` | newest-period selection | **[assert][pure]** picks the max `period_end` (today it trusts `rows[0]`); assert the get_concept newest-first contract, or make selection explicit. |
| HARD-05 | identical-count case through all three copies | **cross-copy consistency** | **[assert][pure]** `screener._latest_shares`, `comps._shares_outstanding`, `dcf._shares_outstanding` return the **same** number for the same input (all wrong together today → all right together after the fix). |

**Root-cause direction to recommend:** dedup by the XBRL **share-class axis** (`StatementClassOfStockAxis` member), not by value. De-duplicating on value is what both undercounts identical classes and fails to collapse near-dupes. If the class dimension isn't surfaced by `get_concept`, dedup by `(period_end, accession)` keeping one fact per class.

### A2. `reconcile_mcap` (pure, shared by snapshot + comps)

See the full boundary table in Appendix A2.

| ID | Case | Criterion |
|----|------|-----------|
| HARD-06 | `(100, 290)` ratio 2.9 vs `(100, 301)` ratio 3.01 | **[assert][pure]** 2.9× → `source=="sec"`; 3.01× → `"vendor"`. Locks the `_MCAP_DISAGREE` boundary. |
| HARD-07 | `(100, 240)` ratio 2.4 — a wrong SEC cap *under* the gate | **[diagnostic]** ships silently as `"sec"`; quantify the max undetected error (~3×). Recommend a tighter gate or third-source tiebreak. This is the residual of the COKE class. |
| HARD-08 | SEC correct, vendor wrong by >3× → `(100_right, 400_wrong)` | **[xfail][pure]** returns `"vendor"` (wrong) — reconcile is direction-blind. Wire `prices.corroborate_price` / independent feed as the tiebreaker; flip to assert when done. |
| HARD-09 | `(0, 200)`, `(100, 0)`, `(None, None)` | **[assert][pure]** → `vendor`, `sec`, `(None,"none",…)`. Zero treated as not-usable. |

### A3. Dotted tickers — end to end, not just the lookup

| ID | Command / call | Criterion |
|----|----------------|-----------|
| HARD-10 | `store.company_by_ticker` on `"BRK.B"`, `"BRK-B"`, `"brk.b"`, `"bf.b"` | **[assert][pure]** all resolve to the canonical hyphen row (seed `companies`). |
| HARD-11 | `$ORCH --ticker-in BRK.B BF.B --max-candidates 2` (keyless) | **[assert/golden]** both get a **non-null** `market_cap` and comps/dcf resolve (canonicalized to `info["ticker"]` before yfinance). BRK.B ~$1T order. |
| HARD-12 | `store.company_by_ticker("A.B.C")`, `""`, `"BRK..B"` | **[assert][pure]** no crash; returns `None` for the bogus forms (single `.`↔`-` swap only). |

### A4. Falsy-zero & routing (`is not None`)

| ID | Command | Criterion |
|----|---------|-----------|
| HARD-13 | `$SCR --min-mcap 0 --max-mcap 0` | **[assert]** matches only a cap of exactly `0` (seed a `ZEROCAP` name); real universe → empty. |
| HARD-14 | `$SCR --max-mcap 0` and `$SCR --us-only` (no band/sector) | **[assert]** each routes through the **expensive/snapshot** path (`wants_expensive` true via `is not None` / `us_only`), not the cheap pass-through. `--max-mcap 0` → empty; `--us-only` → only US rows. |

### A5. `SECTOR_SYNONYMS` / `_sic_match`

| ID | Input descriptions (seed or live) | Criterion |
|----|-----------------------------------|-----------|
| HARD-15 | descs: "aircraft parts & auxiliary equipment", "metal tanks", "guided missiles" with `--sic-contains defense` | **[diagnostic]** "defense" synonyms include `aircraft`/`tank` → **over-matches** commercial aircraft-parts and "metal tanks". Recommend scoping `defense` to SIC codes (3760/3795/348x) instead of substrings. |
| HARD-16 | `--sic-contains telecom` over "cable & other pay television", "communications services, nec" | **[diagnostic]** does `communications services` over-pull? Note the actual synonym **keys** (`oilgas`, not `oil`/`gas`); a user typing `oil` or `gas` gets only a raw substring match. |
| HARD-17 | `--sic-contains` for `energy`, `mining`, `semiconductor`, `fintech`, `media`, `renewable`, `ev`, `consumer` | **[diagnostic]** which still return 0 or partial (unmapped → raw substring). Output the next synonym-map batch. (`semiconductor` is the ASML taxonomy gap — see LIMIT-01.) |

### A6. Country / `--us-only` (incl. the migration trap)

| ID | Case | Criterion |
|----|------|-----------|
| HARD-18 | stub `company_meta`: business `stateOrCountry` ∈ {`CA`, `PR`, `F4`(foreign), missing→`stateOfIncorporation`} | **[assert][pure]** `CA`→`US`, `PR`→`US`, `F4`→`F4` (foreign), missing→fallback, both missing→`None`. |
| HARD-19 | seed a **US** `company_metrics` row with `country = None` (pre-migration row), then `$SCR --us-only` | **[assert]** the US name is **wrongly dropped** today (`(None).upper() != "US"`). **Expected fix:** treat `NULL` country as "unknown" (don't exclude, or trigger a refresh/backfill), not as foreign. High-impact: the additive `_migrate` adds the column but **does not backfill**. |
| HARD-20 | US-HQ foreign issuer (business address = US state, foreign incorporation) and the reverse | **[diagnostic]** business address wins in `company_meta`; document the classification for a redomiciled name (e.g. Bermuda-incorp, US-HQ). |

### A7. `skipped_unknown` & ticker dedupe

| ID | Call | Criterion |
|----|------|-----------|
| HARD-21 | `refresh_metrics(["MSFT","msft","BRK.B","XXXX",""])` | **[assert]** `XXXX`/`""` in `skipped_unknown`; `BRK.B`→`BRK-B` resolved (not skipped); **no null junk rows** in `company_metrics`. **[diagnostic]** `MSFT`+`msft` both resolve to `MSFT` — confirm the refresh **targets** are deduped (the screen `--ticker-in` path dedups; the refresh path may double-fetch). |
| HARD-22 | `$ORCH --ticker-in msft MSFT msft XXXX --max-candidates 5` | **[assert]** one `MSFT` candidate, `XXXX` dropped, no empty-ticker row. |

### A8. Business-model valuation propagation

| ID | Call | Criterion |
|----|------|-----------|
| HARD-23 | `$ORCH --ticker-in <mid-cap bank> --max-candidates 1` (keyless) | **[assert]** candidate `valuation_method=="financial"`, `valuation_caveat` non-empty, present in `data_flags` **and** `report.risks`. |
| HARD-24 | `comps._valuation_profile` on `"6798"`, `"6022"`, `"6311"`, `"6770"`, `"6726"`, `"3674"` | **[assert][pure]** `6798`→`reit`; `60xx/61xx/62xx/63xx`→`financial`; `3674`→`standard`. **[diagnostic]** `6770` (SPAC) and `6726` (BDC/closed-end) → `standard` today → they still get EV/EBITDA. Flag for COMBO-08. |

---

## Bucket B — Track the documented limitations (xfail)

Encode each so it's *measured*, not forgotten; flipping to xpass signals "promote to hard assert." Full registry in Appendix C.

| ID | Limitation | Encoded test | Flip-when |
|----|-----------|--------------|-----------|
| LIMIT-01 | ASML / SIC 3559 not caught by `--sic-contains semiconductor` | **[xfail]** assert ASML absent from a `semiconductor` screen; assert it *is* present once a SIC-code map (35xx/3674 + "semiconductor equipment") exists | a sector→SIC-code map lands |
| LIMIT-02 | FX flagged, not converted | **[xfail]** a non-USD snapshot row carries the `non-USD … FX not applied` note (assert), but its cap is **not** USD-restated (xfail the "cap is USD-correct") | FX conversion wired |
| LIMIT-03 | DCF on financials is meaningless | **[xfail]** `$ORCH --ticker-in BRK-B` returns a DCF number with no hard block; assert the comps `valuation_method=financial` caveat exists as the current guard | a P/B model or DCF-suppress-for-financials lands |
| LIMIT-04 | NL dotted-ticker extraction in `ask.py` | **[xfail]** prompt "value BRK.B" via the `ask.py` path fails to resolve (regex splits on `.`); **[assert]** the skill/`--ticker-in BRK.B` path succeeds — locks the regression boundary | `ask.py` entity extraction handles class tickers |
| LIMIT-05 | Partial snapshot coverage | **[assert]** a sector/`--us-only` screen on a partially-warmed snapshot reports `snapshot_coverage` so a miss reads as "partial coverage," not "no such name" | n/a (disclosure, keep as assert) |

---

## Bucket C — Combinatorial & new dimensions

### C1. Interactions (round 1 tested one axis at a time)

| ID | Case | Criterion |
|----|------|-----------|
| COMBO-01 | dual-class **financial** (bank holdco with A+B) | **[assert][pure]** through `comps.metrics`-style path (stubbed): shares summed (A2 rules), `reconcile_mcap` applied, `valuation_method=="financial"` — all three fire together. |
| COMBO-02 | **foreign × dual-class** ADR | **[assert]** `--us-only` excludes it; non-USD note present; share handling doesn't crash. |
| COMBO-03 | **foreign × financial × synonym**: `$SCR --sic-contains bank --us-only` vs without | **[assert]** a foreign bank (seed `FORBANK`, country≠US) is excluded with `--us-only`, included without (and would carry the financial caveat in comps). |
| COMBO-04 | **synonym × band × us-only**: `$SCR --sic-contains biotech --min-mcap 2e9 --max-mcap 1e10 --us-only` | **[assert]** only US mid-cap `biological products` names; all three gates compose (extend the coverage-test universe). |

### C2. Dimensions round 1 under-reached

| ID | Case | Criterion |
|----|------|-----------|
| COMBO-05 | `$SCR --min-adv 5e6` over seeded `adv` values incl. one low and one `None` | **[assert]** below-threshold and `null`-adv names excluded (mirror null-mcap rule); composes with a band. |
| COMBO-06 | sparse/halted volume history | **[diagnostic]** `_adv_from_history` returns a value from available days or `None`, never a crash. |
| COMBO-07 | off-calendar fiscal year (e.g. a Jan-FYE retailer) | **[diagnostic]** comps/fundamentals pick the correct **latest annual**; `_cagr`/`_annual_series` align on annual periods (no stub-period mix). |
| COMBO-08 | SPAC (`6770`), BDC/closed-end (`6726`), holdco (`671x`) | **[diagnostic]** `_valuation_profile` → `standard` today, so EV/EBITDA is emitted for entities where it's meaningless. Recommend mapping these to a `no-ev-ebitda` profile. |
| COMBO-09 | mixed comp set: bank + software + REIT + biotech | **[assert]** `comps_median` computed over **finite values only**; per-row `valuation_method` set; a financial's missing EV/EBITDA doesn't skew or NaN the median. |
| COMBO-10 | conglomerate / multi-segment | **[diagnostic]** single-line comps distortion noted (segment data is a known future source). |

---

## Bucket D — Cross-path invariants

These lock that the *shared* fixes actually make independent code paths agree.

| ID | Invariant | Criterion |
|----|-----------|-----------|
| XPATH-01 | **snapshot cap ≈ comps cap** for the same ticker (both call `reconcile_mcap`) | **[assert/golden]** for COKE, PNC, BRK-B, SAM the two paths agree within tolerance (allow price-as-of drift, ±10%). Proves the "promote reconcile to shared" fix. |
| XPATH-02 | snapshot vs orchestrator `current_price × shares` | **[diagnostic]** order-of-magnitude consistent where both exist. |
| XPATH-03 | **country migration idempotence + backfill** | **[assert]** running `_migrate` twice → no error, column present once; **[assert]** after migration, pre-existing rows are backfilled or treated as unknown by `--us-only` (ties HARD-19). |
| XPATH-04 | `refresh_metrics` idempotence | **[assert]** warming the same tickers twice → stable `metrics_count`, no duplicate rows, stable values (`INSERT OR REPLACE` keyed on ticker). |
| XPATH-05 | **snapshot vs `--no-snapshot` parity** | **[assert]** same mandate (sector + band + `--us-only`) returns the same set on a fully-warmed snapshot as the live per-name path (modulo `--max-fetch` truncation). The two screen implementations must not diverge. |
| XPATH-06 | determinism | **[assert]** same seeded mandate twice → identical candidate set & order across all new gates (extends round-1 RANK-07). |
| XPATH-07 | caveat chain | **[assert]** multi-financial run → every `valuation_caveat` surfaces in `report.risks`, deduped. |

---

## Appendix A — Pure-function harness & fixtures

### A1. Stub `get_concept` to drive the share-count functions

```python
# offline; no network, no model
import os, sys, tempfile
REPO = "<repo root>"
os.environ["TOOLBOX_CACHE_DIR"] = tempfile.mkdtemp()
os.environ["TOOLBOX_DB_PATH"] = os.path.join(os.environ["TOOLBOX_CACHE_DIR"], "r2.db")
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))
import imdata.screener as sc

def stub(rows):
    def _f(ticker, tag):
        return rows if tag == "EntityCommonStockSharesOutstanding" else []
    return _f

# HARD-01 — identical dual-class counts (FAILS today: returns 50_000_000)
sc.edgar.get_concept = stub([
    {"value": 50_000_000, "period_end": "2025-12-31"},   # Class A
    {"value": 50_000_000, "period_end": "2025-12-31"},   # Class B (separate class)
])
assert sc._latest_shares("X") == 100_000_000

# HARD-02 — near-duplicate same-class facts (FAILS today: returns 14_280_001)
sc.edgar.get_concept = stub([
    {"value": 7_140_000, "period_end": "2025-12-31"},    # accession 1, Class A
    {"value": 7_140_001, "period_end": "2025-12-31"},    # accession 2, same class, off by 1
])
assert sc._latest_shares("X") == 7_140_000
```

Apply the same stub to `comps-builder/run.py::_shares_outstanding` and `dcf-valuation/run.py::_shares_outstanding` (import each `run` module, set its `edgar.get_concept`, and for comps also stub `estimates.get_quote`/`prices.last_price`) to lock **HARD-05** cross-copy consistency.

### A2. `reconcile_mcap` boundary table (extends the 5 cases already in `screener_coverage_test.py`)

| sec_mcap | vendor_mcap | ratio | expected `source` | note |
|---------:|------------:|------:|:------------------|------|
| 100 | 100 | 1.0 | `sec` | agree |
| 100 | 290 | 2.9 | `sec` | **under gate — wrong sec ships silently (HARD-07)** |
| 100 | 301 | 3.01 | `vendor` | over gate |
| 1.3e9 | 12e9 | 9.2 | `vendor` | the COKE case |
| 100 (right) | 400 (wrong) | 4.0 | `vendor` | **direction-blind → wrong (HARD-08, xfail)** |
| 0 | 200 | — | `vendor` | sec not usable |
| 100 | 0 / None | — | `sec` | vendor not usable |
| None | None | — | `none` | `(None,"none","no shares×price and no vendor market cap")` |

### A3. Stub `company_meta` country mapping (HARD-18)

Patch `edgar._sec_json` to return a synthetic submissions blob and assert the `country` derivation: `addresses.business.stateOrCountry` first (`CA`→`US`, `PR`→`US`, `F4`→`F4`), else `stateOfIncorporation`, else `None`.

## Appendix B — Synthetic-universe extensions

Add to the `UNIVERSE` dict in `tests/screener_coverage_test.py` (tuple is `title, sic, sic_desc, market_cap, currency, country`); seed `country` directly into `company_metrics`:

```python
"ZEROCAP": ("Zero Cap Co",   7372, "prepackaged software",            0.0,  "USD", "US"),   # HARD-13
"STALEUS": ("Stale US Co",   7372, "prepackaged software",            6e9,  "USD", None),   # HARD-19 (pre-migration row)
"FORBANK": ("Foreign Bank",  6022, "state commercial banks",          6e9,  "EUR", "F4"),   # COMBO-03
"ADVLO":   ("Thin Trader",   7372, "prepackaged software",            6e9,  "USD", "US"),   # COMBO-05 (seed adv≈1e5)
"ADVNULL": ("No Volume Co",  7372, "prepackaged software",            6e9,  "USD", "US"),   # COMBO-05 (seed adv=None)
"SPACX":   ("Blank Check Co",6770, "blank checks",                    6e9,  "USD", "US"),   # COMBO-08
"BDCX":    ("Midcap BDC",    6726, "investment offices, nec",         6e9,  "USD", "US"),   # COMBO-08
"MREIT":   ("Mortgage REIT", 6798, "real estate investment trusts",   6e9,  "USD", "US"),   # reit profile
```

Note: share-count and `reconcile_mcap` logic is **not** exercised by the snapshot universe (it stores a precomputed `market_cap`). Test those via the pure functions in Appendix A; use this universe for sector/size/country/`--us-only`/ADV composition and the stale-country trap.

## Appendix C — xfail registry & promotion rule

| ID | Owner area | Expected today | Promote to hard assert when |
|----|-----------|----------------|-----------------------------|
| HARD-08 | `reconcile_mcap` | picks vendor even when SEC is right | an independent third source breaks the tie |
| LIMIT-01 | sector map | ASML absent from `semiconductor` | sector→SIC-code map lands |
| LIMIT-02 | FX | non-USD cap not restated | FX conversion wired into the snapshot/comps |
| LIMIT-03 | DCF financials | meaningless DCF returned | P/B model or DCF-suppress-for-financials |
| LIMIT-04 | `ask.py` NL | dotted ticker not extracted | NL entity extraction handles class tickers |

**Rule:** an xfail that starts **passing** (xpass) is itself a failing test — it means the limitation is fixed and the test must be promoted to `[assert]` in the same change.

## Appendix D — Triage template

| Test ID | Status | Observed | Root cause | Fix (file) | **Could this fix introduce…?** | Re-run |
|---------|--------|----------|-----------|-----------|-------------------------------|--------|
| HARD-01 | | | distinct-by-value collapses equal classes | `screener.py` / comps / dcf `_shares_outstanding` | a class-axis dedup that mis-reads single-class names? add HARD-04 | |
| HARD-19 | | | additive migration doesn't backfill `country` | `store._migrate` / `_passes` | NULL-as-US flipping foreign names in? re-check COMBO-03 | |

The new column — **"Could this fix introduce…?"** — is the round-2 lesson made procedural: every fix gets an adversarial test of its *own* new path before it's called done.

## Appendix E — Priority & run order

1. **Fast loop, every change (pure/offline):** HARD-01/02/04/05 (share collapse), HARD-06/09 (reconcile), HARD-13/14 (routing), HARD-15/17 (synonyms), HARD-18 (country), HARD-24 + COMBO-08 (valuation profile), COMBO-04/05 (composition), XPATH-03/04 (migration/idempotence). All extend `tests/screener_coverage_test.py` with no network.
2. **Pre-commit (keyless, seeded/live cache):** HARD-11/21/22/23 (e2e), XPATH-05/06/07, LIMIT-05.
3. **Deliberate / rare:** HARD-03 golden, XPATH-01 golden (snapshot-vs-comps), the live sector recall sweep (HARD-16/17), and the xfail watch (Appendix C) — re-run when the relevant subsystem changes.

*Headline to fix first: **HARD-01** — the identical-count collapse is a live undercount on any dual-class name whose classes happen to match, and it sits on the exact code the last fix touched.*
