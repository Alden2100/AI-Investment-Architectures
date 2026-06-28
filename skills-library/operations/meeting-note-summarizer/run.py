"""meeting-note-summarizer: turn a meeting transcript into concise structured notes. Hybrid model skill."""
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
        "attendees": {"type": "array", "items": {"type": "string"},
                      "description": "People present, as named in the transcript"},
        "topics": {"type": "array", "items": {"type": "string"},
                   "description": "Main subjects discussed"},
        "decisions": {"type": "array", "items": {"type": "string"},
                      "description": "Concrete decisions or conclusions reached"},
        "notes": {"type": "string",
                  "description": "Tight bullet-style notes of the discussion"},
        "summary": {"type": "string", "description": "One-paragraph plain-English summary"},
    },
    "required": ["topics", "summary"],
}

SYSTEM = (
    "You are an executive assistant at an investment firm. Convert the meeting transcript "
    "into concise, accurate structured notes. Only record what is actually stated; do not "
    "invent attendees, decisions, or figures. Quote any numbers exactly as they appear."
)


def _read_input(args):
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if getattr(args, "text", None):
        return args.text
    return sys.stdin.read()


def main(args):
    text = _read_input(args)
    if not text or not text.strip():
        raise ValueError("No input. Provide --text, --file, or pipe text on stdin.")
    clip = skillkit.excerpt(text, max_chars=40000)
    prompt = (
        "Summarize the following meeting transcript into structured notes. Identify the "
        "attendees, the main topics, any decisions reached, key notes, and a one-paragraph "
        "summary.\n\nTRANSCRIPT:\n" + clip
    )
    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2000)
    meta = {"source": "file" if getattr(args, "file", None) else "pasted",
            "input_chars": len(text)}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Turn a meeting transcript into concise structured notes.")
    p.add_argument("--text")
    p.add_argument("--file")
    skillkit.run(main, p)
