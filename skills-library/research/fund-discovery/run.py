"""fund-discovery: identify funds/managers matching an allocator's requirements. Hybrid model skill."""
import argparse
import json as _json
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
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

from imdata import skillkit, news
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": {"type": "string"},
                     "description": "The allocator requirements parsed from the request "
                                    "(strategy, asset class, geography, AUM, etc.)."},
        "candidates": {
            "type": "array",
            "description": "Funds/managers that plausibly fit. Each must carry honest caveats.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Fund or manager name."},
                    "strategy": {"type": "string", "description": "Strategy / asset class."},
                    "why_fit": {"type": "string", "description": "Why it matches the criteria."},
                    "caveats": {"type": "string",
                                "description": "Honest caveats: verify directly; details may be "
                                               "stale, gated, or approximate."},
                },
                "required": ["name", "strategy", "why_fit", "caveats"],
            },
        },
        "data_caveat": {"type": "string",
                        "description": "Plain statement of the data limitation: there is no "
                                       "structured fund database behind this; candidates are "
                                       "from general knowledge plus best-effort headlines and "
                                       "MUST be independently verified."},
        "summary": {"type": "string", "description": "One-paragraph wrap-up and next steps."},
    },
    "required": ["criteria", "candidates", "data_caveat", "summary"],
}

SYSTEM = (
    "You are an investment consultant helping an allocator shortlist funds/managers. There is "
    "NO structured fund database available to you: candidates come from your general knowledge "
    "plus any best-effort news headlines provided. BE HONEST about this limit — populate "
    "data_caveat clearly and attach concrete caveats to every candidate (verify directly, "
    "details may be stale or approximate, do NOT state AUM/returns as fact unless given). "
    "First restate the allocator's criteria, then propose plausible candidates with a why_fit, "
    "and never fabricate specific performance figures or fund terms."
)


def main(args):
    reqs = (args.requirements or "").strip()
    if not reqs:
        raise ValueError("Provide allocator requirements via --requirements.")

    headlines = []
    try:
        headlines = news.keyed_headlines(reqs, limit=10) or []
    except Exception:
        headlines = []

    hl_line = (
        "Best-effort news headlines for context (may be sparse or empty; treat as weak "
        "signal, not a fund database):\n"
        f"{_json.dumps(headlines)}\n" if headlines else
        "News context: none available (no keyed news provider). Rely on general knowledge "
        "and be explicit that nothing here is verified.\n"
    )

    prompt = (
        "Allocator requirements (natural language):\n"
        f"{skillkit.excerpt(reqs, max_chars=6000)}\n\n"
        f"{hl_line}\n"
        "Restate the criteria, then propose candidate funds/managers that plausibly fit, each "
        "with strategy, why_fit, and honest caveats. Fill data_caveat with the clear statement "
        "that there is no fund database behind this and every name must be independently "
        "verified. Do not fabricate AUM, returns, or fund terms. Then write a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    meta = {"requirements": reqs, "headlines": headlines}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Identify funds/managers matching an allocator's requirements.")
    p.add_argument("--requirements", required=True,
                   help="Natural-language allocator requirements.")
    skillkit.run(main, p)
