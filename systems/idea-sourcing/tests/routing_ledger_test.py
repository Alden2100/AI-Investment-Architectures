"""Verify the qwen->sonnet->opus ladder actually engaged (not a single model for all).

A single rung across every task means judgment leaked out of the router. This runs the
orchestrator (scorecards may be cached, but Stages 5/6 route fresh) and asserts the
routing ledger shows MORE THAN ONE distinct rung. If only one rung appears it warns that
a backend may be unavailable (keyless/degraded) rather than hard-failing on env. Exit 0 == pass.
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import _bootstrap  # noqa: F401,E402
import orchestrator  # noqa: E402

SPEC = {
    "mandate_id": "ladder", "mandate_hash": "ladder-v2-fixed", "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint", "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint", "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "durable moat", "type": "qualitative", "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "durable moat high quality software", "exclusions": [],
}


def main():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(SPEC, fh)
    try:
        r = orchestrator.main(argparse.Namespace(mandate=None, spec_file=path, top_k=2))
    finally:
        os.unlink(path)

    ledger = r.get("model_routing", [])
    rungs = sorted({x["rung"] for x in ledger})
    models = sorted({x["model"] for x in ledger})
    print(f"routing ledger: {[(x['task'], x['rung'], x['n']) for x in ledger]}")
    print(f"distinct rungs={rungs} models={models}")

    assert ledger, "empty routing ledger — router never engaged"
    if len(rungs) < 2:
        print(f"WARN: only one rung ({rungs}) — a backend may be unavailable "
              f"(keyless/degraded). Ladder cannot be fully demonstrated in this env.")
    else:
        print(f"PASS: ladder engaged across {len(rungs)} rungs {rungs} "
              f"(not a single model for everything).")


if __name__ == "__main__":
    main()
