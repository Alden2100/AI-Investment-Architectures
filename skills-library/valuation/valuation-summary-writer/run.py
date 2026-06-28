"""valuation-summary-writer: summarize valuation findings and key assumptions. Hybrid model skill."""
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

from imdata import skillkit, finviz, estimates, prices, macro, universe
from imrouter import route as _route

# finviz fundament labels we care about for a valuation snapshot.
_FINVIZ_KEYS = ["P/E", "Forward P/E", "PEG", "P/S", "P/B", "P/FCF", "P/C",
                "EV/EBITDA", "EPS next 5Y", "Sales past 5Y", "ROE", "ROIC",
                "Dividend %", "Target Price", "Market Cap"]

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "methods": {"type": "array", "items": {"type": "string"},
                    "description": "Valuation methods considered, e.g. 'Forward P/E multiple', 'Consensus DCF/target', 'PEG'"},
        "key_assumptions": {"type": "array", "items": {"type": "string"},
                            "description": "The assumptions driving the value, e.g. growth, discount rate / risk-free, exit multiple"},
        "value_range": {"type": "string", "description": "An indicative fair-value range or target, grounded in the inputs"},
        "summary": {"type": "string", "description": "One-paragraph plain-English valuation summary"},
    },
    "required": ["ticker", "methods", "key_assumptions", "value_range", "summary"],
}

SYSTEM = (
    "You are an equity research analyst writing a concise valuation summary. Use the provided "
    "multiples, consensus price target/growth, current price, and risk-free rate. State the methods "
    "you lean on (multiple-based and consensus/DCF-style), the key assumptions (growth, discount rate "
    "anchored on the risk-free rate plus an equity risk premium, exit multiple), and an indicative "
    "value range. Quote every figure exactly as provided; do not invent numbers. Where an input is "
    "missing, say so rather than guessing."
)


def main(args):
    info = universe.resolve(args.ticker)

    stats = {}
    try:
        ks = finviz.key_stats(args.ticker) or {}
        stats = {k: ks.get(k) for k in _FINVIZ_KEYS if ks.get(k) not in (None, "", "-")}
    except Exception:
        stats = {}

    cons = {}
    target = None
    growth = None
    try:
        cons = estimates.get_consensus(args.ticker) or {}
        target = (cons.get("price_target") or {}).get("mean") or (cons.get("price_target") or {}).get("median")
        growth = estimates.consensus_growth(cons)
    except Exception:
        cons = {}

    last = None
    try:
        last = prices.last_price(args.ticker)
    except Exception:
        last = None

    rfr = None
    try:
        rfr = macro.risk_free_rate("10y")
    except Exception:
        rfr = None

    inputs = {
        "last_price": last,
        "consensus_target": target,
        "consensus_growth_next_fy": growth,
        "forward_pe": cons.get("forward_pe"),
        "trailing_pe": cons.get("trailing_pe"),
        "peg": cons.get("peg"),
        "risk_free_rate_10y": rfr,
        "finviz_multiples": stats,
    }
    inputs = {k: v for k, v in inputs.items() if v not in (None, {}, "")}

    import json as _json
    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n\n"
        f"Valuation inputs (computed/fetched in Python, quote exactly):\n"
        f"{_json.dumps(inputs, indent=2, default=str)}\n\n"
        "Write the valuation summary: list the methods, the key assumptions (anchor the discount "
        "rate on the 10y risk-free rate plus an equity risk premium if a DCF lens is used), give an "
        "indicative value_range, and a one-paragraph summary. Compare the consensus target to the "
        "current price for upside/downside if both are present."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "inputs": inputs,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Summarize valuation findings and key assumptions for a stock.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
