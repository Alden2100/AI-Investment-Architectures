"""SQLite store: owns the schema and all reads and writes for the data layer.

Other modules (universe, edgar, prices, news) never open the database directly;
they go through the helpers here. This module also owns the generic HTTP cache so
every raw GET is cached with a TTL.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterable, Optional

import requests

from . import config

_SCHEMA = """
-- Keyed by ticker, not CIK: dual-class names (e.g. GOOG/GOOGL) share one CIK,
-- so a CIK primary key would collapse them.
CREATE TABLE IF NOT EXISTS companies (
    ticker     TEXT PRIMARY KEY,
    cik        INTEGER,
    title      TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_companies_cik ON companies(cik);

CREATE TABLE IF NOT EXISTS filings (
    accession    TEXT PRIMARY KEY,
    cik          INTEGER,
    ticker       TEXT,
    form         TEXT,
    filing_date  TEXT,
    report_date  TEXT,
    primary_doc  TEXT,
    url          TEXT,
    text         TEXT,
    fetched_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_filings_lookup ON filings(cik, form, filing_date);

CREATE TABLE IF NOT EXISTS facts (
    cik          INTEGER,
    taxonomy     TEXT,
    tag          TEXT,
    unit         TEXT,
    fy           INTEGER,
    fp           TEXT,
    form         TEXT,
    period_start TEXT,
    period_end   TEXT,
    value        REAL,
    accession    TEXT,
    PRIMARY KEY (cik, taxonomy, tag, unit, period_start, period_end, accession)
);
CREATE INDEX IF NOT EXISTS idx_facts_lookup ON facts(cik, tag);

CREATE TABLE IF NOT EXISTS prices (
    ticker    TEXT,
    date      TEXT,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL,
    adj_close REAL,
    volume    REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS news (
    id         TEXT PRIMARY KEY,
    ticker     TEXT,
    title      TEXT,
    published  TEXT,
    source     TEXT,
    url        TEXT,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news(ticker, published);

CREATE TABLE IF NOT EXISTS http_cache (
    url        TEXT PRIMARY KEY,
    body       TEXT,
    status     INTEGER,
    fetched_at REAL
);

CREATE TABLE IF NOT EXISTS theses (
    thesis_id  TEXT PRIMARY KEY,
    ticker     TEXT,
    title      TEXT,
    body       TEXT,
    kpis_json  TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_theses_ticker ON theses(ticker);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT,
    actor     TEXT,
    action    TEXT,
    target    TEXT,
    detail    TEXT
);
"""

_conn: Optional[sqlite3.Connection] = None
_last_net_call: float = 0.0


def get_conn() -> sqlite3.Connection:
    """Return a process-wide connection, creating the schema on first use."""
    global _conn
    if _conn is None:
        config.ensure_cache_dir()
        _conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
        _conn.row_factory = sqlite3.Row
        # WAL + busy timeout so concurrent skill processes don't hit lock errors.
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=30000")
        _conn.executescript(_SCHEMA)
        _conn.commit()
    return _conn


@contextmanager
def _tx():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _now_iso() -> str:
    # Caller passes time; we keep a single import point.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Generic cached HTTP
# --------------------------------------------------------------------------- #
def cached_get(
    url: str,
    *,
    ttl: int,
    headers: Optional[dict] = None,
    timeout: int = 30,
    force: bool = False,
    min_interval: float = 0.0,
    data: Optional[dict] = None,
) -> str:
    """Fetch a URL, returning the body text. Caches successful bodies by key.

    GET by default; if `data` (a form dict) is given, issues a POST instead — the
    cache key folds in the form payload so different POST bodies cache separately
    (used by sources like DuckDuckGo's HTML endpoint that require POST).

    `min_interval` enforces a minimum gap (seconds) between *network* calls
    (cache hits are not throttled) so callers can respect source rate limits.

    Raises requests.HTTPError on non-200 responses that are not already cached.
    """
    global _last_net_call
    conn = get_conn()
    now = time.time()
    cache_key = url if data is None else url + "#POST#" + hashlib.sha1(
        json.dumps(data, sort_keys=True).encode()).hexdigest()
    if not force:
        row = conn.execute(
            "SELECT body, status, fetched_at FROM http_cache WHERE url = ?", (cache_key,)
        ).fetchone()
        if row is not None and (now - row["fetched_at"]) < ttl and row["status"] == 200:
            return row["body"]

    if min_interval > 0:
        wait = min_interval - (time.time() - _last_net_call)
        if wait > 0:
            time.sleep(wait)
    _last_net_call = time.time()
    if data is None:
        resp = requests.get(url, headers=headers or {}, timeout=timeout)
    else:
        resp = requests.post(url, data=data, headers=headers or {}, timeout=timeout)
    body = resp.text
    with _tx() as c:
        c.execute(
            "INSERT OR REPLACE INTO http_cache (url, body, status, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            (cache_key, body, resp.status_code, now),
        )
    resp.raise_for_status()
    return body


def cached_get_json(url: str, **kwargs) -> Any:
    return json.loads(cached_get(url, **kwargs))


# --------------------------------------------------------------------------- #
# Companies / universe
# --------------------------------------------------------------------------- #
def upsert_companies(rows: Iterable[dict]) -> None:
    now = _now_iso()
    with _tx() as c:
        c.executemany(
            "INSERT OR REPLACE INTO companies (ticker, cik, title, updated_at) "
            "VALUES (:ticker, :cik, :title, :updated_at)",
            [{**r, "updated_at": now} for r in rows],
        )


def company_by_ticker(ticker: str) -> Optional[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM companies WHERE ticker = ? COLLATE NOCASE", (ticker.upper(),)
    ).fetchone()


def all_companies() -> list[sqlite3.Row]:
    return get_conn().execute("SELECT * FROM companies").fetchall()


def companies_count() -> int:
    return get_conn().execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"]


# --------------------------------------------------------------------------- #
# Filings
# --------------------------------------------------------------------------- #
def upsert_filings(rows: Iterable[dict]) -> None:
    with _tx() as c:
        for r in rows:
            c.execute(
                """INSERT INTO filings
                   (accession, cik, ticker, form, filing_date, report_date,
                    primary_doc, url, text, fetched_at)
                   VALUES (:accession, :cik, :ticker, :form, :filing_date,
                           :report_date, :primary_doc, :url, :text, :fetched_at)
                   ON CONFLICT(accession) DO UPDATE SET
                       cik=excluded.cik, ticker=excluded.ticker, form=excluded.form,
                       filing_date=excluded.filing_date, report_date=excluded.report_date,
                       primary_doc=excluded.primary_doc, url=excluded.url""",
                {
                    "text": None,
                    "report_date": None,
                    "fetched_at": _now_iso(),
                    **r,
                },
            )


def set_filing_text(accession: str, text: str) -> None:
    with _tx() as c:
        c.execute(
            "UPDATE filings SET text = ?, fetched_at = ? WHERE accession = ?",
            (text, _now_iso(), accession),
        )


def get_filing(accession: str) -> Optional[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM filings WHERE accession = ?", (accession,)
    ).fetchone()


def list_filings(
    cik: int,
    form: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[sqlite3.Row]:
    q = "SELECT * FROM filings WHERE cik = ?"
    params: list[Any] = [cik]
    if form:
        q += " AND form = ?"
        params.append(form)
    if start:
        q += " AND filing_date >= ?"
        params.append(start)
    if end:
        q += " AND filing_date <= ?"
        params.append(end)
    q += " ORDER BY filing_date DESC"
    if limit:
        q += f" LIMIT {int(limit)}"
    return get_conn().execute(q, params).fetchall()


# --------------------------------------------------------------------------- #
# XBRL facts
# --------------------------------------------------------------------------- #
def upsert_facts(rows: Iterable[dict]) -> None:
    with _tx() as c:
        c.executemany(
            """INSERT OR REPLACE INTO facts
               (cik, taxonomy, tag, unit, fy, fp, form,
                period_start, period_end, value, accession)
               VALUES (:cik, :taxonomy, :tag, :unit, :fy, :fp, :form,
                       :period_start, :period_end, :value, :accession)""",
            list(rows),
        )


def get_facts(cik: int, tag: Optional[str] = None) -> list[sqlite3.Row]:
    if tag:
        return get_conn().execute(
            "SELECT * FROM facts WHERE cik = ? AND tag = ? ORDER BY period_end DESC",
            (cik, tag),
        ).fetchall()
    return get_conn().execute(
        "SELECT * FROM facts WHERE cik = ? ORDER BY period_end DESC", (cik,)
    ).fetchall()


def facts_count(cik: int) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) AS n FROM facts WHERE cik = ?", (cik,)
    ).fetchone()["n"]


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #
def upsert_prices(ticker: str, rows: Iterable[dict]) -> None:
    t = ticker.upper()
    with _tx() as c:
        c.executemany(
            """INSERT OR REPLACE INTO prices
               (ticker, date, open, high, low, close, adj_close, volume)
               VALUES (:ticker, :date, :open, :high, :low, :close, :adj_close, :volume)""",
            [{"ticker": t, **r} for r in rows],
        )


def get_prices(
    ticker: str, start: Optional[str] = None, end: Optional[str] = None
) -> list[sqlite3.Row]:
    q = "SELECT * FROM prices WHERE ticker = ?"
    params: list[Any] = [ticker.upper()]
    if start:
        q += " AND date >= ?"
        params.append(start)
    if end:
        q += " AND date <= ?"
        params.append(end)
    q += " ORDER BY date ASC"
    return get_conn().execute(q, params).fetchall()


def prices_count(ticker: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) AS n FROM prices WHERE ticker = ?", (ticker.upper(),)
    ).fetchone()["n"]


# --------------------------------------------------------------------------- #
# News
# --------------------------------------------------------------------------- #
def _news_id(url: str, title: str) -> str:
    return hashlib.sha1(f"{url}|{title}".encode("utf-8")).hexdigest()


def upsert_news(ticker: str, items: Iterable[dict]) -> None:
    t = ticker.upper()
    now = _now_iso()
    with _tx() as c:
        for it in items:
            c.execute(
                """INSERT OR REPLACE INTO news
                   (id, ticker, title, published, source, url, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _news_id(it.get("url", ""), it.get("title", "")),
                    t,
                    it.get("title"),
                    it.get("published"),
                    it.get("source"),
                    it.get("url"),
                    now,
                ),
            )


def get_news(ticker: str, since: Optional[str] = None) -> list[sqlite3.Row]:
    q = "SELECT * FROM news WHERE ticker = ?"
    params: list[Any] = [ticker.upper()]
    if since:
        q += " AND published >= ?"
        params.append(since)
    q += " ORDER BY published DESC"
    return get_conn().execute(q, params).fetchall()


# --------------------------------------------------------------------------- #
# Theses (the spine that links research to monitoring)
# --------------------------------------------------------------------------- #
def save_thesis(thesis_id: str, ticker: str, title: str, body: str, kpis_json: str) -> None:
    with _tx() as c:
        c.execute(
            """INSERT OR REPLACE INTO theses
               (thesis_id, ticker, title, body, kpis_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (thesis_id, ticker.upper(), title, body, kpis_json, _now_iso()),
        )


def get_thesis(thesis_id: str) -> Optional[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM theses WHERE thesis_id = ?", (thesis_id,)
    ).fetchone()


def list_theses(ticker: Optional[str] = None) -> list[sqlite3.Row]:
    if ticker:
        return get_conn().execute(
            "SELECT * FROM theses WHERE ticker = ? ORDER BY created_at DESC",
            (ticker.upper(),),
        ).fetchall()
    return get_conn().execute("SELECT * FROM theses ORDER BY created_at DESC").fetchall()


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #
def append_audit(actor: str, action: str, target: str, detail: str) -> int:
    with _tx() as c:
        cur = c.execute(
            "INSERT INTO audit_log (ts, actor, action, target, detail) VALUES (?, ?, ?, ?, ?)",
            (_now_iso(), actor, action, target, detail),
        )
        return cur.lastrowid


def list_audit(limit: int = 50) -> list[sqlite3.Row]:
    return get_conn().execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),)
    ).fetchall()
