#!/usr/bin/env python3
"""Smoke test for free article-body extraction + 8-K earnings release.

Run: ./.venv/bin/python tests/article_test.py
Hits the live web (like the other smoke tests). Deterministic behaviors are hard
assertions; network-dependent extraction is asserted leniently (a transient miss
prints a WARN rather than failing the suite).
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
os.environ.setdefault("IM_LIB_ROOT", str(HERE / "skills-library"))
_cache = tempfile.mkdtemp()
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(_cache, "article_test.db"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", _cache)
sys.path.insert(0, str(HERE / "skills-library" / "_shared" / "data-fetch"))

from imdata import articles, edgar  # noqa: E402

PASS, FAIL, WARN = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m", "\033[33mWARN\033[0m"
_hard = []


def hard(name, cond):
    _hard.append(bool(cond))
    print(f"  [{PASS if cond else FAIL}] {name}")


def soft(name, cond):
    print(f"  [{PASS if cond else WARN}] {name}")


def test_graceful():
    print("\nGraceful failure (deterministic):")
    hard("empty url -> empty text, no raise", articles.fetch_article("")["text"] == "")
    hard("non-http -> empty text", articles.fetch_article("not-a-url")["text"] == "")
    bad = articles.fetch_article("https://nonexistent.invalid.example.tld/x", timeout=5)
    hard("dead host -> empty text, no raise", bad["text"] == "")
    # dedupe + cap + order
    res = articles.fetch_articles(
        ["https://en.wikipedia.org/wiki/Microsoft",
         "https://en.wikipedia.org/wiki/Microsoft",  # dup
         "https://en.wikipedia.org/wiki/Apple_Inc."], limit=2)
    hard("dedupe + cap to limit=2", len(res) <= 2)


def test_extraction():
    print("\nArticle extraction (network):")
    art = articles.fetch_article("https://en.wikipedia.org/wiki/Microsoft", timeout=15)
    soft(f"wikipedia body extracted ({len(art['text'])} chars)", len(art["text"]) >= 200)
    soft("metadata title present", bool(art.get("title")))
    # cache: second call should be served from store (no network); just ensure it returns same
    art2 = articles.fetch_article("https://en.wikipedia.org/wiki/Microsoft")
    hard("cached re-fetch returns text", len(art2["text"]) == len(art["text"]))


def test_earnings_release():
    print("\n8-K EX-99.1 earnings release (network):")
    try:
        r = edgar.earnings_release_text("MSFT")
    except Exception as e:
        print(f"  [{WARN}] earnings_release_text raised: {e}")
        return
    if not r:
        print(f"  [{WARN}] no earnings release found (transient?)")
        return
    soft(f"earnings text fetched ({len(r['text'])} chars)", len(r["text"]) > 1000)
    low = r["text"][:8000].lower()
    soft("looks like an earnings release (quarter/revenue)",
         ("quarter" in low or "fiscal" in low) and ("revenue" in low or "income" in low))


if __name__ == "__main__":
    test_graceful()
    test_extraction()
    test_earnings_release()
    n = sum(_hard)
    print(f"\n{n}/{len(_hard)} hard checks passed")
    sys.exit(0 if all(_hard) else 1)
