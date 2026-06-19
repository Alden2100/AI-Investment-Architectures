#!/usr/bin/env python3
"""Smoke test: portfolio-monitoring runs end-to-end with a small book. Keyless.

Asserts the deterministic breach check fires the max-weight limit (NVDA=0.30 > 0.10).
"""
import json, os, subprocess, sys

SYS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ORCH = os.path.join(SYS_DIR, "orchestrator.py")


def run():
    proc = subprocess.run(
        [sys.executable, ORCH,
         "--positions", "NVDA=0.30", "MSFT=0.20", "AAPL=0.15",
         "--max-weight", "0.10"],
        capture_output=True, text=True, timeout=400)
    assert proc.returncode == 0, f"non-zero exit\n{proc.stderr[-800:]}"
    d = json.loads(proc.stdout)
    assert d["system"] == "portfolio-monitoring"
    assert len(d["positions"]) == 3
    # deterministic limit breach must be present regardless of the model
    assert any("weight" in (b.get("type", "") + b.get("detail", "")).lower()
               or "NVDA" in b.get("detail", "") for b in d["breaches"]), \
        f"expected a weight breach, got {d['breaches']}"
    assert d["exposure"].get("gross") is not None
    assert d.get("summary")
    print(f"PASS portfolio-monitoring: positions={list(d['positions'])} "
          f"breaches={len(d['breaches'])} gross={d['exposure'].get('gross')} "
          f"route={d.get('model_route')}")
    print(f"     summary: {d['summary'][:120]}")


if __name__ == "__main__":
    run()
