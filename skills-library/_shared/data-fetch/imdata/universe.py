"""Ticker <-> CIK mapping and universe lookups, sourced from SEC's free
company_tickers.json. Everything is cached in the store.
"""
from __future__ import annotations

from typing import Optional

from . import config, store

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _headers() -> dict:
    return {"User-Agent": config.SEC_USER_AGENT, "Accept": "application/json"}


def refresh_universe(force: bool = False) -> int:
    """Pull the full ticker->CIK table from SEC and cache it. Returns row count."""
    raw = store.cached_get_json(
        _COMPANY_TICKERS_URL,
        ttl=config.TTL_UNIVERSE,
        headers=_headers(),
        force=force,
    )
    # Shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    rows = [
        {
            "cik": int(rec["cik_str"]),
            "ticker": str(rec["ticker"]).upper(),
            "title": rec.get("title", ""),
        }
        for rec in raw.values()
    ]
    store.upsert_companies(rows)
    return len(rows)


def _ensure_loaded() -> None:
    if store.companies_count() == 0:
        refresh_universe()


def cik_for_ticker(ticker: str) -> Optional[int]:
    """Return the integer CIK for a ticker, or None if unknown."""
    _ensure_loaded()
    row = store.company_by_ticker(ticker)
    return int(row["cik"]) if row else None


def cik10(cik: int) -> str:
    """Zero-padded 10-digit CIK string used by EDGAR JSON endpoints."""
    return f"{int(cik):010d}"


def title_for_ticker(ticker: str) -> Optional[str]:
    _ensure_loaded()
    row = store.company_by_ticker(ticker)
    return row["title"] if row else None


def resolve(ticker: str) -> dict:
    """Return {ticker, cik, cik10, title} or raise if unknown."""
    _ensure_loaded()
    row = store.company_by_ticker(ticker)
    if row is None:
        raise ValueError(f"Unknown ticker: {ticker!r} (not in SEC company_tickers)")
    return {
        "ticker": row["ticker"],
        "cik": int(row["cik"]),
        "cik10": cik10(row["cik"]),
        "title": row["title"],
    }
