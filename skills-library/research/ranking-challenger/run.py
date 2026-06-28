"""ranking-challenger: argue that a contested ranked name's RANK position is wrong. Hybrid model skill."""
import argparse
import json
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

from imdata import skillkit
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "challenge": {"type": "string",
                      "description": "The single strongest argument that this name's RANK "
                                     "position is wrong, grounded in the provided scores/evidence."},
        "suggested_direction": {"type": "string", "enum": ["up", "down", "hold"],
                                "description": "Whether the rank likely belongs higher (up), "
                                               "lower (down), or is defensible as-is (hold)."},
        "rationale": {"type": "string",
                      "description": "Why, citing a SPECIFIC provided figure (e.g. text_score 0.25)."},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"],
                       "description": "How strong the challenge is given the evidence."},
        "summary": {"type": "string",
                    "description": "One-sentence plain-English recap of the rank challenge "
                                   "(no buy/sell/recommend language)."},
    },
    "required": ["challenge", "suggested_direction", "rationale", "confidence"],
}

SYSTEM = (
    "You are a skeptic on a diligence-ordering committee. A list of names has been RANKED "
    "for the ORDER in which a team should research them. Your job is to challenge whether ONE "
    "name's RANK POSITION is justified by its scores and evidence — argue specifically why it "
    "may be ranked too high or too low, citing the provided figures exactly (do not invent or "
    "recompute numbers). This is purely about ranking position for diligence ordering. "
    "It is NOT a buy/sell/investment call. Do NOT use recommendation language: never say buy, "
    "sell, recommend, attractive, overweight, underweight, or price target. Frame everything "
    "as 'ranked too high / too low' relative to the cohort and the score cutoff."
)


def _load_row(args):
    if args.row_file:
        with open(args.row_file, "r") as f:
            return json.load(f)
    if args.row:
        return json.loads(args.row)
    data = sys.stdin.read().strip()
    if not data:
        raise ValueError("Provide the ranked row via --row, --row-file, or stdin.")
    return json.loads(data)


def main(args):
    row = _load_row(args)
    if not isinstance(row, dict):
        raise ValueError("--row must be a JSON object describing one ranked row.")

    ticker = row.get("ticker") or "UNKNOWN"
    company = row.get("company") or ticker

    neighbors = []
    if args.neighbors:
        try:
            neighbors = json.loads(args.neighbors)
        except Exception:
            neighbors = []

    # Deterministic context the skill always knows: how this row sits vs the cutoff
    # and its neighbors. The model judges; Python frames the comparison.
    score = row.get("opportunity_score")
    cutoff_gap = None
    if args.cutoff is not None and isinstance(score, (int, float)):
        cutoff_gap = round(float(score) - float(args.cutoff), 4)

    lines = [
        f"CONTESTED RANKED ROW (challenge its RANK position, not a buy/sell call):",
        json.dumps(row, indent=2, default=str),
    ]
    if args.cutoff is not None:
        lines.append(
            f"\nScore cutoff it sits near: {args.cutoff}. "
            f"This row's opportunity_score minus the cutoff = {cutoff_gap} "
            f"(near zero => borderline; the rank is genuinely contestable)."
        )
    if neighbors:
        lines.append(
            "\nAdjacent rows for context (the names ranked just above/below it):\n"
            + json.dumps(neighbors, indent=2, default=str)
        )
    lines.append(
        "\nUsing ONLY the figures above, give the strongest single argument that this name's "
        "RANK is wrong. Note any TENSION between sub-scores (e.g. a high mandate_fit but a low "
        "text_score, or strong factor_score undermined by data_flags) and what it implies for "
        "ordering. State suggested_direction (up = belongs higher, down = belongs lower, "
        "hold = defensible), a rationale citing a specific figure, and your confidence."
    )
    prompt = "\n".join(lines)

    analysis = _route(prompt, task="debate_generate", system=SYSTEM, schema=SCHEMA, max_tokens=1200)
    meta = {
        "ticker": ticker,
        "company": company,
        "rank": row.get("rank"),
        "opportunity_score": score,
        "cutoff": args.cutoff,
        "cutoff_gap": cutoff_gap,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Challenge whether a contested ranked name's rank position is justified.")
    p.add_argument("--row", help="JSON string of the ranked row.")
    p.add_argument("--row-file", help="Path to a JSON file with the ranked row.")
    p.add_argument("--cutoff", type=float, default=None,
                   help="The score boundary the row sits near (for borderline context).")
    p.add_argument("--neighbors", help="JSON list of adjacent ranked rows for context.")
    skillkit.run(main, p)
