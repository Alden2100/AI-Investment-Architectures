"""portfolio-commentary-writer: draft client-ready portfolio commentary. Hybrid model skill."""
import argparse
import json
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
        "commentary": {"type": "string",
                       "description": "Client-ready performance commentary, 2-4 paragraphs."},
        "attribution_notes": {"type": "string",
                              "description": "What drove returns: contributors and detractors."},
        "outlook": {"type": "string", "description": "Forward-looking positioning / market view."},
        "summary": {"type": "string", "description": "One-sentence executive summary."},
    },
    "required": ["commentary", "outlook", "summary"],
}

SYSTEM = (
    "You are a portfolio manager writing client-ready portfolio commentary for a "
    "performance update. Write in clear, professional, measured prose. Quote any "
    "figures (returns, weights, contributions) EXACTLY as provided in the input; "
    "never invent numbers, tickers, or events. Avoid performance guarantees, forward "
    "return promises, or language that could read as misleading. If the notes are thin, "
    "say what is known and avoid fabricating detail."
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
    perf = None
    if getattr(args, "performance", None):
        perf = args.performance
    if not (text or "").strip() and not perf:
        raise ValueError("No input. Provide --text, --file, --performance JSON, or pipe via stdin.")

    clip = skillkit.excerpt(text or "", max_chars=40000)
    parts = []
    if perf:
        parts.append("Structured performance data (JSON) — quote exactly:\n" + perf)
    if clip.strip():
        parts.append("Performance & holdings notes:\n" + clip)
    body = "\n\n".join(parts)

    prompt = (
        f"{body}\n\n"
        "Draft client-ready portfolio commentary for a performance update. Produce a "
        "`commentary` (overview of the period and results), `attribution_notes` (key "
        "contributors and detractors), an `outlook` (positioning and forward view), and a "
        "one-sentence `summary`. Use only figures present in the input."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {"source": "performance" if perf else "pasted"}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Draft client-ready portfolio commentary / performance update.")
    p.add_argument("--text", help="Performance & holdings notes as text.")
    p.add_argument("--file", help="Path to a file with performance & holdings notes.")
    p.add_argument("--performance", help="Structured performance data as a JSON string.")
    skillkit.run(main, p)
