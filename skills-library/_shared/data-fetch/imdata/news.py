"""Recent news and filing alerts from free RSS feeds.

Two sources: SEC's per-company filing Atom feed (filing alerts) and Google News
RSS (general headlines). Both are parsed with the stdlib and cached in the store.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote
from xml.etree import ElementTree as ET

from . import config, store, universe

_SEC_ATOM = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
    "&type=&dateb=&owner=include&count=40&output=atom"
)
_GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _norm_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except ValueError:
            continue
    return s


def _fetch_sec_filings_feed(ticker: str) -> list[dict]:
    info = universe.resolve(ticker)
    body = store.cached_get(
        _SEC_ATOM.format(cik=info["cik10"]),
        ttl=config.TTL_NEWS,
        headers={"User-Agent": config.SEC_USER_AGENT},
        min_interval=1.0 / config.SEC_MAX_RPS,
    )
    items = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items
    for entry in root.findall("a:entry", _ATOM_NS):
        title = _clean(entry.findtext("a:title", default="", namespaces=_ATOM_NS))
        updated = entry.findtext("a:updated", default="", namespaces=_ATOM_NS)
        link_el = entry.find("a:link", _ATOM_NS)
        url = link_el.get("href") if link_el is not None else ""
        items.append(
            {
                "title": title,
                "published": _norm_date(updated),
                "source": "SEC EDGAR",
                "url": url,
            }
        )
    return items


def _fetch_google_news(query: str) -> list[dict]:
    body = store.cached_get(
        _GOOGLE_NEWS.format(q=quote(query)),
        ttl=config.TTL_NEWS,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    items = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items
    for item in root.iter("item"):
        title = _clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate")
        src_el = item.find("source")
        source = _clean(src_el.text) if src_el is not None else "Google News"
        items.append(
            {
                "title": title,
                "published": _norm_date(pub),
                "source": source,
                "url": link,
            }
        )
    return items


def refresh_news(ticker: str, include_google: bool = True) -> int:
    """Fetch SEC filing alerts (+ optional Google News) and cache. Returns count."""
    items = _fetch_sec_filings_feed(ticker)
    if include_google:
        title = universe.title_for_ticker(ticker) or ticker
        items += _fetch_google_news(f"{title} stock")
    if items:
        store.upsert_news(ticker, items)
    return len(items)


def get_news(ticker: str, lookback_days: int = 30, refresh: bool = True):
    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = store.get_news(ticker, since=since)
    if refresh and not rows:
        refresh_news(ticker)
        rows = store.get_news(ticker, since=since)
    return rows
