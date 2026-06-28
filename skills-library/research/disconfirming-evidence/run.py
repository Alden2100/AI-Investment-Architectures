"""disconfirming-evidence: marshal tagged, cited EVIDENCE AGAINST a stock. Hybrid model skill.

Stage 6 of idea-sourcing v2 (adversarial debate pair). Emits evidence objects only —
never a thesis, recommendation, or buy/sell call.
"""
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

TAG = "disconfirming"

# Trade-direction words this evidence-only skill must never emit (even inside a
# model self-disclaimer like "states no recommendation"). We strip any sentence
# carrying one of these from the summary so the no-thesis rule holds deterministically.
import re as _re
_FORBIDDEN = _re.compile(r"\b(buy|sell|recommend\w*|attractive|overweight|underweight)\b", _re.I)


def _scrub_summary(text):
    if not isinstance(text, str) or not text:
        return text
    kept = [s for s in _re.split(r"(?<=[.;])\s+", text) if not _FORBIDDEN.search(s)]
    return " ".join(kept).strip()


REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
NET_INCOME_TAGS = ["NetIncomeLoss"]
DIMENSIONS = ["business", "financials", "moat", "growth", "valuation", "management", "risk"]

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "company": {"type": "string"},
        "evidence": {
            "type": "array",
            "description": "Tagged, cited evidence objects supporting the case AGAINST the stock "
                           "plus risks. Each item is a single piece of evidence, never a thesis or a call.",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": [TAG]},
                    "claim": {"type": "string",
                              "description": "One factual evidence claim grounded in a provided "
                                             "figure or filing fact. No buy/sell/recommend language."},
                    "citation": {"type": "string",
                                 "description": "The provided figure or filing fact this claim "
                                                "rests on (e.g. a revenue value + period, the "
                                                "consensus target, last price)."},
                    "dimension": {"type": "string", "enum": DIMENSIONS},
                    "confidence": {"type": "number",
                                   "description": "0-1 how well the cited figure supports the claim"},
                },
                "required": ["tag", "claim", "citation", "dimension"],
            },
        },
        "round": {"type": "integer"},
        "summary": {"type": "string",
                    "description": "One-paragraph neutral recap of the evidence marshalled. "
                                   "Describes the evidence; states no recommendation."},
    },
    "required": ["ticker", "company", "evidence", "round", "summary"],
}

SYSTEM = (
    "You are an evidence analyst for an adversarial investment debate. Your job is to produce "
    "EVIDENCE ONLY for the DISCONFIRMING side — the case AGAINST the stock plus its risks: "
    "deteriorating metrics, threats, red flags, and weaknesses. You do NOT write a thesis, a "
    "conclusion, or a recommendation, and you NEVER use buy/sell/recommend/attractive/overweight/"
    "underweight or any trade-direction language. Emit a list of tagged, cited evidence objects. "
    "Each object's `tag` is the fixed string \"disconfirming\"; each `claim` is one factual point; "
    "each `citation` references a provided figure (a revenue/net-income value with its period, the "
    "consensus target/PE/growth, or the last price) or a filing fact; `dimension` is one of "
    "business/financials/moat/growth/valuation/management/risk. All figures were fetched/computed "
    "in Python and must be quoted exactly — never invent numbers. If opposing points are provided "
    "to rebut, you MAY address those specific points, but still only as disconfirming evidence "
    "(facts that counter them or expose risk), never as argument, thesis, or a call."
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
        # NOTE: the analyst `recommendation` field (buy/hold/sell) is deliberately
        # omitted — this skill emits evidence only and must not echo a trade-direction
        # call into its output claims.
        cons_brief = {
            "price_target": cons.get("price_target"),
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

    mandate = None
    if getattr(args, "mandate_file", None) and os.path.isfile(args.mandate_file):
        with open(args.mandate_file) as fh:
            mandate = fh.read().strip()

    rebut = None
    if getattr(args, "rebut", None):
        try:
            rebut = _json.loads(args.rebut)
        except (ValueError, TypeError):
            rebut = args.rebut  # pass through as raw text if not valid JSON

    rnd = int(getattr(args, "round", 1) or 1)

    parts = [context]
    if mandate:
        parts.append("Mandate context (for relevance only — do not turn it into a recommendation):\n"
                     + skillkit.excerpt(mandate, max_chars=2000) + "\n")
    parts.append(
        "Marshal the DISCONFIRMING evidence (the case AGAINST this company plus its risks): "
        "deteriorating metrics, threats, and red flags, each grounded in a provided figure or "
        "filing fact. Use the revenue/net-income trend to evidence deceleration, margin pressure, "
        "or quality concerns; use the consensus target/PE/growth and last price to evidence "
        "valuation/expectations risk. Produce a list of tagged, cited evidence objects (tag must "
        "be \"disconfirming\"); set ticker, company, and "
        f"round={rnd}. Provide a neutral one-paragraph summary that simply describes the "
        "evidence gathered. The summary and every claim must avoid the words "
        "buy/sell/recommend/attractive/overweight/underweight entirely — do not even disclaim "
        "them. Do NOT write a thesis or any trade-direction language."
    )
    if rebut:
        parts.append(
            "\nThe CONFIRMING side raised these specific points. You MAY address them, but ONLY "
            "by supplying disconfirming evidence (facts that counter them or expose risk) — never "
            "as argument, thesis, or a call:\n" + _json.dumps(rebut)[:4000]
        )
    prompt = "\n".join(parts)

    analysis = _route(prompt, task="debate_generate", system=SYSTEM, schema=SCHEMA, max_tokens=2500)

    # Deterministic guard: strip any disclaimer/trade-direction sentence the model may
    # have slipped into the summary, and drop any evidence object whose claim/citation
    # carries trade-direction language. Evidence only — never a call.
    if isinstance(analysis, dict) and not analysis.get("_needs_model"):
        if "summary" in analysis:
            analysis["summary"] = _scrub_summary(analysis.get("summary"))
        ev = analysis.get("evidence")
        if isinstance(ev, list):
            analysis["evidence"] = [
                e for e in ev
                if not (isinstance(e, dict)
                        and _FORBIDDEN.search((e.get("claim", "") or "") + " " + (e.get("citation", "") or "")))
            ]

    meta["round"] = rnd
    meta["tag"] = TAG
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Marshal tagged, cited disconfirming (case-AGAINST + risks) evidence for a stock — evidence only, no thesis.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--mandate-file", dest="mandate_file",
                   help="Optional path to a MandateSpec JSON file for relevance context.")
    p.add_argument("--round", type=int, default=1,
                   help="Debate round (default 1).")
    p.add_argument("--rebut",
                   help="Optional JSON string of the OTHER side's evidence list to address in round 2.")
    skillkit.run(main, p)
