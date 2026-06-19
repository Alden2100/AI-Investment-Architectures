"""Orchestration helpers shared by every system's orchestrator.

Keeps each orchestrator.py focused on *its* deterministic control flow: the
boilerplate of env setup, the bounded final model call (routed per the system's
policy and logged), and writing the deliverable + audit entry lives here.

The PDF's spectrum in one place: orchestrators do deterministic fan-out, then call
`synthesize()` for the one bounded judgment the model is good at, then resume code.
"""
from __future__ import annotations

import json
import os
import sys
import time


def synthesize(prompt: str, *, task: str, system: str = "", schema=None,
               max_tokens: int = 3000) -> dict:
    """Run the orchestrator's final model step through the router.

    Policy comes from IM_ROUTER_POLICY (the orchestrator exports it), so this honors
    the system's Claude-vs-qwen split. The routing decision is logged by the engine.
    Returns the model's structured fields, or a `_needs_model` envelope if neither
    route is available (the caller can still emit the deterministic dossier).
    """
    from imrouter import route  # local import: sys.path is set by the orchestrator
    return route(prompt, task=task, system=system, schema=schema,
                 max_tokens=max_tokens, policy=None)


def recover(result: dict, keys) -> dict:
    """Pull named fields from a model result, even if the 9B model nested them.

    qwen sometimes returns the real payload one level down (e.g. stuffed inside a
    `summary` value, or under a renamed wrapper) instead of at the top level. This
    looks top-level first, then inside nested dicts and JSON-string values, so a
    cosmetic nesting never loses the content.
    """
    keys = tuple(keys)
    empty = (None, "", [], {})
    out = {k: result.get(k) for k in keys}
    if any(out[k] not in empty for k in keys):
        return out
    candidates = [v for v in result.values() if isinstance(v, dict)]
    for v in result.values():
        if isinstance(v, str) and v.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    candidates.append(parsed)
            except (ValueError, TypeError):
                pass
    for c in candidates:
        if any(c.get(k) not in empty for k in keys):
            return {k: c.get(k) for k in keys}
    return out


def first_list(d: dict):
    """Return the first list value in a (possibly loosely-keyed) model result.

    The local 9B model sometimes renames an array field (e.g. `shortlist` ->
    `shortlist_ranking`). Orchestrators use this to read the payload regardless,
    so a cosmetic key drift never loses real data.
    """
    if not isinstance(d, dict):
        return []
    for v in d.values():
        if isinstance(v, list):
            return v
    return []


def text_field(d: dict, *keys: str) -> str:
    """First non-empty string among the named keys (then any string value)."""
    if not isinstance(d, dict):
        return ""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    for v in d.values():
        if isinstance(v, str) and v.strip():
            return v
    return ""


def write_output(name: str, obj: dict) -> str:
    """Persist a deliverable under the system's data/output dir; return its path."""
    out_dir = os.path.join(os.environ.get("TOOLBOX_CACHE_DIR", "."), "output")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(out_dir, f"{name}-{stamp}.json")
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, default=str)
    return path


def audit(actor: str, action: str, target: str, detail: str) -> None:
    """Append a row to the system DB's audit_log (auditable, deterministic trail)."""
    try:
        from imdata import store
        store.append_audit(actor, action, target, detail)
    except Exception as e:  # never let logging break a run
        sys.stderr.write(f"[audit] skipped: {e}\n")
