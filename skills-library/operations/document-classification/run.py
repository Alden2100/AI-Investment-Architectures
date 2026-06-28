"""document-classification: organize and tag a research document. Hybrid model skill."""
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
        "doc_type": {"type": "string",
                     "description": "e.g. research note / IC memo / 10-K excerpt / earnings transcript / "
                                    "news / email / DDQ / legal / other"},
        "tags": {"type": "array", "items": {"type": "string"},
                 "description": "Topical/sector/theme tags for filing and retrieval"},
        "entities": {"type": "array", "items": {"type": "string"},
                     "description": "Companies, tickers, people, or funds named"},
        "confidence": {"type": "string", "description": "high / medium / low"},
        "summary": {"type": "string", "description": "One-line description of the document"},
    },
    "required": ["doc_type", "tags", "summary"],
}

SYSTEM = (
    "You are a document-management assistant at an investment firm. Classify the document by type, "
    "assign useful filing tags, and extract named entities. Judge only from the content provided; "
    "do not invent entities or tags that are not supported by the text."
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
    clip = skillkit.excerpt(text, max_chars=30000)
    fname = getattr(args, "filename", None) or (os.path.basename(args.file) if getattr(args, "file", None) else None)
    prompt = (
        "Classify the document below for filing. Give its doc_type, a set of filing tags, the "
        "named entities (companies/tickers/people/funds), a confidence level, and a one-line "
        "summary.\n"
        + (f"Filename hint: {fname}\n" if fname else "")
        + "\nDOCUMENT:\n" + clip
    )
    analysis = _route(prompt, task="classification", system=SYSTEM, schema=SCHEMA, max_tokens=1500)
    meta = {"source": "file" if getattr(args, "file", None) else "pasted",
            "filename": fname, "input_chars": len(text)}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Classify and tag a research document for filing.")
    p.add_argument("--text")
    p.add_argument("--file")
    p.add_argument("--filename")
    skillkit.run(main, p)
