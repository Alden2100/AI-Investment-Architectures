"""Stage 0 — mandate-interpreter driver. Mandate text -> MandateSpec dict.

Thin: calls the `mandate-parser` leaf skill (a routed model step) and returns its
structured output. The orchestrator runs this once per run.
"""
from __future__ import annotations

from imdata import skillkit


def run(mandate_text: str) -> dict:
    out = skillkit.call_skill("mandate-parser", ["--text", mandate_text])
    if out.get("error"):
        raise RuntimeError(f"mandate-parser failed: {out['error']}")
    if out.get("_needs_model"):
        # No model rung available; surface the envelope so the caller can decide.
        return out
    out.setdefault("criteria", [])
    out.setdefault("exclusions", [])
    out.setdefault("seed_tickers", [])
    return out
