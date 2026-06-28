"""ic-summary-generator: structure an investment-committee discussion into a decision summary. Hybrid model skill."""
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
        "decision": {"type": "string", "description": "The decision reached (e.g. approve / pass / size at X)"},
        "rationale": {"type": "string", "description": "Why the committee landed there"},
        "dissent": {"type": "array", "items": {"type": "string"},
                    "description": "Dissenting views or unresolved concerns raised"},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["task"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph summary of the IC outcome"},
    },
    "required": ["decision", "rationale", "summary"],
}

SYSTEM = (
    "You are the secretary of an investment committee. Summarize the IC discussion into a clear "
    "record of the decision, the rationale, any dissent, and follow-up action items. Capture only "
    "what was discussed; quote figures exactly and do not invent positions, votes, or numbers."
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
        "Summarize the following investment-committee discussion. State the decision reached, "
        "the rationale, any dissent or unresolved concerns, the follow-up action items "
        "(task/owner/due), and a one-paragraph summary.\n\nIC DISCUSSION:\n" + clip
    )
    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    meta = {"source": "file" if getattr(args, "file", None) else "pasted",
            "input_chars": len(text)}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Structure an investment-committee discussion into a decision summary.")
    p.add_argument("--text")
    p.add_argument("--file")
    skillkit.run(main, p)
