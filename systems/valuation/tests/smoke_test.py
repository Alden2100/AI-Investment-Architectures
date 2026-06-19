#!/usr/bin/env python3
"""Smoke test: valuation triangulates DCF/comps/scenarios for a name. Keyless."""
import json, os, subprocess, sys

SYS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ORCH = os.path.join(SYS_DIR, "orchestrator.py")


def run():
    proc = subprocess.run(
        [sys.executable, ORCH, "--ticker", "MSFT", "--peers", "AAPL", "GOOGL"],
        capture_output=True, text=True, timeout=400)
    assert proc.returncode == 0, f"non-zero exit\n{proc.stderr[-800:]}"
    d = json.loads(proc.stdout)
    assert d["system"] == "valuation" and d["ticker"] == "MSFT"
    dz = d["dossier"]
    assert dz.get("dcf_intrinsic") is not None, "no DCF value"
    assert dz.get("scenarios", {}).get("base") is not None, "no scenario value"
    assert d.get("current_price"), "no price"
    assert d.get("summary")
    print(f"PASS valuation: MSFT price={d['current_price']} "
          f"dcf={dz.get('dcf_intrinsic')} scenarios={dz.get('scenarios')} "
          f"route={d.get('model_route')}")
    print(f"     summary: {d['summary'][:120]}")


if __name__ == "__main__":
    run()
