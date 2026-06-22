"""memo-writer: draft an investment-committee (IC) memo from research outputs. Hybrid model skill.

run.py does deterministic prep (resolve ticker; if no input-file, pull a few basics
to ground the memo) and builds the analysis request; the model writes the prose.
No new numbers are computed by the model; figures come from the provided data.
"""
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

from imdata import edgar, prices, skillkit, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "memo_sections": {
            "type": "object",
            "properties": {
                "thesis": {"type": "string"},
                "business_overview": {"type": "string"},
                "financials": {"type": "string"},
                "valuation": {"type": "string"},
                "risks": {"type": "string"},
                "recommendation": {"type": "string"},
            },
            "required": ["thesis", "business_overview", "financials",
                         "valuation", "risks", "recommendation"],
        },
        "summary": {"type": "string", "description": "One-paragraph IC-ready synopsis"},
    },
    "required": ["memo_sections", "summary"],
}

SYSTEM = (
    "You are a senior analyst writing an investment-committee memo that a portfolio "
    "manager will act on. This is client-grade work, not a summary.\n"
    "- Lead with the verdict; the IC must know your call and the core reason immediately.\n"
    "- Argue, don't list: tie every figure to what it IMPLIES for the thesis. A number "
    "with no 'so what' does not belong in the memo. Make the sections cohere into one "
    "connected argument — the thesis, financials, valuation, and risks should reinforce a "
    "single view, not read as disconnected blurbs.\n"
    "- Take a position. State where your read differs from the obvious/consensus one and "
    "why. Name the one thing that would change your mind (in 'risks' or 'recommendation').\n"
    "- Be specific and quantified; quote dollar and per-share figures EXACTLY as given. "
    "Render ratios/margins/growth as percentages (a value like 0.3615 means 36.2%), never "
    "as raw decimals.\n"
    "- Ground everything in the data provided; do NOT invent figures, events, or quotes. "
    "If a section lacks data, say what's missing rather than padding with generalities.\n"
    "- No hedging filler, no marketing language, no restating the prompt."
)

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "SalesRevenueNet"]


def _annual(ticker, tags):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["form"] == "10-K" and r["value"] is not None]
        if rows:
            return rows[0]["value"]
    return None


def main(args):
    info = universe.resolve(args.ticker)

    inputs = None
    grounding = {}
    if args.input_file:
        with open(args.input_file) as f:
            inputs = json.load(f)
    else:
        edgar.refresh_facts(info["ticker"])
        rev = _annual(info["ticker"], REVENUE_TAGS)
        ni = _annual(info["ticker"], ["NetIncomeLoss"])
        px = prices.last_price(info["ticker"])
        if rev is not None:
            grounding["revenue"] = rev
        if ni is not None:
            grounding["net_income"] = ni
        if px is not None:
            grounding["price"] = round(px, 2)

    if inputs is not None:
        data_block = ("Prior research-skill outputs (JSON):\n"
                      + json.dumps(inputs, indent=2, default=str))
    else:
        data_block = ("Grounding basics (latest annual figures and last price):\n"
                      + json.dumps(grounding, indent=2, default=str))

    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n\n{data_block}\n\n"
        "Draft an investment-committee memo. Fill every memo_sections field with a "
        "substantive, well-argued passage:\n"
        "- thesis: the call and the 2-3 pillars it rests on;\n"
        "- business_overview: what the company does and how it makes money, only as it "
        "bears on the thesis;\n"
        "- financials: read the numbers — what the margins/growth/cash flow imply, not a "
        "table in words;\n"
        "- valuation: reconcile the DCF and comps, say what the market is pricing in, and "
        "where you differ;\n"
        "- risks: the real ways this thesis is wrong, plus the single fact that would "
        "change your mind;\n"
        "- recommendation: an unambiguous call (and rough conviction/size if supportable).\n"
        "Then a one-paragraph IC-ready summary. Cite the figures above, quoted exactly. "
        "Do not introduce numbers not present in the data."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=5000)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "inputs_provided": inputs is not None,
        "grounding": grounding,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Draft an IC memo from research outputs.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--input-file", default=None,
                   help="JSON file of prior research-skill outputs (dcf, comps, etc.)")
    skillkit.run(main, p)
