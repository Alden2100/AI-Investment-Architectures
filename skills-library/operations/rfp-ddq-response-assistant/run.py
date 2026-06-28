"""rfp-ddq-response-assistant: draft DDQ/RFP responses grounded in firm materials. Hybrid model skill."""
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
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question being answered."},
                    "draft_answer": {"type": "string", "description": "Drafted response."},
                    "needs_input": {"type": "boolean",
                                    "description": "True if firm materials lacked the facts to "
                                                   "answer and a human must supply them."},
                },
                "required": ["question", "draft_answer", "needs_input"],
            },
        },
        "summary": {"type": "string", "description": "One-sentence summary of the drafting pass."},
    },
    "required": ["responses", "summary"],
}

SYSTEM = (
    "You are drafting responses to a DDQ/RFP for an investment firm. Ground every answer in "
    "the provided firm materials (boilerplate, prior responses, fact sheets); quote figures and "
    "facts exactly as they appear there. Do NOT invent AUM, track record, personnel, policies, or "
    "any fact not present in the materials. If the materials do not contain what a question needs, "
    "write a best-effort placeholder draft AND set needs_input=true so a human fills the gap. "
    "Keep answers professional, specific, and free of return guarantees or misleading claims."
)


def _read_one(text_arg, file_arg, args):
    val = getattr(args, file_arg, None)
    if val:
        with open(val, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return getattr(args, text_arg, None) or ""


def main(args):
    questions = _read_one("questions", "questions_file", args)
    if not (questions or "").strip() and not sys.stdin.isatty():
        questions = sys.stdin.read()
    if not (questions or "").strip():
        raise ValueError("No questions. Provide --questions, --questions-file, or pipe them via stdin.")

    materials = _read_one("materials", "materials_file", args)

    q_clip = skillkit.excerpt(questions, max_chars=30000)
    m_clip = skillkit.excerpt(materials or "", max_chars=40000)
    materials_block = (
        f"Firm materials to ground answers in (quote facts exactly):\n{m_clip}\n\n"
        if m_clip.strip() else
        "No firm materials were provided. Mark every answer needs_input=true and keep drafts "
        "generic — do not invent firm-specific facts.\n\n"
    )

    prompt = (
        f"{materials_block}"
        f"Questions to answer (a DDQ/RFP):\n{q_clip}\n\n"
        "Draft a response to each question, grounded strictly in the firm materials. Return "
        "`responses` (each with the `question`, a `draft_answer`, and a `needs_input` boolean) "
        "and a one-sentence `summary`. Set needs_input=true wherever the materials lack the facts."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=3500)
    meta = {"source": "pasted", "has_materials": bool((materials or "").strip())}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Draft DDQ/RFP responses grounded in prior firm materials.")
    p.add_argument("--questions", help="DDQ/RFP questions as text.")
    p.add_argument("--questions-file", dest="questions_file", help="Path to a file with the questions.")
    p.add_argument("--materials", help="Firm boilerplate / prior materials as text.")
    p.add_argument("--materials-file", dest="materials_file", help="Path to a file with firm materials.")
    skillkit.run(main, p)
