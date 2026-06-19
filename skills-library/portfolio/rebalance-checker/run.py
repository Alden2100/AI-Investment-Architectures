"""rebalance-checker: flag drift from target weights and emit fix trades. Deterministic."""
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

from imdata import skillkit# noqa: F401  (kept for the standard harness/output)


def _parse_pairs(items, label):
    """Parse TICKER=weight pairs into an ordered dict."""
    out = {}
    for it in items or []:
        if "=" not in it:
            raise ValueError(f"--{label} entry '{it}' must be TICKER=weight.")
        tk, _, w = it.partition("=")
        tk = tk.strip().upper()
        if not tk:
            raise ValueError(f"--{label} entry '{it}' missing ticker.")
        try:
            out[tk] = float(w)
        except ValueError:
            raise ValueError(f"--{label} entry '{it}' has non-numeric weight.")
    return out


def main(args):
    current = _parse_pairs(args.current, "current")
    target = _parse_pairs(args.target, "target")
    if not current and not target:
        raise ValueError("Provide at least one --current or --target weight.")

    # Preserve first-seen order: current tickers, then any new target tickers.
    tickers = list(current.keys())
    for t in target.keys():
        if t not in tickers:
            tickers.append(t)

    drift = []
    trades = []
    breaches = 0
    for t in tickers:
        cur = current.get(t, 0.0)
        tgt = target.get(t, 0.0)
        d = cur - tgt
        breach = abs(d) > args.tolerance
        if breach:
            breaches += 1
        drift.append({
            "ticker": t,
            "current": round(cur, 6),
            "target": round(tgt, 6),
            "drift": round(d, 6),
            "breach": breach,
        })
        trade_w = tgt - cur  # positive = buy, negative = sell
        if abs(trade_w) > 1e-12:
            trade = {
                "ticker": t,
                "action": "buy" if trade_w > 0 else "sell",
                "weight_change": round(trade_w, 6),
            }
            if args.portfolio_value is not None:
                trade["dollar_change"] = round(trade_w * args.portfolio_value, 2)
            trades.append(trade)

    cur_sum = sum(current.values())
    tgt_sum = sum(target.values())
    notes = []
    if current and abs(cur_sum - 1.0) > 0.01:
        notes.append(f"current weights sum to {cur_sum:.2f}")
    if target and abs(tgt_sum - 1.0) > 0.01:
        notes.append(f"target weights sum to {tgt_sum:.2f}")

    if breaches:
        worst = max((d for d in drift if d["breach"]), key=lambda x: abs(x["drift"]))
        summary = (
            f"{breaches} holding(s) breach the {args.tolerance:.1%} tolerance; "
            f"{len(trades)} trade(s) to rebalance. Largest drift: {worst['ticker']} "
            f"{worst['drift']:+.1%} (current {worst['current']:.1%} vs target "
            f"{worst['target']:.1%})."
        )
    else:
        summary = (f"Portfolio within {args.tolerance:.1%} tolerance on all "
                   f"{len(tickers)} holding(s); no rebalance required.")
    if notes:
        summary += " Note: " + "; ".join(notes) + "."

    return {
        "tolerance": args.tolerance,
        "drift": drift,
        "trades": trades,
        "breaches_count": breaches,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Flag weight drift and produce rebalance trades.")
    p.add_argument("--current", nargs="+", default=None, help="TICKER=weight ...")
    p.add_argument("--target", nargs="+", default=None, help="TICKER=weight ...")
    p.add_argument("--tolerance", type=float, default=0.02)
    p.add_argument("--portfolio-value", type=float, default=None,
                   help="USD; if given, adds dollar trade sizes")
    skillkit.run(main, p)
