"""evidence-reconciler: reconcile conflicting confirming vs disconfirming evidence into a balanced, evidence-based net read. Hybrid model skill."""
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

from imdata import skillkit, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "reconciled_view": {
            "type": "string",
            "description": "Balanced, evidence-based net read that weighs both sides on the "
                           "figures given. State what the combined evidence shows. NEVER a "
                           "thesis, rating, or buy/sell/recommendation.",
        },
        "unresolved_conflicts": {
            "type": "array",
            "description": "Genuine (not superficial) conflicts the evidence does not resolve.",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "confirming_says": {"type": "string"},
                    "disconfirming_says": {"type": "string"},
                },
                "required": ["topic", "confirming_says", "disconfirming_says"],
            },
        },
        "weight_lean": {
            "type": "string",
            "enum": ["confirming", "disconfirming", "balanced"],
            "description": "Which side the weight of evidence leans toward, or balanced.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence in the reconciled net read given the evidence quality.",
        },
    },
    "required": ["reconciled_view", "unresolved_conflicts", "weight_lean", "confidence"],
}

SYSTEM = (
    "You are reconciling opposing EVIDENCE about a company in an investment-research debate. "
    "Two sides are given: confirming evidence (supports the case) and disconfirming evidence "
    "(cuts against it). Weigh BOTH sides strictly on the figures and claims provided; do not "
    "invent data or import outside facts. Identify which conflicts are GENUINE (the two sides "
    "actually contradict on the same dimension) versus SUPERFICIAL (they address different "
    "things and only appear to conflict). Produce a balanced NET READ that is purely "
    "EVIDENCE-BASED. This is NOT a thesis and NOT a recommendation: never use buy/sell/recommend/"
    "attractive/overweight/underweight/price-target language, and do not tell anyone to take "
    "any action. Describe what the combined evidence shows and where it remains unresolved."
)


def _load_evidence(raw, file_path, label):
    """Parse an evidence list from an inline JSON string or a file path."""
    if file_path:
        with open(file_path, "r") as f:
            raw = f.read()
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        # tolerate {"confirming": [...]} or {"evidence": [...]} wrappers
        for k in (label, "evidence", "items"):
            if isinstance(data.get(k), list):
                return data[k]
        return [data]
    if not isinstance(data, list):
        raise ValueError(f"--{label} must be a JSON list of evidence items.")
    return data


def main(args):
    try:
        info = universe.resolve(args.ticker)
        ticker = info.get("ticker", args.ticker.upper())
        company = info.get("title") or ticker
    except Exception:
        ticker = args.ticker.upper()
        company = ticker

    confirming = _load_evidence(args.confirming, args.confirming_file, "confirming")
    disconfirming = _load_evidence(args.disconfirming, args.disconfirming_file, "disconfirming")

    conf_txt = skillkit.excerpt(json.dumps(confirming, indent=2), max_chars=24000)
    disc_txt = skillkit.excerpt(json.dumps(disconfirming, indent=2), max_chars=24000)

    prompt = (
        f"Company: {company} ({ticker}).\n\n"
        f"CONFIRMING evidence ({len(confirming)} items):\n{conf_txt}\n\n"
        f"DISCONFIRMING evidence ({len(disconfirming)} items):\n{disc_txt}\n\n"
        "These two evidence sides materially conflict. Reconcile them:\n"
        "1. Weigh each side on the figures/claims provided.\n"
        "2. Separate GENUINE conflicts (same dimension, real contradiction) from "
        "SUPERFICIAL ones (different dimensions that only look opposed) and list the "
        "genuine, still-unresolved conflicts.\n"
        "3. State which side the weight of evidence leans toward (or balanced) and how "
        "confident the net read is.\n"
        "4. Write a balanced, EVIDENCE-BASED reconciled_view describing what the combined "
        "evidence shows. Do NOT produce a thesis or any buy/sell/recommendation language."
    )

    analysis = _route(prompt, task="debate_reconcile", system=SYSTEM, schema=SCHEMA, max_tokens=2500)

    meta = {
        "ticker": ticker,
        "company": company,
        "confirming_count": len(confirming),
        "disconfirming_count": len(disconfirming),
        "summary": (f"Reconciled {len(confirming)} confirming vs {len(disconfirming)} "
                    f"disconfirming evidence items for {ticker} into a balanced, "
                    f"evidence-based net read."),
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Reconcile conflicting confirming vs disconfirming evidence into a balanced net read.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--confirming", help="JSON string: list of confirming-evidence items.")
    p.add_argument("--disconfirming", help="JSON string: list of disconfirming-evidence items.")
    p.add_argument("--confirming-file", dest="confirming_file",
                   help="Path to a JSON file of confirming-evidence items.")
    p.add_argument("--disconfirming-file", dest="disconfirming_file",
                   help="Path to a JSON file of disconfirming-evidence items.")
    skillkit.run(main, p)
