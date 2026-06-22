"""Router engine — the MECHANISM. Policy is data, supplied per system.

`route()` takes a *task type* (what kind of cognition is needed) and a *policy*
(which route each task type should take) and dispatches the model call to either
the local qwen3.5:9b (cheap, high-volume) or Claude via the Claude Code CLI on the
user's Max-plan subscription (heavy reasoning).
The engine is identical everywhere; only the policy differs per system — this is
the PDF's mechanism-vs-policy split.

Return shape is a drop-in for the old hybrid helper, so leaf skills are unchanged
in spirit:
  * model produced output  -> {"_source": "ollama"|"api", "_route": "...", **fields}
  * no model available      -> {"_needs_model": True, "system", "prompt", "schema", "_route"}

Every routing decision is logged (file + stderr) for auditability — never stdout,
which skills reserve for their JSON result.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from . import claude_client, ollama_client

# --------------------------------------------------------------------------- #
# Default policy — the firm-wide split. Per-system router-policy.yaml overrides.
#   local  -> qwen3.5:9b via Ollama (free, on-box, appropriately scoped for 9B)
#   claude -> Claude Code CLI on the Max subscription (reasoning / synthesis /
#             final drafting / judgment). See claude_client.py.
# --------------------------------------------------------------------------- #
# High-judgment tasks: the firm routes these to Claude precisely because a 9B
# model produces "childish imitation" here. They must NOT silently degrade to
# qwen — a missing/broken Claude session should fail loud (return _needs_model)
# unless degraded mode is explicitly opted into (IM_ALLOW_DEGRADED=1, or a policy
# `allow_degraded: true`, e.g. for keyless local testing). Low-tier tasks
# (classification/extraction/screening/summarization) keep graceful fallback.
HIGH_JUDGMENT = frozenset({"reasoning", "synthesis", "drafting", "judgment"})

DEFAULT_POLICY = {
    "default": "claude",
    "allow_local_fallback": True,   # if Claude unavailable, use qwen rather than stall
    "allow_claude_fallback": True,  # if qwen unavailable, use Claude rather than stall
    "allow_degraded": False,        # allow qwen to stand in for a HIGH_JUDGMENT route
    "routes": {
        "classification": "local",
        "extraction": "local",
        "screening": "local",
        "summarization": "local",
        "reasoning": "claude",
        "synthesis": "claude",
        "drafting": "claude",
        "judgment": "claude",
    },
}


def load_policy(policy) -> dict:
    """Accept None (default), a dict, or a path to a YAML/JSON policy file.

    When ``policy is None``, the engine honors ``IM_ROUTER_POLICY`` (a path) if set
    — a system's orchestrator exports it so every model call in the run (sub-skills
    included) obeys that system's policy without threading it through every call.
    """
    if policy is None:
        env_policy = os.environ.get("IM_ROUTER_POLICY")
        if env_policy and Path(env_policy).exists():
            policy = env_policy
        else:
            return DEFAULT_POLICY
    if isinstance(policy, dict):
        merged = {**DEFAULT_POLICY, **policy}
        merged["routes"] = {**DEFAULT_POLICY["routes"], **policy.get("routes", {})}
        return merged
    # treat as a path
    p = Path(policy)
    text = p.read_text()
    try:
        import yaml  # optional dependency
        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    return load_policy(data or {})


def _log(decision: dict) -> None:
    line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       **decision})
    log_path = os.environ.get("IM_ROUTER_LOG")
    if log_path:
        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    sys.stderr.write(f"[router] {line}\n")


def route(prompt: str, *, task: str, system: str = "", schema: Optional[dict] = None,
          max_tokens: int = 3000, policy=None, model: Optional[str] = None) -> dict:
    """Dispatch one model call per (task, policy). See module docstring for shape."""
    pol = load_policy(policy)
    desired = pol["routes"].get(task, pol.get("default", "claude"))

    high_judgment = task in HIGH_JUDGMENT
    allow_degraded = (os.environ.get("IM_ALLOW_DEGRADED") == "1"
                      or pol.get("allow_degraded", False))

    claude_ok = claude_client.available()
    degraded = False  # True when qwen stands in for a HIGH_JUDGMENT Claude route
    # Resolve the actual route with graceful fallback.
    if desired == "local":
        if ollama_client.available():
            chosen = "local"
        elif claude_ok and pol.get("allow_claude_fallback", True):
            chosen = "claude"
        else:
            chosen = "none"
    else:  # desired == "claude"
        if claude_ok:
            chosen = "claude"
        # For a HIGH_JUDGMENT task, only drop to qwen if degraded mode is opted in.
        elif (ollama_client.available() and pol.get("allow_local_fallback", True)
              and (not high_judgment or allow_degraded)):
            chosen = "local"
            degraded = high_judgment
        else:
            chosen = "none"

    fell_back = chosen != desired and chosen != "none"
    base = {"task": task, "desired": desired, "chosen": chosen,
            "fell_back": fell_back, "degraded": degraded}

    if chosen == "none":
        # Fail loud for high-judgment: this is the bug the brief calls out — a
        # qwen run logged as result:"ok" was masking the missing Claude session.
        if high_judgment:
            _log({**base, "result": "needs_model", "level": "WARNING"})
            sys.stderr.write(
                f"[router] WARNING: high-judgment task '{task}' has no Claude "
                "session and degraded mode is off — emitting deterministic output "
                "with NO model narrative. Run `claude login` (Max plan), or set "
                "IM_ALLOW_DEGRADED=1 to allow the qwen stand-in.\n"
            )
        else:
            _log({**base, "result": "needs_model"})
        return {"_needs_model": True, "system": system, "prompt": prompt,
                "schema": schema, "_route": "none", "_degraded": False}

    try:
        if chosen == "local":
            out = ollama_client.complete(prompt, system=system, schema=schema,
                                         max_tokens=max_tokens)
            out.setdefault("_source", "ollama")
            out["_route"] = "local"
            out["_model"] = ollama_client.MODEL
        else:
            out = claude_client.complete(prompt, system=system, schema=schema,
                                         max_tokens=max_tokens, model=model)
            out.setdefault("_source", "cli")
            out["_route"] = "claude"
            out["_model"] = model or claude_client.DEFAULT_MODEL
        out["_degraded"] = degraded
        if degraded:
            sys.stderr.write(
                f"[router] WARNING: high-judgment task '{task}' ran DEGRADED on "
                f"{out.get('_model')} (qwen stand-in), not Claude. Output quality "
                "is capped — this is not analyst-grade. Run `claude login`.\n"
            )
        _log({**base, "model": out.get("_model"), "result": "ok"})
        return out
    except Exception as e:  # noqa: BLE001
        # A Claude route that errors is a hard failure for high-judgment work —
        # log loudly and return needs_model. Do NOT silently swap in qwen.
        level = "WARNING" if high_judgment else "info"
        _log({**base, "result": "error", "level": level,
              "error": f"{type(e).__name__}: {e}"})
        if high_judgment and chosen == "claude":
            sys.stderr.write(f"[router] WARNING: Claude route failed for '{task}': {e}\n")
        return {"_needs_model": True, "system": system, "prompt": prompt,
                "schema": schema, "_route": chosen, "_degraded": False,
                "_error": str(e)}
