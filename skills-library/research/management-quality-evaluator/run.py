"""management-quality-evaluator: assess management execution & capital allocation. Hybrid model skill."""
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

import json as _json

from imdata import skillkit, edgar, universe
from imrouter import route as _route

OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "capital_allocation": {
            "type": "object",
            "properties": {
                "buybacks": {"type": "string", "description": "Assessment of share-repurchase history"},
                "dividends": {"type": "string", "description": "Assessment of dividend history"},
                "debt_trend": {"type": "string", "description": "Assessment of leverage trajectory"},
                "shares_trend": {"type": "string",
                                 "description": "Diluted-share-count trajectory: dilution vs reduction"},
            },
            "required": ["buybacks", "dividends", "debt_trend", "shares_trend"],
        },
        "roic_series": {"type": "string",
                        "description": "Narrative on the ROIC trend (returns on capital over time)"},
        "track_record": {"type": "string",
                         "description": "Overall judgment of management's execution & capital allocation"},
        "red_flags": {"type": "array", "items": {"type": "string"},
                      "description": "Specific concerns: value-destructive M&A, dilution, "
                                     "rising leverage with falling returns, etc."},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["ticker", "capital_allocation", "track_record", "summary"],
}

SYSTEM = (
    "You are an equity research analyst assessing management quality through the lens of "
    "execution and capital allocation. Reason from the multi-year series provided: diluted "
    "share count, buybacks, dividends, long-term debt, and ROIC. All figures were computed "
    "in Python from XBRL and must be quoted exactly as provided; do not recompute or invent "
    "numbers. Good capital allocators grow ROIC, reduce share count opportunistically, and "
    "avoid leveraging up into falling returns. Judge the track record and flag concrete risks."
)


def _annual_map(ticker, tags, n=8):
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


def _series(m, n=6):
    """[{period_end, value}] newest-first, capped at n."""
    return [{"period_end": y, "value": m[y]} for y in sorted(m, reverse=True)[:n]]


def main(args):
    info = universe.resolve(args.ticker)

    shares = _annual_map(args.ticker, ["WeightedAverageNumberOfDilutedSharesOutstanding",
                                       "WeightedAverageNumberOfSharesOutstandingDiluted"])
    buybacks = _annual_map(args.ticker, ["PaymentsForRepurchaseOfCommonStock"])
    dividends = _annual_map(args.ticker, ["PaymentsOfDividendsCommon", "PaymentsOfDividends"])
    debt_lt = _annual_map(args.ticker, ["LongTermDebt", "LongTermDebtNoncurrent"])

    # --- ROIC = NOPAT / invested capital (mirrors moat-analyzer) ---------------
    oi_map = _annual_map(args.ticker, OPERATING_INCOME_TAGS)
    eq_map = _annual_map(args.ticker, ["StockholdersEquity"])
    debt_cur = _annual_map(args.ticker, ["LongTermDebtCurrent", "DebtCurrent"])
    cash_map = _annual_map(args.ticker, ["CashAndCashEquivalentsAtCarryingValue",
                                         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"])
    pretax_map = _annual_map(args.ticker, [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"])
    tax_map = _annual_map(args.ticker, ["IncomeTaxExpenseBenefit"])
    roic_series = []
    for y in sorted(oi_map, reverse=True)[:6]:
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

    cap = {
        "shares_trend": _series(shares),
        "buybacks": _series(buybacks),
        "dividends": _series(dividends),
        "debt_trend": _series(debt_lt),
    }

    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n\n"
        "Multi-year series computed in Python from XBRL (newest first; quote exactly):\n"
        f"Diluted shares outstanding: {_json.dumps(cap['shares_trend'])}\n"
        f"Share repurchases (PaymentsForRepurchaseOfCommonStock): {_json.dumps(cap['buybacks'])}\n"
        f"Common dividends paid: {_json.dumps(cap['dividends'])}\n"
        f"Long-term debt: {_json.dumps(cap['debt_trend'])}\n"
        f"ROIC (NOPAT / invested capital): {_json.dumps(roic_series)}\n\n"
        "Assess management's track record of execution and capital allocation. Did the "
        "share count fall (accretive buybacks) or rise (dilution)? Are dividends/buybacks "
        "sustainable? Is leverage rising into rising or falling ROIC? Judge the track "
        "record, fill capital_allocation for each lever, summarize the ROIC trend, and "
        "list concrete red flags. Set ticker in your answer."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "capital_allocation_series": cap,
        "roic_series": roic_series,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Assess management execution and capital allocation.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
