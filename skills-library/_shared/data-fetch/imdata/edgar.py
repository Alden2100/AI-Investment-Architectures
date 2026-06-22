"""SEC EDGAR access: filings list, filing documents (as text), structured XBRL
financials from companyfacts, and full-text search for change scanning.

All requests carry the required User-Agent and are throttled under SEC's
10 req/sec guidance. Everything is cached through the store.
"""
from __future__ import annotations

import html
import re
from typing import Optional

from . import config, store, universe

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
_FTS_URL = "https://efts.sec.gov/LATEST/search-index?q={q}"
_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"

_MIN_INTERVAL = 1.0 / config.SEC_MAX_RPS


def _headers() -> dict:
    return {"User-Agent": config.SEC_USER_AGENT, "Accept": "application/json"}


def _doc_headers() -> dict:
    return {"User-Agent": config.SEC_USER_AGENT}


def _sec_json(url: str, ttl: int, force: bool = False):
    return store.cached_get_json(
        url, ttl=ttl, headers=_headers(), force=force, min_interval=_MIN_INTERVAL
    )


# --------------------------------------------------------------------------- #
# Filings list (submissions endpoint)
# --------------------------------------------------------------------------- #
_SUBMISSIONS_FILE_URL = "https://data.sec.gov/submissions/{name}"


def _filing_rows(block: dict, info: dict) -> list:
    """Turn a submissions filings block (parallel arrays) into filing rows."""
    forms = block.get("form", [])
    out = []
    for i in range(len(forms)):
        acc = block["accessionNumber"][i]
        out.append({
            "accession": acc,
            "cik": info["cik"],
            "ticker": info["ticker"],
            "form": block["form"][i],
            "filing_date": block["filingDate"][i],
            "report_date": (block.get("reportDate") or [None] * len(forms))[i] or None,
            "primary_doc": block["primaryDocument"][i],
            "url": _ARCHIVE.format(cik=info["cik"], acc_nodash=acc.replace("-", ""),
                                   doc=block["primaryDocument"][i]),
        })
    return out


def refresh_filings(ticker: str, force: bool = False) -> int:
    """Pull the recent-filings index for a ticker into the store. Returns count."""
    info = universe.resolve(ticker)
    data = _sec_json(_SUBMISSIONS_URL.format(cik10=info["cik10"]),
                     ttl=config.TTL_SUBMISSIONS, force=force)
    rows = _filing_rows(data.get("filings", {}).get("recent", {}), info)
    if rows:
        store.upsert_filings(rows)
    return len(rows)


def ensure_form_history(ticker: str, form: str, min_count: int = 2, max_pages: int = 10) -> int:
    """Make sure the store holds at least ``min_count`` filings of ``form``.

    The submissions endpoint inlines only the most recent ~1000 filings; for prolific
    filers (big banks file 8-Ks almost daily) last year's 10-K is paged out into
    additional files. This fetches those pages oldest-needed-first, stopping as soon as
    ``min_count`` of the form are present (so a 10-K comparison gets a prior year).
    Returns how many of the form are in the store afterward.
    """
    info = universe.resolve(ticker)
    have = len(store.list_filings(info["cik"], form=form))
    if have >= min_count:
        return have
    data = _sec_json(_SUBMISSIONS_URL.format(cik10=info["cik10"]), ttl=config.TTL_SUBMISSIONS)
    for f in (data.get("filings", {}).get("files", []) or [])[:max_pages]:
        name = f.get("name")
        if not name:
            continue
        try:
            page = _sec_json(_SUBMISSIONS_FILE_URL.format(name=name), ttl=config.TTL_SUBMISSIONS)
            store.upsert_filings(_filing_rows(page, info))
        except Exception:
            pass
        if len(store.list_filings(info["cik"], form=form)) >= min_count:
            break
    return len(store.list_filings(info["cik"], form=form))


def list_filings(
    ticker: str,
    form: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
    refresh: bool = True,
):
    info = universe.resolve(ticker)
    if refresh and store.list_filings(info["cik"], form=form) == []:
        refresh_filings(ticker)
    rows = store.list_filings(info["cik"], form=form, start=start, end=end, limit=limit)
    if not rows and refresh:
        refresh_filings(ticker)
        rows = store.list_filings(info["cik"], form=form, start=start, end=end, limit=limit)
    # Prolific filers: the recent window can hold <2 of a given form (e.g. last year's
    # 10-K paged out). Fetch older pages until two of the form exist.
    if refresh and form and len(store.list_filings(info["cik"], form=form)) < 2:
        ensure_form_history(ticker, form, min_count=2)
        rows = store.list_filings(info["cik"], form=form, start=start, end=end, limit=limit)
    return rows


def latest_filing(ticker: str, form: str):
    rows = list_filings(ticker, form=form, limit=1)
    return rows[0] if rows else None


def company_meta(ticker: str, force: bool = False) -> dict:
    """Company metadata from the submissions endpoint: SIC/sector, exchanges, etc."""
    info = universe.resolve(ticker)
    data = _sec_json(
        _SUBMISSIONS_URL.format(cik10=info["cik10"]),
        ttl=config.TTL_SUBMISSIONS,
        force=force,
    )
    return {
        "ticker": info["ticker"],
        "cik": info["cik"],
        "name": data.get("name"),
        "sic": data.get("sic"),
        "sic_description": data.get("sicDescription"),
        "exchanges": data.get("exchanges"),
        "fiscal_year_end": data.get("fiscalYearEnd"),
        "state": data.get("stateOfIncorporation"),
    }


# --------------------------------------------------------------------------- #
# Filing document text
# --------------------------------------------------------------------------- #
def _html_to_text(raw: str) -> str:
    # Drop scripts/styles, strip tags, collapse whitespace. Adequate for reading
    # filing prose; we do not need perfect layout.
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?is)</(p|div|tr|li|h[1-6])>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t ]+", " ", raw)
    raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
    return raw.strip()


def filing_text(accession: str, force: bool = False) -> str:
    """Return the plain text of a filing's primary document, cached."""
    row = store.get_filing(accession)
    if row is None:
        raise ValueError(f"Unknown accession {accession!r}; list filings first.")
    if row["text"] and not force:
        return row["text"]
    raw = store.cached_get(
        row["url"],
        ttl=config.TTL_FILING_TEXT,
        headers=_doc_headers(),
        force=force,
        min_interval=_MIN_INTERVAL,
    )
    text = _html_to_text(raw) if "<" in raw[:2000] else raw
    store.set_filing_text(accession, text)
    return text


def _filing_index(cik: int, accession: str) -> Optional[dict]:
    """The filing folder's index.json (lists every document in the submission)."""
    acc_nodash = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/index.json"
    try:
        return store.cached_get_json(url, ttl=config.TTL_FILING_TEXT,
                                     headers=_headers(), min_interval=_MIN_INTERVAL)
    except Exception:
        return None


_EX99_RE = re.compile(r"ex[-_]?99", re.I)


def _ex99_doc(cik: int, accession: str) -> Optional[str]:
    """Filename of the EX-99 press-release exhibit in a filing, or None. The
    index.json `type` field is only an icon name, so match on the document NAME
    (earnings exhibits are conventionally named like ...ex991.htm / ex-99_1.htm)."""
    idx = _filing_index(cik, accession)
    if not idx:
        return None
    items = (idx.get("directory", {}) or {}).get("item", []) or []
    cand = [it.get("name", "") for it in items
            if _EX99_RE.search(it.get("name", "") or "")
            and it.get("name", "").lower().endswith((".htm", ".html", ".txt"))]
    if not cand:
        return None
    # prefer EX-99.1 (the press release) over EX-99.2/.3 (slides, etc.)
    cand.sort(key=lambda n: ("991" not in n.replace("-", "").replace("_", ""), n))
    return cand[0]


def earnings_release_text(ticker: str, *, max_chars: int = 40000,
                          scan: int = 8) -> Optional[dict]:
    """Earnings press release (8-K exhibit EX-99.1) — the closest free proxy for an
    earnings call / prepared remarks. The 8-K primary doc is usually just the Item
    2.02 cover that points at the exhibit, and the *latest* 8-K is often not an
    earnings filing, so this scans recent 8-Ks for the one carrying an EX-99 exhibit
    and returns its readable text.

    Returns {accession, filing_date, exhibit, url, text} or None. Falls back to the
    most recent 8-K's primary text only if no EX-99 exhibit is found in the scan.
    """
    info = universe.resolve(ticker)
    rows = list_filings(ticker, form="8-K", limit=scan) or []
    if not rows:
        return None
    first_ex99 = None   # newest EX-99 of any kind, as a fallback
    for row in rows:
        doc = _ex99_doc(info["cik"], row["accession"])
        if not doc:
            continue
        url = _ARCHIVE.format(cik=info["cik"], acc_nodash=row["accession"].replace("-", ""),
                              doc=doc)
        try:
            raw = store.cached_get(url, ttl=config.TTL_FILING_TEXT, headers=_doc_headers(),
                                   min_interval=_MIN_INTERVAL)
            text = _html_to_text(raw) if "<" in raw[:2000] else raw
        except Exception:
            continue
        if not text or len(text) <= 400:
            continue
        rec = {"accession": row["accession"], "filing_date": row["filing_date"],
               "exhibit": doc, "url": url, "text": text[:max_chars]}
        if first_ex99 is None:
            first_ex99 = rec
        # Earnings press releases talk about a quarter/fiscal period AND report
        # revenue / EPS / net income — distinguish them from other EX-99 releases.
        low = text[:8000].lower()
        if re.search(r"quarter|fiscal", low) and re.search(
                r"revenue|earnings per share|net income|diluted|operating income", low):
            return rec
    if first_ex99 is not None:
        return first_ex99
    # fallback: most recent 8-K primary document (no EX-99 found at all)
    row = rows[0]
    try:
        text = filing_text(row["accession"])
        return {"accession": row["accession"], "filing_date": row["filing_date"],
                "exhibit": row.get("primary_doc"), "url": row.get("url"),
                "text": (text or "")[:max_chars]}
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# XBRL companyfacts -> structured financials
# --------------------------------------------------------------------------- #
def refresh_facts(ticker: str, force: bool = False) -> int:
    """Pull all XBRL facts for a ticker into the store. Returns fact count.

    Not every filer has companyfacts XBRL (foreign private issuers, certain funds,
    very new filers) — SEC returns 404 for those. Treat a missing dataset as "no
    facts" (return 0) rather than raising, so a universe scan or a single skill
    degrades gracefully on those names instead of crashing the whole run.
    """
    import requests as _requests
    info = universe.resolve(ticker)
    try:
        data = _sec_json(
            _COMPANYFACTS_URL.format(cik10=info["cik10"]),
            ttl=config.TTL_COMPANYFACTS,
            force=force,
        )
    except _requests.HTTPError as e:
        if getattr(e.response, "status_code", None) in (403, 404):
            return 0
        raise
    def _num(v):
        # Coerce to float so a malformed/huge XBRL int can't overflow SQLite's int64 bind.
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f and f not in (float("inf"), float("-inf")) else None

    def _fy(v):
        return v if isinstance(v, int) and -(1 << 31) < v < (1 << 31) else None

    rows = []
    for taxonomy, tags in data.get("facts", {}).items():
        for tag, body in tags.items():
            for unit, points in body.get("units", {}).items():
                for p in points:
                    rows.append(
                        {
                            "cik": info["cik"],
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "unit": unit,
                            "fy": _fy(p.get("fy")),
                            "fp": p.get("fp"),
                            "form": p.get("form"),
                            "period_start": p.get("start"),
                            "period_end": p.get("end"),
                            "value": _num(p.get("val")),
                            "accession": p.get("accn"),
                        }
                    )
    if rows:
        store.upsert_facts(rows)
    return len(rows)


def get_concept(ticker: str, tag: str, unit: Optional[str] = None, refresh: bool = True):
    """Return time-ordered fact rows for one XBRL concept (e.g. 'Revenues')."""
    info = universe.resolve(ticker)
    if refresh and store.facts_count(info["cik"]) == 0:
        refresh_facts(ticker)
    rows = store.get_facts(info["cik"], tag=tag)
    if unit:
        rows = [r for r in rows if r["unit"] == unit]
    return rows


# --------------------------------------------------------------------------- #
# Full-text search (for change scanning across companies)
# --------------------------------------------------------------------------- #
def full_text_search(query: str, forms: Optional[str] = None, limit: int = 20):
    """EDGAR full-text search. Returns a list of hit dicts."""
    from urllib.parse import quote

    url = _FTS_URL.format(q=quote(f'"{query}"'))
    if forms:
        url += f"&forms={forms}"
    data = store.cached_get_json(
        url, ttl=config.TTL_NEWS, headers=_headers(), min_interval=_MIN_INTERVAL
    )
    hits = data.get("hits", {}).get("hits", [])[:limit]
    out = []
    for h in hits:
        src = h.get("_source", {})
        out.append(
            {
                "title": src.get("display_names", [""])[0] if src.get("display_names") else "",
                "form": src.get("file_type") or src.get("root_forms", [""])[0]
                if src.get("root_forms")
                else src.get("file_type"),
                "filing_date": src.get("file_date"),
                "accession": h.get("_id"),
                "ciks": src.get("ciks"),
            }
        )
    return out
