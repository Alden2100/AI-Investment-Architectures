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


def _intrinsic_per_share(base_fcf, g, r, gt, years, fade_years, net_debt, shares):
    """Replicated 2-stage (explicit + linear fade) unlevered-FCF DCF -> value/share.
    Mirrors dcf-valuation exactly so the BASE scenario equals the DCF intrinsic."""
    if r <= gt:
        return None
    growth_path = [g] * years + [g + (gt - g) * (i / fade_years)
                                 for i in range(1, max(0, fade_years) + 1)]
    fcf_t = base_fcf
    pv_fcf_total = 0.0
    for t, g_t in enumerate(growth_path, start=1):
        fcf_t = fcf_t * (1 + g_t)
        pv_fcf_total += fcf_t / (1 + r) ** t
    n = len(growth_path)
    tv = fcf_t * (1 + gt) / (r - gt)
    pv_tv = tv / (1 + r) ** n
    ev = pv_fcf_total + pv_tv
    equity = ev - net_debt
    return equity / shares if shares else None


def _scenario(base_fcf, g, r, gt, years, fade_years, net_debt, shares, price):
    ivps = _intrinsic_per_share(base_fcf, g, r, gt, years, fade_years, net_debt, shares)
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
    fade_years = max(0, args.fade_years)

    # --- company-specific scenario widths (not a fixed ±3% for every name) -
    # Growth dispersion scales with the company's OWN growth rate (a 15%-grower has a
    # wider plausible band than a 4%-grower); WACC dispersion scales with beta (riskier
    # names get a wider rate band). Explicit deltas, if passed, override the derivation.
    beta = args.beta if args.beta is not None else 1.0
    g_delta = (args.growth_delta if args.growth_delta is not None
               else round(max(0.02, min(0.08, 0.4 * abs(g))), 4))
    r_delta = (args.wacc_delta if args.wacc_delta is not None
               else round(max(0.005, min(0.025, 0.01 * beta)), 4))

    # --- scenarios ------------------------------------------------------- #
    bull_g, bull_r = g + g_delta, r - r_delta      # faster growth, lower risk
    bear_g, bear_r = g - g_delta, r + r_delta      # slower growth, higher risk
    scenarios = {
        "bull": _scenario(base_fcf, bull_g, bull_r, gt, args.years, fade_years, net_debt, shares, price),
        "base": _scenario(base_fcf, g, r, gt, args.years, fade_years, net_debt, shares, price),
        "bear": _scenario(base_fcf, bear_g, bear_r, gt, args.years, fade_years, net_debt, shares, price),
    }

    # --- sensitivity grid: growth (rows) x discount rate (cols) ---------- #
    growth_axis = [round(g - g_delta, 6), round(g, 6), round(g + g_delta, 6)]
    rate_axis = [round(r - r_delta, 6), round(r, 6), round(r + r_delta, 6)]
    matrix = []
    for gg in growth_axis:
        row = []
        for rr in rate_axis:
            if rr <= gt:
                row.append(None)
            else:
                ivps = _intrinsic_per_share(base_fcf, gg, rr, gt, args.years, fade_years, net_debt, shares)
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
        "years": args.years, "fade_years": fade_years,
        "net_debt": net_debt, "shares": shares,
        "price": round(price, 2) if price else None,
        "beta": round(beta, 3), "growth_delta": g_delta, "wacc_delta": r_delta,
        "scenario_basis": (f"bull/bear = base growth ±{g_delta:.1%} (scaled to the "
                           f"company's growth) and WACC ∓{r_delta:.2%} (scaled to beta {beta:.2f})"),
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
    p.add_argument("--fade-years", type=int, default=5)
    p.add_argument("--net-debt", type=float, default=None)
    p.add_argument("--shares", type=float, default=None)
    p.add_argument("--price", type=float, default=None)
    p.add_argument("--beta", type=float, default=None, help="beta to scale the WACC band")
    p.add_argument("--growth-delta", type=float, default=None,
                   help="bull/bear growth half-width (default: scaled to growth)")
    p.add_argument("--wacc-delta", type=float, default=None,
                   help="bull/bear WACC half-width (default: scaled to beta)")
    skillkit.run(main, p)
