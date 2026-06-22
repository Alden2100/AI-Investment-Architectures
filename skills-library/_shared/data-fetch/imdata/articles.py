"""Fetch and extract the main body text of web articles. Free, keyless.

Skills run headless and cannot call any external web tool, so this is fully
self-contained: `requests` to fetch the HTML, `trafilatura` to extract the
readable article body. Best-effort by design — paywalled, JS-rendered, blocked,
or slow pages return empty text rather than raising, so a caller can enrich a
batch of results and simply skip the ones that didn't resolve.

Bodies are cached in the shared SQLite store (kv, 7-day TTL) so repeated runs
don't re-hit the network. Batch fetches run concurrently with plain `requests`
(never the store's single-threaded sqlite connection); caching happens on the
calling thread only.
"""
from __future__ import annotations

import concurrent.futures
from typing import Iterable, Optional

import requests

from . import store

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_TTL = 7 * 24 * 3600          # article text is static; cache a week
_EMPTY = {"text": "", "title": None, "published": None, "site": None}


def _fetch_and_extract(url: str, timeout: int) -> dict:
    """Pure network+parse, NO store access (safe to run in a worker thread)."""
    out = {"url": url, **_EMPTY}
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        if resp.status_code != 200 or not resp.text:
            return out
        html = resp.text
    except Exception:
        return out
    try:
        import trafilatura
        text = trafilatura.extract(
            html, include_comments=False, include_tables=False,
            favor_precision=True, no_fallback=False) or ""
        out["text"] = text.strip()
        try:
            md = trafilatura.extract_metadata(html)
            if md is not None:
                out["title"] = getattr(md, "title", None)
                out["published"] = getattr(md, "date", None)
                out["site"] = getattr(md, "sitename", None) or getattr(md, "hostname", None)
        except Exception:
            pass
    except Exception:
        pass
    return out


def fetch_article(url: str, *, timeout: int = 10, ttl: int = _TTL,
                  force: bool = False) -> dict:
    """Return {url, text, title, published, site} for one URL. Cached; empty text
    on any failure (never raises)."""
    out = {"url": url or "", **_EMPTY}
    if not url or not str(url).startswith("http"):
        return out
    key = f"article/{url}"
    if not force:
        cached = store.kv_get(key, ttl=ttl)
        if cached is not None:
            return cached
    out = _fetch_and_extract(url, timeout)
    store.kv_put(key, out)              # cache even empties → don't re-hit dead URLs
    return out


def fetch_articles(urls: Iterable[str], *, limit: int = 5, timeout: int = 10,
                   max_workers: int = 5, ttl: int = _TTL,
                   min_chars: int = 0) -> list[dict]:
    """Fetch+extract up to `limit` deduped URLs concurrently. Returns a list of
    {url, text, title, published, site} in input order. Network failures are
    skipped (empty text), never fatal. Cached results don't re-hit the network."""
    seen: set = set()
    uniq: list[str] = []
    for u in urls or []:
        if u and str(u).startswith("http") and u not in seen:
            seen.add(u)
            uniq.append(u)
        if len(uniq) >= limit:
            break
    if not uniq:
        return []

    results: dict[str, dict] = {}
    to_fetch: list[str] = []
    for u in uniq:                                   # main-thread cache check
        cached = store.kv_get(f"article/{u}", ttl=ttl)
        if cached is not None:
            results[u] = cached
        else:
            to_fetch.append(u)

    if to_fetch:
        workers = min(max_workers, len(to_fetch))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_fetch_and_extract, u, timeout): u for u in to_fetch}
            for fut in concurrent.futures.as_completed(futs):
                u = futs[fut]
                try:
                    results[u] = fut.result()
                except Exception:
                    results[u] = {"url": u, **_EMPTY}
        for u in to_fetch:                            # main-thread cache write
            store.kv_put(f"article/{u}", results.get(u, {"url": u, **_EMPTY}))

    ordered = [results[u] for u in uniq if u in results]
    if min_chars > 0:
        ordered = [r for r in ordered if len(r.get("text") or "") >= min_chars]
    return ordered
