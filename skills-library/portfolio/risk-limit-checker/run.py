"""risk-limit-checker: check drawdown, exposures, and limit breaches for positions."""
import argparse
import os
import sys

import numpy as np

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

from imdata import skillkit, prices, universe


def _parse_position(spec):
    """Parse 'TICKER=weight' into (ticker, weight)."""
    if "=" not in spec:
        raise ValueError(f"Bad --positions {spec!r}; expected TICKER=weight")
    tkr, w = spec.split("=", 1)
    tkr = universe.resolve(tkr)["ticker"]
    return tkr, float(w)


def _closes_by_date(ticker, lookback):
    """Map date -> close for a ticker over the lookback window."""
    hist = prices.get_history(ticker, lookback_days=lookback)
    return {h["date"]: h["close"] for h in hist if h["close"] is not None}


def main(args):
    if not args.positions:
        raise ValueError("Provide at least one --positions TICKER=weight.")

    exposures = {}
    for spec in args.positions:
        tkr, w = _parse_position(spec)
        exposures[tkr] = exposures.get(tkr, 0.0) + w

    gross_exposure = sum(abs(w) for w in exposures.values())
    net_exposure = sum(exposures.values())

    # Build a weighted portfolio index aligned on the intersection of dates.
    series = {t: _closes_by_date(t, args.lookback) for t in exposures}
    missing = [t for t, s in series.items() if not s]
    common = None
    for t, s in series.items():
        if not s:
            continue
        common = set(s) if common is None else (common & set(s))
    common_dates = sorted(common) if common else []

    max_drawdown = None
    if len(common_dates) >= 2:
        base = {t: series[t][common_dates[0]] for t in exposures if series[t]}
        index = []
        for d in common_dates:
            val = 0.0
            for t, w in exposures.items():
                if series[t] and base.get(t):
                    val += w * (series[t][d] / base[t])
            index.append(val)
        arr = np.array(index, dtype=float)
        running_max = np.maximum.accumulate(arr)
        drawdowns = arr / running_max - 1.0  # negative numbers
        max_drawdown = float(drawdowns.min())  # most negative

    dd_mag = abs(max_drawdown) if max_drawdown is not None else None

    breaches = []
    for t, w in exposures.items():
        if w > args.max_weight:
            breaches.append({
                "type": "max_weight",
                "detail": f"{t} weight {w:.4f} > max_weight {args.max_weight:.4f}",
            })
    if gross_exposure > args.max_gross:
        breaches.append({
            "type": "max_gross",
            "detail": f"gross_exposure {gross_exposure:.4f} > max_gross {args.max_gross:.4f}",
        })
    if dd_mag is not None and dd_mag > args.max_drawdown:
        breaches.append({
            "type": "max_drawdown",
            "detail": f"max_drawdown {dd_mag:.4f} > limit {args.max_drawdown:.4f}",
        })

    summary = (
        f"{len(exposures)} position(s): gross {gross_exposure:.2%}, net {net_exposure:.2%}, "
        + (f"max drawdown {dd_mag:.2%} over {args.lookback}d. " if dd_mag is not None
           else "drawdown unavailable (no overlapping prices). ")
        + (f"{len(breaches)} breach(es): "
           + "; ".join(b["type"] for b in breaches) + "."
           if breaches else "No limit breaches.")
        + (f" Price data missing for: {', '.join(missing)}." if missing else "")
    )
    return {
        "positions": args.positions,
        "exposures": {"by_ticker": {t: round(w, 6) for t, w in exposures.items()}},
        "gross_exposure": round(gross_exposure, 6),
        "net_exposure": round(net_exposure, 6),
        "max_drawdown": round(dd_mag, 6) if dd_mag is not None else None,
        "limits": {
            "max_weight": args.max_weight,
            "max_drawdown": args.max_drawdown,
            "max_gross": args.max_gross,
            "lookback": args.lookback,
        },
        "breaches": breaches,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Check drawdown, exposures, and limit breaches for positions."
    )
    p.add_argument("--positions", action="append", default=None,
                   help="repeatable TICKER=weight (fractions), e.g. MSFT=0.40")
    p.add_argument("--lookback", type=int, default=365, help="days")
    p.add_argument("--max-weight", type=float, default=0.10)
    p.add_argument("--max-drawdown", type=float, default=0.25,
                   help="positive magnitude")
    p.add_argument("--max-gross", type=float, default=1.5)
    skillkit.run(main, p)
