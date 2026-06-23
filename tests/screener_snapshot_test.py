#!/usr/bin/env python3
"""Deterministic test for the size-aware screener snapshot (no network).

Seeds a synthetic `company_metrics` table spanning mega/mid/small caps, then asserts
the universe-screener filters the market-cap band across the WHOLE universe (not the
first N by size) and reports truncated == False when the snapshot covers it.

    .venv/bin/python tests/screener_snapshot_test.py
"""
import argparse
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
# Isolate the DB/cache to a temp dir BEFORE importing the data layer.
_TMP = tempfile.mkdtemp()
os.environ["TOOLBOX_CACHE_DIR"] = _TMP
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["IM_LIB_ROOT"] = os.path.join(REPO, "skills-library")
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))
sys.path.insert(0, os.path.join(REPO, "skills-library", "research", "universe-screener"))

from imdata import store  # noqa: E402
import run as screener_cli  # noqa: E402  (universe-screener/run.py)

# Synthetic universe: ticker -> (title, sic_description, market_cap)
UNIVERSE = {
    "MEGA1": ("Mega Cap One", "beverages", 250e9),
    "MEGA2": ("Mega Cap Two", "beverages", 120e9),
    "MID1":  ("Mid Cap One", "beverages", 8e9),     # in band
    "MID2":  ("Mid Cap Two", "beverages", 3e9),     # in band
    "MID3":  ("Mid Cap Three", "software", 5e9),    # in band but wrong sector
    "SMALL1": ("Small Cap One", "beverages", 0.5e9),
    "NOCAP": ("No Cap Co", "beverages", None),      # null mcap must not match a band
}


def _seed():
    store.upsert_companies([{"ticker": t, "cik": i + 1, "title": v[0]}
                            for i, (t, v) in enumerate(UNIVERSE.items())])
    store.upsert_metrics([{"ticker": t, "market_cap": v[2], "sic": None,
                           "sic_description": v[1], "adv": 1e7, "last_px": 10.0,
                           "currency": "USD", "source": "test", "note": None}
                          for t, v in UNIVERSE.items()])


def _args(**kw):
    base = dict(name_contains=None, ticker_in=None, sic=None, sic_contains=None,
                min_mcap=None, max_mcap=None, min_adv=None, max_fetch=30,
                warm_names=500, use_snapshot=True, limit=50)
    base.update(kw)
    return argparse.Namespace(**base)


def run():
    _seed()
    checks = []

    # Mid-cap beverage band across the full universe.
    res = screener_cli.main(_args(sic_contains="beverage", min_mcap=2e9, max_mcap=2e10))
    got = {m["ticker"] for m in res["matches"]}
    checks.append(("mid-cap beverage band returns MID1+MID2", got == {"MID1", "MID2"}, got))
    checks.append(("truncated is False on snapshot path", res["truncated"] is False, res["truncated"]))
    checks.append(("snapshot_coverage reported", bool(res.get("snapshot_coverage")), res.get("snapshot_coverage")))

    # Sector filter excludes the in-band software name.
    checks.append(("software MID3 excluded from beverage screen", "MID3" not in got, got))

    # Null market cap never satisfies a band.
    checks.append(("null-mcap name excluded", "NOCAP" not in got, got))

    # Size ordering: largest first.
    res2 = screener_cli.main(_args(sic_contains="beverage", min_mcap=1e9, max_mcap=1e12))
    order = [m["ticker"] for m in res2["matches"]]
    checks.append(("ordered by market cap desc", order == ["MEGA1", "MEGA2", "MID1", "MID2"], order))

    # --no-snapshot forces the live path (will truncate flag semantics differ).
    res3 = screener_cli.main(_args(sic_contains="beverage", min_mcap=2e9, max_mcap=2e10, use_snapshot=False))
    checks.append(("no-snapshot path still runs", isinstance(res3.get("matches"), list), type(res3.get("matches"))))

    ok = 0
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + ("" if passed else f"  -> {detail!r}"))
        ok += bool(passed)
    print(f"{ok}/{len(checks)} screener-snapshot checks passed")
    if ok != len(checks):
        sys.exit(1)


if __name__ == "__main__":
    run()
