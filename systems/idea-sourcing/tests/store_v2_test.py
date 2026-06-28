"""Phase 1 verification: the v2 Evidence Store tables + helpers round-trip.

Runs keyless and against an isolated temp DB (no network). Exit 0 == pass.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
_d, LIB = HERE, None
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "skills-library")):
        LIB = os.path.join(_d, "skills-library"); break
    _d = os.path.dirname(_d)

# Isolate the DB BEFORE importing the store so config picks up the temp path.
_tmp = tempfile.mkdtemp(prefix="store_v2_test_")
os.environ["TOOLBOX_CACHE_DIR"] = _tmp
os.environ["TOOLBOX_DB_PATH"] = os.path.join(_tmp, "test.db")
sys.path.insert(0, os.path.join(LIB, "_shared", "data-fetch"))

from imdata import store  # noqa: E402

sys.path.insert(0, os.path.join(HERE, ".."))
from stages._cache import inputs_hash  # noqa: E402


def _tables():
    return {r[0] for r in store.get_conn().execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def main():
    # 1) All v2 tables materialized from _SCHEMA.
    tabs = _tables()
    for t in ("runs", "evidence", "scores", "events", "reject_log"):
        assert t in tabs, f"missing table {t} (have {sorted(tabs)})"

    # 2) runs round-trip.
    store.start_run("run1", "hashA", {"style": "quality"})
    assert store.get_run("run1")["mandate_hash"] == "hashA"
    store.finish_run("run1", [{"task": "synthesis", "rung": "sonnet"}])
    assert store.get_run("run1")["finished_at"]
    assert store.latest_run_for_mandate("hashA")["run_id"] == "run1"

    # 3) evidence cache: same inputs_hash -> cache hit ACROSS runs; different -> miss.
    ih = inputs_hash(4, "hashA", {"accession": "0001-x", "criteria": ["c1"]})
    store.put_evidence("run1", "MSFT", 4, "mandate-scorecard",
                       {"overall_fit": 0.8}, [{"source": "10-K"}], ih)
    hit = store.get_cached_evidence("MSFT", 4, "mandate-scorecard", ih)
    assert hit and hit["overall_fit"] == 0.8 and hit["_cached"] is True
    assert store.get_cached_evidence("MSFT", 4, "mandate-scorecard", "different") is None
    # case-insensitive ticker
    assert store.get_cached_evidence("msft", 4, "mandate-scorecard", ih) is not None

    # 4) scores upsert (PK collision replaces).
    store.put_score("run1", "MSFT", "quality", 0.9, {"gross_margin": 0.69})
    store.put_score("run1", "MSFT", "quality", 0.95)
    rows = [r for r in store.scores_for_run("run1") if r["factor"] == "quality"]
    assert len(rows) == 1 and rows[0]["value"] == 0.95

    # 5) events.
    store.put_events("run1", "MSFT", [
        {"type": "8-K", "date": "2026-06-01", "source": "EDGAR", "confidence": 0.9,
         "hard_event": True, "rationale": "buyback"}])
    evs = store.events_for_run("run1", "MSFT")
    assert len(evs) == 1 and evs[0]["type"] == "8-K"

    # 6) reject log: NO SILENT DROPS — `constraint` maps to constraint_text.
    store.put_rejects("run1", [
        {"ticker": "XYZ", "removed_by": "c1", "constraint": "country in [US]",
         "value_seen": "CN"}])
    rj = store.rejects_for_run("run1")
    assert len(rj) == 1 and rj[0]["constraint_text"] == "country in [US]" \
        and rj[0]["value_seen"] == "CN"

    print("store_v2_test: PASS (tables + runs/evidence-cache/scores/events/reject_log round-trip)")


if __name__ == "__main__":
    main()
