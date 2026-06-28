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
# The model ladder — three rungs, cheapest first. A task picks a rung; the engine
# may promote it one rung on a deterministic guard (size or low confidence).
#   qwen   -> qwen3.5:9b via Ollama   (free, on-box; high-volume mechanical work)
#   sonnet -> Claude Sonnet via CLI   (basic judgment / synthesis)
#   opus   -> Claude Opus via CLI     (hardest / client-facing judgment & drafting)
# Both Claude rungs run in-process through the Max-plan `claude -p` CLI; only the
# --model alias differs. See claude_client.py.
# --------------------------------------------------------------------------- #
LADDER = {
    "qwen":   ("local",  os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")),
    "sonnet": ("claude", os.environ.get("SONNET_MODEL", "claude-sonnet-4-6")),
    "opus":   ("claude", os.environ.get("OPUS_MODEL",   "claude-opus-4-8")),
}
_RUNG_ORDER = ["qwen", "sonnet", "opus"]
# Back-compat: old policies say `local`/`claude`; map them onto the ladder so they
# behave unchanged (`claude` was the firm's Opus judgment model).
_ALIAS = {"local": "qwen", "claude": "opus"}

# The opus rung is the high-judgment tier: it fails loud (_needs_model) when no
# Claude session exists, rather than silently degrading to qwen, unless degraded
# mode is opted in (IM_ALLOW_DEGRADED=1 or policy allow_degraded: true).
HIGH_JUDGMENT_RUNG = "opus"
# Legacy export (task names) — some callers/tests still reference the task set.
HIGH_JUDGMENT = frozenset({"reasoning", "synthesis", "drafting", "judgment"})

# Cheap task types must never sit on a paid rung absent an explicit escalation.
CHEAP_TASKS = frozenset({"classification", "extraction", "screening", "summarization"})
PAID_RUNGS = frozenset({"sonnet", "opus"})

# Length-guard thresholds (estimated input tokens ≈ chars/4). A nominally cheap
# step over the small model's useful window (a full 10-K / long transcript) gets
# promoted before the call.
QWEN_MAX_TOKENS = int(os.environ.get("QWEN_MAX_TOKENS", "32000"))  # speed profile: was 24000. A
# larger cheap-rung window means fewer prompts trip the length guard or return low-confidence and
# re-run on a higher rung. Set QWEN_MAX_TOKENS=24000 to restore the token-thrifty profile.
SONNET_MAX_TOKENS = int(os.environ.get("SONNET_MAX_TOKENS", "150000"))

DEFAULT_POLICY = {
    "default": "opus",
    "allow_local_fallback": True,   # if a Claude rung is down, use qwen rather than stall
    "allow_claude_fallback": True,  # if qwen is down, step up to a Claude rung
    "allow_degraded": False,        # allow qwen to stand in for the opus rung
    "routes": {
        "classification": "qwen",
        "extraction": "qwen",
        "screening": "qwen",
        "summarization": "qwen",
        "synthesis": "sonnet",
        "reasoning": "sonnet",
        "drafting": "opus",
        "judgment": "opus",
    },
}


def _bump(rung: str) -> str:
    """Next rung up, capped at opus."""
    i = _RUNG_ORDER.index(rung)
    return _RUNG_ORDER[min(i + 1, len(_RUNG_ORDER) - 1)]


def resolve_rung(task: str, pol: dict) -> str:
    """The base rung for a task under a policy (before any escalation). Pure."""
    raw = pol["routes"].get(task, pol.get("default", "opus"))
    rung = _ALIAS.get(raw, raw)
    return rung if rung in LADDER else "opus"


def _length_promote(rung: str, est_tokens: int):
    """Promote a rung while the estimated prompt exceeds that rung's window. Caps at
    opus, returns (rung, reason|None)."""
    reason = None
    while rung != "opus":
        cap = QWEN_MAX_TOKENS if rung == "qwen" else SONNET_MAX_TOKENS
        if est_tokens > cap:
            rung, reason = _bump(rung), "length"
        else:
            break
    return rung, reason


def _invalid_reason(out: dict, schema: Optional[dict]) -> Optional[str]:
    """Why a model result is unusable (for the post-call escalation guard), or None.
    Returns 'invalid_schema' | 'low_confidence'."""
    if not isinstance(out, dict) or out.get("_needs_model"):
        return None  # missing-model is handled separately, not an escalation trigger
    real = {k: v for k, v in out.items() if not k.startswith("_")}
    if not real:
        return "low_confidence"
    if schema:
        for k in (schema.get("required") or []):
            if k not in real or real[k] in (None, "", [], {}):
                return "invalid_schema"
    return None


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


# In-process routing ledger — every dispatch appends here so an orchestrator can
# report which rung (qwen / sonnet / opus) actually ran each task. This is what makes
# the "some qwen, some sonnet, some opus" claim verifiable: if a run shows one model
# for everything (or all needs_model), the ladder didn't engage.
_LEDGER: list = []


def ledger() -> list:
    return list(_LEDGER)


def reset_ledger() -> None:
    _LEDGER.clear()


def _log(decision: dict) -> None:
    _LEDGER.append({k: decision.get(k) for k in
                    ("task", "rung", "chosen_rung", "route", "model", "result", "reason")})
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


def _resolve_availability(rung: str, pol: dict, allow_degraded: bool):
    """Pick the rung that will actually run, honoring availability + fallback policy.
    Returns (chosen_rung|None, degraded, reason|None). reason names an availability
    fallback ('local_unavailable' when qwen is down and we step up to Claude)."""
    kind = LADDER[rung][0]
    if kind == "local":
        if ollama_client.available():
            return rung, False, None
        # qwen down: step up to a Claude rung rather than stall (availability fallback).
        if claude_client.available() and pol.get("allow_claude_fallback", True):
            return "sonnet", False, "local_unavailable"
        return None, False, None
    # a Claude rung (sonnet / opus)
    if claude_client.available():
        return rung, False, None
    high = (rung == HIGH_JUDGMENT_RUNG)
    if (ollama_client.available() and pol.get("allow_local_fallback", True)
            and (not high or allow_degraded)):
        # qwen stands in for a Claude rung — quality is capped; flag it.
        return "qwen", True, None
    return None, False, None


def _dispatch(prompt, *, rung, system, schema, max_tokens, model):
    """Run one model call on a concrete rung. Returns the populated output dict.
    Raises on transport failure (caller logs + decides)."""
    kind, model_id = LADDER[rung]
    if kind == "local":
        out = ollama_client.complete(prompt, system=system, schema=schema, max_tokens=max_tokens)
        out.setdefault("_source", "ollama")
        out["_route"], out["_rung"], out["_model"] = "local", rung, ollama_client.MODEL
    else:
        out = claude_client.complete(prompt, system=system, schema=schema,
                                     max_tokens=max_tokens, model=model or model_id)
        out.setdefault("_source", "cli")
        out["_route"], out["_rung"], out["_model"] = "claude", rung, (model or model_id)
    return out


def _attempt(prompt, *, task, target_rung, system, schema, max_tokens, model, pol,
             allow_degraded, reason):
    """One ladder attempt: resolve availability, dispatch, log. Returns the output
    dict (which may be a `_needs_model` envelope)."""
    chosen, degraded, avail_reason = _resolve_availability(target_rung, pol, allow_degraded)
    reason = reason or avail_reason
    base = {"task": task, "rung": target_rung, "chosen_rung": chosen,
            "route": (LADDER[chosen][0] if chosen else "none"),
            "degraded": degraded}
    if reason:
        base["reason"] = reason

    if chosen is None:
        high = (target_rung == HIGH_JUDGMENT_RUNG)
        if high:
            _log({**base, "result": "needs_model", "level": "WARNING"})
            sys.stderr.write(
                f"[router] WARNING: opus-rung task '{task}' has no Claude session and "
                "degraded mode is off — emitting deterministic output with NO model "
                "narrative. Run `claude login` (Max plan), or set IM_ALLOW_DEGRADED=1.\n")
        else:
            _log({**base, "result": "needs_model"})
        return {"_needs_model": True, "system": system, "prompt": prompt,
                "schema": schema, "_route": "none", "_rung": target_rung, "_degraded": False}

    try:
        out = _dispatch(prompt, rung=chosen, system=system, schema=schema,
                        max_tokens=max_tokens, model=model)
        out["_degraded"] = degraded
        if degraded:
            sys.stderr.write(
                f"[router] WARNING: opus-rung task '{task}' ran DEGRADED on "
                f"{out.get('_model')} (qwen stand-in), not Claude. Output quality is "
                "capped — not analyst-grade. Run `claude login`.\n")
        _log({**base, "model": out.get("_model"), "result": "ok"})
        return out
    except Exception as e:  # noqa: BLE001
        high = (target_rung == HIGH_JUDGMENT_RUNG)
        _log({**base, "result": "error", "level": "WARNING" if high else "info",
              "error": f"{type(e).__name__}: {e}"})
        if high and LADDER[chosen][0] == "claude":
            sys.stderr.write(f"[router] WARNING: Claude route failed for '{task}': {e}\n")
        return {"_needs_model": True, "system": system, "prompt": prompt,
                "schema": schema, "_route": LADDER[chosen][0], "_rung": chosen,
                "_degraded": False, "_error": str(e)}


def route(prompt: str, *, task: str, system: str = "", schema: Optional[dict] = None,
          max_tokens: int = 3000, policy=None, model: Optional[str] = None) -> dict:
    """Dispatch one model call per (task, policy), choosing a ladder rung and
    promoting it one rung on a deterministic guard (size pre-call, low confidence
    post-call). See module docstring for the return shape."""
    pol = load_policy(policy)
    allow_degraded = (os.environ.get("IM_ALLOW_DEGRADED") == "1"
                      or pol.get("allow_degraded", False))

    base_rung = resolve_rung(task, pol)
    # --- pre-call length guard: a too-big prompt promotes the rung ----------- #
    est = (len(prompt) + len(system or "")) // 4
    target_rung, length_reason = _length_promote(base_rung, est)

    out = _attempt(prompt, task=task, target_rung=target_rung, system=system, schema=schema,
                   max_tokens=max_tokens, model=model, pol=pol, allow_degraded=allow_degraded,
                   reason=length_reason)

    # --- post-call confidence/validity guard: retry once, one rung up -------- #
    chosen_rung = out.get("_rung")
    if (not out.get("_needs_model") and chosen_rung in _RUNG_ORDER and chosen_rung != "opus"):
        why = _invalid_reason(out, schema)
        if why:
            retry = _attempt(prompt, task=task, target_rung=_bump(chosen_rung), system=system,
                             schema=schema, max_tokens=max_tokens, model=model, pol=pol,
                             allow_degraded=allow_degraded, reason=why)
            if not retry.get("_needs_model") and not _invalid_reason(retry, schema):
                return retry
    return out
