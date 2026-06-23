"""Size-aware universe snapshot.

Precomputes slow-changing per-company metrics (market cap, SIC, ADV, last price)
into the ``company_metrics`` table so a screen becomes an INSTANT filter over the
whole universe — no per-name SEC/price fetches at screen time, and no top-down
truncation that hid mid-caps below the first N mega-caps.

Keyless and foundational, so it lives in ``imdata`` (shared spine), reachable by
≥2 systems. It reuses the same SEC EDGAR + ``prices`` feed every system already
uses — no new data exposure. The only change vs. the old screen-time computation
is *when* it runs: a bounded, resumable batch refresher.

A provider abstraction is kept so a richer source (e.g. a snapshot API) could be
slotted in later, but only the keyless ``SecPriceProvider`` is built now — the
commercial providers (FMP/Finviz) are product work and explicitly deferred.

CLI:  python -m imdata.screener --refresh --max-names 500
"""
from __future__ import annotations

import argparse
import json
from typing import Optional

from . import config, edgar, estimates, prices, store, universe

# Cover-page share-count tags, in preference order.
SHARES_TAGS = ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]
# Above this SEC-vs-vendor market-cap ratio (either direction) we treat the SEC
# share count as wrong (the COKE case: a split share/price mismatch produced a ~10x
# UNDER-estimate) and prefer the vendor figure rather than shipping a bad level or
# silently dropping the name.
_MCAP_DISAGREE = 3.0  # max(sec/vendor, vendor/sec) > 3  => >3x off either way


def _latest_shares(ticker: str) -> Optional[float]:
    """Newest cover-page shares outstanding — a SINGLE fact, not a sum.

    companyfacts carries no share-class axis and the facts store's PK collapses two
    classes filed in one accession, so multiple rows in a period are the SAME class
    re-reported across filings (often with tiny differences). Summing them therefore
    overcounts; we take the value from the newest period instead. Genuine dual-class
    TOTALS are recovered by the vendor reconciliation in reconcile_mcap()."""
    return _newest_share_fact(ticker)


def _newest_share_fact(ticker: str) -> Optional[float]:
    for tag in SHARES_TAGS:
        rows = [r for r in edgar.get_concept(ticker, tag) if r["value"] and r["period_end"]]
        if rows:
            newest = max(r["period_end"] for r in rows)   # explicit, not rows[0]
            return float(next(r["value"] for r in rows if r["period_end"] == newest))
        rows0 = [r for r in edgar.get_concept(ticker, tag) if r["value"]]
        if rows0:
            return float(rows0[0]["value"])
    return None


def _row_get(row, key):
    """Works for both dicts and sqlite3.Row (which lacks .get)."""
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _adv_from_history(hist: list, days: int = 30) -> Optional[float]:
    vals = []
    for h in hist[-days:]:
        c, v = _row_get(h, "close"), _row_get(h, "volume")
        if c and v:
            vals.append(c * v)
    return float(sum(vals) / len(vals)) if vals else None


def reconcile_mcap(sec_mcap, vendor_mcap, third_mcap=None):
    """Pure decision: reconcile a SEC shares×price market cap against the vendor's.
    Returns (value, source, note). Prefers SEC when they agree; on a >3x disagreement
    (split/dual-class mismatch) it breaks the tie with an independent third source when
    one is supplied — picking whichever of SEC/vendor is closer — else falls back to
    the vendor; uses the vendor when SEC is missing; (None,'none',reason) when neither
    is usable. Shared by the snapshot builder AND comps-builder so the fix holds on
    every code path. Pure: the caller supplies third_mcap (no network here)."""
    sec_ok = isinstance(sec_mcap, (int, float)) and sec_mcap > 0
    ven_ok = isinstance(vendor_mcap, (int, float)) and vendor_mcap > 0
    if sec_ok and ven_ok:
        if max(sec_mcap / vendor_mcap, vendor_mcap / sec_mcap) > _MCAP_DISAGREE:
            if isinstance(third_mcap, (int, float)) and third_mcap > 0:
                # Independent tiebreak — not direction-blind: trust whoever the third
                # feed corroborates (fixes the "SEC right, vendor wrong" case).
                if abs(sec_mcap / third_mcap - 1) <= abs(vendor_mcap / third_mcap - 1):
                    return sec_mcap, "sec", (f"SEC ${sec_mcap/1e9:.1f}B vs vendor "
                                             f"${vendor_mcap/1e9:.1f}B disagree; independent "
                                             f"${third_mcap/1e9:.1f}B corroborates SEC")
                return vendor_mcap, "vendor", (f"SEC ${sec_mcap/1e9:.1f}B vs vendor "
                                               f"${vendor_mcap/1e9:.1f}B disagree; independent "
                                               f"${third_mcap/1e9:.1f}B corroborates vendor")
            return vendor_mcap, "vendor", (f"SEC shares×price ${sec_mcap/1e9:.1f}B disagrees "
                                           f"with vendor ${vendor_mcap/1e9:.1f}B — used vendor "
                                           "(likely split/dual-class share mismatch)")
        return sec_mcap, "sec", None
    if sec_ok:
        return sec_mcap, "sec", None
    if ven_ok:
        return vendor_mcap, "vendor", "SEC shares unavailable — used vendor market cap"
    return None, "none", "no shares×price and no vendor market cap"


# Back-compat alias (kept for callers/tests using the original underscore name).
_reconcile_mcap = reconcile_mcap


def _market_cap(ticker: str, quote: dict, last_px: Optional[float]):
    """Robust market cap -> (value, source, note). Computes the SEC shares×price
    figure (dual-class aware) and reconciles it against the vendor quote."""
    try:
        shares = _latest_shares(ticker)
    except Exception:
        shares = None
    sec_mcap = shares * last_px if (shares and last_px) else None
    vendor_mcap = quote.get("market_cap")
    # Only pay for the independent third feed when SEC & vendor actually disagree.
    third = None
    if (isinstance(sec_mcap, (int, float)) and sec_mcap > 0
            and isinstance(vendor_mcap, (int, float)) and vendor_mcap > 0
            and max(sec_mcap / vendor_mcap, vendor_mcap / sec_mcap) > _MCAP_DISAGREE):
        try:
            third = prices.independent_market_cap(ticker)
        except Exception:
            third = None
    return reconcile_mcap(sec_mcap, vendor_mcap, third)


class SecPriceProvider:
    """Keyless metrics from SEC EDGAR + the shared prices feed (+ a vendor quote
    cross-check). One fetch path per name; everything is cached in the store."""
    name = "sec+price"

    def metrics(self, ticker: str) -> dict:
        t = ticker.upper()
        quote = {}
        try:
            quote = estimates.get_quote(t) or {}
        except Exception:
            quote = {}
        hist = []
        try:
            hist = prices.get_history(t, lookback_days=400) or []
        except Exception:
            hist = []
        last_px = _row_get(hist[-1], "close") if hist else prices.last_price(t)
        mcap, src, note = _market_cap(t, quote, last_px)
        sic = sic_desc = country = None
        try:
            meta = edgar.company_meta(t)
            sic, sic_desc, country = meta.get("sic"), meta.get("sic_description"), meta.get("country")
        except Exception:
            note = (note + "; " if note else "") + "SIC/country unavailable"
        try:
            sic = int(sic) if sic not in (None, "") else None
        except (TypeError, ValueError):
            pass
        # Non-USD vendor quote: flag (FX not applied) so a foreign-currency cap isn't
        # silently compared against USD bands. See estimates.data_quality for the
        # per-figure flag; here we annotate the snapshot row.
        cur = quote.get("currency")
        if cur and cur != "USD":
            note = (note + "; " if note else "") + f"non-USD quote ({cur}); FX not applied"
        return {"ticker": t, "market_cap": mcap, "sic": sic, "sic_description": sic_desc,
                "adv": _adv_from_history(hist), "last_px": last_px,
                "currency": cur, "country": country, "source": src, "note": note}


def refresh_metrics(tickers=None, max_names: int = 500, provider=None) -> dict:
    """Populate/refresh ``company_metrics`` for the stalest ``max_names`` tickers
    (or an explicit ``tickers`` list). Bounded and resumable — call repeatedly to
    page coverage through the whole universe."""
    provider = provider or SecPriceProvider()
    if store.companies_count() == 0:
        universe.refresh_universe()
    if tickers is None:
        targets = store.stale_tickers(config.TTL_METRICS, max_names)
    else:
        # Resolve to canonical universe tickers (handles BRK.B -> BRK-B) and drop
        # anything not in the universe, so a typo never becomes a null junk row.
        targets, skipped = [], []
        for raw in tickers[:max_names]:
            row = store.company_by_ticker(raw)
            (targets.append(row["ticker"]) if row else skipped.append(raw))
    rows, ok, fail = [], 0, 0
    for t in targets:
        try:
            rows.append(provider.metrics(t))
            ok += 1
        except Exception:
            fail += 1
    if rows:
        store.upsert_metrics(rows)
    out = {"provider": provider.name, "requested": len(targets),
           "refreshed": ok, "failed": fail,
           "snapshot_coverage": store.metrics_count(),
           "universe": store.companies_count()}
    if tickers is not None and skipped:
        out["skipped_unknown"] = skipped
    return out


def _main():
    p = argparse.ArgumentParser(description="Refresh the size-aware universe snapshot.")
    p.add_argument("--refresh", action="store_true", help="refresh the stalest metrics")
    p.add_argument("--max-names", type=int, default=500, help="bound on names per run")
    p.add_argument("--tickers", nargs="*", default=None, help="explicit tickers to refresh")
    args = p.parse_args()
    if args.refresh or args.tickers:
        print(json.dumps(refresh_metrics(args.tickers, args.max_names), indent=2))
    else:
        print(json.dumps({"snapshot_coverage": store.metrics_count(),
                          "universe": store.companies_count()}, indent=2))


if __name__ == "__main__":
    _main()
