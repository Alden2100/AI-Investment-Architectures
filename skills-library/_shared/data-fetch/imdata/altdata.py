"""Alt-data sentiment overlays for PUBLIC EQUITIES — retail attention, never
decision-grade. Surfaced as context only, clearly labelled as sentiment.

- Google Trends (pytrends, keyless): relative search interest for a company/ticker.
- Reddit (PRAW, keyed): recent mention volume on investing subreddits.

Both lazy-import their library; if the library (or Reddit key) is absent they return
{} and the caller simply omits the overlay. kv-cached. Tiers: pytrends =
keyless_unofficial; reddit = free_key_eval.
"""
from __future__ import annotations

import os
from typing import Optional

from . import config, store


def google_trends(query: str, *, force: bool = False) -> Optional[dict]:
    """Relative Google search interest (0-100) + 90-day direction for a query.
    Keyless. Returns None if pytrends isn't installed or the call fails."""
    key = f"trends:{query.lower()}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_NEWS)
        if cached is not None:
            return cached or None
    out = None
    try:
        from pytrends.request import TrendReq  # lazy, optional dep
        tr = TrendReq(hl="en-US", tz=0)
        tr.build_payload([query], timeframe="today 3-m")
        df = tr.interest_over_time()
        if df is not None and not df.empty and query in df:
            vals = [int(v) for v in df[query].tolist() if v == v]
            if vals:
                first_half = sum(vals[: len(vals) // 2]) / max(1, len(vals) // 2)
                second_half = sum(vals[len(vals) // 2:]) / max(1, len(vals) - len(vals) // 2)
                out = {"query": query, "latest_interest": vals[-1],
                       "avg_interest": round(sum(vals) / len(vals), 1),
                       "direction": ("rising" if second_half > first_half * 1.1
                                     else "falling" if second_half < first_half * 0.9 else "flat"),
                       "source": "Google Trends (pytrends)"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def reddit_mentions(query: str, *, subreddits="stocks+investing+wallstreetbets",
                    force: bool = False) -> Optional[dict]:
    """Recent mention volume for a query on investing subreddits. KEYED (PRAW): needs
    REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET. Returns None when unavailable."""
    if not (os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET")):
        return None
    key = f"reddit:{query.lower()}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_NEWS)
        if cached is not None:
            return cached or None
    out = None
    try:
        import praw  # lazy, optional dep
        reddit = praw.Reddit(client_id=os.environ["REDDIT_CLIENT_ID"],
                             client_secret=os.environ["REDDIT_CLIENT_SECRET"],
                             user_agent="im-research/1.0")
        posts = list(reddit.subreddit(subreddits).search(query, sort="new", time_filter="week", limit=40))
        out = {"query": query, "mentions_7d": len(posts),
               "top_titles": [p.title[:120] for p in posts[:5]],
               "source": "Reddit (PRAW) — sentiment overlay, not decision-grade"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out
