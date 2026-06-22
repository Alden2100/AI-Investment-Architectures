"""news-fetcher: recent news + SEC filing alerts. Deterministic retrieval."""
import argparse
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
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

from imdata import news, skillkit, universe


def main(args):
    info = universe.resolve(args.ticker)
    news.refresh_news(args.ticker, include_google=not args.no_google)
    rows = news.get_news(args.ticker, lookback_days=args.lookback, refresh=False)
    items = [
        {"title": r["title"], "date": r["published"], "source": r["source"], "url": r["url"]}
        for r in rows
    ]
    bodies_added = 0
    if args.full and items:
        # Opt-in: attach extracted article BODY text to the top items so a downstream
        # model reasons over real content, not just headlines. Best-effort; paywalled
        # or redirect-only (e.g. Google News) links come back empty and are skipped.
        from imdata import articles
        fetched = {a["url"]: a for a in articles.fetch_articles(
            [i["url"] for i in items[:args.full_max]],
            limit=args.full_max, timeout=args.full_timeout)}
        for it in items[:args.full_max]:
            art = fetched.get(it["url"])
            if art and art.get("text"):
                it["body"] = art["text"]
                bodies_added += 1
    sources = sorted({i["source"] for i in items if i["source"]})
    return {
        "ticker": info["ticker"],
        "company": info["title"],
        "items": items,
        "count": len(items),
        "bodies_extracted": bodies_added,
        "summary": (
            f"{info['title']} ({info['ticker']}): {len(items)} item(s) in the last "
            f"{args.lookback} days"
            + (f" from {', '.join(sources[:4])}." if sources else ".")
            + (f" {bodies_added} with article text." if args.full else "")
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch recent news and filing alerts.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--no-google", action="store_true", help="SEC filing alerts only")
    p.add_argument("--full", action="store_true",
                   help="fetch + extract article body text for the top items")
    p.add_argument("--full-max", type=int, default=5, help="max bodies to fetch (default 5)")
    p.add_argument("--full-timeout", type=int, default=10, help="per-URL timeout seconds")
    skillkit.run(main, p)
