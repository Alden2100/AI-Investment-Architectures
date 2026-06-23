"""Price history with caching and a layered fallback chain.

Sources, tried in order until one returns data:
  1. yfinance              (primary; rich but breaks when Yahoo changes things)
  2. Yahoo raw chart API   (key-free JSON, a different code path than yfinance)
  3. Stooq CSV             (best-effort; sometimes behind an anti-bot challenge)

Everything is cached in the store so a working fetch keeps serving even when all
live sources are down.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config, store

_YAHOO_CHART = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    "?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit"
)


def _today() -> datetime:
    return datetime.now(timezone.utc)


def _yfinance_history(ticker: str, start: str) -> list[dict]:
    import yfinance as yf

    df = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    if df is None or df.empty:
        return []
    rows = []
    for idx, r in df.iterrows():
        rows.append(
            {
                "date": idx.strftime("%Y-%m-%d"),
                "open": _f(r.get("Open")),
                "high": _f(r.get("High")),
                "low": _f(r.get("Low")),
                "close": _f(r.get("Close")),
                "adj_close": _f(r.get("Adj Close", r.get("Close"))),
                "volume": _f(r.get("Volume")),
            }
        )
    return rows


def _yahoo_chart_history(ticker: str, start: str) -> list[dict]:
    p1 = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    p2 = int(_today().timestamp())
    url = _YAHOO_CHART.format(ticker=ticker.upper(), p1=p1, p2=p2)
    body = store.cached_get(url, ttl=config.TTL_PRICES, headers={"User-Agent": "Mozilla/5.0"})
    data = json.loads(body)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    ts = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    adj = (result.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose")
    rows = []
    for i, t in enumerate(ts):
        date = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        close = _f(quote.get("close", [None] * len(ts))[i])
        rows.append(
            {
                "date": date,
                "open": _f(quote.get("open", [None] * len(ts))[i]),
                "high": _f(quote.get("high", [None] * len(ts))[i]),
                "low": _f(quote.get("low", [None] * len(ts))[i]),
                "close": close,
                "adj_close": _f(adj[i]) if adj else close,
                "volume": _f(quote.get("volume", [None] * len(ts))[i]),
            }
        )
    return [r for r in rows if r["close"] is not None]


def _stooq_history(ticker: str, start: str) -> list[dict]:
    # Stooq uses lowercase ticker with a .us suffix for US equities.
    url = f"https://stooq.com/q/d/l/?s={ticker.lower()}.us&i=d"
    body = store.cached_get(url, ttl=config.TTL_PRICES, headers={"User-Agent": "Mozilla/5.0"})
    rows = []
    reader = csv.DictReader(io.StringIO(body))
    for r in reader:
        d = r.get("Date")
        if not d or d < start:
            continue
        rows.append(
            {
                "date": d,
                "open": _f(r.get("Open")),
                "high": _f(r.get("High")),
                "low": _f(r.get("Low")),
                "close": _f(r.get("Close")),
                "adj_close": _f(r.get("Close")),  # Stooq daily is already adjusted
                "volume": _f(r.get("Volume")),
            }
        )
    return rows


def _f(v) -> Optional[float]:
    try:
        if v is None or v == "" or (isinstance(v, str) and v.upper() == "N/D"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def refresh_prices(ticker: str, lookback_days: int = 400, force: bool = False) -> dict:
    """Fetch and cache price history. Returns {source, rows}."""
    start = (_today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    chain = [
        ("yfinance", _yfinance_history),
        ("yahoo_chart", _yahoo_chart_history),
        ("stooq", _stooq_history),
    ]
    rows: list[dict] = []
    source = "none"
    for name, fn in chain:
        try:
            rows = fn(ticker, start)
        except Exception:
            rows = []
        if rows:
            source = name
            break
    if rows:
        store.upsert_prices(ticker, rows)
    return {"source": source, "rows": len(rows)}


def get_history(ticker: str, lookback_days: int = 365, refresh: bool = True):
    """Return cached price rows for a ticker, fetching if empty or stale-empty."""
    start = (_today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    rows = store.get_prices(ticker, start=start)
    if refresh and not rows:
        refresh_prices(ticker, lookback_days=max(lookback_days + 35, 400))
        rows = store.get_prices(ticker, start=start)
    return rows


def last_price(ticker: str, refresh: bool = True) -> Optional[float]:
    rows = get_history(ticker, lookback_days=10, refresh=refresh)
    if not rows:
        rows = get_history(ticker, lookback_days=400, refresh=refresh)
    return rows[-1]["close"] if rows else None


# --------------------------------------------------------------------------- #
# Keyed EOD providers — Polygon.io / Alpha Vantage (free_key_eval tier). A keyed
# cross-check / upgrade for the keyless chain above; gated on the key and not
# IM_COMMERCIAL_MODE. Alpha Vantage free = 25 req/day; cached. Returns the latest
# close or None — the keyless yfinance→Yahoo→Stooq chain stays the default.
# --------------------------------------------------------------------------- #
def keyed_last_price(ticker: str) -> Optional[dict]:
    import os
    if config.COMMERCIAL_MODE:
        return None
    poly = os.environ.get("POLYGON_API_KEY")
    av = os.environ.get("ALPHAVANTAGE_API_KEY")
    try:
        if poly:
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker.upper()}/prev?apiKey={poly}"
            d = store.cached_get_json(url, ttl=config.TTL_PRICES, timeout=30)
            res = (d.get("results") or [])
            if res:
                return {"last": res[0].get("c"), "source": "polygon"}
        if av:
            url = (f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
                   f"&symbol={ticker.upper()}&apikey={av}")
            d = store.cached_get_json(url, ttl=config.TTL_PRICES, timeout=30)
            q = d.get("Global Quote") or {}
            if q.get("05. price"):
                return {"last": float(q["05. price"]), "source": "alpha_vantage"}
    except Exception:
        return None
    return None


def _parse_si(s) -> Optional[float]:
    """'4.36T' / '14.69B' / '122.58M' / '297.01' -> float. None on failure."""
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    s = s.strip().replace(",", "").replace("$", "")
    mult = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}.get(s[-1:].upper())
    try:
        return float(s[:-1]) * mult if mult else float(s)
    except ValueError:
        return None


def _stockanalysis_overview(ticker: str) -> dict:
    """Raw stockanalysis.com overview dict (keyless, UNOFFICIAL; gated off commercial
    mode). {} on any failure."""
    if config.COMMERCIAL_MODE:
        return {}
    try:
        url = f"https://stockanalysis.com/api/symbol/s/{ticker.upper()}/overview"
        d = store.cached_get_json(
            url, ttl=config.TTL_PRICES,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=20)
        return (d or {}).get("data") or {}
    except Exception:
        return {}


def _stockanalysis_price(ticker: str) -> Optional[dict]:
    """Independent (non-Yahoo) last price = market cap / shares outstanding."""
    data = _stockanalysis_overview(ticker)
    mcap, shares = _parse_si(data.get("marketCap")), _parse_si(data.get("sharesOut"))
    if mcap and shares and shares > 0:
        return {"last": round(mcap / shares, 4), "source": "stockanalysis.com (unofficial)"}
    return None


def independent_market_cap(ticker: str) -> Optional[float]:
    """An independent (non-Yahoo) market cap for breaking a SEC-vs-vendor tie. From
    stockanalysis.com (keyless, gated off commercial mode). None if unavailable."""
    return _parse_si(_stockanalysis_overview(ticker).get("marketCap")) or None


# --------------------------------------------------------------------------- #
# Independent corroboration — a SECOND, non-Yahoo last close.
#
# The default chain (yfinance → Yahoo chart → Stooq) returns the first source that
# has data, so a name normally never leaves Yahoo. A single vendor can be internally
# consistent yet wrong (the MU/AMD bad-tick problem). This returns a price from a
# genuinely INDEPENDENT vendor so a caller can validate the level itself rather than
# trust one feed:
#   1. keyed Polygon / Alpha Vantage   (most reliable; gated on a key)
#   2. stockanalysis.com               (keyless, non-Yahoo; gated off commercial mode)
#   3. Stooq CSV                        (keyless public; often behind an anti-bot wall)
# Returns {last, source[, as_of]} or None when no independent feed is reachable.
# --------------------------------------------------------------------------- #
def independent_last_price(ticker: str) -> Optional[dict]:
    keyed = keyed_last_price(ticker)                  # Polygon / Alpha Vantage (gated)
    if keyed and isinstance(keyed.get("last"), (int, float)) and keyed["last"] > 0:
        return keyed
    sa = _stockanalysis_price(ticker)
    if sa:
        return sa
    try:
        start = (_today() - timedelta(days=10)).strftime("%Y-%m-%d")
        rows = _stooq_history(ticker, start)
        last = rows[-1]["close"] if rows else None
        if isinstance(last, (int, float)) and last > 0:
            return {"last": float(last), "source": "stooq", "as_of": rows[-1]["date"]}
    except Exception:
        pass
    return None


def corroborate_price(ticker: str, used_price: float, tol: float = 0.05) -> Optional[dict]:
    """Cross-check ``used_price`` against an independent (non-Yahoo) feed. Returns
    ``{agree, used, independent, source, divergence, as_of}`` or None when no second
    source is reachable. ``agree`` is False when the two disagree by more than ``tol``."""
    if not isinstance(used_price, (int, float)) or used_price <= 0:
        return None
    ind = independent_last_price(ticker)
    if not ind or not isinstance(ind.get("last"), (int, float)) or ind["last"] <= 0:
        return None
    div = used_price / ind["last"] - 1
    return {"agree": abs(div) <= tol, "used": float(used_price), "independent": ind["last"],
            "source": ind["source"], "divergence": round(div, 4), "as_of": ind.get("as_of")}
