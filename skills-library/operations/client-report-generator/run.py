"""client-report-generator: produce a client-facing investment report. Hybrid model skill."""
import argparse
import os
import sys

_here = os.path.realpath(__file__)
_root = os.environ.get("IM_LIB_ROOT", "")
if not _root:
    _d = os.path.dirname(_here)
    while _d != os.path.dirname(_d):
        if os.path.isdir(os.path.join(_d, "_shared", "data-fetch")):
            _root = _d
            break
        _d = os.path.dirname(_d)
for _p in ("data-fetch", "router", "web-search"):
    _cand = os.path.join(_root, "_shared", _p)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from imdata import skillkit
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "report": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Executive summary section."},
                "performance": {"type": "string", "description": "Performance section."},
                "positioning": {"type": "string", "description": "Current positioning / holdings section."},
                "outlook": {"type": "string", "description": "Outlook / forward view section."},
            },
            "required": ["summary", "performance", "positioning", "outlook"],
        },
        "summary": {"type": "string", "description": "One-sentence executive summary of the whole report."},
    },
    "required": ["report", "summary"],
}

SYSTEM = (
    "You are an investment professional writing a client-facing report. Produce clear, "
    "well-structured sections in measured, professional prose. Quote every figure exactly "
    "as provided; never invent returns, holdings, tickers, or events. Avoid performance "
    "guarantees and misleading language. If the input is sparse, report only what is known."
)


def _read_text(args):
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    if getattr(args, "text", None):
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def main(args):
    text = _read_text(args)
    portfolio = getattr(args, "portfolio", None)
    if not (text or "").strip() and not portfolio:
        raise ValueError("No input. Provide --text, --file, --portfolio JSON, or pipe via stdin.")

    clip = skillkit.excerpt(text or "", max_chars=40000)
    parts = []
    if portfolio:
        parts.append("Structured portfolio data (JSON) — quote exactly:\n" + portfolio)
    if clip.strip():
        parts.append("Notes / source material:\n" + clip)
    body = "\n\n".join(parts)

    prompt = (
        f"{body}\n\n"
        "Write a client-facing investment report with four sections: `summary` (executive "
        "overview), `performance`, `positioning`, and `outlook`. Also give a one-sentence "
        "top-level `summary`. Use only figures present in the input."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=3000)
    meta = {"source": "portfolio" if portfolio else "pasted"}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Create a client-facing investment report / summary.")
    p.add_argument("--text", help="Source material / notes as text.")
    p.add_argument("--file", help="Path to a file with source material.")
    p.add_argument("--portfolio", help="Structured portfolio data as a JSON string.")
    skillkit.run(main, p)
