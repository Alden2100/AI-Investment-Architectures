"""Phase 3 orchestrator stress: edge cases + the no-thesis invariant.

  * 0-survivor mandate -> graceful empty ranking, no crash (no model calls).
  * gate logging -> survivors beyond top_k are recorded in reject_log (NO SILENT DROPS).
  * ranking shape -> sequential ranks, opportunity_score in [0,1], why_ranked present.
  * NO THESIS -> the system's own ranking prose (why_ranked, summary) contains no
    buy/sell/recommendation language. (Cited filing evidence is exempt — it may quote
    business text like "customers buy".)

Reuses the cached spec from the cache test so the scored run needs no fresh model calls.
Exit 0 == pass.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import _bootstrap  # noqa: F401,E402
from imdata import store  # noqa: E402
import orchestrator  # noqa: E402

FORBIDDEN = ("buy", "sell", "recommend", "overweight", "underweight",
             "price target", "we like", "attractive entry", "strong buy", "outperform")

CACHED_SPEC = {
    "mandate_id": "test-sw", "mandate_hash": "phase3-cache-test-v1", "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint", "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint", "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "high gross margin", "type": "soft_preference", "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "high gross margin software durable moat", "exclusions": [],
}
IMPOSSIBLE_SPEC = {
    "mandate_id": "imposs", "mandate_hash": "imposs-v1", "seed_tickers": [],
    "criteria": [{"id": "c1", "text": "absurd cap", "type": "hard_constraint",
                  "field": "market_cap", "operator": "gte", "value": 1e15}],
    "semantic_query": "", "exclusions": [],
}
fails = []


def _spec_file(spec):
    fd, path = tempfile.mkstemp(suffix=".json", prefix="spec_")
    with os.fdopen(fd, "w") as fh:
        json.dump(spec, fh)
    return path


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def _run(spec, top_k):
    p = _spec_file(spec)
    try:
        return orchestrator.main(argparse.Namespace(mandate=None, spec_file=p, top_k=top_k))
    finally:
        os.unlink(p)


def main():
    # ---- Edge 1: impossible cap -> 0 known-cap survivors, graceful ----------
    print("Edge: impossible-cap + empty semantic_query mandate")
    r = _run(IMPOSSIBLE_SPEC, 1)
    check("no crash + ranked is a list", isinstance(r.get("ranked"), list))
    check("graceful summary present", bool(r.get("summary")))

    # ---- Scored run on the cached spec (fast: cache hits) -------------------
    print("Scored run (cached spec, top_k=3)")
    r = _run(CACHED_SPEC, 3)
    ranked = r.get("ranked", [])
    check("produced ranked rows", len(ranked) >= 1, f"{len(ranked)}")
    check("ranks are sequential 1..N",
          [x["rank"] for x in ranked] == list(range(1, len(ranked) + 1)))
    check("opportunity_score in [0,1]",
          all(0.0 <= x.get("opportunity_score", -1) <= 1.0 for x in ranked))
    check("every row has why_ranked", all(x.get("why_ranked") for x in ranked))

    # ---- Gate logging: top_k=2 on a fixed run -> beyond-gate names logged ---
    print("Gate logging (top_k=2)")
    r2 = _run(CACHED_SPEC, 2)
    rid = r2["run_id"]
    rej = store.rejects_for_run(rid)
    gate = [x for x in rej if x["removed_by"] == "gate:stage2"]
    check("gate drops recorded in reject_log (no silent drops)", len(gate) >= 1,
          f"{len(gate)} gate rows")

    # ---- NO THESIS lint on the system's own prose --------------------------
    print("No-thesis lint (why_ranked + summary)")
    prose = " ".join([x.get("why_ranked", "") for x in ranked] + [r.get("summary", "")]).lower()
    hits = [w for w in FORBIDDEN if w in prose]
    check("no buy/sell/recommendation language in ranking prose", not hits, str(hits))

    print()
    if fails:
        print(f"ORCH STRESS: {len(fails)} FAIL: {fails}")
        raise SystemExit(1)
    print("ORCH STRESS: ALL PASS (edge cases, gate logging, ranking shape, no-thesis)")


if __name__ == "__main__":
    main()
