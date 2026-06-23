#!/usr/bin/env python3
"""Unit test for imdata.entities — name->ticker resolution, TICKER=weight parsing,
and stop-word collision guards. Seeds a synthetic universe, no network.

    .venv/bin/python tests/entities_test.py
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
_TMP = tempfile.mkdtemp()
os.environ["TOOLBOX_CACHE_DIR"] = _TMP
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_TMP, "ent.db")
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))

from imdata import store, entities  # noqa: E402

# Synthetic universe (ticker -> title). 'DCF' is a stop-word collision (a real-looking
# symbol that must never be extracted from prose).
COMPANIES = {
    "MU": "Micron Technology, Inc.", "KO": "Coca-Cola Co", "AAPL": "Apple Inc.",
    "NVDA": "NVIDIA Corporation", "MSFT": "Microsoft Corporation",
    "DCF": "Dummy Collision Fund",  # collides with the _STOP word "DCF"
    "PFE": "Pfizer Inc.",
}
_results = []


def check(name, cond, detail=None):
    _results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail!r}"))


def run():
    store.upsert_companies([{"ticker": t, "cik": i + 1, "title": ti}
                            for i, (t, ti) in enumerate(COMPANIES.items())])
    entities.clear_cache()

    # name -> ticker
    check("'Micron Technology's' -> MU", entities.match_company_name("Micron Technology's") == "MU",
          entities.match_company_name("Micron Technology's"))
    check("'Coca-Cola' -> KO", entities.match_company_name("Coca-Cola") == "KO",
          entities.match_company_name("Coca-Cola"))
    check("'Pfizer' -> PFE", entities.match_company_name("Pfizer") == "PFE",
          entities.match_company_name("Pfizer"))
    check("unknown name -> None", entities.match_company_name("Wakanda Vibranium") is None)

    # extract_tickers: order preserved, names + symbols, stop-words excluded
    got = entities.extract_tickers("what's Micron worth versus AAPL and MSFT?")
    check("extract_tickers order MU, AAPL, MSFT", got == ["MU", "AAPL", "MSFT"], got)

    # stop-word collision: 'DCF' is a valid ticker here but must be filtered from prose
    check("valid_ticker('DCF') true (seeded)", entities.valid_ticker("DCF"))
    got2 = entities.extract_tickers("run a DCF and tell me IT IS A good idea")
    check("stop-word collisions excluded (no DCF/IT/IS/A)", got2 == [], got2)

    # positions
    pos = entities.extract_positions("NVDA 30%, MSFT=0.2, AAPL: 15%")
    check("extract_positions parses weights", pos == ["NVDA=0.3", "MSFT=0.2", "AAPL=0.15"], pos)
    pos2 = entities.extract_positions("hold THE book at 50 and OR at 10%")
    check("positions skip stop-words", pos2 == [], pos2)

    n = sum(_results)
    print(f"{n}/{len(_results)} entity checks passed")
    sys.exit(0 if all(_results) else 1)


if __name__ == "__main__":
    run()
