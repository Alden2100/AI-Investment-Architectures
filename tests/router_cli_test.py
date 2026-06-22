#!/usr/bin/env python3
"""Tests for fix #1: Claude Code CLI transport + fail-loud high-judgment routing.

Run: ./.venv/bin/python tests/router_cli_test.py
No network, no real CLI, no API key. Uses a fake `claude` shim to exercise the
subprocess transport, and toggles availability via env to exercise the engine.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "skills-library" / "_shared" / "router"))

from imrouter import claude_client, engine  # noqa: E402
from imrouter import orchestration as orch  # noqa: E402

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
_results = []


def check(name, cond):
    _results.append(bool(cond))
    print(f"  [{PASS if cond else FAIL}] {name}")


def make_fake_cli(body: str) -> str:
    """Write an executable fake `claude` that prints a print-mode JSON envelope."""
    d = tempfile.mkdtemp()
    p = Path(d) / "claude"
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(0o755)
    return str(p)


# A fake CLI that echoes a fixed `result`, asserts stdin was used, and asserts
# ANTHROPIC_API_KEY was stripped from its environment.
FAKE_BODY = r'''
import sys, json, os
stdin = sys.stdin.read()
result = {"got_stdin": bool(stdin.strip()),
          "had_api_key": "ANTHROPIC_API_KEY" in os.environ,
          "thesis": "Fake analyst thesis."}
print(json.dumps({"result": json.dumps(result), "is_error": False,
                  "session_id": "x", "total_cost_usd": 0}))
'''


def test_cli_transport():
    print("\nCLI transport (fake shim):")
    cli = make_fake_cli(FAKE_BODY)
    os.environ["CLAUDE_CLI"] = cli
    os.environ["ANTHROPIC_API_KEY"] = "sk-should-be-stripped"
    try:
        check("available() true when CLI resolves", claude_client.available())
        out = claude_client.complete("Write a thesis.", system="You are an analyst.",
                                     schema={"type": "object",
                                             "properties": {"thesis": {"type": "string"}}})
        check("parsed JSON from .result", out.get("thesis") == "Fake analyst thesis.")
        check("prompt delivered via stdin", out.get("got_stdin") is True)
        check("ANTHROPIC_API_KEY stripped from child env", out.get("had_api_key") is False)
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("CLAUDE_CLI", None)


def test_cli_error_fails_loud():
    print("\nCLI non-zero exit raises (fail loud):")
    cli = make_fake_cli('import sys\nsys.stderr.write("Invalid API key / not logged in")\nsys.exit(1)\n')
    os.environ["CLAUDE_CLI"] = cli
    try:
        raised = False
        try:
            claude_client.complete("x")
        except RuntimeError as e:
            raised = "exited 1" in str(e)
        check("complete() raises RuntimeError on non-zero exit", raised)
    finally:
        os.environ.pop("CLAUDE_CLI", None)


def test_available_false_without_cli():
    print("\navailable() without a CLI:")
    os.environ["IM_DISABLE_CLAUDE"] = "1"
    try:
        check("available() false when disabled", claude_client.available() is False)
    finally:
        os.environ.pop("IM_DISABLE_CLAUDE", None)


def test_high_judgment_fails_loud():
    print("\nHigh-judgment routing without Claude:")
    os.environ["IM_DISABLE_CLAUDE"] = "1"          # force no Claude
    os.environ.pop("IM_ALLOW_DEGRADED", None)       # degraded OFF
    try:
        res = engine.route("Draft the memo.", task="drafting", schema=None)
        check("drafting -> _needs_model (no silent qwen)", res.get("_needs_model") is True)
        check("route marked none", res.get("_route") == "none")
        # A low-tier task should still fall back to qwen if Ollama is up.
        if claude_client._resolve_cli() is None and engine.ollama_client.available():
            low = engine.route("Classify this.", task="classification",
                               schema={"type": "object",
                                       "properties": {"x": {"type": "string"}}})
            check("classification still runs on local qwen",
                  low.get("_route") == "local" and not low.get("_needs_model"))
        else:
            print("  [skip] classification check (ollama unavailable)")
    finally:
        os.environ.pop("IM_DISABLE_CLAUDE", None)


def test_degraded_opt_in():
    print("\nDegraded opt-in (IM_ALLOW_DEGRADED=1):")
    if not engine.ollama_client.available():
        print("  [skip] ollama unavailable")
        return
    os.environ["IM_DISABLE_CLAUDE"] = "1"
    os.environ["IM_ALLOW_DEGRADED"] = "1"
    try:
        res = engine.route("Draft the memo briefly in one sentence.", task="drafting",
                           schema={"type": "object",
                                   "properties": {"thesis": {"type": "string"}},
                                   "required": ["thesis"]})
        check("drafting runs on qwen when degraded allowed", res.get("_route") == "local")
        check("result flagged _degraded=True", res.get("_degraded") is True)
    finally:
        os.environ.pop("IM_DISABLE_CLAUDE", None)
        os.environ.pop("IM_ALLOW_DEGRADED", None)


def test_coherence_check():
    print("\nCoherence check (memo rec vs DCF signal):")
    # DCF -50% => bearish numbers; a BUY/OVERWEIGHT rec must be flagged.
    bearish = orch.numeric_lean(dcf_upside=-0.50)
    check("DCF -50% reads bearish", bearish == "bearish")
    warn = orch.coherence(bearish, "We rate MSFT OVERWEIGHT and a clear buy here.")
    check("BUY rec vs bearish numbers is flagged", bool(warn))
    # Consistent: SELL rec vs bearish numbers => no warning.
    ok = orch.coherence(bearish, "We recommend selling; the stock is overvalued.")
    check("SELL rec vs bearish numbers is coherent", ok == "")
    # Leading call wins: a BUY rec that also states sell-discipline ("trim if...")
    # is still bullish, so vs bearish numbers it must be flagged.
    mixed = "BUY / Overweight, a full position. Sell discipline: trim or move to Hold if ROIC falls."
    check("leading BUY beats trailing 'trim/Hold' -> bullish", orch.text_lean(mixed) == "bullish")
    check("mixed BUY rec vs bearish numbers is flagged", bool(orch.coherence(bearish, mixed)))
    # Bullish numbers + buy => coherent.
    bull = orch.numeric_lean(dcf_upside=0.40)
    check("DCF +40% reads bullish", bull == "bullish")
    check("BUY rec vs bullish numbers is coherent",
          orch.coherence(bull, "Initiate long; undervalued.") == "")
    # price-vs-range cross-check
    check("price above range reads bearish",
          orch.numeric_lean(price=100, value_range={"low": 40, "high": 60}) == "bearish")


def test_persona_loads_agent():
    print("\nPersona loads the agent role file:")
    os.environ.setdefault("IM_LIB_ROOT",
                          os.path.join(HERE, "skills-library"))
    p = orch.persona("valuation-analyst", audience="the IC")
    check("persona pulls the role mandate", "Mandate" in p or "value range" in p)
    check("persona includes the house standard", "HOUSE STANDARD" in p)
    check("persona names the audience", "the IC" in p)


if __name__ == "__main__":
    test_coherence_check()
    test_persona_loads_agent()
    test_cli_transport()
    test_cli_error_fails_loud()
    test_available_false_without_cli()
    test_high_judgment_fails_loud()
    test_degraded_opt_in()
    n_pass = sum(_results)
    print(f"\n{n_pass}/{len(_results)} checks passed")
    sys.exit(0 if all(_results) else 1)
