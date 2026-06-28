"""ddq-analyzer: review a due-diligence questionnaire for gaps/concerns/inconsistencies. Hybrid model skill."""
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
        "gaps": {"type": "array", "items": {"type": "string"},
                 "description": "Missing or unanswered items / information not provided."},
        "concerns": {"type": "array", "items": {"type": "string"},
                     "description": "Red flags, weak answers, or inconsistencies to probe."},
        "strengths": {"type": "array", "items": {"type": "string"},
                      "description": "Well-answered or reassuring items."},
        "summary": {"type": "string", "description": "Plain-English assessment of the DDQ."},
    },
    "required": ["gaps", "concerns", "strengths", "summary"],
}

SYSTEM = (
    "You are an investment due-diligence analyst reviewing a completed due-diligence "
    "questionnaire (DDQ). Identify GAPS (questions unanswered, vague, or missing required "
    "detail), CONCERNS (red flags, evasive or boilerplate answers, internal inconsistencies, "
    "claims that warrant verification), and STRENGTHS (well-substantiated answers). Reason only "
    "from the provided text; do not invent facts. Be specific about which item each point refers to."
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
        raise ValueError("No input. Provide --text, --file, or pipe the DDQ via stdin.")

    clip = skillkit.excerpt(text, max_chars=60000)
    prompt = (
        f"Due-diligence questionnaire (questions and answers):\n{clip}\n\n"
        "Review this DDQ. Return `gaps` (missing/unanswered/vague items), `concerns` (red flags "
        "and inconsistencies to probe), `strengths` (well-answered items), and a plain-English "
        "`summary`. Reference specific items and reason only from the provided text."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {"source": "pasted"}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Review a due-diligence questionnaire for gaps/concerns/inconsistencies.")
    p.add_argument("--text", help="DDQ text (questions and answers).")
    p.add_argument("--file", help="Path to a file with the DDQ.")
    skillkit.run(main, p)
