"""factor-exposure-analyzer: portfolio tilts to size/value/momentum/quality. Hybrid model skill."""
import argparse
import json
import os
import re
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

from imdata import edgar, finviz, prices, skillkit, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "factors": {
            "type": "object",
            "properties": {
                "size": {"type": "string", "description": "Interpretation of the size tilt."},
                "value": {"type": "string", "description": "Interpretation of the value tilt."},
                "momentum": {"type": "string", "description": "Interpretation of the momentum tilt."},
                "quality": {"type": "string", "description": "Interpretation of the quality tilt."},
            },
            "required": ["size", "value", "momentum", "quality"],
        },
        "summary": {"type": "string", "description": "One-paragraph plain-English style read."},
    },
    "required": ["factors", "summary"],
}

SYSTEM = (
    "You are a quantitative equity analyst interpreting a portfolio's factor exposures. The "
    "per-holding factor metrics (market cap, P/E, P/B, 12-month return, margins, ROIC) and the "
    "weighted portfolio aggregates were computed in Python and must be quoted exactly; never "
    "invent figures. Translate the aggregates into a clear read of the portfolio's style: "
    "large vs small cap, value vs growth (low P/E,P/B = value), momentum (high trailing return), "
    "and quality (high margins/ROIC). Note missing data where metrics are null."
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
    out = []
    for h in data:
        t = (h.get("ticker") or h.get("symbol") or "").strip()
        if not t:
            continue
        w = h.get("weight")
        out.append({"ticker": t, "weight": float(w) if w is not None else None})
    if not out:
        raise ValueError("No valid {ticker,weight} entries found.")
    return out


_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _parse_mcap(s):
    """Parse finviz 'Market Cap' like '2.95T' / '410.2B' -> float USD, or None."""
    if not s or s in ("-", "—"):
        return None
    m = re.match(r"^\s*([\d.]+)\s*([KMBT]?)\s*$", str(s).strip(), re.I)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2).upper()
    return val * _MULT.get(suf, 1.0)


def _parse_num(s):
    if s is None or s in ("-", "—", ""):
        return None
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def _latest_annual(ticker, tags):
    for tag in tags:
        rows = edgar.get_concept(ticker, tag)
        for r in rows:
            if r.get("form") == "10-K" and r.get("value") is not None:
                return float(r["value"])
    return None


def _momentum_12m(ticker):
    hist = prices.get_history(ticker, lookback_days=400, refresh=True)
    closes = [r["close"] for r in (skillkit.as_dict(h) for h in hist) if r.get("close") is not None]
    if len(closes) < 2:
        return None
    # ~252 trading days back, or earliest available.
    start = closes[-252] if len(closes) >= 252 else closes[0]
    if not start:
        return None
    return (closes[-1] / start) - 1.0


def _quality(ticker):
    rev = _latest_annual(ticker, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
    op = _latest_annual(ticker, ["OperatingIncomeLoss"])
    ni = _latest_annual(ticker, ["NetIncomeLoss"])
    op_margin = (op / rev) if (op is not None and rev) else None
    net_margin = (ni / rev) if (ni is not None and rev) else None
    eq = _latest_annual(ticker, ["StockholdersEquity"])
    roic = None
    if op is not None and eq:
        debt = (_latest_annual(ticker, ["LongTermDebt", "LongTermDebtNoncurrent"]) or 0.0)
        cash = (_latest_annual(ticker, ["CashAndCashEquivalentsAtCarryingValue"]) or 0.0)
        invested = eq + debt - cash
        if invested and invested > 0:
            roic = (op * 0.79) / invested  # ~21% tax assumption
    return {
        "op_margin": round(op_margin, 4) if op_margin is not None else None,
        "net_margin": round(net_margin, 4) if net_margin is not None else None,
        "roic": round(roic, 4) if roic is not None else None,
    }


def _wmean(pairs):
    """pairs = [(weight, value)]; weighted mean over non-null values, renormalized."""
    num = den = 0.0
    for wt, v in pairs:
        if v is not None and wt is not None:
            num += wt * v
            den += wt
    return round(num / den, 4) if den > 0 else None


def main(args):
    holdings = _load_holdings(args)
    tickers = [universe.resolve(h["ticker"])["ticker"] for h in holdings]
    given = [h["weight"] for h in holdings]
    if any(w is None for w in given):
        weights = [1.0 / len(tickers)] * len(tickers)
    else:
        s = sum(given)
        weights = [w / s for w in given] if s > 0 else [1.0 / len(tickers)] * len(tickers)

    by_holding = []
    for t, wt in zip(tickers, weights):
        ks = finviz.key_stats(t) or {}
        mcap = _parse_mcap(ks.get("Market Cap"))
        pe = _parse_num(ks.get("P/E"))
        pb = _parse_num(ks.get("P/B"))
        mom = _momentum_12m(t)
        q = _quality(t)
        by_holding.append({
            "ticker": t,
            "weight": round(wt, 4),
            "market_cap": mcap,
            "pe": pe,
            "pb": pb,
            "momentum_12m": round(mom, 4) if mom is not None else None,
            "op_margin": q["op_margin"],
            "net_margin": q["net_margin"],
            "roic": q["roic"],
        })

    factors_num = {
        "size_market_cap_wmean": _wmean([(h["weight"], h["market_cap"]) for h in by_holding]),
        "value_pe_wmean": _wmean([(h["weight"], h["pe"]) for h in by_holding]),
        "value_pb_wmean": _wmean([(h["weight"], h["pb"]) for h in by_holding]),
        "momentum_12m_wmean": _wmean([(h["weight"], h["momentum_12m"]) for h in by_holding]),
        "quality_net_margin_wmean": _wmean([(h["weight"], h["net_margin"]) for h in by_holding]),
        "quality_roic_wmean": _wmean([(h["weight"], h["roic"]) for h in by_holding]),
    }

    prompt = (
        f"Portfolio factor snapshot for {len(by_holding)} holdings. All figures computed in "
        f"Python (finviz key stats, price history, EDGAR XBRL) — quote exactly, do not invent.\n\n"
        f"Weighted portfolio aggregates:\n{json.dumps(factors_num, indent=2)}\n\n"
        f"Per holding:\n{json.dumps(by_holding, indent=2)}\n\n"
        "Interpret the portfolio's tilt on each factor: SIZE (mega/large/mid/small from the "
        "weighted market cap), VALUE (lower weighted P/E and P/B => value tilt; higher => growth), "
        "MOMENTUM (weighted 12-month return), and QUALITY (weighted net margin and ROIC). Fill "
        "factors.size/value/momentum/quality with concise reads and write a summary. Call out "
        "any factor where data was largely null."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2000)
    meta = {
        "by_holding": by_holding,
        "factor_aggregates": factors_num,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Measure portfolio exposure to systematic factors.")
    p.add_argument("--holdings", help='JSON array: [{"ticker":..,"weight":..}]')
    p.add_argument("--file", help="path to a JSON file of the same shape")
    skillkit.run(main, p)
