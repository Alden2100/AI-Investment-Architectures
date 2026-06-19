"""fundamentals-fetcher: structured financials from SEC XBRL companyfacts.

Deterministic. Reported values only; the one derived figure (EBITDA) is computed
in Python from reported operating income + D&A. Handles XBRL tag drift via a
candidate-tag list per logical line item.
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

from imdata import edgar, skillkit, universe

# Logical line item -> ordered list of candidate us-gaap/dei XBRL tags.
LINE_ITEMS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "eps_basic": ["EarningsPerShareBasic"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "total_debt": ["LongTermDebt", "LongTermDebtNoncurrent"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndOther",
    ],
}

# Fallback components when no combined D&A tag is reported (e.g. MSFT reports
# Depreciation and AmortizationOfIntangibleAssets separately).
DA_COMPONENTS = ["Depreciation", "AmortizationOfIntangibleAssets"]


def _annual_series(ticker, tags):
    """Return [{period_end, value, fy, tag, unit}] for 10-K periods, newest first,
    picking the first candidate tag that has annual data."""
    for tag in tags:
        rows = [
            r for r in edgar.get_concept(ticker, tag)
            if r["form"] == "10-K" and r["value"] is not None and r["period_end"]
        ]
        # De-dup by period_end (keep first / most recently filed).
        seen, series = set(), []
        for r in sorted(rows, key=lambda x: x["period_end"], reverse=True):
            if r["period_end"] in seen:
                continue
            seen.add(r["period_end"])
            series.append(
                {
                    "period_end": r["period_end"],
                    "value": r["value"],
                    "fy": r["fy"],
                    "tag": tag,
                    "unit": r["unit"],
                }
            )
        if series:
            return series
    return []


def main(args):
    info = universe.resolve(args.ticker)
    edgar.refresh_facts(args.ticker)  # ensure facts cached

    items = args.items or list(LINE_ITEMS.keys())
    detail, financials, periods = {}, {}, []
    for item in items:
        if item in ("ebitda",):  # derived; handled after
            continue
        series = _annual_series(args.ticker, LINE_ITEMS[item])
        # Fallback: reconstruct combined D&A from its components.
        if not series and item == "depreciation_amortization":
            comp = [_annual_series(args.ticker, [t]) for t in DA_COMPONENTS]
            comp = [c for c in comp if c]
            if comp:
                by_period = {}
                for c in comp:
                    for s in c:
                        by_period.setdefault(s["period_end"], {"fy": s["fy"],
                            "unit": s["unit"], "value": 0.0})
                        by_period[s["period_end"]]["value"] += s["value"]
                series = [
                    {"period_end": pe, "value": v["value"], "fy": v["fy"],
                     "tag": "computed: Depreciation + AmortizationOfIntangibleAssets",
                     "unit": v["unit"]}
                    for pe, v in sorted(by_period.items(), reverse=True)
                ]
        if series:
            detail[item] = series[0]
            financials[item] = series[0]["value"]
            periods.append(
                {"item": item, "series": [
                    {"period_end": s["period_end"], "value": s["value"]}
                    for s in series[: args.periods]
                ]}
            )

    # Derived EBITDA = operating_income + D&A (computed in Python).
    if (not args.items) or ("ebitda" in args.items):
        oi = detail.get("operating_income", {}).get("value")
        da = detail.get("depreciation_amortization", {}).get("value")
        if oi is not None and da is not None:
            financials["ebitda"] = oi + da
            detail["ebitda"] = {
                "value": oi + da,
                "period_end": detail["operating_income"]["period_end"],
                "fy": detail["operating_income"]["fy"],
                "tag": "computed: operating_income + D&A",
                "unit": detail["operating_income"]["unit"],
            }

    rev = financials.get("revenue")
    ni = financials.get("net_income")
    margin = f", net margin {ni / rev:.1%}" if (rev and ni) else ""
    latest_period = detail.get("revenue", {}).get("period_end", "latest")
    summary = (
        f"{info['title']} ({info['ticker']}) FY ending {latest_period}: "
        f"revenue ${rev:,.0f}" if rev else f"{info['title']} ({info['ticker']}) financials"
    ) + (f", net income ${ni:,.0f}{margin}" if ni else "") + "."

    return {
        "ticker": info["ticker"],
        "company": info["title"],
        "financials": financials,
        "detail": detail,
        "periods": periods,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch structured financials from XBRL.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--items", nargs="*", default=None, help="subset of line items")
    p.add_argument("--periods", type=int, default=4)
    skillkit.run(main, p)
