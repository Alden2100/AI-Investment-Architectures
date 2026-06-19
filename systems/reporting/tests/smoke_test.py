#!/usr/bin/env python3
"""Smoke test: reporting drafts an IC memo end-to-end. Keyless (qwen drafts)."""
import json, os, subprocess, sys

SYS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ORCH = os.path.join(SYS_DIR, "orchestrator.py")


def run():
    proc = subprocess.run([sys.executable, ORCH, "--memo", "MSFT"],
                          capture_output=True, text=True, timeout=500)
    assert proc.returncode == 0, f"non-zero exit\n{proc.stderr[-800:]}"
    d = json.loads(proc.stdout)
    assert d["system"] == "reporting" and d["kind"] == "memo" and d["ticker"] == "MSFT"
    assert "dcf" in d["inputs_used"] and "comps" in d["inputs_used"]
    # qwen route should produce sections; if no model at all, needs_model is acceptable
    assert d.get("memo_sections") or d.get("needs_model"), "no memo and not flagged needs_model"
    assert d.get("summary")
    sec = d.get("memo_sections") or {}
    print(f"PASS reporting(memo): MSFT inputs={d['inputs_used']} route={d.get('model_route')} "
          f"sections={list(sec.keys()) if isinstance(sec, dict) else 'n/a'}")
    print(f"     summary: {str(d['summary'])[:120]}")


if __name__ == "__main__":
    run()
