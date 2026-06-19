#!/usr/bin/env python3
"""Smoke test: filing-intelligence runs end-to-end on a real 10-K. Keyless."""
import json, os, subprocess, sys

SYS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ORCH = os.path.join(SYS_DIR, "orchestrator.py")


def run():
    proc = subprocess.run([sys.executable, ORCH, "--ticker", "KO", "--form", "10-K"],
                          capture_output=True, text=True, timeout=500)
    assert proc.returncode == 0, f"non-zero exit\n{proc.stderr[-800:]}"
    d = json.loads(proc.stdout)
    assert d["system"] == "filing-intelligence"
    assert d.get("filing", {}).get("accession"), "no filing retrieved"
    assert "change" in d, "no change lens"
    assert d.get("summary"), "empty summary"
    print(f"PASS filing-intelligence: {d['ticker']} {d['form']} "
          f"({d['filing']['date']}) changes={d['change'].get('raw_change_count')} "
          f"route={d.get('model_route')}")
    print(f"     summary: {d['summary'][:120]}")


if __name__ == "__main__":
    run()
