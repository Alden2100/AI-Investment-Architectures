#!/usr/bin/env python3
"""Smoke test: idea-sourcing runs end-to-end and returns a sane dossier.

Keyless — uses live free data (SEC/Yahoo) and the local qwen route for ranking.
Run:  .venv/bin/python systems/idea-sourcing/tests/smoke_test.py
"""
import json, os, subprocess, sys

SYS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ORCH = os.path.join(SYS_DIR, "orchestrator.py")


def run():
    proc = subprocess.run(
        [sys.executable, ORCH, "--ticker-in", "MSFT", "AAPL", "--max-candidates", "2"],
        capture_output=True, text=True, timeout=400)
    assert proc.returncode == 0, f"non-zero exit\n{proc.stderr[-800:]}"
    d = json.loads(proc.stdout)
    assert d["system"] == "idea-sourcing"
    tickers = [c["ticker"] for c in d["candidates"]]
    assert set(tickers) == {"MSFT", "AAPL"}, f"unexpected candidates: {tickers}"
    for c in d["candidates"]:
        assert c.get("dcf_upside") is not None, f"{c['ticker']} missing DCF"
        assert c.get("current_price"), f"{c['ticker']} missing price"
    assert d.get("summary"), "empty summary"
    print(f"PASS idea-sourcing: candidates={tickers} route={d.get('model_route')} "
          f"shortlist={len(d.get('shortlist', []))}")
    print(f"     summary: {d['summary'][:120]}")


if __name__ == "__main__":
    run()
