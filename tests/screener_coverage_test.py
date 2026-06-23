#!/usr/bin/env python3
"""Offline coverage test for the size-aware screener (no network, no model).

Seeds a synthetic universe spanning every size band, one clean sector each, and the
edge cases the idea-sourcing stress suite targets (Appendix A): null-cap exclusion,
inclusive floor, sector isolation, the biotech/reit/defense synonym map, foreign-
issuer + --us-only, falsy-zero bounds, and the pure _market_cap reconciliation.

    .venv/bin/python tests/screener_coverage_test.py
"""
import argparse
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_TMP = tempfile.mkdtemp()
os.environ["TOOLBOX_CACHE_DIR"] = _TMP
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_TMP, "cov.db")
os.environ["IM_LIB_ROOT"] = os.path.join(REPO, "skills-library")
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))
sys.path.insert(0, os.path.join(REPO, "skills-library", "research", "universe-screener"))

from imdata import store, screener  # noqa: E402
import run as scr  # noqa: E402  (universe-screener/run.py)

# ticker -> (title, sic, sic_description, market_cap, currency, country)
UNIVERSE = {
    "MEGA":  ("Mega Soft", 7372, "prepackaged software", 3.0e11, "USD", "US"),
    "LARGE": ("Large Soft", 7372, "prepackaged software", 5.0e10, "USD", "US"),
    "MID":   ("Mid Soft", 7372, "prepackaged software", 6.0e9, "USD", "US"),
    "SMALL": ("Small Soft", 7372, "prepackaged software", 1.0e9, "USD", "US"),
    "MICRO": ("Micro Soft Co", 7372, "prepackaged software", 2.0e8, "USD", "US"),
    "EDGE":  ("Edge Soft", 7372, "prepackaged software", 2.0e9, "USD", "US"),   # exactly at 2e9 floor
    "NOCAP": ("No Cap Soft", 7372, "prepackaged software", None, "USD", "US"),  # null cap never matches
    "BANK":  ("Midcap Bank", 6021, "national commercial banks", 6.0e9, "USD", "US"),
    "INSUR": ("Midcap Insurer", 6331, "fire, marine & casualty insurance", 6.0e9, "USD", "US"),
    "PHARM": ("Midcap Pharma", 2834, "pharmaceutical preparations", 6.0e9, "USD", "US"),
    "BIOTC": ("Midcap Biotech", 2836, "biological products", 6.0e9, "USD", "US"),
    "REITX": ("Midcap REIT", 6798, "real estate investment trusts", 6.0e9, "USD", "US"),
    "DEFEN": ("Midcap Defense", 3760, "guided missiles & space vehicles", 6.0e9, "USD", "US"),
    "THRIF": ("Midcap Thrift", 6035, "savings institution, federally chartered", 6.0e9, "USD", "US"),
    "FORGN": ("Foreign ADR", 3674, "semiconductors & related devices", 6.0e9, "EUR", "P7"),
}
_results = []


def check(name, cond, detail=None):
    _results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail!r}"))


def _seed():
    store.upsert_companies([{"ticker": t, "cik": i + 1, "title": v[0]}
                            for i, (t, v) in enumerate(UNIVERSE.items())])
    store.upsert_metrics([{"ticker": t, "market_cap": v[3], "sic": v[1],
                           "sic_description": v[2], "adv": 1e7, "last_px": 10.0,
                           "currency": v[4], "country": v[5], "source": "test", "note": None}
                          for t, v in UNIVERSE.items()])


def _args(**kw):
    base = dict(name_contains=None, ticker_in=None, sic=None, sic_contains=None,
                min_mcap=None, max_mcap=None, min_adv=None, max_fetch=30,
                warm_names=500, use_snapshot=True, us_only=False, limit=50)
    base.update(kw)
    return argparse.Namespace(**base)


def _tk(res):
    return {m["ticker"] for m in res["matches"]}


def run():
    _seed()

    # --- size bands ---
    check("mega ≥200B", _tk(scr.main(_args(min_mcap=2e11))) == {"MEGA"})
    check("large 10–200B", _tk(scr.main(_args(min_mcap=1e10, max_mcap=2e11))) == {"LARGE"})
    mid = scr.main(_args(min_mcap=2e9, max_mcap=1e10))
    mid_tk = _tk(mid)
    check("mid band includes MID+EDGE, excludes NOCAP/SMALL",
          {"MID", "EDGE"} <= mid_tk and "NOCAP" not in mid_tk and "SMALL" not in mid_tk, mid_tk)
    check("every mid-band match is in [2e9,1e10]",
          all(2e9 <= m["market_cap"] <= 1e10 for m in mid["matches"]),
          [(m["ticker"], m["market_cap"]) for m in mid["matches"]])
    check("small 0.3–2B", _tk(scr.main(_args(min_mcap=3e8, max_mcap=2e9))) == {"SMALL", "EDGE"})
    check("micro ≤300M", _tk(scr.main(_args(max_mcap=3e8))) == {"MICRO"})

    # --- null cap & boundary ---
    check("NOCAP never in any band", "NOCAP" not in _tk(scr.main(_args(min_mcap=0, max_mcap=1e13))))
    check("EDGE (==floor) included", "EDGE" in _tk(scr.main(_args(min_mcap=2e9, max_mcap=2e9))))

    # --- falsy-zero bounds (SIZE-08) ---
    check("max-mcap 0 → empty (real ceiling)", _tk(scr.main(_args(max_mcap=0))) == set())
    check("min-mcap 0 → no floor", "MICRO" in _tk(scr.main(_args(min_mcap=0))))
    check("inverted band → empty", _tk(scr.main(_args(min_mcap=1e10, max_mcap=2e9))) == set())

    # --- sector isolation ---
    check("bank isolates BANK", _tk(scr.main(_args(sic_contains="bank"))) == {"BANK"})
    check("insurance isolates INSUR", _tk(scr.main(_args(sic_contains="insurance"))) == {"INSUR"})
    check("pharmaceutical isolates PHARM", _tk(scr.main(_args(sic_contains="pharmaceutical"))) == {"PHARM"})
    check("real estate isolates REITX", _tk(scr.main(_args(sic_contains="real estate"))) == {"REITX"})

    # --- synonym map (the SEC-05/16 finding, now fixed) ---
    check("biotech synonym → BIOTC", _tk(scr.main(_args(sic_contains="biotech"))) == {"BIOTC"})
    check("reit synonym → REITX", _tk(scr.main(_args(sic_contains="reit"))) == {"REITX"})
    check("defense synonym → DEFEN", _tk(scr.main(_args(sic_contains="defense"))) == {"DEFEN"})
    check("thrift synonym → THRIF", _tk(scr.main(_args(sic_contains="thrift"))) == {"THRIF"})

    # --- exact SIC code path ---
    check("exact --sic 6021 → BANK", _tk(scr.main(_args(sic="6021"))) == {"BANK"})

    # --- foreign issuer + --us-only ---
    semis = _tk(scr.main(_args(sic_contains="semiconductor")))
    check("FORGN returned without --us-only", "FORGN" in semis, semis)
    check("FORGN excluded with --us-only", "FORGN" not in _tk(scr.main(_args(sic_contains="semiconductor", us_only=True))))
    check("--us-only keeps US names", "MID" in _tk(scr.main(_args(min_mcap=2e9, max_mcap=1e10, us_only=True))))

    # --- ordering ---
    order = [m["ticker"] for m in scr.main(_args(sic_contains="software", min_mcap=1e8, max_mcap=1e13))["matches"]]
    check("ordered by mcap desc", order == ["MEGA", "LARGE", "MID", "EDGE", "SMALL", "MICRO"], order)

    # --- pure _market_cap reconciliation (MCAP fix-map unit test) ---
    check("reconcile: agree → sec", screener._reconcile_mcap(100e9, 105e9)[1] == "sec")
    check("reconcile: >3x under (COKE) → vendor", screener._reconcile_mcap(1.3e9, 12e9)[1] == "vendor")
    check("reconcile: >3x over → vendor", screener._reconcile_mcap(40e9, 1e9)[1] == "vendor")
    check("reconcile: sec missing → vendor", screener._reconcile_mcap(None, 2e9)[1] == "vendor")
    check("reconcile: both missing → none", screener._reconcile_mcap(None, None) == (None, "none",
          "no shares×price and no vendor market cap"))

    n = sum(_results)
    print(f"{n}/{len(_results)} screener-coverage checks passed")
    sys.exit(0 if all(_results) else 1)


if __name__ == "__main__":
    run()
