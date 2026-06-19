"""position-sizer: volatility-based position sizing. Deterministic (numpy)."""
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


def _annualized_vol(ticker, lookback):
    """Annualized vol from daily log returns over the lookback window."""
    prices.refresh_prices(ticker, lookback_days=max(lookback + 35, 400))
    hist = prices.get_history(ticker, lookback_days=lookback, refresh=False)
    closes = np.array([h["close"] for h in hist if h["close"] is not None], dtype=float)
    if len(closes) < 3:
        return None
    logret = np.diff(np.log(closes))
    return float(np.std(logret, ddof=1) * np.sqrt(252))


def main(args):
    if not 0.0 <= args.conviction <= 1.0:
        raise ValueError("--conviction must be between 0 and 1.")
    if args.risk_budget <= 0:
        raise ValueError("--risk-budget must be positive.")

    ticker = None
    vol = args.volatility
    vol_note = "user-supplied"
    if vol is None:
        if not args.ticker:
            raise ValueError("Provide --volatility or --ticker to derive it.")
        info = universe.resolve(args.ticker)
        ticker = info["ticker"]
        vol = _annualized_vol(args.ticker, args.lookback)
        if vol is None or vol <= 0:
            raise ValueError("Could not derive volatility from prices; pass --volatility.")
        vol_note = f"annualized from {args.lookback}d daily log returns"
    elif args.ticker:
        ticker = universe.resolve(args.ticker)["ticker"]
    if vol <= 0:
        raise ValueError("volatility must be positive.")

    # weight = (risk_budget * conviction) / volatility, floored at 0, capped at max_weight.
    raw_weight = (args.risk_budget * args.conviction) / vol
    raw_weight = max(0.0, raw_weight)
    weight = min(raw_weight, args.max_weight)
    capped = raw_weight > args.max_weight
    dollar_size = weight * args.portfolio_value

    rationale = (
        f"weight = (risk_budget {args.risk_budget:.4f} * conviction {args.conviction:.2f}) "
        f"/ volatility {vol:.4f} = {raw_weight:.4f}"
        + (f", capped at max_weight {args.max_weight:.2f}" if capped else "")
        + f". Halving volatility doubles the weight (below the cap). Volatility {vol_note}."
    )
    summary = (
        (f"{ticker}: " if ticker else "")
        + f"suggested weight {weight:.2%} "
        + (f"(raw {raw_weight:.2%}, hit {args.max_weight:.0%} cap) " if capped else "")
        + f"= ${dollar_size:,.0f} on a ${args.portfolio_value:,.0f} book "
        + f"at {args.conviction:.0%} conviction, {args.risk_budget:.2%} risk budget, "
        + f"{vol:.1%} annualized vol."
    )
    return {
        "ticker": ticker,
        "conviction": args.conviction,
        "risk_budget": args.risk_budget,
        "volatility": round(vol, 6),
        "weight": round(weight, 6),
        "dollar_size": round(dollar_size, 2),
        "capped": capped,
        "rationale": rationale,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Volatility-based position sizing.")
    p.add_argument("--ticker", default=None)
    p.add_argument("--conviction", type=float, required=True, help="0..1")
    p.add_argument("--risk-budget", type=float, required=True, help="fraction, e.g. 0.02")
    p.add_argument("--volatility", type=float, default=None, help="annualized decimal")
    p.add_argument("--portfolio-value", type=float, default=1e7, help="USD")
    p.add_argument("--max-weight", type=float, default=0.10, help="weight cap")
    p.add_argument("--lookback", type=int, default=365, help="calendar days")
    skillkit.run(main, p)
