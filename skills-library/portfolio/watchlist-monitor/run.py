"""watchlist-monitor: price moves, news, upcoming earnings for prospective buys. Hybrid model skill."""
import argparse
import json
import os
import sys
from datetime import date, datetime

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

from imdata import estimates, news, prices, skillkit, universe
from imrouter import route as _route

MOVE_THRESHOLD = 0.10        # |move| >= 10% over the window is "notable"
EARNINGS_SOON_DAYS = 14      # earnings within 14 days is flagged

SCHEMA = {
    "type": "object",
    "properties": {
        "alerts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "trigger": {"type": "string",
                                "description": "price_move / news / upcoming_earnings"},
                    "detail": {"type": "string"},
                },
                "required": ["ticker", "trigger", "detail"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph digest of the watchlist."},
    },
    "required": ["alerts", "summary"],
}

SYSTEM = (
    "You are an analyst monitoring a watchlist of prospective investments. The price moves, news "
    "headlines, and earnings dates listed were computed in Python — quote them exactly and do not "
    "invent any. Produce a prioritized list of alerts (notable price moves, fresh material news, "
    "and imminent earnings) with concise details, and a summary highlighting which names warrant "
    "the closest attention."
)


def _days_until(d):
    try:
        target = datetime.strptime(d, "%Y-%m-%d").date()
        return (target - date.today()).days
    except Exception:
        return None


def _pct_move(ticker, lookback):
    prices.refresh_prices(ticker, lookback_days=max(lookback + 35, 120))
    hist = prices.get_history(ticker, lookback_days=lookback, refresh=False)
    closes = [r["close"] for r in (skillkit.as_dict(h) for h in hist) if r.get("close") is not None]
    if len(closes) < 2:
        return None, None, None
    move = (closes[-1] / closes[0]) - 1.0
    return round(move, 4), closes[0], closes[-1]


def main(args):
    tickers = [universe.resolve(t)["ticker"] for t in args.tickers if t.strip()]
    if not tickers:
        raise ValueError("Provide at least one ticker via --tickers.")
    lookback = args.lookback

    per_ticker = []
    notes = []
    for t in tickers:
        move, p0, p1 = _pct_move(t, lookback)
        headlines = []
        try:
            for it in (news.get_news(t, lookback_days=lookback) or [])[:6]:
                d = skillkit.as_dict(it)
                headlines.append({"date": d.get("published"), "title": d.get("title")})
        except Exception as e:
            notes.append(f"{t} news error: {e}")
        try:
            edate = estimates.next_earnings_date(t)
        except Exception as e:
            edate = None
            notes.append(f"{t} earnings-date error: {e}")
        days_to_earn = _days_until(edate) if edate else None

        flags = []
        if move is not None and abs(move) >= MOVE_THRESHOLD:
            flags.append(f"notable {move:+.1%} move over {lookback}d")
        if days_to_earn is not None and 0 <= days_to_earn <= EARNINGS_SOON_DAYS:
            flags.append(f"earnings in {days_to_earn}d ({edate})")

        per_ticker.append({
            "ticker": t,
            "pct_move": move,
            "price_start": p0,
            "price_last": p1,
            "next_earnings_date": edate,
            "days_to_earnings": days_to_earn,
            "headlines": headlines,
            "deterministic_flags": flags,
        })

    prompt = (
        f"Watchlist of {len(tickers)} tickers, lookback {lookback} days. All figures computed in "
        f"Python — quote exactly, do not invent.\n\n"
        f"Per ticker (pct_move over window, next earnings date / days away, recent headlines, and "
        f"deterministic flags already raised):\n{json.dumps(per_ticker, indent=2)}\n\n"
        + (("Notes: " + "; ".join(notes) + "\n\n") if notes else "")
        + f"Notable price move threshold is +/-{MOVE_THRESHOLD:.0%}; earnings within "
        f"{EARNINGS_SOON_DAYS} days is imminent. Build a prioritized alerts list "
        "(trigger = price_move / news / upcoming_earnings) with a concrete detail each, then a "
        "summary of which names warrant attention."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "tickers": tickers,
        "lookback_days": lookback,
        "by_ticker": per_ticker,
        "notes": notes,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Track prospective investments and alert on developments.")
    p.add_argument("--tickers", nargs="+", required=True, help="one or more tickers")
    p.add_argument("--lookback", type=int, default=30, help="lookback window in days")
    skillkit.run(main, p)
