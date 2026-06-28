"""crm-note-generator: convert a client interaction into a structured CRM record. Hybrid model skill."""
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
        "contact": {"type": "string", "description": "Client / contact name(s), or 'unknown'."},
        "date": {"type": "string", "description": "Date of the interaction if stated, else 'unknown'."},
        "type": {"type": "string",
                 "description": "Interaction type: call / meeting / email / event / other."},
        "summary_note": {"type": "string", "description": "Concise CRM summary note of the interaction."},
        "follow_ups": {"type": "array", "items": {"type": "string"},
                       "description": "Action items / follow-ups, each as a short imperative."},
        "summary": {"type": "string", "description": "One-line summary of the record."},
    },
    "required": ["contact", "type", "summary_note", "follow_ups", "summary"],
}

SYSTEM = (
    "You are a relationship manager's assistant converting a client interaction into a "
    "structured CRM record. Extract only what is stated; do not invent names, dates, or "
    "commitments. If a field is not present in the input, use 'unknown' (or an empty list "
    "for follow_ups). Keep the summary note factual and concise."
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
        raise ValueError("No input. Provide --text, --file, or pipe the interaction via stdin.")

    clip = skillkit.excerpt(text, max_chars=30000)
    prompt = (
        f"Client interaction notes:\n{clip}\n\n"
        "Convert this into a structured CRM record: `contact`, `date`, `type`, a concise "
        "`summary_note`, a list of `follow_ups` (action items), and a one-line `summary`. "
        "Use 'unknown' for any field not stated."
    )

    analysis = _route(prompt, task="extraction", system=SYSTEM, schema=SCHEMA, max_tokens=1500)
    meta = {"source": "pasted"}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Convert a client interaction into a structured CRM record.")
    p.add_argument("--text", help="Interaction notes as text.")
    p.add_argument("--file", help="Path to a file with the interaction notes.")
    skillkit.run(main, p)
