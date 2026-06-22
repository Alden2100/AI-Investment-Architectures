"""moat-analyzer: assess competitive advantage / moat from a 10-K plus computed margins. Hybrid model skill."""
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

from imdata import skillkit, edgar, universe
from imrouter import route as _route

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
GROSS_PROFIT_TAGS = ["GrossProfit"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
NET_INCOME_TAGS = ["NetIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "moat_type": {"type": "string",
                      "description": "Primary moat: network effects / switching costs / "
                                     "scale / brand / cost advantage / intangibles / none"},
        "durability": {"type": "string",
                       "description": "high/medium/low plus a brief why"},
        "threats": {"type": "array", "items": {"type": "string"},
                    "description": "Key threats to the moat / competitive position"},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["moat_type", "durability", "summary"],
}

SYSTEM = (
    "You are an equity research analyst assessing a company's competitive advantage "
    "(economic moat) and industry position. Reason qualitatively from the 10-K business, "
    "competition, and risk-factor text, using the provided margin metrics as supporting "
    "evidence. Do not compute or invent figures; the margins given were computed in Python "
    "and must be quoted exactly as provided. Classify the moat type and judge its durability."
)


def _latest_annual(ticker, tags):
    """First 10-K row (newest-first) with a non-None value across the given tags."""
    for tag in tags:
        rows = edgar.get_concept(ticker, tag)
        for r in rows:
            if r["form"] == "10-K" and r["value"] is not None:
                return float(r["value"]), r["period_end"]
    return None, None


def _annual_map(ticker, tags, n=6):
    """period_end -> value for the last n annual (10-K) periods (deduped)."""
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["value"] is not None and r["form"] == "10-K" and r["period_end"]]
        if rows:
            m = {}
            for r in sorted(rows, key=lambda x: x["period_end"], reverse=True):
                if r["period_end"] not in m:
                    m[r["period_end"]] = float(r["value"])
                if len(m) >= n:
                    break
            return m
    return {}


def _round(x):
    return round(x, 4) if x is not None else None


def main(args):
    info = universe.resolve(args.ticker)

    revenue, rev_end = _latest_annual(args.ticker, REVENUE_TAGS)
    gross, _ = _latest_annual(args.ticker, GROSS_PROFIT_TAGS)
    op_inc, _ = _latest_annual(args.ticker, OPERATING_INCOME_TAGS)
    net_inc, _ = _latest_annual(args.ticker, NET_INCOME_TAGS)

    gross_margin = _round(gross / revenue) if (gross is not None and revenue) else None
    operating_margin = _round(op_inc / revenue) if (op_inc is not None and revenue) else None
    net_margin = _round(net_inc / revenue) if (net_inc is not None and revenue) else None
    margins = {
        "gross": gross_margin,
        "operating": operating_margin,
        "net": net_margin,
        "period_end": rev_end,
    }

    # --- multi-year margin trend (durability evidence, not a single snapshot) --
    rev_map = _annual_map(args.ticker, REVENUE_TAGS)
    gp_map = _annual_map(args.ticker, GROSS_PROFIT_TAGS)
    oi_map = _annual_map(args.ticker, OPERATING_INCOME_TAGS)
    ni_map = _annual_map(args.ticker, NET_INCOME_TAGS)
    margin_trend = []
    for y in sorted(rev_map, reverse=True)[:5]:
        rev = rev_map.get(y)
        if not rev:
            continue
        margin_trend.append({
            "period_end": y,
            "gross": _round(gp_map[y] / rev) if y in gp_map else None,
            "operating": _round(oi_map[y] / rev) if y in oi_map else None,
            "net": _round(ni_map[y] / rev) if y in ni_map else None,
        })

    # --- ROIC = NOPAT / invested capital (pricing power shows up as ROIC) ------
    eq_map = _annual_map(args.ticker, ["StockholdersEquity"])
    debt_lt = _annual_map(args.ticker, ["LongTermDebt", "LongTermDebtNoncurrent"])
    debt_cur = _annual_map(args.ticker, ["LongTermDebtCurrent", "DebtCurrent"])
    cash_map = _annual_map(args.ticker, ["CashAndCashEquivalentsAtCarryingValue",
                                         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"])
    pretax_map = _annual_map(args.ticker, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"])
    tax_map = _annual_map(args.ticker, ["IncomeTaxExpenseBenefit"])
    roic_series = []
    for y in sorted(oi_map, reverse=True)[:3]:
        oi = oi_map.get(y)
        eq = eq_map.get(y)
        if oi is None or eq is None:
            continue
        invested = eq + (debt_lt.get(y, 0.0) or 0.0) + (debt_cur.get(y, 0.0) or 0.0) - (cash_map.get(y, 0.0) or 0.0)
        if invested and invested > 0:
            tr = 0.21
            if pretax_map.get(y) and tax_map.get(y) is not None and pretax_map[y] > 0:
                tr = max(0.0, min(0.35, tax_map[y] / pretax_map[y]))
            nopat = oi * (1 - tr)
            roic_series.append({"period_end": y, "roic": _round(nopat / invested)})
    roic = roic_series[0]["roic"] if roic_series else None

    row = edgar.latest_filing(args.ticker, "10-K")
    if row is None:
        raise ValueError(f"No 10-K found for {args.ticker}.")
    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=60000,
        anchors=[r"item\s*1\b", r"compet", r"risk factors",
                 r"business", r"intellectual property"],
    )

    import json as _json
    margin_lines = (
        f"Computed in Python from XBRL — quote exactly, do not recompute.\n"
        f"Latest annual margins (period_end {rev_end}): gross {gross_margin}, "
        f"operating {operating_margin}, net {net_margin}.\n"
        f"Margin TREND (last {len(margin_trend)} annual periods, newest first): "
        f"{_json.dumps(margin_trend)}\n"
        f"ROIC (NOPAT / invested capital, newest first): {_json.dumps(roic_series)}\n"
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). 10-K filed {row['filing_date']}.\n\n"
        f"{margin_lines}\n"
        f"10-K text (excerpted around business/competition/risk):\n{clip}\n\n"
        "Assess the economic moat. A durable moat shows up as HIGH and STABLE-OR-RISING "
        "margins and a ROIC comfortably above the cost of capital (~9-11%); margin "
        "compression or ROIC erosion is evidence AGAINST durability. Use the trend, not "
        "just the latest snapshot. Classify moat_type, judge durability (high/medium/low "
        "+ why, citing the trend/ROIC), list threats, and write a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "margins": margins,
        "margin_trend": margin_trend,
        "roic": roic,
        "roic_series": roic_series,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Assess a company's competitive moat and position.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
