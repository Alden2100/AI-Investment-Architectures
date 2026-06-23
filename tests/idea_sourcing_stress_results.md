# Idea-Sourcing Stress-Test Results

Run date: 2026-06-22. Cache isolated per run (`/tmp/stress*`); dev cache untouched.
Deterministic coverage encoded in `tests/screener_coverage_test.py` (29 checks, offline).

## Bugs found & fixed (root cause, not symptom)

| Test ID | Status | Observed | Root cause | Fix |
|---------|--------|----------|------------|-----|
| MCAP-04 | fixed | `BRK.B`/`BF.B`/`LEN.B` resolved to NOT FOUND → silently dropped | SEC universe uses hyphen tickers (`BRK-B`); lookups didn't try `.`↔`-` | `store.company_by_ticker` dot/hyphen fallback; comps/dcf canonicalize to `info["ticker"]` before price/quote feeds |
| MCAP-01 | fixed (regression) | COKE comps cap $6.4B (snapshot ok at $11.9B) | my dual-class summing summed **duplicate** cover-page rows (5×7.14M) → inflated, slipped under the 3× reconcile gate | sum **distinct** class values in `_latest_shares`/`_shares_outstanding` (all 3 copies) → COKE sec $1.28B → reconcile → vendor $11.9B |
| MCAP (PNC) | fixed | bank cap $283B (3× over) carried into comps | comps did plain `price×shares`; the vendor cross-check lived only in the snapshot | promoted `screener.reconcile_mcap` to shared; comps reconciles + re-derives shares from the chosen cap |
| SIZE-08 | fixed | `--max-mcap 0` returned everything; routing wrong for `--min-mcap 0` | `if args.min_mcap` / `any([...])` treat `0` as unset | band/ADV filters and `wants_expensive` use `is not None` |
| SEC-05/16 | fixed | `biotech`/`reit`/`defense`/`thrift` returned 0 (not SIC words) | raw SIC-description substring is lossy | `SECTOR_SYNONYMS` map → match any mapped substring |
| GEO-01/04 | fixed | foreign issuers (TSM/BABA/ASML/SAP) leak into "US" screens; no way to exclude | no country signal on the screen | `country` from EDGAR business address (US-state→`US` else foreign code) on the snapshot row + `--us-only` flag |
| ROB-01/06 | fixed | `msft MSFT msft XXXX` → duplicate rows / junk | `--ticker-in` not deduped/validated | dedupe by canonical ticker, drop unknowns/blanks |
| (snapshot) | fixed | invalid ticker (`NScorp`) stored as a null junk row | `refresh_metrics` didn't validate against the universe | resolve+skip unknown tickers (reports `skipped_unknown`) |
| VAL-01/02/03 | fixed | banks/REITs got EV/EBITDA with no caveat | no business-model awareness | SIC-keyed `valuation_method`/`valuation_caveat` in comps → propagated to candidate `data_flags` and `report.risks` |
| MCAP-08 | fixed | non-USD quotes not surfaced on the snapshot | only `data_quality` flagged it | snapshot row `note` records `non-USD quote; FX not applied` |

## Held (claimed fixes verified)
- MCAP-01/02/03 (COKE 10×, SAM dual-class, GOOGL/GOOG no double-count), SIZE-03 mid-cap screen: all confirmed.
- VAL-04/05/08: negative P/E and negative EBITDA already null (not shown as "cheap"); median ignores None.
- DCF graceful on SAM (dual-class) and PRMB (merged, no clean FCF) — values returned, no crash.

## Known / documented limitations (diagnostic, not fixed)
- ASML (semiconductor equipment, SIC 3559 "special industry machinery") is not caught by `--sic-contains semiconductor` — genuine SEC taxonomy gap; not mapped to avoid over-matching all machinery.
- FX is **flagged but not converted** — non-USD caps are annotated, not restated; US-listed ADRs (TSM/BABA) report USD via the vendor so rarely trigger it.
- DCF on financials (e.g. BRK-B) is meaningless (uses A-share count vs B price); the comps `valuation_method=financial` caveat is the guard rather than a P/B model.
- Dotted tickers in **natural-language** prompts (`ask.py`) still aren't extracted (regex splits on `.`); the skills/`--ticker-in` path is fixed.
- Full-universe snapshot coverage is built by repeated `python -m imdata.screener --refresh`; a partial warm discloses `snapshot_coverage`.

---

# Round 2 — regression-hardening (the fixes' own new failure modes)

Encoded offline in `tests/screener_r2_test.py` (33 pure checks + xfail registry).

| Test | Status | Observed | Root cause | Fix |
|------|--------|----------|------------|-----|
| HARD-01/02 | fixed (regression) | round-1's "sum distinct" overcounts near-dup facts (7.14M/7.14M+1 → 14.28M) and undercounts two equal classes | facts table has **no share-class axis**; its PK collapses same-filing classes, so multiple rows are one class re-reported — summing is wrong in principle | share count = **newest single fact**; dual-class totals come from the vendor reconcile (all 3 copies) |
| HARD-04 | fixed | newest period trusted `rows[0]` | implicit ordering | explicit `max(period_end)` |
| HARD-05 | verified | — | — | screener/comps/dcf return identical share counts for identical input |
| HARD-08 | fixed (was xfail) | reconcile was direction-blind: SEC-right + vendor-wrong → vendor | only two sources | `reconcile_mcap(…, third_mcap)` independent tiebreak (`prices.independent_market_cap`); picks whoever the third feed corroborates |
| HARD-06/07/09 | verified | — | — | boundary (2.9→sec, 3.01→vendor), zero/None handling locked |
| HARD-19 | fixed | a pre-migration US row (`country=NULL`) wrongly dropped by `--us-only` | additive `_migrate` adds the column but doesn't backfill; `(None)!="US"` | `--us-only` treats NULL as *unknown* (kept), excludes only known-foreign |
| HARD-15 | fixed | `defense` synonym over-matched commercial aircraft parts & "metal tanks" | loose description substrings ("aircraft"/"tank") | SIC-**code** scoping in `SECTOR_SYNONYMS` (`defense`→348x/3760/3761/3795/3812); `_sic_match(term, sic, desc)` |
| HARD-18 | verified | — | — | `company_meta` country: US-state/territory→`US`, else foreign code, else incorporation-state, else None |
| HARD-24 / COMBO-08 | fixed | SPACs/BDCs got EV/EBITDA | profile only knew financials/REITs | `_valuation_profile` adds SPAC (6770), BDC/fund (672x/6726); EV/EBITDA suppressed for non-standard models |
| XPATH-03/04 | verified | — | — | `_migrate` idempotent (column once); `upsert_metrics` re-run → no dup rows |

## Round-2 xfail registry (xpass ⇒ promote to assert)
- **LIMIT-01** ASML/SIC-3559 not caught by `semiconductor` (3559 is generic machinery; mapping it would over-match) — promote when a precise sector→SIC map lands.
- **LIMIT-02** FX flagged, not converted.
- **LIMIT-03** DCF on financials still returns a (meaningless) number; comps `valuation_method=financial` is the guard.
- **LIMIT-04** `ask.py` NL extraction drops dotted class tickers (`BRK.B`); the `--ticker-in`/skill path resolves them (boundary locked in the test).

## Key correction vs round 1
Round 1's dual-class "sum distinct values" was itself a regression (it produced COKE $6.4B by summing duplicate cover-page facts under the 3× gate). Round 2 establishes that companyfacts **cannot** represent share classes, so the correct primitive is newest-single-fact + vendor reconciliation, now hardened with an independent third-source tiebreak.
