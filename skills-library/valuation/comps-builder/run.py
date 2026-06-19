"""comps-builder: comparable-company multiples table. Deterministic."""
import argparse
import os
import statistics
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

from imdata import edgar, prices, skillkit, universe

SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]
REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                "SalesRevenueNet"]
DEBT_TAGS = ["LongTermDebt", "LongTermDebtNoncurrent"]
CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]


def _annual(ticker, tags):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["form"] == "10-K" and r["value"] is not None]
        if rows:
            return rows[0]["value"]
    return None


def _any(ticker, tags):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag) if r["value"] is not None]
        if rows:
            return rows[0]["value"]
    return None


def _ebitda(ticker):
    oi = _annual(ticker, ["OperatingIncomeLoss"])
    da = _annual(ticker, ["DepreciationDepletionAndAmortization",
                          "DepreciationAmortizationAndOther"])
    if da is None:
        dep = _annual(ticker, ["Depreciation"])
        amort = _annual(ticker, ["AmortizationOfIntangibleAssets"])
        da = (dep or 0) + (amort or 0) if (dep or amort) else None
    if oi is None or da is None:
        return None
    return oi + da


def metrics(ticker):
    edgar.refresh_facts(ticker)
    info = universe.resolve(ticker)
    price = prices.last_price(ticker)
    shares = _any(ticker, SHARES_TAGS)
    revenue = _annual(ticker, REVENUE_TAGS)
    net_income = _annual(ticker, ["NetIncomeLoss"])
    ebitda = _ebitda(ticker)
    debt = _any(ticker, DEBT_TAGS) or 0.0
    cash = _any(ticker, CASH_TAGS) or 0.0
    net_debt = debt - cash
    mcap = price * shares if (price and shares) else None
    ev = mcap + net_debt if mcap is not None else None
    return {
        "ticker": info["ticker"], "price": price, "shares": shares,
        "market_cap": mcap, "net_debt": net_debt, "ev": ev,
        "revenue": revenue, "net_income": net_income, "ebitda": ebitda,
        "ev_ebitda": (ev / ebitda) if (ev and ebitda and ebitda > 0) else None,
        "pe": (mcap / net_income) if (mcap and net_income and net_income > 0) else None,
        "ps": (mcap / revenue) if (mcap and revenue and revenue > 0) else None,
    }


def _median(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def main(args):
    table = [metrics(t) for t in args.tickers]
    med = {
        "ev_ebitda": _median([r["ev_ebitda"] for r in table]),
        "pe": _median([r["pe"] for r in table]),
        "ps": _median([r["ps"] for r in table]),
    }
    out = {
        "peers": [t.upper() for t in args.tickers],
        "table": [
            {"ticker": r["ticker"],
             "market_cap": round(r["market_cap"], 0) if r["market_cap"] else None,
             "ev": round(r["ev"], 0) if r["ev"] else None,
             "ev_ebitda": round(r["ev_ebitda"], 2) if r["ev_ebitda"] else None,
             "pe": round(r["pe"], 2) if r["pe"] else None,
             "ps": round(r["ps"], 2) if r["ps"] else None}
            for r in table
        ],
        "median": {k: (round(v, 2) if v else None) for k, v in med.items()},
    }

    summary = (f"Comps for {', '.join(out['peers'])}: median EV/EBITDA "
               f"{med['ev_ebitda']:.1f}x, P/E {med['pe']:.1f}x, P/S {med['ps']:.1f}x."
               if all(med.values()) else f"Comps for {', '.join(out['peers'])}.")

    if args.target:
        tm = metrics(args.target)
        implied = {}
        if med["ev_ebitda"] and tm["ebitda"] and tm["shares"]:
            ev_imp = med["ev_ebitda"] * tm["ebitda"]
            implied["by_ev_ebitda"] = round((ev_imp - tm["net_debt"]) / tm["shares"], 2)
        if med["pe"] and tm["net_income"] and tm["shares"]:
            implied["by_pe"] = round(med["pe"] * tm["net_income"] / tm["shares"], 2)
        if med["ps"] and tm["revenue"] and tm["shares"]:
            implied["by_ps"] = round(med["ps"] * tm["revenue"] / tm["shares"], 2)
        vals = [v for v in implied.values() if v is not None]
        implied["average"] = round(sum(vals) / len(vals), 2) if vals else None
        out["target"] = tm["ticker"]
        out["target_current_price"] = round(tm["price"], 2) if tm["price"] else None
        out["target_implied_value"] = implied
        if implied.get("average") and tm["price"]:
            up = implied["average"] / tm["price"] - 1
            summary += (f" {tm['ticker']} peer-implied ${implied['average']:,.2f}/share "
                        f"vs ${tm['price']:,.2f} ({up:+.1%}).")
    out["summary"] = summary
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build a comps multiples table.")
    p.add_argument("--tickers", nargs="+", required=True, help="peer set")
    p.add_argument("--target", default=None, help="ticker to value off peer medians")
    skillkit.run(main, p)
