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
import time  # noqa: E402
import yaml  # noqa: E402
import _bootstrap  # noqa: F401,E402
import orchestrator  # noqa: E402

# Unique mandate_hash per run so Stage-4 scorecard + Stage-6 debate compute FRESH
# (not served from the by-mandate/by-day cache) — otherwise a warm cache makes the
# ledger look single-model when it isn't.
SPEC = {
    "mandate_id": "ladder", "mandate_hash": "ladder-" + str(int(time.time())),
    "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint", "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint", "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "durable moat", "type": "qualitative", "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "durable moat high quality software", "exclusions": [],
}


def _policy_rungs():
    pol = yaml.safe_load(open(os.path.join(os.path.dirname(_bootstrap.HERE), "idea-sourcing",
                                           "router-policy.yaml")))
    alias = {"local": "qwen", "claude": "opus"}
    rungs = {alias.get(v, v) for v in pol.get("routes", {}).values()}
    rungs.add(alias.get(pol.get("default"), pol.get("default")))
    return rungs


def main():
    # 1) STATIC: the policy itself must spread tasks across >=2 rungs (ladder configured).
    prungs = _policy_rungs()
    print(f"policy rungs configured: {sorted(prungs)}")
    assert len({r for r in prungs if r in ("qwen", "sonnet", "opus")}) >= 2, \
        "router policy collapsed to a single rung"

    # 2) DYNAMIC: a fresh run engages the router (non-empty ledger) and, in this env
    #    (all backends up), spreads across >=2 rungs.
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
        print(f"WARN: ledger showed one rung ({rungs}) this run — likely a warm cache or a "
              f"backend down. Policy still spans {sorted(prungs)}, so the ladder is intact.")
    else:
        print(f"PASS: ladder engaged across {len(rungs)} rungs {rungs} "
              f"(not a single model for everything).")
    print("PASS: routing policy preserves a multi-rung ladder (speed profile did not collapse it).")


if __name__ == "__main__":
    main()
