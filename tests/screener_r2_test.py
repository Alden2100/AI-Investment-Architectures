#!/usr/bin/env python3
"""Round-2 regression-hardening tests for the idea-sourcing fixes (offline/pure).

Targets the NEW code paths round-1 introduced: share-count selection, the shared
market-cap reconciliation (+ third-source tiebreak), country derivation, the NULL-
country --us-only trap, sector synonyms (incl. SIC-code scoping), valuation profiles,
and migration idempotence. Plus an xfail registry for the documented limitations.

    .venv/bin/python tests/screener_r2_test.py
"""
import importlib.util
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_TMP = tempfile.mkdtemp()
os.environ["TOOLBOX_CACHE_DIR"] = _TMP
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_TMP, "r2.db")
os.environ["IM_LIB_ROOT"] = os.path.join(REPO, "skills-library")
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))
sys.path.insert(0, os.path.join(REPO, "skills-library", "research", "universe-screener"))

import imdata.edgar as E          # noqa: E402
import imdata.universe as U       # noqa: E402
from imdata import screener, store  # noqa: E402
import run as scr                 # noqa: E402  (universe-screener)


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


comps = _load("skills-library/valuation/comps-builder/run.py", "comps_run")
dcf = _load("skills-library/valuation/dcf-valuation/run.py", "dcf_run")

_results = []
_xfails = []


def check(name, cond, detail=None):
    _results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail!r}"))


def xfail(name, cond_now):
    """cond_now == True means the limitation still holds (expected). xpass = a fail."""
    ok = bool(cond_now)
    _xfails.append(ok)
    print(f"  [{'xfail' if ok else 'XPASS!'}] {name}" + ("" if ok else "  (limitation fixed → promote to assert)"))


def _stub_concept(rows):
    E.get_concept = lambda ticker, tag: (rows if tag == "EntityCommonStockSharesOutstanding" else [])


# --------------------------------------------------------------------------- #
# A1 — share-count selection (newest single fact, no summing)
# --------------------------------------------------------------------------- #
def test_share_counts():
    print("\nShare-count selection (companyfacts can't separate classes → newest single):")
    # HARD-02: near-duplicate same-class facts must NOT overcount.
    _stub_concept([{"value": 7_140_000, "period_end": "2025-12-31"},
                   {"value": 7_140_001, "period_end": "2025-12-31"}])
    check("near-dup facts → one value (not summed)", screener._latest_shares("X") == 7_140_000,
          screener._latest_shares("X"))
    # COKE-style: same value across many accessions → one value.
    _stub_concept([{"value": 7_141_447, "period_end": "2016-03-04"}] * 5)
    check("repeated same-class facts → single value", screener._latest_shares("X") == 7_141_447)
    # HARD-04: rows out of period order → pick the max period_end.
    _stub_concept([{"value": 10, "period_end": "2020-12-31"},
                   {"value": 99, "period_end": "2025-12-31"},
                   {"value": 50, "period_end": "2023-12-31"}])
    check("picks newest period explicitly", screener._latest_shares("X") == 99)
    # HARD-05: cross-copy consistency (all three share one imdata.edgar).
    _stub_concept([{"value": 12_345_678, "period_end": "2025-12-31"},
                   {"value": 12_345_678, "period_end": "2025-12-31"}])
    a = screener._latest_shares("X")
    b = comps._shares_outstanding("X", price=10.0)
    c = dcf._shares_outstanding("X", price=10.0)
    check("screener/comps/dcf agree on same input", a == b == c == 12_345_678, (a, b, c))


# --------------------------------------------------------------------------- #
# A2 — reconcile_mcap boundaries + third-source tiebreak
# --------------------------------------------------------------------------- #
def test_reconcile():
    print("\nreconcile_mcap boundaries + tiebreak:")
    R = screener.reconcile_mcap
    check("agree → sec", R(100, 105)[1] == "sec")
    check("2.9x (under gate) → sec", R(100, 290)[1] == "sec")
    check("3.01x (over gate) → vendor", R(100, 301)[1] == "vendor")
    check("COKE 9.2x → vendor", R(1.3e9, 12e9)[1] == "vendor")
    check("zero sec → vendor", R(0, 200)[1] == "vendor")
    check("zero vendor → sec", R(100, 0)[1] == "sec")
    check("both None → none", R(None, None) == (None, "none", "no shares×price and no vendor market cap"))
    # HARD-08: direction-blind no more — third source breaks the tie.
    check("disagree + third corroborates SEC → sec", R(100, 400, third_mcap=100)[1] == "sec")
    check("disagree + third corroborates vendor → vendor", R(100, 400, third_mcap=390)[1] == "vendor")
    check("disagree + no third → vendor (fallback)", R(100, 400)[1] == "vendor")


# --------------------------------------------------------------------------- #
# A3 — country derivation (HARD-18)
# --------------------------------------------------------------------------- #
def test_country():
    print("\ncompany_meta country derivation:")
    U.resolve = lambda t: {"ticker": t, "cik": 1, "cik10": "0000000001", "title": t}

    def country(soc=None, soi=None):
        E._sec_json = lambda *a, **k: {"addresses": {"business": {"stateOrCountry": soc}},
                                       "stateOfIncorporation": soi, "sic": "100", "sicDescription": "x"}
        return E.company_meta("X")["country"]

    check("US state → US", country("CA") == "US")
    check("territory PR → US", country("PR") == "US")
    check("foreign code F4 → F4", country("F4") == "F4")
    check("missing business → falls back to incorporation state", country(None, "DE") == "US")
    check("both missing → None", country(None, None) is None)


# --------------------------------------------------------------------------- #
# A4/A6 — screener gates: NULL-country trap, falsy-zero, synonym scoping, profiles
# --------------------------------------------------------------------------- #
class _A:
    def __init__(self, **kw):
        d = dict(sic=None, sic_contains=None, us_only=False, min_mcap=None,
                 max_mcap=None, min_adv=None)
        d.update(kw)
        self.__dict__.update(d)


def test_gates_and_profiles():
    print("\n--us-only NULL-country trap + synonym scoping + valuation profiles:")
    # HARD-19: a NULL-country US row (pre-migration) must NOT be dropped by --us-only.
    us_null = {"sic": 7372, "sic_description": "prepackaged software", "market_cap": 6e9, "country": None}
    check("NULL country kept under --us-only (unknown, not foreign)",
          scr._passes(us_null, _A(us_only=True)) is True)
    foreign = {"sic": 6022, "sic_description": "state commercial banks", "market_cap": 6e9, "country": "F4"}
    check("known-foreign dropped under --us-only", scr._passes(foreign, _A(us_only=True)) is False)

    # HARD-15: defense synonym scoped to SIC codes, not loose words.
    missile = {"sic": 3760, "sic_description": "guided missiles & space vehicles", "market_cap": 6e9, "country": "US"}
    commercial_air = {"sic": 3728, "sic_description": "aircraft parts & auxiliary equipment", "market_cap": 6e9, "country": "US"}
    metal_tank = {"sic": 3443, "sic_description": "fabricated plate work (boiler shops)", "market_cap": 6e9, "country": "US"}
    check("defense matches a missile maker (SIC 3760)", scr._passes(missile, _A(sic_contains="defense")))
    check("defense no longer over-matches aircraft parts", not scr._passes(commercial_air, _A(sic_contains="defense")))
    check("defense no longer over-matches metal tanks", not scr._passes(metal_tank, _A(sic_contains="defense")))

    # HARD-24 + COMBO-08: valuation profiles.
    prof = comps._valuation_profile
    check("6798 → reit", prof("6798")[0] == "reit")
    check("6022 → financial", prof("6022")[0] == "financial")
    check("6311 → financial", prof("6311")[0] == "financial")
    check("6770 (SPAC) → spac", prof("6770")[0] == "spac")
    check("6726 (BDC) → fund", prof("6726")[0] == "fund")
    check("3674 → standard", prof("3674")[0] == "standard")


# --------------------------------------------------------------------------- #
# XPATH-03/04 — migration idempotence + upsert idempotence
# --------------------------------------------------------------------------- #
def test_migration_idempotence():
    print("\nMigration + upsert idempotence:")
    conn = store.get_conn()
    store._migrate(conn)
    store._migrate(conn)  # twice → no error
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(company_metrics)")]
    check("country column present exactly once", cols.count("country") == 1, cols)
    row = {"ticker": "TST", "market_cap": 1e9, "sic": 7372, "sic_description": "x",
           "adv": 1e6, "last_px": 10.0, "currency": "USD", "country": "US",
           "source": "test", "note": None}
    store.upsert_metrics([row]); n1 = store.metrics_count()
    store.upsert_metrics([row]); n2 = store.metrics_count()
    check("re-upsert same ticker → no duplicate row", n1 == n2)


# --------------------------------------------------------------------------- #
# Bucket B — documented limitations as xfail (xpass ⇒ promote)
# --------------------------------------------------------------------------- #
def test_xfail_registry():
    print("\nxfail registry (documented limitations):")
    from imdata import entities
    # LIMIT-04: ask.py NL path can't extract a dotted class ticker (regex splits on '.').
    store.upsert_companies([{"ticker": "BRK-B", "cik": 1, "title": "Berkshire Hathaway"}])
    nl_miss = "BRK-B" not in entities.extract_tickers("what is BRK.B worth")
    xfail("LIMIT-04: NL 'BRK.B' not extracted (regex splits on '.')", nl_miss)
    # …but the skill / --ticker-in path resolves it (the regression boundary).
    check("skill path resolves BRK.B → BRK-B", store.company_by_ticker("BRK.B") is not None
          and store.company_by_ticker("BRK.B")["ticker"] == "BRK-B")


if __name__ == "__main__":
    test_share_counts()
    test_reconcile()
    test_country()
    test_gates_and_profiles()
    test_migration_idempotence()
    test_xfail_registry()
    n = sum(_results)
    print(f"\n{n}/{len(_results)} round-2 checks passed; "
          f"{sum(_xfails)}/{len(_xfails)} xfails holding")
    sys.exit(0 if all(_results) else 1)
