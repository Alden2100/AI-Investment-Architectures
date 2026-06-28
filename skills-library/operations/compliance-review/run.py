"""compliance-review: review communications/documents for compliance concerns. Hybrid model skill."""
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
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue": {"type": "string", "description": "What the concern is."},
                    "severity": {"type": "string", "description": "high / medium / low."},
                    "excerpt": {"type": "string", "description": "The exact problematic text, quoted."},
                    "rule": {"type": "string",
                             "description": "The compliance principle/rule implicated "
                                            "(e.g. performance-claim rules, guarantee prohibition, "
                                            "misleading statement, potential MNPI)."},
                },
                "required": ["issue", "severity", "excerpt", "rule"],
            },
        },
        "overall_risk": {"type": "string", "description": "Overall risk level: high / medium / low."},
        "summary": {"type": "string", "description": "Plain-English summary of the review."},
    },
    "required": ["flags", "overall_risk", "summary"],
}

SYSTEM = (
    "You are a compliance officer at an investment firm reviewing a communication or "
    "document for regulatory concerns. Flag, with the exact offending excerpt: performance "
    "claims lacking required context or disclosures, guarantees of returns or 'no risk' "
    "language, misleading or unbalanced statements, cherry-picked performance, omitted "
    "material risks, and anything suggesting use or disclosure of material non-public "
    "information (MNPI). Be precise and conservative: quote the text, name the rule/principle "
    "implicated, and rate severity. Do not invent issues that are not in the text; if the "
    "communication is clean, return an empty flags list and low overall_risk."
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
        raise ValueError("No input. Provide --text, --file, or pipe the communication via stdin.")

    clip = skillkit.excerpt(text, max_chars=50000)
    prompt = (
        f"Communication / document to review for compliance:\n{clip}\n\n"
        "Review for compliance concerns. Return `flags` (each with `issue`, `severity`, the "
        "exact `excerpt`, and the `rule`/principle implicated), an `overall_risk` rating, and "
        "a plain-English `summary`. If clean, return an empty flags list and low risk."
    )

    analysis = _route(prompt, task="judgment", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {"source": "pasted"}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Review communications/documents for compliance concerns.")
    p.add_argument("--text", help="Communication / document text to review.")
    p.add_argument("--file", help="Path to a file with the communication / document.")
    skillkit.run(main, p)
