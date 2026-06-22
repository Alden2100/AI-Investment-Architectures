"""web-search: model-agnostic, keyless-by-default web search.

Default provider is DuckDuckGo's HTML endpoint (no key, no account). If a keyed
provider is configured in the environment (BRAVE_API_KEY), it is used instead for
higher-quality results. Results are cached in the shared SQLite store so repeated
queries don't re-hit the network. Output is the standard skill JSON envelope.
"""
import argparse
import html
import os
import re
import sys
from urllib.parse import quote, unquote, urlparse, parse_qs

# --- locate the shared library (_shared/) regardless of symlink/standalone ---
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

from imdata import config, skillkit, store

_DDG = "https://html.duckduckgo.com/html/"
_BRAVE = "https://api.search.brave.com/res/v1/web/search?q={q}&count={n}"
_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
TTL_SEARCH = int(os.environ.get("TTL_WEB_SEARCH", str(6 * 3600)))

_A_RE = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIP_RE = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _clean(t: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t))).strip()


def _unwrap(href: str) -> str:
    """DDG wraps targets as /l/?uddg=<encoded>. Unwrap to the real URL."""
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        q = parse_qs(urlparse(href).query)
        if "uddg" in q:
            return unquote(q["uddg"][0])
    return href


def _duckduckgo(query: str, n: int) -> list:
    # DDG's HTML endpoint requires POST form data; the store caches by url+body.
    body = store.cached_get(_DDG, ttl=TTL_SEARCH, headers=_UA, timeout=30,
                            data={"q": query})
    titles = _A_RE.findall(body)
    snips = _SNIP_RE.findall(body)
    out = []
    for i, (href, title) in enumerate(titles[:n]):
        out.append({
            "title": _clean(title),
            "url": _unwrap(html.unescape(href)),
            "snippet": _clean(snips[i]) if i < len(snips) else "",
        })
    return out


def _brave(query: str, n: int) -> list:
    import requests
    r = requests.get(_BRAVE.format(q=quote(query), n=n), timeout=30, headers={
        "Accept": "application/json", "X-Subscription-Token": os.environ["BRAVE_API_KEY"]})
    r.raise_for_status()
    items = r.json().get("web", {}).get("results", [])[:n]
    return [{"title": it.get("title", ""), "url": it.get("url", ""),
             "snippet": _clean(it.get("description", ""))} for it in items]


def main(args):
    n = max(1, min(args.max, 25))
    if os.environ.get("BRAVE_API_KEY"):
        provider, results = "brave", _brave(args.query, n)
    else:
        provider, results = "duckduckgo", _duckduckgo(args.query, n)

    bodies_added = 0
    if args.full and results:
        # Opt-in: fetch + extract the article body for the top results so the model
        # reads real content, not just titles/snippets. Additive — leaves the
        # {title,url,snippet} shape intact and only adds a `text` field. Best-effort:
        # paywalled/JS pages come back empty and are simply left without text.
        from imdata import articles
        top = results[:max(1, args.full_max)]
        fetched = {a["url"]: a for a in articles.fetch_articles(
            [r["url"] for r in top], limit=args.full_max, timeout=args.full_timeout)}
        for r in top:
            art = fetched.get(r["url"])
            if art and art.get("text"):
                r["text"] = art["text"]
                if art.get("site"):
                    r["site"] = art["site"]
                if art.get("published"):
                    r["published"] = art["published"]
                bodies_added += 1

    summ = (f"{len(results)} result(s) for '{args.query}' via {provider}."
            if results else f"No results for '{args.query}' via {provider}.")
    if args.full:
        summ += f" {bodies_added} with extracted article text."
    return {
        "query": args.query,
        "provider": provider,
        "count": len(results),
        "results": results,
        "bodies_extracted": bodies_added,
        "summary": summ,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Keyless-by-default web search.")
    p.add_argument("--query", required=True)
    p.add_argument("--max", type=int, default=8, help="max results (1-25)")
    p.add_argument("--full", action="store_true",
                   help="fetch + extract article BODY text for the top results")
    p.add_argument("--full-max", type=int, default=5,
                   help="max article bodies to fetch when --full (default 5)")
    p.add_argument("--full-timeout", type=int, default=10,
                   help="per-URL fetch timeout in seconds when --full")
    skillkit.run(main, p)
