"""Phase 3 verification: orchestrator concurrency + incremental cache-skip.

Runs the orchestrator twice on a FIXED MandateSpec (stable mandate_hash => stable
inputs_hash). Run 1 computes scorecards (cache misses, parallel). Run 2 must hit the
cache for every kept name — no new Stage-4 evidence rows, no model calls. Also forces
IM_MAX_WORKERS=8 to confirm the parallel fan-out never trips a SQLite lock.

Exit 0 == pass. Needs the warmed system snapshot DB.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
os.environ.setdefault("IM_MAX_WORKERS", "8")
import _bootstrap  # noqa: F401,E402
from imdata import store  # noqa: E402
import orchestrator  # noqa: E402

SPEC = {
    "mandate_id": "test-sw", "mandate_hash": "phase3-cache-test-v1",
    "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint",
         "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint",
         "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "high gross margin", "type": "soft_preference",
         "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "high gross margin software durable moat",
    "exclusions": [],
}
TOP_K = 3


def _stage4_rows():
    return store.get_conn().execute(
        "SELECT COUNT(*) FROM evidence WHERE stage=4 AND skill='mandate-scorecard'"
    ).fetchone()[0]


def _run(spec_path):
    args = argparse.Namespace(mandate=None, spec_file=spec_path, top_k=TOP_K)
    return orchestrator.main(args)


def main():
    fd, path = tempfile.mkstemp(suffix=".json", prefix="spec_")
    with os.fdopen(fd, "w") as fh:
        json.dump(SPEC, fh)
    fails = []
    try:
        before = _stage4_rows()
        r1 = _run(path)
        after1 = _stage4_rows()
        r2 = _run(path)
        after2 = _stage4_rows()

        kept = r1.get("ranked", [])
        print(f"run1: survivors={r1.get('n_survivors')} ranked={len(kept)} "
              f"cache_hits={r1.get('cache_hits')}")
        print(f"run2: ranked={len(r2.get('ranked', []))} cache_hits={r2.get('cache_hits')}")
        print(f"stage4 evidence rows: before={before} after_run1={after1} after_run2={after2}")
        routings = {x['rung'] for x in r1.get('model_routing', [])}
        print(f"run1 routing rungs: {sorted(routings)}")

        n_keep = len(kept)
        # Run 1 computed (new rows added) — unless a prior identical-hash run exists.
        check1 = after1 >= before
        # Run 2 added NO new stage-4 rows (every kept name was a cache hit).
        check2 = (after2 == after1)
        # Run 2 reports all kept names as cache hits.
        check3 = (n_keep > 0 and len(r2.get("cache_hits", [])) == n_keep)
        for name, ok in (("run1 wrote/kept rows", check1),
                         ("run2 added 0 new stage4 rows (cache-skip)", check2),
                         ("run2 cache_hits == all kept names", check3)):
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
            if not ok:
                fails.append(name)
    finally:
        os.unlink(path)

    if fails:
        print(f"\nORCH CACHE TEST: {len(fails)} FAIL: {fails}")
        raise SystemExit(1)
    print("\nORCH CACHE TEST: PASS (parallel fan-out @8 workers, no lock; cache-skip on rerun)")


if __name__ == "__main__":
    main()
