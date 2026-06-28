"""presentation-builder: convert research output into presentation-ready slides. Hybrid model skill."""
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
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Slide title."},
                    "bullets": {"type": "array", "items": {"type": "string"},
                                "description": "Concise bullet points for the slide."},
                    "notes": {"type": "string", "description": "Presenter / speaker notes."},
                },
                "required": ["title", "bullets"],
            },
        },
        "summary": {"type": "string", "description": "One-sentence summary of the deck."},
    },
    "required": ["slides", "summary"],
}

SYSTEM = (
    "You are an analyst converting research output into a presentation-ready slide deck. "
    "Each slide has a tight title, a few crisp bullets (not paragraphs), and optional "
    "presenter notes. Quote any figures exactly as provided; never invent data, tickers, "
    "or claims. Keep bullets parallel and scannable. Build a logical flow: open with the "
    "thesis/summary, then evidence, then implications/conclusion."
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
    if not (text or "").strip():
        raise ValueError("No input. Provide --text, --file, or pipe research output via stdin.")

    clip = skillkit.excerpt(text, max_chars=50000)
    title_line = f"Deck title: {args.title}\n\n" if getattr(args, "title", None) else ""
    prompt = (
        f"{title_line}Research output to convert into slides:\n{clip}\n\n"
        "Convert this into a presentation-ready slide deck. Return `slides` (each with a "
        "`title`, a short list of `bullets`, and optional presenter `notes`) and a "
        "one-sentence `summary`. Use only facts and figures present in the input."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=3500)
    meta = {"source": "pasted"}
    if getattr(args, "title", None):
        meta["title"] = args.title
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Convert research output into presentation-ready slides.")
    p.add_argument("--text", help="Research output as text.")
    p.add_argument("--file", help="Path to a file with research output.")
    p.add_argument("--title", help="Optional deck title.")
    skillkit.run(main, p)
