"""Finviz key stats + screener (keyless_unofficial; dev-only for client work).

Via the `finvizfinance` library (lazy import). Returns {}/[] when the library isn't
installed or a scrape fails. Soft scrape limit → cached. Useful for a fast snapshot
(short float, inst. ownership %, analyst recom, perf) and quick screens.
"""
from __future__ import annotations

from typing import Optional

from . import config, store


def key_stats(ticker: str, *, force: bool = False) -> dict:
    """Finviz fundamentals snapshot (a dict of ~70 key stats) or {}."""
    key = f"finviz:{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_ESTIMATES)
        if cached is not None:
            return cached
    out = {}
    try:
        from finvizfinance.quote import finvizfinance  # lazy, optional dep
        out = finvizfinance(ticker.upper()).ticker_fundament() or {}
    except Exception:
        out = {}
    store.kv_put(key, out)
    return out


def screen(filters: dict = None, *, limit: int = 30) -> list:
    """Run a Finviz screen; returns a list of tickers. `filters` uses finvizfinance
    filter labels, e.g. {'Sector': 'Technology', 'Market Cap.': 'Mid (over $2bln)'}."""
    try:
        from finvizfinance.screener.overview import Overview  # lazy
        o = Overview()
        if filters:
            o.set_filter(filters_dict=filters)
        df = o.screener_view()
        if df is not None and "Ticker" in df:
            return df["Ticker"].head(limit).tolist()
    except Exception:
        pass
    return []
