"""Free, keyless forward-looking data: analyst consensus + ownership/short interest.

Source: yfinance (Yahoo), the same vendor already used for prices. This fills the
two gaps a real note needs — the CONSENSUS to differentiate a view against (forward
EPS/revenue estimates, growth, price targets, recommendations) and the OWNERSHIP /
float / short-interest picture for risk. All best-effort: Yahoo's schema drifts and
fields go missing, so every accessor degrades to None rather than raising. Results
are cached (kv, 1-day TTL) so repeat calls in a run are cheap.

No API key. yfinance is an unofficial Yahoo scrape — fine for individual research;
treat values as best-effort, not gospel.
"""
from __future__ import annotations

from typing import Optional

from . import store

_TTL = 24 * 3600  # consensus/ownership move slowly; one day is plenty


def _yf(ticker: str):
    import yfinance as yf  # lazy: only import when actually used
    return yf.Ticker(ticker.upper())


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


def _df_records(df):
    """A yfinance DataFrame -> list of {period, **cols} dicts, JSON-safe."""
    try:
        if df is None or getattr(df, "empty", True):
            return []
        d = df.reset_index()
        out = []
        for rec in d.to_dict("records"):
            out.append({str(k): (_num(v) if isinstance(v, (int, float)) else str(v))
                        for k, v in rec.items()})
        return out
    except Exception:
        return []


def get_consensus(ticker: str, *, force: bool = False) -> dict:
    """Analyst consensus: forward EPS/revenue estimates, growth, price target,
    recommendation mix. Empty dict if Yahoo gives nothing."""
    key = f"consensus/{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=_TTL)
        if cached is not None:
            return cached
    out: dict = {}
    try:
        t = _yf(ticker)
        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        pt = None
        try:
            pt = t.analyst_price_targets
        except Exception:
            pt = None
        if isinstance(pt, dict) and pt:
            out["price_target"] = {k: _num(v) for k, v in pt.items()}
        elif info:
            out["price_target"] = {
                "current": _num(info.get("currentPrice")),
                "mean": _num(info.get("targetMeanPrice")),
                "high": _num(info.get("targetHighPrice")),
                "low": _num(info.get("targetLowPrice")),
                "median": _num(info.get("targetMedianPrice")),
            }
        out["n_analysts"] = _num(info.get("numberOfAnalystOpinions"))
        out["recommendation"] = info.get("recommendationKey")
        out["recommendation_mean"] = _num(info.get("recommendationMean"))
        out["forward_eps"] = _num(info.get("forwardEps"))
        out["trailing_eps"] = _num(info.get("trailingEps"))
        out["forward_pe"] = _num(info.get("forwardPE"))
        out["trailing_pe"] = _num(info.get("trailingPE"))
        out["peg"] = _num(info.get("trailingPegRatio") or info.get("pegRatio"))

        # estimate tables (period index: 0q/+1q current-qtr, 0y/+1y current/next FY)
        try:
            out["eps_estimate"] = _df_records(t.earnings_estimate)
        except Exception:
            pass
        try:
            out["revenue_estimate"] = _df_records(t.revenue_estimate)
        except Exception:
            pass
        try:
            out["growth_estimates"] = _df_records(t.growth_estimates)
        except Exception:
            pass
        try:
            recs = t.recommendations
            out["recommendation_trend"] = _df_records(recs)
        except Exception:
            pass
    except Exception:
        out = {}
    # prune empties
    out = {k: v for k, v in out.items() if v not in (None, [], {}, "")}
    store.kv_put(key, out)
    return out


def get_ownership(ticker: str, *, force: bool = False) -> dict:
    """Float, institutional/insider ownership, and short interest. Best-effort."""
    key = f"ownership/{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=_TTL)
        if cached is not None:
            return cached
    out: dict = {}
    try:
        t = _yf(ticker)
        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}
        out = {
            "float_shares": _num(info.get("floatShares")),
            "shares_outstanding": _num(info.get("sharesOutstanding")),
            "pct_held_institutions": _num(info.get("heldPercentInstitutions")),
            "pct_held_insiders": _num(info.get("heldPercentInsiders")),
            "short": {
                "shares_short": _num(info.get("sharesShort")),
                "shares_short_prior_month": _num(info.get("sharesShortPriorMonth")),
                "pct_of_float": _num(info.get("shortPercentOfFloat")),
                "short_ratio": _num(info.get("shortRatio")),
                "as_of_epoch": _num(info.get("dateShortInterest")),
            },
        }
    except Exception:
        out = {}
    out = {k: v for k, v in out.items() if v not in (None, [], {}, "")}
    if isinstance(out.get("short"), dict):
        out["short"] = {k: v for k, v in out["short"].items() if v is not None}
        if not out["short"]:
            out.pop("short")
    store.kv_put(key, out)
    return out


def next_earnings_date(ticker: str, *, force: bool = False) -> Optional[str]:
    """Next scheduled earnings date (YYYY-MM-DD) — a real FORWARD catalyst — or None.
    Best-effort via yfinance; cached."""
    key = f"earndate/{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=_TTL)
        if cached is not None:
            return cached or None
    out = None
    try:
        info = _yf(ticker).info or {}
        ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
        if ts:
            import datetime as _dt
            out = _dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        out = None
    store.kv_put(key, out or "")
    return out


def get_quote(ticker: str, *, force: bool = False) -> dict:
    """Yahoo's own reported price / market cap / shares / 52-wk range — used to
    cross-check the figures our pipeline computed. Best-effort, cached."""
    key = f"quote/{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=_TTL)
        if cached is not None:
            return cached
    out: dict = {}
    try:
        info = _yf(ticker).info or {}
        out = {
            "price": _num(info.get("currentPrice") or info.get("regularMarketPrice")),
            "market_cap": _num(info.get("marketCap")),
            "shares_outstanding": _num(info.get("sharesOutstanding")),
            "fifty_two_week_high": _num(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": _num(info.get("fiftyTwoWeekLow")),
            "currency": info.get("currency"),
        }
    except Exception:
        out = {}
    out = {k: v for k, v in out.items() if v not in (None, "")}
    store.kv_put(key, out)
    return out


def data_quality(ticker: str, *, used_price=None, computed_mcap=None) -> list:
    """Cross-check the price / market cap our pipeline used against Yahoo's own
    reported figures. Returns a list of human-readable flag strings (empty when
    consistent). NOTE: a single vendor can be internally consistent yet wrong — a
    truly independent second price source is needed to validate the level itself;
    this catches share-count mismatches, currency, stale ticks, and (when a second
    source is wired) cross-source divergence."""
    flags = []
    q = get_quote(ticker)
    rp, rc = q.get("price"), q.get("market_cap")
    cur = q.get("currency")
    if cur and cur != "USD":
        flags.append(f"non-USD quote ({cur}) — FX not applied")
    if isinstance(used_price, (int, float)) and isinstance(rp, (int, float)) and rp > 0:
        if abs(used_price / rp - 1) > 0.05:
            flags.append(f"price ${used_price:,.2f} ≠ vendor quote ${rp:,.2f}")
    if isinstance(computed_mcap, (int, float)) and isinstance(rc, (int, float)) and rc > 0:
        if abs(computed_mcap / rc - 1) > 0.30:
            flags.append(f"market cap ${computed_mcap/1e9:,.0f}B vs vendor ${rc/1e9:,.0f}B "
                         "(share-count mismatch)")
    hi = q.get("fifty_two_week_high")
    if isinstance(used_price, (int, float)) and isinstance(hi, (int, float)) and hi > 0 \
            and used_price > hi * 1.10:
        flags.append("price above the 52-week high — possible bad tick")
    # Independent second-source corroboration: the checks above all lean on Yahoo's
    # own figures, so they can't catch a wholly wrong Yahoo level. Cross-check the
    # used price against a genuinely independent feed (Stooq, or keyed Polygon/AV).
    if isinstance(used_price, (int, float)):
        try:
            from . import prices
            cc = prices.corroborate_price(ticker, used_price)
            if cc and not cc["agree"]:
                flags.append(f"price ${used_price:,.2f} not corroborated by independent "
                             f"{cc['source']} feed ${cc['independent']:,.2f} "
                             f"({cc['divergence']:+.0%}) — level uncertain")
        except Exception:
            pass
    return flags


def stockanalysis_estimates(ticker: str, *, force: bool = False) -> dict:
    """Forward EPS/revenue estimates from stockanalysis.com (keyless, UNOFFICIAL —
    a fallback for the yfinance consensus). Best-effort: returns {} if the endpoint
    shape changes or is blocked. Tier: keyless_unofficial (dev-only for client work)."""
    key = f"stockanalysis:{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=_TTL)
        if cached is not None:
            return cached
    out = {}
    try:
        url = f"https://stockanalysis.com/api/symbol/s/{ticker.upper()}/overview"
        data = store.cached_get_json(
            url, ttl=_TTL, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20, force=force)
        d = (data or {}).get("data") or {}
        out = {k: d.get(k) for k in ("epsThisYear", "epsNextYear", "epsGrowthNext5Y",
                                     "revenueThisYear", "peForward", "targetPrice")
               if d.get(k) is not None}
        if out:
            out["source"] = "stockanalysis.com (unofficial)"
    except Exception:
        out = {}
    store.kv_put(key, out)
    return out


def consensus_growth(cons: dict) -> Optional[float]:
    """Pull the next-FY consensus revenue growth (a clean number to differentiate a
    DCF growth assumption against), as a decimal. None if unavailable."""
    for rec in (cons or {}).get("revenue_estimate", []):
        if str(rec.get("period")) in ("+1y", "1y"):
            g = _num(rec.get("growth"))
            if g is not None:
                return g
    for rec in (cons or {}).get("growth_estimates", []):
        if str(rec.get("period")) in ("+1y", "1y"):
            return _num(rec.get("stockTrend"))
    return None
