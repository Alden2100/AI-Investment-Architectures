"""insider-trading-monitor: monitor insider buys/sells from Form 4 and read the signal. Hybrid model skill."""
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

from imdata import skillkit, ownership, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "signal": {"type": "string", "description": "Overall insider signal, e.g. net buying / net selling / balanced / no open-market activity"},
        "net_open_market_usd": {"type": ["number", "null"], "description": "Net open-market dollar flow (buys minus sells)"},
        "recent": {"type": "array", "items": {"type": "object"},
                   "description": "The most recent insider transactions (echo the provided list)"},
        "note": {"type": "string", "description": "Caveats — Form 4 coverage is best-effort and excludes some option/grant activity"},
        "summary": {"type": "string", "description": "One-paragraph plain-English read of insider activity"},
    },
    "required": ["ticker", "signal", "summary"],
}

SYSTEM = (
    "You are an equity analyst interpreting insider (Form 4) activity. Open-market PURCHASES (code P) "
    "are a meaningful bullish signal; routine sales (code S) are weaker since insiders sell for many "
    "reasons (taxes, diversification). Read the net open-market dollar flow and the recent transactions "
    "and give a measured signal. Quote figures exactly as provided; do not invent transactions. Note "
    "that Form 4 parsing is best-effort and may miss option exercises or grants."
)


def main(args):
    info = universe.resolve(args.ticker)
    summ = ownership.insider_summary(args.ticker) or {}
    recent = ownership.insider_transactions(args.ticker, limit=12) or []

    signal = summ.get("signal", "no open-market activity")
    net = summ.get("net_open_market_usd")
    note = ("Form 4 parsing is best-effort and may not capture option exercises, grants, or 10b5-1 "
            "context; treat as directional.")

    if not recent and not summ.get("transactions"):
        return {
            "ticker": info["ticker"],
            "company": info["title"],
            "signal": "no open-market activity",
            "net_open_market_usd": None,
            "recent": [],
            "note": "No recent Form 4 insider transactions found for this ticker.",
            "summary": f"No recent insider (Form 4) transactions found for {info['title']} ({info['ticker']}).",
        }

    import json as _json
    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n\n"
        f"Insider summary (computed in Python, quote exactly):\n{_json.dumps(summ, indent=2, default=str)}\n\n"
        f"Recent transactions (newest first):\n{_json.dumps(recent[:12], indent=2, default=str)}\n\n"
        "Interpret the insider activity: read the signal and net open-market flow, then write a "
        "summary. Populate signal, net_open_market_usd, recent (echo the list), note, and summary."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "signal": signal,
        "net_open_market_usd": net,
        "recent": recent[:12],
        "note": note,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Monitor insider buys/sells from Form 4 filings.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
