"""idea-sourcing v2 smoke test — mandate -> ranked opportunities, end to end.

Runs the orchestrator on a fixed MandateSpec with a tiny top_k to bound model calls.
Asserts the system produces a ranked, evidence-backed shortlist with a reject log and a
routing ledger — and emits no buy/sell/recommendation language. Keyless-capable (routes
fall back to qwen). Exit 0 == pass.
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

FORBIDDEN = ("recommend", "overweight", "underweight", "we like",
             "attractive entry", "strong buy", "outperform", "buy rating", "sell rating")
SPEC = {
    "mandate_id": "smoke", "mandate_hash": "smoke-v2-fixed", "seed_tickers": ["MSFT"],
    "criteria": [
        {"id": "c1", "text": "large cap", "type": "hard_constraint", "field": "market_cap", "operator": "gte", "value": 1e10},
        {"id": "c2", "text": "software", "type": "hard_constraint", "field": "sic", "operator": "in", "value": ["software"]},
        {"id": "c3", "text": "high gross margin", "type": "soft_preference", "field": None, "operator": None, "value": None},
    ],
    "semantic_query": "high gross margin software durable moat", "exclusions": [],
}


def run():
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(SPEC, fh)
    try:
        r = orchestrator.main(argparse.Namespace(mandate=None, spec_file=path, top_k=2))
    finally:
        os.unlink(path)

    assert r.get("system") == "idea-sourcing", "system tag missing"
    assert isinstance(r.get("ranked"), list) and r["ranked"], "no ranked rows"
    for row in r["ranked"]:
        for k in ("rank", "ticker", "opportunity_score", "why_ranked", "confidence"):
            assert k in row, f"ranked row missing {k}"
        assert 0.0 <= row["opportunity_score"] <= 1.0, "opportunity_score out of range"
    assert r.get("n_rejects", 0) >= 1, "reject log empty (expected hard-filtered names)"
    assert r.get("model_routing"), "no routing ledger"

    prose = " ".join([r.get("summary", "")] + [x.get("why_ranked", "") for x in r["ranked"]]).lower()
    bad = [w for w in FORBIDDEN if w in prose]
    assert not bad, f"recommendation language leaked: {bad}"
    assert store.rejects_for_run(r["run_id"]), "reject_log not persisted"

    print(f"PASS idea-sourcing v2: {r['n_survivors']} survivors -> ranked {len(r['ranked'])} "
          f"({', '.join(x['ticker'] for x in r['ranked'])}); rejects={r['n_rejects']}; "
          f"routing rungs={sorted({x['rung'] for x in r['model_routing']})}")


if __name__ == "__main__":
    run()
