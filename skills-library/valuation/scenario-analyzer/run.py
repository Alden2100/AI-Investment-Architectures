"""scenario-analyzer: bull/base/bear DCF scenarios + sensitivity grid. Deterministic."""
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

from imdata import edgar, prices, skillkit, universe

SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]


def _latest_annual(ticker, tags):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["form"] == "10-K" and r["value"] is not None]
        if rows:
            return rows[0]["value"]
    return None


def _latest_any(ticker, tags):
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag) if r["value"] is not None]
        if rows:
            return rows[0]["value"]
    return None


def _intrinsic_per_share(base_fcf, g, r, gt, years, net_debt, shares):
    """Replicated unlevered-FCF DCF -> intrinsic value per share."""
    if r <= gt:
        return None
    pv_fcf_total = 0.0
    for t in range(1, years + 1):
        fcf_t = base_fcf * (1 + g) ** t
        pv_fcf_total += fcf_t / (1 + r) ** t
    fcf_n = base_fcf * (1 + g) ** years
    tv = fcf_n * (1 + gt) / (r - gt)
    pv_tv = tv / (1 + r) ** years
    ev = pv_fcf_total + pv_tv
    equity = ev - net_debt
    return equity / shares if shares else None


def _scenario(base_fcf, g, r, gt, years, net_debt, shares, price):
    ivps = _intrinsic_per_share(base_fcf, g, r, gt, years, net_debt, shares)
    upside = (ivps / price - 1) if (ivps is not None and price) else None
    return {
        "growth": round(g, 6),
        "discount_rate": round(r, 6),
        "intrinsic_value_per_share": round(ivps, 2) if ivps is not None else None,
        "upside_vs_price": round(upside, 4) if upside is not None else None,
    }


def main(args):
    info = universe.resolve(args.ticker)
    edgar.refresh_facts(args.ticker)

    if args.base_fcf is not None:
        base_fcf = args.base_fcf
        fcf_note = "user-supplied"
    else:
        ocf = _latest_annual(args.ticker, ["NetCashProvidedByUsedInOperatingActivities"])
        capex = _latest_annual(args.ticker, ["PaymentsToAcquirePropertyPlantAndEquipment"])
        if ocf is None or capex is None:
            raise ValueError("Could not derive base FCF from filings; pass --base-fcf.")
        base_fcf = ocf - capex
        fcf_note = f"reported OCF {ocf:,.0f} - capex {capex:,.0f}"

    g = args.growth
    r = args.discount_rate
    gt = args.terminal_growth
    if r <= gt:
        raise ValueError(f"discount rate ({r}) must exceed terminal growth ({gt}).")

    if args.net_debt is not None:
        net_debt = args.net_debt
    else:
        debt = _latest_any(args.ticker, ["LongTermDebt", "LongTermDebtNoncurrent"]) or 0.0
        cash = _latest_any(args.ticker, [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]) or 0.0
        net_debt = debt - cash

    shares = args.shares if args.shares is not None else _latest_any(args.ticker, SHARES_TAGS)
    if not shares:
        raise ValueError("Could not determine shares outstanding; pass --shares.")

    price = args.price if args.price is not None else prices.last_price(args.ticker)

    # --- scenarios ------------------------------------------------------- #
    bull_g = g + args.bull_growth_delta
    bull_r = r + args.bull_wacc_delta
    bear_g = g + args.bear_growth_delta
    bear_r = r + args.bear_wacc_delta
    scenarios = {
        "bull": _scenario(base_fcf, bull_g, bull_r, gt, args.years, net_debt, shares, price),
        "base": _scenario(base_fcf, g, r, gt, args.years, net_debt, shares, price),
        "bear": _scenario(base_fcf, bear_g, bear_r, gt, args.years, net_debt, shares, price),
    }

    # --- sensitivity grid: growth (rows) x discount rate (cols) ---------- #
    growth_axis = [round(g - 0.02, 6), round(g, 6), round(g + 0.02, 6)]
    rate_axis = [round(r - 0.01, 6), round(r, 6), round(r + 0.01, 6)]
    matrix = []
    for gg in growth_axis:
        row = []
        for rr in rate_axis:
            if rr <= gt:
                row.append(None)
            else:
                ivps = _intrinsic_per_share(base_fcf, gg, rr, gt, args.years, net_debt, shares)
                row.append(round(ivps, 2) if ivps is not None else None)
        matrix.append(row)
    sensitivity_table = {
        "row_label": "growth",
        "col_label": "discount_rate",
        "rows": growth_axis,
        "cols": rate_axis,
        "matrix": matrix,
    }

    assumptions = {
        "base_fcf": base_fcf, "base_fcf_note": fcf_note,
        "growth": g, "discount_rate": r, "terminal_growth": gt,
        "years": args.years, "net_debt": net_debt, "shares": shares,
        "price": round(price, 2) if price else None,
        "bull_growth_delta": args.bull_growth_delta, "bull_wacc_delta": args.bull_wacc_delta,
        "bear_growth_delta": args.bear_growth_delta, "bear_wacc_delta": args.bear_wacc_delta,
    }

    base_iv = scenarios["base"]["intrinsic_value_per_share"]
    bull_iv = scenarios["bull"]["intrinsic_value_per_share"]
    bear_iv = scenarios["bear"]["intrinsic_value_per_share"]
    summary = (
        f"{info['title']} ({info['ticker']}) scenarios — "
        f"bull ${bull_iv:,.2f}, base ${base_iv:,.2f}, bear ${bear_iv:,.2f}/share"
        + (f" vs price ${price:,.2f} (base {scenarios['base']['upside_vs_price']:+.1%})."
           if price else ".")
        + f" Sensitivity grid spans growth {growth_axis[0]:.0%}-{growth_axis[-1]:.0%} "
        + f"x WACC {rate_axis[0]:.1%}-{rate_axis[-1]:.1%}."
    )
    return {
        "ticker": info["ticker"],
        "company": info["title"],
        "assumptions": assumptions,
        "scenarios": scenarios,
        "sensitivity_table": sensitivity_table,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Bull/base/bear DCF scenarios + sensitivity.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--base-fcf", type=float, default=None)
    p.add_argument("--growth", type=float, default=0.08)
    p.add_argument("--discount-rate", type=float, default=0.09)
    p.add_argument("--terminal-growth", type=float, default=0.025)
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--net-debt", type=float, default=None)
    p.add_argument("--shares", type=float, default=None)
    p.add_argument("--price", type=float, default=None)
    p.add_argument("--bull-growth-delta", type=float, default=0.03)
    p.add_argument("--bear-growth-delta", type=float, default=-0.03)
    p.add_argument("--bull-wacc-delta", type=float, default=-0.01)
    p.add_argument("--bear-wacc-delta", type=float, default=0.01)
    skillkit.run(main, p)
