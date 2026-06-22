"""Market volatility overlay — CBOE VIX (public). Fetched via yfinance ^VIX (keyless),
kv-cached. A portfolio/reporting overlay for the risk regime. Best-effort."""
from __future__ import annotations

from typing import Optional

from . import config, store


def vix(*, force: bool = False) -> Optional[dict]:
    key = "vix:level"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_PRICES)
        if cached is not None:
            return cached or None
    out = None
    try:
        from . import prices
        rows = prices.get_history("^VIX", lookback_days=40)
        closes = [r["close"] for r in rows if r["close"]]
        if closes:
            last = closes[-1]
            avg = sum(closes) / len(closes)
            out = {"level": round(last, 2), "30d_avg": round(avg, 2),
                   "regime": ("calm" if last < 15 else "normal" if last < 22
                              else "elevated" if last < 30 else "stressed"),
                   "as_of": rows[-1]["date"], "source": "CBOE VIX (via ^VIX)"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out
