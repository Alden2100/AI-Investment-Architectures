"""research-update-generator: periodic updates on portfolio/watchlist companies. Hybrid model skill."""
import argparse
import json as _json
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

from imdata import skillkit, universe, news, estimates, prices
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "whats_new": {"type": "string", "description": "What happened over the period"},
                    "so_what": {"type": "string", "description": "Why it matters for the thesis"},
                },
                "required": ["ticker", "whats_new", "so_what"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph portfolio-level summary"},
    },
    "required": ["updates", "summary"],
}

SYSTEM = (
    "You are a buy-side analyst writing a periodic update on portfolio/watchlist names. For each "
    "company, summarize what's new from the provided news, consensus, and price move, then say why "
    "it matters. Quote all figures exactly as provided and do not invent news or numbers."
)


def _round(x):
    return round(x, 4) if x is not None else None


def _price_move(ticker, lookback):
    rows = prices.get_history(ticker, lookback_days=lookback) or []
    if len(rows) < 2:
        return None
    first = rows[0].get("close")
    last = rows[-1].get("close")
    if not first or not last:
        return None
    return {"start": first, "end": last, "pct_change": _round((last - first) / first)}


def main(args):
    lookback = getattr(args, "lookback", 30) or 30
    per_ticker = []
    for raw in args.tickers:
        ticker = raw.strip().upper()
        if not ticker:
            continue
        info = universe.resolve(ticker)
        headlines = []
        for r in (news.get_news(ticker, lookback_days=lookback) or [])[:6]:
            d = skillkit.as_dict(r)
            headlines.append({"title": d.get("title"), "published": d.get("published")})
        cons = estimates.get_consensus(ticker) or {}
        per_ticker.append({
            "ticker": info.get("ticker", ticker),
            "company": info.get("title"),
            "price_move": _price_move(ticker, lookback),
            "consensus": {
                "price_target": cons.get("price_target"),
                "recommendation": cons.get("recommendation"),
                "forward_eps": cons.get("forward_eps"),
                "forward_pe": cons.get("forward_pe"),
            },
            "headlines": headlines,
        })

    if not per_ticker:
        raise ValueError("Provide at least one ticker via --tickers.")

    prompt = (
        f"Write a {lookback}-day research update for these names. For each, capture what's new and "
        "why it matters; then a portfolio-level summary.\n\n"
        "DATA (computed in Python — quote exactly, do not recompute):\n"
        + _json.dumps(per_ticker, default=str)[:30000]
    )
    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=2800)
    meta = {"lookback_days": lookback,
            "tickers": [t["ticker"] for t in per_ticker],
            "data": per_ticker}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Produce periodic updates on portfolio/watchlist companies.")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--lookback", type=int, default=30)
    skillkit.run(main, p)
