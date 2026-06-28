"""analyst-estimate-monitor: track consensus expectations and revisions. Hybrid model skill."""
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

from imdata import skillkit, estimates, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "consensus": {"type": "object", "description": "The consensus snapshot (echo the provided numbers)"},
        "recommendation": {"type": "string", "description": "Consensus recommendation, e.g. buy / hold / sell"},
        "n_analysts": {"type": ["integer", "number", "null"], "description": "Number of analysts covering"},
        "growth": {"type": ["number", "string", "null"], "description": "Next-FY consensus revenue growth (decimal)"},
        "note": {"type": "string", "description": "Caveats — e.g. whether revision history was available"},
        "summary": {"type": "string", "description": "One-paragraph plain-English readout of expectations"},
    },
    "required": ["ticker", "recommendation", "summary"],
}

SYSTEM = (
    "You are an equity analyst summarizing the Street's consensus for a stock. Report the price "
    "target vs current price, EPS/revenue estimates, expected growth, recommendation mix, and any "
    "revision trend. Quote every figure exactly as provided; do not invent or recompute. If revision "
    "history is missing, say so plainly in the note rather than implying a trend."
)


def main(args):
    info = universe.resolve(args.ticker)
    cons = estimates.get_consensus(args.ticker) or {}
    growth = estimates.consensus_growth(cons)
    sa = {}
    try:
        sa = estimates.stockanalysis_estimates(args.ticker) or {}
    except Exception:
        sa = {}

    recommendation = cons.get("recommendation") or "n/a"
    n_analysts = cons.get("n_analysts")
    rec_trend = cons.get("recommendation_trend") or []
    note = ""
    if not rec_trend:
        note = "No analyst revision history available from the data source; only a point-in-time consensus snapshot is shown."

    if not cons and not sa:
        return {
            "ticker": info["ticker"],
            "company": info["title"],
            "consensus": {},
            "recommendation": "n/a",
            "n_analysts": None,
            "growth": None,
            "note": "No analyst consensus data available from the data source for this ticker.",
            "summary": f"No analyst consensus data available for {info['title']} ({info['ticker']}).",
        }

    import json as _json
    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n\n"
        f"Consensus (yfinance, quote exactly):\n{_json.dumps(cons, indent=2, default=str)}\n\n"
        f"Cross-check (stockanalysis.com, best-effort): {_json.dumps(sa, default=str)}\n"
        f"Next-FY consensus revenue growth (decimal): {growth}\n"
        f"Recommendation: {recommendation}; analysts covering: {n_analysts}\n"
        f"Revision-history note: {note or 'recommendation_trend table present above'}\n\n"
        "Summarize the consensus expectations and any revision signal. Populate recommendation, "
        "n_analysts, growth, note (caveats), and the consensus object echoing the key numbers."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "consensus": cons,
        "recommendation": recommendation,
        "n_analysts": n_analysts,
        "growth": growth,
        "note": note,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Track analyst consensus expectations and revisions.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
