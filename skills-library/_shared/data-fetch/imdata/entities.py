"""Entity resolution against the real company universe.

The genuinely valuable, reusable part of the old keyword front door: turning the
fuzzy things a user types — a company name, a bare symbol, a "TICKER=weight" pair —
into VALIDATED tickers. A model can hallucinate a ticker; the SEC universe can't, so
every result here is checked against ``companies`` before it's returned.

Lives in ``imdata`` (shared spine) so any front end or system can reuse it and it
can be unit-tested on its own, independent of ``ask.py``.
"""
from __future__ import annotations

import re
from typing import Optional

from . import store, universe

# Common company-name -> ticker aliases (extend freely). A fast path before the
# universe-title search; also covers nicknames a title prefix wouldn't ("coke").
ALIASES = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "nvidia": "NVDA", "amazon": "AMZN", "meta": "META", "facebook": "META",
    "tesla": "TSLA", "netflix": "NFLX", "coca-cola": "KO", "coke": "KO",
    "intel": "INTC", "amd": "AMD", "broadcom": "AVGO", "oracle": "ORCL",
    "salesforce": "CRM", "adobe": "ADBE", "disney": "DIS", "boeing": "BA",
    "walmart": "WMT", "exxon": "XOM", "pepsi": "PEP", "pepsico": "PEP",
}

# Tokens that look like tickers but aren't — common English/finance words. Guards
# the bare-symbol scan so "IT IS A DCF" doesn't resolve to phantom tickers.
_STOP = {"A", "I", "THE", "IS", "IT", "MY", "ME", "AN", "OK", "OR", "TO", "VS",
         "AND", "FOR", "ANY", "ARE", "DCF", "IC", "LP", "WHAT", "HOW", "DO",
         "GIVE", "FIND", "WRITE", "WORTH", "BOOK", "CAP", "FY", "Q"}

_CORP_SUFFIX = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|holdings?|group|"
    r"technologies|technology|ltd|limited|plc|llc|lp|sa|nv|ag|the)\b\.?", re.I)
_NAME_PHRASE = re.compile(r"\b([A-Z][A-Za-z0-9&.'\-]*(?:\s+[A-Z][A-Za-z0-9&.'\-]*){0,4})")
_NAME_CACHE: dict = {}


def ensure_universe() -> None:
    """Load the SEC ticker universe if the store is empty. Best-effort."""
    try:
        if store.companies_count() == 0:
            universe.refresh_universe()
    except Exception:
        pass


def clear_cache() -> None:
    _NAME_CACHE.clear()


def valid_ticker(tok: str) -> bool:
    try:
        return store.company_by_ticker(tok) is not None
    except Exception:
        return False


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def match_company_name(phrase: str) -> Optional[str]:
    """Resolve a company-name phrase to a ticker via the universe titles, or None.
    Conservative: the normalized title must START with the (suffix-stripped) phrase
    (or its first significant word), and the shortest such title wins (the canonical
    'Apple Inc.' over 'Apple Hospitality REIT')."""
    # Drop stray single-letter tokens (possessive "'s", middle initials) that would
    # defeat the prefix match, e.g. "Micron Technology's" -> "micron".
    words = [w for w in _norm(_CORP_SUFFIX.sub(" ", phrase)).split()
             if len(w) > 1 or w.isdigit()]
    core = " ".join(words)
    if not core or core.upper() in _STOP:
        return None
    if core in _NAME_CACHE:
        return _NAME_CACHE[core]
    first = words[0] if words else ""
    if len(first) < 3:
        _NAME_CACHE[core] = None
        return None
    best, best_len = None, 1 << 30
    try:
        rows = store.get_conn().execute(
            "SELECT ticker, title FROM companies WHERE LOWER(title) LIKE ? LIMIT 300",
            (first + "%",)).fetchall()
    except Exception:
        rows = []
    for r in rows:
        tn = _norm(r["title"])
        # full phrase is a title prefix, or (single-word) the title's first word matches
        if tn.startswith(core) or (len(words) == 1 and tn.split()[:1] == [first]):
            if len(tn) < best_len:
                best, best_len = r["ticker"], len(tn)
    _NAME_CACHE[core] = best
    return best


def extract_tickers(text: str) -> list:
    """Validated tickers in TEXT order: company names (aliases + universe titles) +
    explicit symbols.

    Ordering matters — the first ticker is typically the subject (e.g. the company to
    value), the rest peers — so every hit is sorted by where it appears."""
    hits = []  # (position, ticker)
    low = text.lower()
    for name, tk in ALIASES.items():
        m = re.search(rf"\b{re.escape(name)}\b", low)
        if m:
            hits.append((m.start(), tk))
    for m in _NAME_PHRASE.finditer(text):
        phrase = m.group(1)
        # Don't fuzzy-resolve something that's already an exact symbol or alias —
        # the ticker "AMD" must not prefix-match the name "Amdocs". The alias and
        # bare-symbol scans below catch these correctly.
        if phrase.lower() in ALIASES or valid_ticker(phrase.upper().strip()):
            continue
        tk = match_company_name(phrase)
        if tk:
            hits.append((m.start(), tk))
    for m in re.finditer(r"\b[A-Z]{1,5}\b", text):
        tok = m.group(0)
        if tok not in _STOP and valid_ticker(tok):
            hits.append((m.start(), tok))
    found, seen = [], set()
    for _pos, tk in sorted(hits, key=lambda h: h[0]):
        if tk not in seen:
            found.append(tk)
            seen.add(tk)
    return found


def extract_positions(text: str) -> list:
    """TICKER=weight pairs from forms like 'NVDA 30%', 'MSFT=0.20', 'AAPL: 15%'."""
    out = []
    for sym, num, pct in re.findall(r"\b([A-Za-z]{1,5})\b\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(%)?", text):
        sym = sym.upper()
        if sym in _STOP or not valid_ticker(sym):
            continue
        v = float(num)
        if pct or v > 1:        # 30% or 30 -> 0.30
            v = v / 100.0
        out.append(f"{sym}={v:g}")
    return out
