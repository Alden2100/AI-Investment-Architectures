"""price-fetcher: price history + basic stats. Deterministic (numpy)."""
import argparse
import os
import sys

import numpy as np

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

from imdata import prices, skillkit, universe


def main(args):
    info = universe.resolve(args.ticker)
    # Fetch a little extra so we can also compute a trailing 1y return.
    fetch = prices.refresh_prices(args.ticker, lookback_days=max(args.lookback + 35, 400))
    hist = prices.get_history(args.ticker, lookback_days=args.lookback, refresh=False)
    if not hist:
        return {"ticker": info["ticker"], "error": "no price data available",
                "summary": f"No price data for {info['ticker']}."}

    closes = np.array([h["close"] for h in hist if h["close"] is not None], dtype=float)
    last = float(closes[-1])
    ret_period = float(closes[-1] / closes[0] - 1) if len(closes) > 1 else None

    # Annualized volatility from daily log returns.
    logret = np.diff(np.log(closes))
    vol = float(np.std(logret, ddof=1) * np.sqrt(252)) if len(logret) > 1 else None

    # Max drawdown over the window.
    running_max = np.maximum.accumulate(closes)
    drawdowns = closes / running_max - 1.0
    max_dd = float(drawdowns.min()) if len(drawdowns) else None

    # Trailing 1y return from the fuller cache.
    hist_1y = prices.get_history(args.ticker, lookback_days=365, refresh=False)
    c1y = [h["close"] for h in hist_1y if h["close"] is not None]
    ret_1y = float(c1y[-1] / c1y[0] - 1) if len(c1y) > 1 else None

    result = {
        "ticker": info["ticker"],
        "company": info["title"],
        "source": fetch["source"],
        "last": round(last, 4),
        "return_period": round(ret_period, 4) if ret_period is not None else None,
        "return_1y": round(ret_1y, 4) if ret_1y is not None else None,
        "annualized_volatility": round(vol, 4) if vol is not None else None,
        "max_drawdown": round(max_dd, 4) if max_dd is not None else None,
        "trading_days": len(closes),
        "lookback_days": args.lookback,
        "summary": (
            f"{info['ticker']} last ${last:,.2f}; "
            f"{args.lookback}d return {ret_period:+.1%}" if ret_period is not None else
            f"{info['ticker']} last ${last:,.2f}"
        ) + (f", 1y {ret_1y:+.1%}" if ret_1y is not None else "")
          + (f", ann. vol {vol:.1%}" if vol is not None else "")
          + (f", max drawdown {max_dd:.1%}." if max_dd is not None else "."),
    }
    if not args.no_series:
        result["prices"] = [{"date": h["date"], "close": h["close"]} for h in hist]
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch price history and basic stats.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--lookback", type=int, default=365, help="calendar days")
    p.add_argument("--no-series", action="store_true", help="omit daily series")
    skillkit.run(main, p)
