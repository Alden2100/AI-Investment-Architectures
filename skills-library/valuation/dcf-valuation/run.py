"""dcf-valuation: unlevered FCF DCF. All math deterministic, in Python.

Two-stage with fade: an explicit high-growth stage, a linear fade to the terminal
rate, then a Gordon perpetuity — so value isn't pinned to one flat growth number.
WACC is DERIVED from the company's own capital structure and a CAPM cost of equity
(beta estimated vs SPY), not a hardcoded 9% — pass --discount-rate to override
(scenario-analyzer does this to stress the rate). Every driver is carried in
`assumptions` so the downstream model can reason about *why*, not just the answer.
"""
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
DEBT_TAGS = ["LongTermDebt", "LongTermDebtNoncurrent"]
DEBT_CURRENT_TAGS = ["LongTermDebtCurrent", "DebtCurrent"]
CASH_TAGS = ["CashAndCashEquivalentsAtCarryingValue",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
INTEREST_TAGS = ["InterestExpense", "InterestExpenseDebt",
                 "InterestAndDebtExpense"]
PRETAX_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesAndExtraordinaryItems"]
TAX_TAGS = ["IncomeTaxExpenseBenefit"]


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


def _estimate_beta(ticker, benchmark="SPY", lookback_days=730):
    """Levered equity beta from ~2y of weekly returns vs the benchmark.
    Returns None if data is too thin (caller falls back to 1.0)."""
    try:
        a = prices.get_history(ticker, lookback_days=lookback_days)
        m = prices.get_history(benchmark, lookback_days=lookback_days)
        if not a or not m:
            return None
        # rows may be sqlite3.Row (no .get) or dict — index by column name directly
        ac = {r["date"]: r["close"] for r in a if r["close"] is not None}
        mc = {r["date"]: r["close"] for r in m if r["close"] is not None}
        dates = sorted(set(ac) & set(mc))
        # weekly sample (every ~5th trading day) to damp daily microstructure noise
        sampled = dates[::5]
        if len(sampled) < 30:
            sampled = dates
        ra, rm = [], []
        for i in range(1, len(sampled)):
            p0a, p1a = ac[sampled[i - 1]], ac[sampled[i]]
            p0m, p1m = mc[sampled[i - 1]], mc[sampled[i]]
            if p0a and p0m:
                ra.append(p1a / p0a - 1.0)
                rm.append(p1m / p0m - 1.0)
        n = len(rm)
        if n < 25:
            return None
        mean_a = sum(ra) / n
        mean_m = sum(rm) / n
        cov = sum((ra[i] - mean_a) * (rm[i] - mean_m) for i in range(n)) / n
        var = sum((rm[i] - mean_m) ** 2 for i in range(n)) / n
        if var <= 0:
            return None
        beta = cov / var
        # guard against absurd estimates from thin/illiquid data
        return max(0.3, min(2.5, beta))
    except Exception:
        return None


def _derive_wacc(ticker, *, shares, price, net_debt, args):
    """Derive WACC from CAPM cost of equity + after-tax cost of debt, weighted by
    market equity and book debt. Returns (wacc, components). Every input falls
    back to a sane default so this never crashes a valuation."""
    rf, erp = args.rf, args.erp
    beta = args.beta if args.beta is not None else _estimate_beta(ticker)
    beta_used = beta if beta is not None else 1.0
    cost_of_equity = rf + beta_used * erp

    total_debt = (_latest_any(ticker, DEBT_TAGS) or 0.0) + (_latest_any(ticker, DEBT_CURRENT_TAGS) or 0.0)

    # cost of debt = interest expense / total debt, clamped; else a default
    interest = _latest_annual(ticker, INTEREST_TAGS)
    if interest and total_debt:
        cost_of_debt = max(0.02, min(0.12, abs(interest) / total_debt))
        kd_note = "interest expense / total debt"
    else:
        cost_of_debt = 0.055
        kd_note = "default (interest/debt unavailable)"

    # effective tax rate, clamped
    pretax = _latest_annual(ticker, PRETAX_TAGS)
    tax = _latest_annual(ticker, TAX_TAGS)
    if pretax and tax is not None and pretax > 0:
        tax_rate = max(0.0, min(0.35, tax / pretax))
        tax_note = "income tax / pretax income"
    else:
        tax_rate = 0.21
        tax_note = "default 21% (statutory)"

    equity_mv = (shares * price) if (shares and price) else None
    if equity_mv and (equity_mv + total_debt) > 0:
        we = equity_mv / (equity_mv + total_debt)
    else:
        we = 0.85  # most names we cover are equity-heavy; reasonable prior
    wd = 1.0 - we

    wacc = we * cost_of_equity + wd * cost_of_debt * (1.0 - tax_rate)
    wacc = max(0.06, min(0.14, wacc))  # keep within a defensible band
    components = {
        "method": "CAPM equity + after-tax debt, market-weighted",
        "beta": round(beta_used, 3), "beta_estimated": beta is not None,
        "risk_free": rf, "equity_risk_premium": erp,
        "cost_of_equity": round(cost_of_equity, 4),
        "cost_of_debt": round(cost_of_debt, 4), "cost_of_debt_note": kd_note,
        "tax_rate": round(tax_rate, 4), "tax_rate_note": tax_note,
        "equity_weight": round(we, 3), "debt_weight": round(wd, 3),
        "total_debt": round(total_debt, 2),
        "equity_market_value": round(equity_mv, 2) if equity_mv else None,
    }
    return round(wacc, 4), components


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

    # --- shares / price / net-debt (needed for WACC weights & the bridge) -- #
    shares = args.shares if args.shares is not None else _latest_any(args.ticker, SHARES_TAGS)
    if not shares:
        raise ValueError("Could not determine shares outstanding; pass --shares.")
    price = args.price if args.price is not None else prices.last_price(args.ticker)

    if args.net_debt is not None:
        net_debt = args.net_debt
    else:
        debt = (_latest_any(args.ticker, DEBT_TAGS) or 0.0) + (_latest_any(args.ticker, DEBT_CURRENT_TAGS) or 0.0)
        cash = _latest_any(args.ticker, CASH_TAGS) or 0.0
        net_debt = debt - cash

    # --- discount rate: derive WACC unless explicitly overridden ---------- #
    if args.discount_rate is not None:
        r = args.discount_rate
        wacc_components = {"method": "user-supplied / scenario override"}
    else:
        r, wacc_components = _derive_wacc(args.ticker, shares=shares, price=price,
                                          net_debt=net_debt, args=args)

    g = args.growth                 # stage-1 (explicit high-growth) rate
    gt = args.terminal_growth
    if r <= gt:
        raise ValueError(f"discount rate ({r}) must exceed terminal growth ({gt}).")

    # --- growth path: explicit stage, then linear fade to terminal -------- #
    fade_years = max(0, args.fade_years)
    growth_path = [g] * args.years
    for i in range(1, fade_years + 1):
        growth_path.append(g + (gt - g) * (i / fade_years))

    # --- projection + discounting ---------------------------------------- #
    projection = []
    pv_fcf_total = 0.0
    fcf_t = base_fcf
    for t, g_t in enumerate(growth_path, start=1):
        fcf_t = fcf_t * (1 + g_t)
        disc = (1 + r) ** t
        pv = fcf_t / disc
        pv_fcf_total += pv
        projection.append({"year": t, "growth": round(g_t, 4),
                           "fcf": round(fcf_t, 2), "pv": round(pv, 2)})

    n_years = len(growth_path)
    fcf_n = fcf_t  # final-year FCF after the fade
    terminal_value = fcf_n * (1 + gt) / (r - gt)
    pv_terminal = terminal_value / (1 + r) ** n_years
    enterprise_value = pv_fcf_total + pv_terminal

    # --- bridge EV -> equity -> per share -------------------------------- #
    equity_value = enterprise_value - net_debt
    intrinsic_ps = equity_value / shares
    upside = (intrinsic_ps / price - 1) if price else None
    terminal_pct = pv_terminal / enterprise_value if enterprise_value else None

    assumptions = {
        "base_fcf": base_fcf, "base_fcf_note": fcf_note,
        "growth": g, "years": args.years,             # explicit stage
        "fade_years": fade_years,                      # glide to terminal
        "discount_rate": r, "wacc_components": wacc_components,
        "terminal_growth": gt, "net_debt": net_debt, "shares": shares,
        "terminal_value_pct_of_ev": round(terminal_pct, 3) if terminal_pct else None,
        "model": f"2-stage DCF: {args.years}y explicit @ {g:.0%} → {fade_years}y fade → {gt:.1%} terminal",
    }
    if price:
        head = (f"{info['title']} ({info['ticker']}) DCF: intrinsic value "
                f"${intrinsic_ps:,.2f}/share vs price ${price:,.2f} ({upside:+.1%} upside)")
    else:
        head = f"{info['title']} DCF intrinsic value ${intrinsic_ps:,.2f}/share"
    beta_str = f" (β {wacc_components['beta']})" if wacc_components.get("beta") else ""
    tail = (f". EV ${enterprise_value/1e9:,.1f}B; {args.years}y@{g:.0%}→{gt:.1%} terminal, "
            f"WACC {r:.1%}{beta_str}")
    if terminal_pct is not None:
        tail += f"; terminal = {terminal_pct:.0%} of EV."
    else:
        tail += "."
    summary = head + tail
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
    p = argparse.ArgumentParser(description="Discounted cash flow valuation (2-stage, derived WACC).")
    p.add_argument("--ticker", required=True)
    p.add_argument("--base-fcf", type=float, default=None)
    p.add_argument("--growth", type=float, default=0.08, help="stage-1 (explicit) FCF growth")
    p.add_argument("--years", type=int, default=5, help="explicit high-growth years")
    p.add_argument("--fade-years", type=int, default=5, help="years to fade from stage-1 to terminal")
    p.add_argument("--terminal-growth", type=float, default=0.025)
    p.add_argument("--discount-rate", type=float, default=None,
                   help="WACC override; if omitted, derived from beta + capital structure")
    p.add_argument("--rf", type=float, default=0.043, help="risk-free rate for CAPM")
    p.add_argument("--erp", type=float, default=0.05, help="equity risk premium for CAPM")
    p.add_argument("--beta", type=float, default=None, help="override estimated beta")
    p.add_argument("--net-debt", type=float, default=None)
    p.add_argument("--shares", type=float, default=None)
    p.add_argument("--price", type=float, default=None)
    skillkit.run(main, p)
