"""portfolio-optimizer: allocation tradeoffs + rebalancing suggestions. Hybrid model skill."""
import argparse
import json
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
from imrouter import route as _route

TRADING_DAYS = 252

SCHEMA = {
    "type": "object",
    "properties": {
        "suggested": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "from": {"type": "number", "description": "current weight"},
                    "to": {"type": "number", "description": "suggested weight"},
                    "reason": {"type": "string"},
                },
                "required": ["ticker", "from", "to", "reason"],
            },
        },
        "rationale": {"type": "string",
                      "description": "Plain-English explanation of the rebalancing logic."},
        "summary": {"type": "string", "description": "One-paragraph takeaway."},
    },
    "required": ["suggested", "rationale", "summary"],
}

SYSTEM = (
    "You are a portfolio risk analyst recommending allocation adjustments. The per-name "
    "volatilities, correlation matrix, and percentage risk contributions were all computed "
    "in Python from price history and must be quoted exactly as provided; never invent or "
    "recompute figures. Recommend trims for names whose risk contribution far exceeds their "
    "weight (concentration) and adds for low-risk-contribution diversifiers, keeping total "
    "weight ~1.0. Explain each move with reference to the provided numbers."
)


def _load_holdings(args):
    raw = None
    if args.file:
        with open(args.file, "r") as f:
            raw = f.read()
    elif args.holdings:
        raw = args.holdings
    if not raw:
        raise ValueError("Provide --holdings (JSON string) or --file (path to JSON).")
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError('Holdings must be a non-empty JSON array of {"ticker","weight"}.')
    holdings = []
    for h in data:
        t = (h.get("ticker") or h.get("symbol") or "").strip()
        if not t:
            continue
        w = h.get("weight")
        holdings.append({"ticker": t, "weight": float(w) if w is not None else None})
    if not holdings:
        raise ValueError("No valid {ticker,weight} entries found.")
    return holdings


def main(args):
    holdings = _load_holdings(args)
    tickers = [universe.resolve(h["ticker"])["ticker"] for h in holdings]

    # Weights: use provided; default to equal-weight if any are missing.
    given = [h["weight"] for h in holdings]
    if any(w is None for w in given):
        weights_in = [1.0 / len(tickers)] * len(tickers)
    else:
        wsum = sum(given)
        weights_in = [w / wsum for w in given] if wsum > 0 else [1.0 / len(tickers)] * len(tickers)

    notes = []
    series = {}
    for t in tickers:
        prices.refresh_prices(t, lookback_days=max(TRADING_DAYS + 60, 400))
        hist = prices.get_history(t, lookback_days=int(TRADING_DAYS * 1.5), refresh=False)
        closes = {h["date"]: h["close"] for h in hist if h["close"] is not None}
        if len(closes) < 30:
            notes.append(f"dropped {t} (insufficient price data)")
            continue
        series[t] = closes

    kept = [t for t in tickers if t in series]
    idx = {t: i for i, t in enumerate(tickers)}
    if len(kept) < 1:
        return {
            "current": [], "suggested": [], "rationale": "",
            "summary": "Could not compute risk: " + ("; ".join(notes) or "no usable price data."),
        }

    kept_w_raw = [weights_in[idx[t]] for t in kept]
    wsum = sum(kept_w_raw)
    kept_w = [w / wsum for w in kept_w_raw] if wsum > 0 else [1.0 / len(kept)] * len(kept)

    # Align dates, daily log returns.
    common = sorted(set.intersection(*[set(series[t].keys()) for t in kept])) if len(kept) > 1 \
        else sorted(series[kept[0]].keys())
    if len(common) < 30:
        return {
            "current": [{"ticker": t, "weight": round(w, 4), "vol": None, "risk_contrib": None}
                        for t, w in zip(kept, kept_w)],
            "suggested": [], "rationale": "",
            "summary": "Too few overlapping trading days to compute risk contributions.",
        }
    price_mat = np.array([[series[t][d] for d in common] for t in kept], dtype=float)
    ret_mat = np.diff(np.log(price_mat), axis=1)  # rows = tickers

    # Annualized per-name volatility.
    daily_vol = ret_mat.std(axis=1, ddof=1)
    ann_vol = daily_vol * np.sqrt(TRADING_DAYS)

    # Covariance (annualized) and portfolio risk decomposition.
    cov = np.cov(ret_mat) * TRADING_DAYS
    if cov.ndim == 0:  # single name
        cov = np.array([[float(cov)]])
    w = np.array(kept_w, dtype=float)
    port_var = float(w @ cov @ w)
    if port_var > 0:
        marginal = cov @ w                      # marginal contribution to variance
        risk_contrib = (w * marginal) / port_var  # fraction of total portfolio variance
    else:
        risk_contrib = np.array([float("nan")] * len(kept))
    port_vol = float(np.sqrt(port_var)) if port_var > 0 else None

    current = []
    for i, t in enumerate(kept):
        rc = risk_contrib[i]
        current.append({
            "ticker": t,
            "weight": round(float(w[i]), 4),
            "vol": round(float(ann_vol[i]), 4),
            "risk_contrib": round(float(rc), 4) if np.isfinite(rc) else None,
        })

    rc_lines = "\n".join(
        f"  {c['ticker']}: weight {c['weight']:.4f}, ann_vol {c['vol']}, "
        f"risk_contribution {c['risk_contrib']}"
        for c in current
    )
    corr = np.corrcoef(ret_mat) if len(kept) > 1 else np.array([[1.0]])
    corr_obj = {a: {b: round(float(corr[i, j]), 3) for j, b in enumerate(kept)}
                for i, a in enumerate(kept)}

    prompt = (
        f"Portfolio of {len(kept)} holdings over {len(common)} trading days "
        f"(target ~{TRADING_DAYS}d). All figures computed in Python — quote exactly.\n\n"
        f"Portfolio annualized volatility: {round(port_vol, 4) if port_vol else None}\n"
        f"Per-holding (weight / annualized vol / share of total portfolio variance):\n"
        f"{rc_lines}\n\n"
        f"Return correlation matrix:\n{json.dumps(corr_obj, indent=2)}\n\n"
        + (("Notes: " + "; ".join(notes) + "\n\n") if notes else "")
        + "A holding whose risk_contribution materially exceeds its weight is a concentration "
        "source; a holding with low/negative marginal risk is a diversifier. Recommend specific "
        "trims and adds (with from/to weights summing to ~1.0) to move the book toward balanced "
        "risk contributions and lower concentration. Provide a rationale and a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "current": current,
        "portfolio_vol": round(port_vol, 4) if port_vol else None,
        "lookback_days": len(common),
        "correlation_matrix": corr_obj,
        "dropped": notes,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Evaluate allocation tradeoffs and recommend adjustments.")
    p.add_argument("--holdings", help='JSON array: [{"ticker":..,"weight":..}]')
    p.add_argument("--file", help="path to a JSON file of the same shape")
    skillkit.run(main, p)
