"""dcf-valuation: unlevered FCF DCF. All math deterministic, in Python."""
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


def main(args):
    info = universe.resolve(args.ticker)
    edgar.refresh_facts(args.ticker)

    # --- base free cash flow (reported OCF - capex) unless overridden ----- #
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

    r = args.discount_rate
    g = args.growth
    gt = args.terminal_growth
    if r <= gt:
        raise ValueError(f"discount rate ({r}) must exceed terminal growth ({gt}).")

    # --- projection + discounting ---------------------------------------- #
    projection = []
    pv_fcf_total = 0.0
    fcf_t = base_fcf
    for t in range(1, args.years + 1):
        fcf_t = base_fcf * (1 + g) ** t
        disc = (1 + r) ** t
        pv = fcf_t / disc
        pv_fcf_total += pv
        projection.append({"year": t, "fcf": round(fcf_t, 2), "pv": round(pv, 2)})

    fcf_n = base_fcf * (1 + g) ** args.years
    terminal_value = fcf_n * (1 + gt) / (r - gt)
    pv_terminal = terminal_value / (1 + r) ** args.years
    enterprise_value = pv_fcf_total + pv_terminal

    # --- bridge EV -> equity -> per share -------------------------------- #
    if args.net_debt is not None:
        net_debt = args.net_debt
    else:
        debt = _latest_any(args.ticker, ["LongTermDebt", "LongTermDebtNoncurrent"]) or 0.0
        cash = _latest_any(args.ticker, [
            "CashAndCashEquivalentsAtCarryingValue",
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]) or 0.0
        net_debt = debt - cash
    equity_value = enterprise_value - net_debt

    shares = args.shares if args.shares is not None else _latest_any(args.ticker, SHARES_TAGS)
    if not shares:
        raise ValueError("Could not determine shares outstanding; pass --shares.")
    intrinsic_ps = equity_value / shares

    price = args.price if args.price is not None else prices.last_price(args.ticker)
    upside = (intrinsic_ps / price - 1) if price else None

    assumptions = {
        "base_fcf": base_fcf, "base_fcf_note": fcf_note,
        "growth": g, "years": args.years, "discount_rate": r,
        "terminal_growth": gt, "net_debt": net_debt, "shares": shares,
    }
    summary = (
        f"{info['title']} ({info['ticker']}) DCF: intrinsic value "
        f"${intrinsic_ps:,.2f}/share vs price ${price:,.2f} "
        f"({upside:+.1%} upside)" if price else
        f"{info['title']} DCF intrinsic value ${intrinsic_ps:,.2f}/share"
    ) + (f". EV ${enterprise_value/1e9:,.1f}B on {g:.0%} growth, {r:.1%} WACC, "
         f"{gt:.1%} terminal.")
    return {
        "ticker": info["ticker"],
        "company": info["title"],
        "assumptions": assumptions,
        "projection": projection,
        "terminal_value": round(terminal_value, 2),
        "pv_terminal": round(pv_terminal, 2),
        "pv_fcf_explicit": round(pv_fcf_total, 2),
        "enterprise_value": round(enterprise_value, 2),
        "equity_value": round(equity_value, 2),
        "intrinsic_value_per_share": round(intrinsic_ps, 2),
        "current_price": round(price, 2) if price else None,
        "upside_vs_price": round(upside, 4) if upside is not None else None,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Discounted cash flow valuation.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--base-fcf", type=float, default=None)
    p.add_argument("--growth", type=float, default=0.08)
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--discount-rate", type=float, default=0.09)
    p.add_argument("--terminal-growth", type=float, default=0.025)
    p.add_argument("--net-debt", type=float, default=None)
    p.add_argument("--shares", type=float, default=None)
    p.add_argument("--price", type=float, default=None)
    skillkit.run(main, p)
