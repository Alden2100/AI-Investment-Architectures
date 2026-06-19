"""kpi-tracker: compare a thesis's target KPIs to current values and flag breaches."""
import argparse
import json
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

from imdata import skillkit, store, prices, edgar

# --- metric spec shared concept -------------------------------------------- #
# A KPI is name:metric:comparator:target. metric resolves to a current numeric
# value for a ticker via _metric_value(); comparators are exact deterministic ops.

_XBRL_TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "net_income": ["NetIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
}

METRICS = set(_XBRL_TAGS) | {"price", "return_1y"}

_COMPARATORS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: abs(a - b) <= (1e-6 + 1e-4 * abs(b)),  # approx equality
}


def _latest_annual_xbrl(ticker, tags):
    """First 10-K value (newest-first) across the candidate tags, else None."""
    for tag in tags:
        for row in edgar.get_concept(ticker, tag):
            if row["form"] == "10-K" and row["value"] is not None:
                return float(row["value"])
    return None


def _metric_value(ticker, metric):
    """Resolve a metric name to a current numeric value, or None if unavailable."""
    if metric in _XBRL_TAGS:
        return _latest_annual_xbrl(ticker, _XBRL_TAGS[metric])
    if metric == "price":
        return prices.last_price(ticker)
    if metric == "return_1y":
        hist = prices.get_history(ticker, lookback_days=365)
        closes = [h["close"] for h in hist if h["close"] is not None]
        if len(closes) < 2 or closes[0] == 0:
            return None
        return closes[-1] / closes[0] - 1.0
    raise ValueError(f"Unknown metric {metric!r}; choose from {sorted(METRICS)}")


def _parse_kpi(spec):
    """Parse 'name:metric:comparator:target' into a dict."""
    parts = spec.split(":")
    if len(parts) != 4:
        raise ValueError(
            f"Bad --kpi {spec!r}; expected name:metric:comparator:target"
        )
    name, metric, comparator, target = parts
    if metric not in METRICS:
        raise ValueError(f"Unknown metric {metric!r} in --kpi {spec!r}")
    if comparator not in _COMPARATORS:
        raise ValueError(f"Unknown comparator {comparator!r} in --kpi {spec!r}")
    return {
        "name": name,
        "metric": metric,
        "comparator": comparator,
        "target": float(target),
    }


def main(args):
    ticker = args.ticker.upper() if args.ticker else None
    kpis = []

    if args.thesis_id:
        row = store.get_thesis(args.thesis_id)
        if row is None:
            raise ValueError(f"No thesis found with id {args.thesis_id!r}")
        ticker = (ticker or row["ticker"]).upper()
        for k in json.loads(row["kpis_json"] or "[]"):
            kpis.append({
                "name": k["name"],
                "metric": k["metric"],
                "comparator": k["comparator"],
                "target": float(k["target"]),
            })

    for spec in (args.kpi or []):
        kpis.append(_parse_kpi(spec))

    if not ticker:
        raise ValueError("Provide --ticker (or a --thesis-id that carries one).")
    if not kpis:
        raise ValueError("No KPIs given; supply --kpi and/or --thesis-id.")

    results = []
    breaches = []
    for k in kpis:
        current = _metric_value(ticker, k["metric"])
        if current is None:
            status = "unknown"
        elif _COMPARATORS[k["comparator"]](current, k["target"]):
            status = "ok"
        else:
            status = "breach"
            breaches.append(k["name"])
        results.append({
            "name": k["name"],
            "metric": k["metric"],
            "comparator": k["comparator"],
            "target": k["target"],
            "current": round(current, 6) if current is not None else None,
            "status": status,
        })

    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_unknown = sum(1 for r in results if r["status"] == "unknown")
    summary = (
        f"{ticker}: {len(results)} KPI(s) checked - {n_ok} ok, "
        f"{len(breaches)} breach, {n_unknown} unknown."
        + (f" Breaches: {', '.join(breaches)}." if breaches else "")
    )
    out = {
        "ticker": ticker,
        "kpis": results,
        "breaches": breaches,
        "summary": summary,
    }
    if args.thesis_id:
        out["thesis_id"] = args.thesis_id
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Compare a thesis's target KPIs to current values and flag breaches."
    )
    p.add_argument("--ticker", default=None, help="required unless --thesis-id given")
    p.add_argument("--thesis-id", default=None, help="load KPIs+ticker from the store")
    p.add_argument(
        "--kpi", action="append", default=None,
        help="repeatable name:metric:comparator:target, e.g. rev:revenue:>=:3.0e11",
    )
    skillkit.run(main, p)
