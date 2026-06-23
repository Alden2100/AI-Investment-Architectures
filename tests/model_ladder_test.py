#!/usr/bin/env python3
"""Tests for the qwen -> sonnet -> opus model ladder (Part 2).

Pure-resolution checks need no models. The live escalation/log check uses a fake
`claude` CLI whose output depends on the --model alias, so we can force a sonnet
result to fail schema and watch the confidence guard promote it to opus.

    .venv/bin/python tests/model_ladder_test.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "skills-library" / "_shared" / "router"))

from imrouter import engine  # noqa: E402

_results = []


def check(name, cond, detail=None):
    _results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail!r}"))


CHEAP = ["classification", "extraction", "screening", "summarization"]
SYS_DIR = REPO / "systems"
# Expected rung for the system's signature narrative step (guide §2.4).
EXPECTED = {
    "reporting": ("drafting", "opus"),
    "filing-intelligence": ("synthesis", "opus"),
    "due-diligence": ("reasoning", "opus"),
    "idea-sourcing": ("synthesis", "sonnet"),
    "valuation": ("reasoning", "sonnet"),
    "portfolio-monitoring": ("judgment", "sonnet"),
    "governance-audit": ("judgment", "sonnet"),
}


def test_resolution_and_cost_guard():
    print("\nRung resolution + cost guard (per-system policies):")
    for name, (task, want) in EXPECTED.items():
        pol = engine.load_policy(str(SYS_DIR / name / "router-policy.yaml"))
        got = engine.resolve_rung(task, pol)
        check(f"{name}: {task} -> {want}", got == want, got)
        # Cost guard: cheap task types resolve to qwen (never a paid rung) at base.
        for ct in CHEAP:
            r = engine.resolve_rung(ct, pol)
            check(f"{name}: cheap '{ct}' base rung is qwen (not paid)",
                  r not in engine.PAID_RUNGS and r == "qwen", r)


def test_backcompat_alias():
    print("\nLegacy local/claude policies still resolve onto the ladder:")
    pol = engine.load_policy({"routes": {"summarization": "local", "judgment": "claude"}})
    check("legacy 'local' -> qwen", engine.resolve_rung("summarization", pol) == "qwen")
    check("legacy 'claude' -> opus", engine.resolve_rung("judgment", pol) == "opus")


def test_length_guard():
    print("\nLength guard promotes one rung at a time, caps at opus:")
    small = 1000
    big = (engine.QWEN_MAX_TOKENS + 1000)
    huge = (engine.SONNET_MAX_TOKENS + 1000)
    check("qwen small stays qwen", engine._length_promote("qwen", small) == ("qwen", None))
    check("qwen over window -> sonnet (length)", engine._length_promote("qwen", big) == ("sonnet", "length"))
    check("qwen over sonnet window -> opus (length)", engine._length_promote("qwen", huge) == ("opus", "length"))
    check("sonnet over window -> opus (length)", engine._length_promote("sonnet", huge) == ("opus", "length"))


def test_invalid_reason():
    print("\nConfidence/validity guard classification:")
    schema = {"type": "object", "required": ["x"]}
    check("missing required key -> invalid_schema",
          engine._invalid_reason({"y": 1, "_route": "claude"}, schema) == "invalid_schema")
    check("empty result -> low_confidence",
          engine._invalid_reason({"_route": "claude"}, None) == "low_confidence")
    check("valid result -> None",
          engine._invalid_reason({"x": "ok", "_route": "claude"}, schema) is None)


# A fake CLI: returns a valid {x:...} object ONLY for the opus model; for any other
# model it returns an empty object — so a sonnet attempt fails the schema and the
# confidence guard must promote to opus.
FAKE_BODY = r'''
import sys, json
argv = sys.argv
model = argv[argv.index("--model") + 1] if "--model" in argv else ""
sys.stdin.read()
payload = {"x": "opus-answer"} if "opus" in model else {}
print(json.dumps({"result": json.dumps(payload), "is_error": False,
                  "session_id": "x", "total_cost_usd": 0}))
'''


def test_live_escalation_and_log():
    print("\nLive: confidence guard promotes sonnet -> opus, log carries rung+reason:")
    d = tempfile.mkdtemp()
    cli = Path(d) / "claude"
    cli.write_text("#!/usr/bin/env python3\n" + FAKE_BODY)
    cli.chmod(0o755)
    log = Path(d) / "router.jsonl"
    os.environ["CLAUDE_CLI"] = str(cli)
    os.environ["IM_ROUTER_LOG"] = str(log)
    os.environ.pop("IM_DISABLE_CLAUDE", None)
    try:
        pol = {"routes": {"synthesis": "sonnet"}}
        out = engine.route("rank these", task="synthesis",
                           schema={"type": "object", "required": ["x"]}, policy=pol)
        check("final result valid (x present)", out.get("x") == "opus-answer", out)
        check("escalated to opus rung", out.get("_rung") == "opus", out.get("_rung"))
        lines = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        rungs = [(ln.get("rung"), ln.get("reason"), ln.get("result")) for ln in lines]
        check("first attempt logged at sonnet", any(r[0] == "sonnet" for r in rungs), rungs)
        check("escalation logged at opus with reason",
              any(r[0] == "opus" and r[1] in ("invalid_schema", "low_confidence") for r in rungs), rungs)
        check("every log line names a rung", all(ln.get("rung") for ln in lines), rungs)
    finally:
        os.environ.pop("CLAUDE_CLI", None)
        os.environ.pop("IM_ROUTER_LOG", None)


def test_routing_ledger():
    print("\nRouting ledger (per-run, file-backed, cross-process):")
    from imrouter import orchestration as orch
    d = tempfile.mkdtemp()
    cli = Path(d) / "claude"
    cli.write_text("#!/usr/bin/env python3\n" + FAKE_BODY)
    cli.chmod(0o755)
    os.environ["CLAUDE_CLI"] = str(cli)
    os.environ["IM_ROUTER_LOG"] = str(Path(d) / "r.jsonl")
    os.environ.pop("IM_DISABLE_CLAUDE", None)
    try:
        orch.reset_routing_log()
        engine.route("rank", task="synthesis", schema={"type": "object", "required": ["x"]},
                     policy={"routes": {"synthesis": "sonnet"}})
        led = orch.routing_ledger()
        tasks = {e["task"] for e in led}
        check("ledger captured the synthesis task", "synthesis" in tasks, led)
        check("ledger names a model", any(e.get("model") for e in led), led)
        orch.reset_routing_log()
        check("reset clears the ledger", orch.routing_ledger() == [])
    finally:
        os.environ.pop("CLAUDE_CLI", None)
        os.environ.pop("IM_ROUTER_LOG", None)


if __name__ == "__main__":
    test_resolution_and_cost_guard()
    test_backcompat_alias()
    test_length_guard()
    test_invalid_reason()
    test_live_escalation_and_log()
    test_routing_ledger()
    n = sum(_results)
    print(f"\n{n}/{len(_results)} model-ladder checks passed")
    sys.exit(0 if all(_results) else 1)
