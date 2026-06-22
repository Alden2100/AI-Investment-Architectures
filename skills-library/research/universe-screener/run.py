"""universe-screener: filter the US public universe by mandate. Deterministic."""
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

from imdata import edgar, prices, skillkit, store, universe

SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]


def _latest_shares(ticker):
    for tag in SHARES_TAGS:
        rows = [r for r in edgar.get_concept(ticker, tag) if r["value"]]
        if rows:
            return rows[0]["value"]  # get_concept returns newest-first
    return None


def _market_cap(ticker):
    shares = _latest_shares(ticker)
    px = prices.last_price(ticker)
    if shares and px:
        return shares * px
    return None


def _adv(ticker, days=30):
    hist = prices.get_history(ticker, lookback_days=max(days + 10, 60))
    vals = [h["close"] * h["volume"] for h in hist[-days:]
            if h["close"] and h["volume"]]
    return float(np.mean(vals)) if vals else None


def main(args):
    if store.companies_count() == 0:
        universe.refresh_universe()

    # --- base candidate set --------------------------------------------- #
    if args.ticker_in:
        base = []
        for t in args.ticker_in:
            row = store.company_by_ticker(t)
            if row:
                base.append({"ticker": row["ticker"], "title": row["title"]})
    else:
        base = [{"ticker": r["ticker"], "title": r["title"]} for r in store.all_companies()]

    # --- cheap filters --------------------------------------------------- #
    if args.name_contains:
        nc = args.name_contains.lower()
        base = [c for c in base if nc in (c["title"] or "").lower()]

    wants_expensive = any([args.sic, args.sic_contains, args.min_mcap,
                           args.max_mcap, args.min_adv])
    truncated = False
    if wants_expensive and len(base) > args.max_fetch:
        base = base[: args.max_fetch]
        truncated = True

    # --- expensive filters ---------------------------------------------- #
    matches = []
    for c in base:
        rec = {"ticker": c["ticker"], "title": c["title"]}
        keep = True
        if args.sic or args.sic_contains:
            try:
                meta = edgar.company_meta(c["ticker"])
            except Exception:
                continue
            rec["sic"] = meta.get("sic")
            rec["sic_description"] = meta.get("sic_description")
            if args.sic and str(meta.get("sic")) != str(args.sic):
                keep = False
            if args.sic_contains and args.sic_contains.lower() not in (
                meta.get("sic_description") or "").lower():
                keep = False
        if keep and (args.min_mcap or args.max_mcap):
            try:
                mcap = _market_cap(c["ticker"])
            except Exception:
                continue  # a single name without facts/prices must not kill the scan
            rec["market_cap"] = mcap
            if mcap is None or (args.min_mcap and mcap < args.min_mcap) or (
                args.max_mcap and mcap > args.max_mcap):
                keep = False
        if keep and args.min_adv:
            try:
                adv = _adv(c["ticker"])
            except Exception:
                continue
            rec["adv"] = adv
            if adv is None or adv < args.min_adv:
                keep = False
        if keep:
            matches.append(rec)

    matches = matches[: args.limit]
    criteria = {k: v for k, v in vars(args).items() if v not in (None, False)}
    summary = (
        f"{len(matches)} match(es) for criteria {criteria}."
        + (f" Candidate set truncated to {args.max_fetch} for the expensive filters."
           if truncated else "")
    )
    return {
        "criteria": criteria,
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Screen the investable universe.")
    p.add_argument("--name-contains", default=None)
    p.add_argument("--ticker-in", nargs="*", default=None)
    p.add_argument("--sic", default=None, help="exact SIC code")
    p.add_argument("--sic-contains", default=None, help="SIC description substring")
    p.add_argument("--min-mcap", type=float, default=None, help="min market cap USD")
    p.add_argument("--max-mcap", type=float, default=None, help="max market cap USD")
    p.add_argument("--min-adv", type=float, default=None, help="min avg daily $ volume")
    p.add_argument("--max-fetch", type=int, default=30)
    p.add_argument("--limit", type=int, default=50)
    skillkit.run(main, p)
