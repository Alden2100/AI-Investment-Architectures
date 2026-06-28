"""Phase 1 verification (deterministic, no network): mandate-driven prescreen.

Uses a temp DB with synthetic companies + classification rows, so it asserts the
candidate-narrowing logic without any SEC fetch:
  * _mandate_sectors extracts preferred / avoid / countries from a MandateSpec
  * prescreen narrows to preferred-industry + geography, drops avoid-list + foreign
  * word-boundary matching: "industrial automation" does NOT pull "auto"
Exit 0 == pass.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
_tmp = tempfile.mkdtemp(prefix="prescreen_test_")
os.environ["TOOLBOX_CACHE_DIR"] = _tmp
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_tmp, "t.db")
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))

from imdata import screener, store  # noqa: E402

fails = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)

COMPANIES = [
    ("SWCO", 1, "Software Co"), ("MEDCO", 2, "Medical Devices Co"),
    ("AIRCO", 3, "Airline Co"), ("TOBCO", 4, "Tobacco Co"),
    ("FORCO", 5, "Foreign Software Co"), ("AUTOCO", 6, "Auto Maker Co"),
]
CLASSIFICATION = [
    {"ticker": "SWCO", "sic": 7372, "sic_description": "Services-Prepackaged Software", "country": "US"},
    {"ticker": "MEDCO", "sic": 3841, "sic_description": "Surgical & Medical Instruments & Apparatus", "country": "US"},
    {"ticker": "AIRCO", "sic": 4512, "sic_description": "Air Transportation, Scheduled", "country": "US"},
    {"ticker": "TOBCO", "sic": 2111, "sic_description": "Cigarettes", "country": "US"},
    {"ticker": "FORCO", "sic": 7372, "sic_description": "Services-Prepackaged Software", "country": "CN"},
    {"ticker": "AUTOCO", "sic": 3711, "sic_description": "Motor Vehicles & Passenger Car Bodies", "country": "US"},
]
MANDATE = {
    "mandate_id": "m", "mandate_hash": "h", "seed_tickers": [],
    "criteria": [
        {"id": "c1", "text": "enterprise software", "type": "soft_preference", "field": None, "operator": None, "value": None},
        {"id": "c2", "text": "medical devices", "type": "soft_preference", "field": None, "operator": None, "value": None},
        {"id": "c3", "text": "industrial automation", "type": "qualitative", "field": None, "operator": None, "value": None},
        {"id": "c4", "text": "US listed", "type": "hard_constraint", "field": "country", "operator": "in", "value": ["US"]},
    ],
    "semantic_query": "enterprise software medical devices industrial automation",
    "exclusions": ["airlines", "tobacco"],
}


def main():
    store.upsert_companies([{"ticker": t, "cik": c, "title": n} for t, c, n in COMPANIES])
    store.upsert_classification(CLASSIFICATION)

    pref, avoid, countries = screener._mandate_sectors(MANDATE)
    print("preferred:", pref, "| avoid:", avoid, "| countries:", countries)
    check("preferred has enterprise software + medical devices",
          "enterprise software" in pref and "medical devices" in pref)
    check("word-boundary: 'auto' NOT in preferred (from 'automation')", "auto" not in pref)
    check("avoid has an airline + tobacco entry",
          any(a in avoid for a in ("airline", "airlines")) and "tobacco" in avoid)
    check("countries == [US]", countries == ["US"])

    # max_classify=0 => no SEC calls; just filter the synthetic classification
    pre = screener.prescreen_universe(MANDATE, max_classify=0)
    cands = set(pre["candidates"])
    print("candidates:", sorted(cands))
    check("SWCO (software, US) is a candidate", "SWCO" in cands)
    check("MEDCO (medical, US) is a candidate", "MEDCO" in cands)
    check("AIRCO (airline) excluded by avoid-list", "AIRCO" not in cands)
    check("TOBCO (tobacco) excluded by avoid-list", "TOBCO" not in cands)
    check("FORCO (software but CN) excluded by geography", "FORCO" not in cands)
    check("AUTOCO (motor vehicle) not pulled in as 'auto'", "AUTOCO" not in cands)

    print()
    if fails:
        print(f"PRESCREEN TEST: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("PRESCREEN TEST: ALL PASS (mandate-driven narrowing; no silent industry/geo leaks)")


if __name__ == "__main__":
    main()
