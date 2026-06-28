"""action-item-extractor: pull tasks, owners, deadlines and follow-ups out of notes. Hybrid model skill."""
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
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "What needs to be done"},
                    "owner": {"type": "string", "description": "Person responsible, or 'unassigned'"},
                    "due": {"type": "string", "description": "Deadline as stated, or 'none'"},
                    "priority": {"type": "string", "description": "high / medium / low"},
                },
                "required": ["task"],
            },
        },
        "summary": {"type": "string", "description": "One-line summary of the follow-ups"},
    },
    "required": ["action_items", "summary"],
}

SYSTEM = (
    "You extract action items from meeting notes, emails, or transcripts. Capture only tasks "
    "that are actually stated or clearly implied. Attribute owners and deadlines exactly as "
    "written; use 'unassigned' or 'none' when not specified. Do not invent tasks or dates."
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
        "Extract every action item from the text below. For each, give the task, the owner "
        "(or 'unassigned'), the due date as stated (or 'none'), and a priority (high/medium/low). "
        "Then write a one-line summary.\n\nTEXT:\n" + clip
    )
    analysis = _route(prompt, task="extraction", system=SYSTEM, schema=SCHEMA, max_tokens=2000)
    meta = {"source": "file" if getattr(args, "file", None) else "pasted",
            "input_chars": len(text)}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Extract tasks, owners, deadlines and follow-ups from notes.")
    p.add_argument("--text")
    p.add_argument("--file")
    skillkit.run(main, p)
