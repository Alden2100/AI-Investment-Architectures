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
import re
import sys
import time


def now_stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())


# --------------------------------------------------------------------------- #
# Analyst persona / house standard. The judgment layer was being given one-liner
# system prompts ("You are a valuation analyst. Decisive, brief.") with no
# audience, no rubric — which caps quality even on a strong model. persona() loads
# the reusable agent ROLE file (skills-library/agents/<role>.md — these were never
# actually loaded into any prompt before) and layers a named audience + a writing
# rubric that targets the exact failure modes: tautological theses, number-dumps
# with no "so what", hedging filler, invented figures.
# --------------------------------------------------------------------------- #
HOUSE_STANDARD = """\
HOUSE STANDARD — how we write (this is what separates analyst-grade work from a generic summary):
- Lead with the verdict. The reader must know your call and why from the first sentence.
- Argue, don't list. Tie every number to what it IMPLIES for the thesis — a figure with no "so what" is noise. Connect cause to effect.
- Be specific and quantified. Cite the exact figure and period; never "strong" or "solid" on its own.
- Render ratios, margins, and growth as PERCENTAGES (a value like 0.3615 means 36.2%), never as raw decimals. Quote dollar and per-share figures exactly as given.
- Take a differentiated view. Where your read differs from the obvious or consensus interpretation, say so and why. A note with no edge is not worth writing.
- Name the swing factor. State the single thing that would change your mind, concretely enough to monitor.
- Ground everything in the data provided. Do NOT invent figures, events, guidance, or quotes; if something material is missing, say so plainly rather than guessing.
- No filler. No hedging boilerplate, no marketing language, no restating the prompt. Every sentence earns its place."""

_AGENT_CACHE: dict = {}


def _load_agent(role: str) -> str:
    """Return the body (frontmatter stripped) of skills-library/agents/<role>.md,
    or '' if unavailable. Cached per process."""
    if role in _AGENT_CACHE:
        return _AGENT_CACHE[role]
    body = ""
    root = os.environ.get("IM_LIB_ROOT")
    if root:
        path = os.path.join(root, "agents", f"{role}.md")
        try:
            raw = open(path, encoding="utf-8").read()
            raw = re.sub(r"^---\n.*?\n---\n", "", raw, count=1, flags=re.DOTALL)
            # Drop the machine-facing Contract block — it's I/O wiring, not guidance.
            raw = re.split(r"\n##\s+Contract\b", raw, maxsplit=1)[0]
            body = raw.strip()
        except OSError:
            body = ""
    _AGENT_CACHE[role] = body
    return body


def persona(role: str, *, audience: str, json_only: bool = False,
            extra: str = "") -> str:
    """Compose a rich analyst system prompt: the agent role file + a named
    audience + the house writing standard. Use as the ``system=`` for a drafting/
    judgment synthesize call instead of a one-line persona."""
    base = _load_agent(role) or f"You are a senior {role.replace('-', ' ')}."
    parts = [base, f"\nYOUR AUDIENCE: {audience}. Write directly for them, at their level.",
             HOUSE_STANDARD]
    if extra:
        parts.append(extra.strip())
    if json_only:
        parts.append("Return ONLY the single JSON object the schema describes, every "
                     "field filled with substantive content — no preamble, no fences.")
    return "\n\n".join(parts)


def report(*, classification="Internal", as_of=None, assumptions=None, provenance=None,
           commentary=None, bluf="", risks=None, falsifiers=None):
    """Package the Universal Report Contract envelope the PDF renders.

    Deterministic pieces (assumptions/provenance/commentary/as_of) make the report
    defensible on a buy-side desk; bluf/risks/falsifiers carry the view. Every field
    is optional and rendered only if present.
    """
    return {
        "run_at": now_stamp(),
        "classification": classification,
        "as_of": as_of or {},
        "assumptions": assumptions or [],     # [{param, value, why}]
        "provenance": provenance or [],       # [{figure, source, as_of}]
        "commentary": commentary or [],       # [{skill, note}]
        "bluf": bluf or "",                   # executive summary (verdict, BLUF)
        "risks": risks or [],                 # [str]
        "falsifiers": falsifiers or [],       # [str] monitoring triggers
    }


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


def numeric_lean(dcf_upside=None, price=None, value_range=None, band=0.15) -> str:
    """The directional lean implied by the NUMBERS (deterministic): 'bullish' /
    'bearish' / 'neutral'. Uses DCF upside primarily; price-vs-value-range as a
    cross-check. This is the anchor the model's recommendation must not contradict."""
    votes = []
    if isinstance(dcf_upside, (int, float)):
        votes.append("bullish" if dcf_upside >= band else
                     "bearish" if dcf_upside <= -band else "neutral")
    if isinstance(price, (int, float)) and isinstance(value_range, dict):
        lo, hi = value_range.get("low"), value_range.get("high")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            votes.append("bearish" if price > hi else "bullish" if price < lo else "neutral")
    if not votes:
        return "neutral"
    if "bullish" in votes and "bearish" not in votes:
        return "bullish"
    if "bearish" in votes and "bullish" not in votes:
        return "bearish"
    return "neutral"


_BULL_RE = re.compile(r"\b(buy|overweight|accumulate|add to|initiate|long|outperform|"
                      r"attractive|undervalued|compelling)\b", re.I)
_BEAR_RE = re.compile(r"\b(sell|underweight|trim|reduce|avoid|short|exit|"
                      r"overvalued|expensive|unattractive)\b", re.I)


def text_lean(text: str) -> str:
    """The directional lean a recommendation's PROSE expresses: 'bullish' /
    'bearish' / 'neutral'. When both directions appear (e.g. a BUY call that also
    states sell-discipline like "trim if..."), the LEADING call wins — a memo leads
    with its recommendation, and incidental risk/sell-discipline language later
    shouldn't neutralize it."""
    if not isinstance(text, str) or not text.strip():
        return "neutral"
    bm, rm = _BULL_RE.search(text), _BEAR_RE.search(text)
    if bm and not rm:
        return "bullish"
    if rm and not bm:
        return "bearish"
    if bm and rm:
        return "bullish" if bm.start() < rm.start() else "bearish"
    return "neutral"


def coherence(numeric: str, rec_text: str) -> str:
    """Return a warning string if the recommendation prose directionally
    contradicts the numbers, else ''. (e.g. memo says BUY while DCF says -50%.)"""
    spoken = text_lean(rec_text)
    if {numeric, spoken} == {"bullish", "bearish"}:
        return (f"COHERENCE: the recommendation reads {spoken.upper()} but the numbers "
                f"point {numeric.upper()} (e.g. DCF/price). The call must be reconciled "
                "with the valuation or explicitly justify why the model is wrong.")
    return ""


def model_meta(res: dict) -> dict:
    """Provenance for the narrative model step, so a qwen/degraded run is never
    mistaken for Claude. Spread into an orchestrator's output dict alongside the
    deterministic fields:  ``**orch.model_meta(brief)``.

    Returns ``{model_route, model_id, degraded}``:
      * model_route — "claude" | "local" | "none"
      * model_id    — the concrete model (e.g. claude-opus-4-8, qwen3.5:9b)
      * degraded    — True when qwen stood in for a high-judgment Claude route
    """
    res = res or {}
    return {
        "model_route": res.get("_route", "none"),
        "model_id": res.get("_model"),
        "degraded": bool(res.get("_degraded")),
    }


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


def synthesize_fields(prompt, keys, *, task, schema, system="", max_tokens=2000,
                      retry_prompt=None, retry_system=None):
    """Run the final model step, recover `keys`, and retry once if it comes back empty.

    Returns ``(result, fields)`` where ``fields`` is the recovered dict (or None if no
    model was available). The retry uses a terser prompt — the local 9B model often
    succeeds on a smaller, higher-signal second attempt. This is the standard way an
    orchestrator gets reliable structured narration out of a keyless run.
    """
    res = synthesize(prompt, task=task, system=system, schema=schema, max_tokens=max_tokens)
    if res.get("_needs_model"):
        return res, None
    fields = recover(res, keys)
    if not any((fields or {}).values()) and retry_prompt:
        res = synthesize(retry_prompt, task=task, schema=schema,
                         system=retry_system or system, max_tokens=max(1200, max_tokens - 400))
        fields = recover(res, keys)
    return res, fields


def write_output(name: str, obj: dict) -> str:
    """No-op by design: orchestrators stream their result as JSON on stdout (consumed
    by the front door), and the only on-disk deliverable is a PDF — produced solely
    when the user asks for one. We deliberately do NOT litter data/output with JSON.
    Set IM_WRITE_JSON=1 to opt back into a single stable <name>.json for debugging."""
    if os.environ.get("IM_WRITE_JSON") != "1":
        return ""
    out_dir = os.path.join(os.environ.get("TOOLBOX_CACHE_DIR", "."), "output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}.json")
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
