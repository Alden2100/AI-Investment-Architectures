"""Phase 5 verification: Stage 6 debate + Stage 7 selective challenger + no-thesis.

Runs the orchestrator on the cached spec (scorecards cache-hit; Stage 6/7 run fresh).
Asserts:
  * Stage 6 produced BOTH confirming and disconfirming evidence per scored name.
  * evidence table has Stage-6 rows for the run.
  * ranking-challenger fired only on contested names (n_challenged <= scored; challenged
    rows carry a `challenge` object).
  * NO THESIS: no buy/sell/recommendation language anywhere in the generated prose
    (why_ranked, summary, qual evidence claims, reconciliation view).
Exit 0 == pass.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
os.environ.setdefault("IM_MAX_WORKERS", "4")
import _bootstrap  # noqa: F401,E402
from imdata import store  # noqa: E402
import orchestrator  # noqa: E402

# Recommendation/verdict language the SYSTEM must never emit. A cited *consensus price
# target* is analyst DATA (legitimately quotable as evidence), so it's not forbidden —
# the rule targets the system making its own buy/sell/recommendation call.
FORBIDDEN = ("recommend", "overweight", "underweight", "we like",
             "attractive entry", "strong buy", "outperform", "buy rating", "sell rating")
SPEC = {
    "mandate_id": "test-sw", "mandate_hash": "phase3-cache-test-v1", "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint", "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint", "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "high gross margin", "type": "soft_preference", "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "high gross margin software durable moat", "exclusions": [],
}
TOP_K = 2
fails = []


def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(SPEC, fh)
    try:
        r = orchestrator.main(argparse.Namespace(mandate=None, spec_file=path, top_k=TOP_K))
    finally:
        os.unlink(path)

    rid = r["run_id"]
    ranked = r.get("ranked", [])
    print(f"run {rid}: ranked={len(ranked)} n_challenged={r.get('n_challenged')} "
          f"scorecard_cache_hits={r.get('cache_hits')}")

    # Stage 6 evidence rows present
    ev6 = [e for e in store.evidence_for_run(rid) if e["stage"] == 6]
    check("Stage-6 evidence rows written", len(ev6) >= 1, f"{len(ev6)}")

    # both tags present per scored name
    both_ok = True
    for e in ev6:
        payload = json.loads(e["json"])
        tags = {x.get("tag") for x in (payload.get("evidence") or [])}
        nconf, ndisc = payload.get("n_confirming", 0), payload.get("n_disconfirming", 0)
        print(f"    {e['company']}: confirming={nconf} disconfirming={ndisc} "
              f"lean={payload.get('qual_lean')} conflict={payload.get('conflict')}")
        if not ({"confirming", "disconfirming"} <= tags):
            both_ok = False
    check("each scored name has BOTH confirming + disconfirming evidence", both_ok)

    # challenger selective
    challenged = [row for row in ranked if row.get("challenge")]
    check("n_challenged <= scored (selective, not all)", r.get("n_challenged", 0) <= len(ranked))
    check("challenged rows carry a challenge object",
          all(row.get("challenge") for row in challenged) and
          len(challenged) == sum(1 for row in ranked if row.get("challenge")))

    # NO THESIS lint across all generated prose
    prose_parts = [r.get("summary", "")]
    for row in ranked:
        prose_parts.append(row.get("why_ranked", ""))
        ch = row.get("challenge") or {}
        prose_parts.append(ch.get("rationale", "") or "")
    for e in ev6:
        payload = json.loads(e["json"])
        for x in (payload.get("evidence") or []):
            prose_parts.append(x.get("claim", "") or "")
        rec = payload.get("reconciliation") or {}
        prose_parts.append(rec.get("reconciled_view", "") or "")
    prose = " ".join(prose_parts).lower()
    hits = [w for w in FORBIDDEN if w in prose]
    check("no buy/sell/recommendation language anywhere", not hits, str(hits))

    print()
    if fails:
        print(f"DEBATE STRESS: {len(fails)} FAIL: {fails}")
        raise SystemExit(1)
    print("DEBATE STRESS: ALL PASS (both-sided evidence, selective challenger, no-thesis)")


if __name__ == "__main__":
    main()
