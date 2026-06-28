"""bear-case-generator: construct the strongest argument AGAINST an opportunity. Hybrid model skill."""
import argparse
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

import json as _json

from imdata import skillkit, edgar, universe, estimates, prices
from imrouter import route as _route

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
NET_INCOME_TAGS = ["NetIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "thesis": {"type": "string", "description": "The core bear thesis in 1-2 sentences"},
        "key_risks": {"type": "array", "items": {"type": "string"},
                      "description": "The specific risks that drive the downside"},
        "downside_scenario": {"type": "string",
                              "description": "What the business/stock looks like if the bear "
                                             "case plays out, with the value path"},
        "what_could_break": {"type": "array", "items": {"type": "string"},
                             "description": "The triggers/fault lines that would break the "
                                            "investment"},
        "summary": {"type": "string", "description": "One-paragraph plain-English bear case"},
    },
    "required": ["ticker", "thesis", "key_risks", "downside_scenario", "summary"],
}

SYSTEM = (
    "You are a short-seller / skeptical analyst constructing the STRONGEST possible bear case "
    "for a stock — the most compelling argument AGAINST owning it, made honestly. Reason from "
    "the fundamentals (revenue and net-income trends), consensus estimates, price target, and "
    "last price provided. All figures were fetched/computed in Python and must be quoted "
    "exactly; do not invent numbers. Be specific and intellectually honest: state the thesis, "
    "the risks, the downside scenario with a value path, and what could break the investment."
)


def _annual_series(ticker, tags, n=5):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["value"] is not None and r["form"] == "10-K" and r["period_end"]]
        if rows:
            m = {}
            for r in sorted(rows, key=lambda x: x["period_end"], reverse=True):
                if r["period_end"] not in m:
                    m[r["period_end"]] = float(r["value"])
                if len(m) >= n:
                    break
            return [{"period_end": y, "value": m[y]} for y in sorted(m, reverse=True)]
    return []


def _gather(ticker):
    info = universe.resolve(ticker)
    rev = _annual_series(ticker, REVENUE_TAGS)
    ni = _annual_series(ticker, NET_INCOME_TAGS)
    cons = estimates.get_consensus(ticker)
    growth = estimates.consensus_growth(cons) if cons else None
    last_px = prices.last_price(ticker)
    cons_brief = {}
    if cons:
        cons_brief = {
            "price_target": cons.get("price_target"),
            "recommendation": cons.get("recommendation"),
            "n_analysts": cons.get("n_analysts"),
            "forward_pe": cons.get("forward_pe"),
            "forward_eps": cons.get("forward_eps"),
            "implied_growth": growth,
        }
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "revenue_series": rev,
        "net_income_series": ni,
        "consensus": cons_brief,
        "last_price": last_px,
    }
    context = (
        f"Company: {info['title']} ({info['ticker']}). Last price: {last_px}.\n\n"
        "Fundamentals computed in Python from XBRL (annual, newest first; quote exactly):\n"
        f"Revenue: {_json.dumps(rev)}\n"
        f"Net income: {_json.dumps(ni)}\n\n"
        f"Analyst consensus (fetched — quote exactly):\n{_json.dumps(cons_brief)}\n"
    )
    return info, context, meta


def main(args):
    info, context, meta = _gather(args.ticker)
    prompt = (
        f"{context}\n"
        "Construct the STRONGEST bear case. Use the revenue/net-income trend to expose "
        "deceleration, margin pressure, or quality concerns, and the consensus target/PE to "
        "argue valuation/expectations risk vs the last price. State the thesis, list the key "
        "risks, describe the downside scenario with a value path, and enumerate what could "
        "break the investment. Set ticker in your answer."
    )
    analysis = _route(prompt, task="judgment", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Construct the strongest bear case against a stock.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
