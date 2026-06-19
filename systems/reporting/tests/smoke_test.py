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
    # Pipeline must produce a draft in some form (sections / raw text) or flag needs_model.
    assert d.get("memo_sections") or d.get("draft_text") or d.get("needs_model"), \
        "no memo draft and not flagged needs_model"
    assert d.get("summary")
    sec = d.get("memo_sections") or {}
    drafted = "sections=" + str(list(sec.keys())) if isinstance(sec, dict) and sec else (
        "raw_text" if d.get("draft_text") else "needs_model")
    print(f"PASS reporting(memo): MSFT inputs={d['inputs_used']} route={d.get('model_route')} {drafted}")
    print(f"     summary: {str(d['summary'])[:120]}")


if __name__ == "__main__":
    run()
