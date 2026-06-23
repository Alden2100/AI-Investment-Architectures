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


# SIC descriptions are idiosyncratic, so an intuitive sector word silently misses
# whole sub-industries. Map friendly terms to the SIC-description substrings AND/OR
# SIC-code prefixes that actually identify the sector (match ANY) — recall, not the
# raw substring. A value is either a list of description substrings, or a dict
# {"desc": [...], "sic": [<code prefixes>]}. Code prefixes are precise where a
# description substring would over-match (e.g. "defense" via "aircraft"/"tank").
SECTOR_SYNONYMS = {
    # Software hides under several SICs: 7372 prepackaged, 7370 computer services
    # (where many internet/SaaS names + Alphabet sit), 7371 programming services,
    # 7389 services-NEC. A bare "software" substring only matches 7372 — miss the rest.
    "software": {"desc": ["software"], "sic": ["7372", "7370", "7371", "7389"]},
    "saas": {"desc": ["software"], "sic": ["7372", "7370", "7371", "7389"]},
    "biotech": ["biological", "life sciences", "physical & biological research",
                "in vitro & in vivo"],
    "biotechnology": ["biological", "life sciences", "physical & biological research"],
    "reit": ["real estate investment trust"],
    "reits": ["real estate investment trust"],
    # Scope defense to ordnance/missile/tank/defense-systems SIC codes, not loose
    # description words ("aircraft" pulled commercial planes, "tank" pulled metal tanks).
    "defense": {"desc": ["guided missile", "ordnance", "ammunition"],
                "sic": ["348", "3760", "3761", "3795", "3812"]},
    "defence": {"desc": ["guided missile", "ordnance", "ammunition"],
                "sic": ["348", "3760", "3761", "3795", "3812"]},
    "thrift": ["savings institution"],
    "thrifts": ["savings institution"],
    "savings": ["savings institution"],
    "auto": ["motor vehicle"],
    "automotive": ["motor vehicle"],
    "airline": ["air transportation"],
    "airlines": ["air transportation"],
    "telecom": ["telephone", "telegraph", "communications services"],
    "oilgas": ["crude petroleum", "petroleum refining", "oil & gas"],
    "oil": ["crude petroleum", "petroleum refining", "oil & gas"],
    "gas": ["crude petroleum", "natural gas", "oil & gas"],
}


def _sic_match(term, sic, desc):
    """True if a row's SIC code/description matches a sector term, expanding synonyms.
    Synonym value may be a list of description substrings or a {desc, sic} dict."""
    if not term:
        return True
    d = (desc or "").lower()
    syn = SECTOR_SYNONYMS.get(term.lower().strip())
    if isinstance(syn, dict):
        if any(s in d for s in syn.get("desc", [])):
            return True
        sc = str(sic or "")
        return any(sc.startswith(p) for p in syn.get("sic", []))
    if isinstance(syn, list):
        return any(s in d for s in syn)
    return term.lower() in d


def _passes(rec, args):
    """Apply the expensive filters (SIC / cap band / ADV / country) to a snapshot row.
    Band/ADV bounds use ``is not None`` so an explicit 0 is a real bound, not 'unset'."""
    if args.sic and str(rec.get("sic")) != str(args.sic):
        return False
    if args.sic_contains and not _sic_match(args.sic_contains, rec.get("sic"), rec.get("sic_description")):
        return False
    # --us-only excludes only KNOWN-foreign rows. A NULL country is "unknown" (e.g. a
    # pre-migration snapshot row the additive ALTER didn't backfill) — don't silently
    # drop it as foreign; re-warm to classify it.
    if getattr(args, "us_only", False):
        ctry = rec.get("country")
        if ctry is not None and str(ctry).upper() != "US":
            return False
    mcap = rec.get("market_cap")
    if args.min_mcap is not None and (mcap is None or mcap < args.min_mcap):
        return False
    if args.max_mcap is not None and (mcap is None or mcap > args.max_mcap):
        return False
    adv = rec.get("adv")
    if args.min_adv is not None and (adv is None or adv < args.min_adv):
        return False
    return True


def _snapshot_screen(args):
    """Filter company_metrics across the WHOLE universe — no per-name fetch, no
    truncation. Returns (matches, coverage_count)."""
    matches = []
    rows = store.all_metrics()
    for m in rows:
        rec = {"ticker": m["ticker"], "title": m["title"] or m["ticker"],
               "sic": m["sic"], "sic_description": m["sic_description"],
               "market_cap": m["market_cap"], "adv": m["adv"], "country": m["country"]}
        if m["note"]:
            rec["data_note"] = m["note"]
        if args.name_contains and args.name_contains.lower() not in (rec["title"] or "").lower():
            continue
        if _passes(rec, args):
            matches.append(rec)
    # Explicit size ordering — no longer leaning on insertion (≈ size) order.
    matches.sort(key=lambda r: (r.get("market_cap") is None, -(r.get("market_cap") or 0)))
    return matches, len(rows)


def _live_screen(args):
    """Cold-cache fallback: compute metrics per name, bounded by --max-fetch (this
    is the only path that can still truncate). Kept for a cold snapshot and for
    tickers missing from it."""
    if args.ticker_in:
        base, seen = [], set()
        for t in args.ticker_in:
            row = store.company_by_ticker(t)            # case/dot-normalized; drops unknowns
            if row and row["ticker"] not in seen:
                base.append({"ticker": row["ticker"], "title": row["title"]})
                seen.add(row["ticker"])
    else:
        base = [{"ticker": r["ticker"], "title": r["title"]} for r in store.all_companies()]
    if args.name_contains:
        nc = args.name_contains.lower()
        base = [c for c in base if nc in (c["title"] or "").lower()]
    wants_expensive = any([args.sic, args.sic_contains, getattr(args, 'us_only', False),
                           args.min_mcap is not None, args.max_mcap is not None,
                           args.min_adv is not None])
    truncated = False
    if wants_expensive and len(base) > args.max_fetch:
        base = base[: args.max_fetch]
        truncated = True
    matches = []
    for c in base:
        rec = {"ticker": c["ticker"], "title": c["title"]}
        keep = True
        if args.sic or args.sic_contains or getattr(args, "us_only", False):
            try:
                meta = edgar.company_meta(c["ticker"])
            except Exception:
                continue
            rec["sic"], rec["sic_description"] = meta.get("sic"), meta.get("sic_description")
            rec["country"] = meta.get("country")
            if args.sic and str(meta.get("sic")) != str(args.sic):
                keep = False
            if args.sic_contains and not _sic_match(args.sic_contains, meta.get("sic"), meta.get("sic_description")):
                keep = False
            _ctry = meta.get("country")
            if getattr(args, "us_only", False) and _ctry is not None and str(_ctry).upper() != "US":
                keep = False
        if keep and (args.min_mcap is not None or args.max_mcap is not None):
            try:
                mcap = _market_cap(c["ticker"])
            except Exception:
                continue
            rec["market_cap"] = mcap
            if mcap is None or (args.min_mcap is not None and mcap < args.min_mcap) \
                    or (args.max_mcap is not None and mcap > args.max_mcap):
                keep = False
        if keep and args.min_adv is not None:
            try:
                adv = _adv(c["ticker"])
            except Exception:
                continue
            rec["adv"] = adv
            if adv is None or adv < args.min_adv:
                keep = False
        if keep:
            matches.append(rec)
    return matches, truncated


def main(args):
    if store.companies_count() == 0:
        universe.refresh_universe()

    wants_expensive = any([args.sic, args.sic_contains, getattr(args, 'us_only', False),
                           args.min_mcap is not None, args.max_mcap is not None,
                           args.min_adv is not None])
    # The snapshot path is for sector/size mandates over the open universe; an
    # explicit ticker list or a cheap name-only screen still goes the direct route.
    use_snapshot = args.use_snapshot and wants_expensive and not args.ticker_in

    # Cold snapshot + a size/sector mandate: trigger a bounded warm so we report
    # partial coverage rather than silently returning a near-empty mega-cap slice.
    warmed = None
    if use_snapshot and store.metrics_count() == 0:
        try:
            from imdata import screener
            warmed = screener.refresh_metrics(max_names=args.warm_names)
        except Exception:
            warmed = None

    truncated = False
    snapshot_coverage = None
    if use_snapshot and store.metrics_count() > 0:
        matches, cov = _snapshot_screen(args)
        snapshot_coverage = {"snapshot_names": cov, "universe": store.companies_count()}
    else:
        matches, truncated = _live_screen(args)

    matches = matches[: args.limit]
    criteria = {k: v for k, v in vars(args).items()
                if v not in (None, False) and k not in ("use_snapshot",)}
    # Partial coverage = the snapshot index isn't fully built. Surface a clear,
    # actionable hint so a thin result reads as "index not warmed yet", NOT as "no
    # such names exist" (the failure that led to hand-seeding tickers).
    setup_hint = None
    if snapshot_coverage:
        frac = snapshot_coverage["snapshot_names"] / max(1, snapshot_coverage["universe"])
        if frac < 0.6:
            setup_hint = (
                f"PARTIAL INDEX: the size-aware snapshot covers only "
                f"{snapshot_coverage['snapshot_names']} of {snapshot_coverage['universe']} "
                "names, so this screen is incomplete — a thin result here does NOT mean no "
                "such companies exist. Build the index once (a few minutes, then cached): "
                "`python -m imdata.screener --refresh --max-names 3000` (repeat to page the "
                "whole universe), then re-run this screen.")

    summary = f"{len(matches)} match(es) for criteria {criteria}."
    if truncated:
        summary += (f" Candidate set truncated to {args.max_fetch} for the expensive "
                    "filters (cold-cache live path — warm the snapshot to remove this).")
    elif snapshot_coverage:
        summary += (f" Filtered over {snapshot_coverage['snapshot_names']} of "
                    f"{snapshot_coverage['universe']} names in the size-aware snapshot.")
        if setup_hint:
            summary += " ⚠ Index partial — see setup_hint."
    out = {
        "criteria": criteria,
        "matches": matches,
        "count": len(matches),
        "truncated": truncated,
        "snapshot_coverage": snapshot_coverage,
        "summary": summary,
    }
    if warmed:
        out["warmed"] = warmed
    if setup_hint:
        out["setup_hint"] = setup_hint
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Screen the investable universe.")
    p.add_argument("--name-contains", default=None)
    p.add_argument("--ticker-in", nargs="*", default=None)
    p.add_argument("--sic", default=None, help="exact SIC code")
    p.add_argument("--sic-contains", default=None, help="SIC description substring")
    p.add_argument("--min-mcap", type=float, default=None, help="min market cap USD")
    p.add_argument("--max-mcap", type=float, default=None, help="max market cap USD")
    p.add_argument("--min-adv", type=float, default=None, help="min avg daily $ volume")
    p.add_argument("--us-only", dest="us_only", action="store_true",
                   help="keep only US filers (EDGAR business address); excludes foreign "
                        "private issuers / ADRs")
    p.add_argument("--max-fetch", type=int, default=30, help="cap for the cold-cache live path only")
    p.add_argument("--warm-names", type=int, default=500,
                   help="names to warm on a cold snapshot before screening")
    p.add_argument("--use-snapshot", dest="use_snapshot", action="store_true", default=True,
                   help="filter the precomputed snapshot across the whole universe (default)")
    p.add_argument("--no-snapshot", dest="use_snapshot", action="store_false",
                   help="force the per-name live path (cold cache / debugging)")
    p.add_argument("--limit", type=int, default=50)
    skillkit.run(main, p)
