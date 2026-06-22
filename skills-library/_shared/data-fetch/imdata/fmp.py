"""Financial Modeling Prep (FMP) + SimFin — KEYED upgrade (free tiers).

License tier: free_key_eval — eval/dev only; commercial use needs a paid agreement.
So these are gated on (a) the API key being present AND (b) NOT IM_COMMERCIAL_MODE.
Without a key (or in commercial mode) every accessor is a no-op returning {}/[] and the
caller falls back to the SEC-XBRL path. Rate limit: FMP free = 250 req/day → cached.
"""
from __future__ import annotations

import os
from typing import Optional

from . import config, store

_BASE = "https://financialmodelingprep.com/api/v3"


def enabled() -> bool:
    return bool(os.environ.get("FMP_API_KEY")) and not config.COMMERCIAL_MODE


def _get(path: str, *, ttl: int = None, force: bool = False):
    if not enabled():
        return None
    api = os.environ.get("FMP_API_KEY")
    sep = "&" if "?" in path else "?"
    url = f"{_BASE}/{path}{sep}apikey={api}"
    try:
        return store.cached_get_json(url, ttl=ttl or config.TTL_ESTIMATES, timeout=30, force=force)
    except Exception:
        return None


def income_statement(ticker: str, *, limit: int = 4) -> list:
    data = _get(f"income-statement/{ticker.upper()}?limit={limit}")
    return data if isinstance(data, list) else []


def ratios(ticker: str) -> dict:
    data = _get(f"ratios-ttm/{ticker.upper()}")
    return data[0] if isinstance(data, list) and data else {}


def key_metrics(ticker: str) -> dict:
    data = _get(f"key-metrics-ttm/{ticker.upper()}")
    return data[0] if isinstance(data, list) and data else {}


def peers(ticker: str) -> list:
    data = _get(f"stock_peers?symbol={ticker.upper()}")
    if isinstance(data, list) and data:
        return data[0].get("peersList", []) if isinstance(data[0], dict) else []
    return []
