"""correlation-analyzer: cross-holding correlation + concentration. Deterministic (numpy)."""
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

from imdata import prices, skillkit, universe


def main(args):
    if len(args.tickers) < 2:
        raise ValueError("Provide at least 2 tickers.")
    tickers = [universe.resolve(t)["ticker"] for t in args.tickers]

    if args.weights:
        if len(args.weights) != len(tickers):
            raise ValueError("--weights count must match --tickers count.")
        weights_in = list(args.weights)
    else:
        weights_in = [1.0 / len(tickers)] * len(tickers)

    # Build per-ticker date->close maps over the lookback window.
    notes = []
    series = {}
    for t in tickers:
        prices.refresh_prices(t, lookback_days=max(args.lookback + 35, 400))
        hist = prices.get_history(t, lookback_days=args.lookback, refresh=False)
        closes = {h["date"]: h["close"] for h in hist if h["close"] is not None}
        if len(closes) < 5:
            notes.append(f"dropped {t} (insufficient price data)")
            continue
        series[t] = closes

    kept = [t for t in tickers if t in series]
    if len(kept) < 2:
        return {
            "tickers": tickers, "weights": weights_in, "lookback_days": args.lookback,
            "correlation_matrix": {}, "avg_pairwise_correlation": None,
            "herfindahl_index": None, "concentration_flags": [],
            "summary": "Could not compute correlations: " + ("; ".join(notes) or "too few series."),
        }

    # Re-normalize kept weights to sum to 1 over the surviving set.
    idx = {t: i for i, t in enumerate(tickers)}
    kept_weights_raw = [weights_in[idx[t]] for t in kept]
    wsum = sum(kept_weights_raw)
    kept_weights = [w / wsum for w in kept_weights_raw] if wsum > 0 else \
        [1.0 / len(kept)] * len(kept)

    # Align on the intersection of dates, then daily simple returns.
    common = set.intersection(*[set(series[t].keys()) for t in kept])
    common_dates = sorted(common)
    if len(common_dates) < 5:
        return {
            "tickers": tickers, "weights": kept_weights, "lookback_days": args.lookback,
            "correlation_matrix": {}, "avg_pairwise_correlation": None,
            "herfindahl_index": round(float(sum(w * w for w in kept_weights)), 4),
            "concentration_flags": [],
            "summary": "Too few overlapping trading days across holdings to correlate.",
        }
    price_mat = np.array([[series[t][d] for d in common_dates] for t in kept], dtype=float)
    ret_mat = np.diff(np.log(price_mat), axis=1)
    corr = np.corrcoef(ret_mat)

    correlation_matrix = {}
    for i, a in enumerate(kept):
        correlation_matrix[a] = {b: round(float(corr[i, j]), 3) for j, b in enumerate(kept)}

    # Average pairwise correlation (upper triangle, excluding diagonal).
    n = len(kept)
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    avg_corr = round(float(np.mean([corr[i, j] for i, j in pairs])), 4) if pairs else None

    herfindahl = round(float(sum(w * w for w in kept_weights)), 4)

    # --- concentration flags --------------------------------------------- #
    flags = []
    for i, j in pairs:
        c = float(corr[i, j])
        if abs(c) >= args.corr_threshold:
            flags.append({
                "type": "high_correlation",
                "pair": [kept[i], kept[j]],
                "correlation": round(c, 3),
            })
    for t, w in zip(kept, kept_weights):
        if w >= args.weight_threshold:
            flags.append({"type": "large_position", "ticker": t, "weight": round(w, 4)})
    flags.append({"type": "herfindahl_index", "value": herfindahl,
                  "note": "1/N would be %.4f for an equal-weight book" % (1.0 / n)})

    high_corr = [f for f in flags if f["type"] == "high_correlation"]
    big_pos = [f for f in flags if f["type"] == "large_position"]
    summary = (
        f"{n} holdings over {args.lookback}d: avg pairwise correlation "
        f"{avg_corr:+.2f}, Herfindahl {herfindahl:.3f}. "
        + (f"{len(high_corr)} pair(s) >= {args.corr_threshold:.2f} correlation. "
           if high_corr else "No highly-correlated pairs. ")
        + (f"{len(big_pos)} position(s) >= {args.weight_threshold:.0%} weight. "
           if big_pos else "")
        + ("; ".join(notes) + "." if notes else "")
    ).strip()
    return {
        "tickers": tickers,
        "weights": [round(w, 6) for w in kept_weights],
        "kept_tickers": kept,
        "lookback_days": args.lookback,
        "overlapping_days": len(common_dates),
        "correlation_matrix": correlation_matrix,
        "avg_pairwise_correlation": avg_corr,
        "herfindahl_index": herfindahl,
        "concentration_flags": flags,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cross-holding correlation and concentration.")
    p.add_argument("--tickers", nargs="+", required=True, help="2+ tickers")
    p.add_argument("--weights", nargs="+", type=float, default=None,
                   help="optional, same count as tickers; else equal-weight")
    p.add_argument("--lookback", type=int, default=365, help="calendar days")
    p.add_argument("--corr-threshold", type=float, default=0.8)
    p.add_argument("--weight-threshold", type=float, default=0.25)
    skillkit.run(main, p)
