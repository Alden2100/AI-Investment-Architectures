"""SEC DERA Financial Statement Data Sets — bulk offline bootstrap (public domain).

Every filer's numeric XBRL facts for a quarter, as TSV inside a ZIP. This is the
offline/batch path (cross-company screening, backfill) that complements the per-
company companyfacts API. Downloads a quarter's ZIP to the cache dir and queries the
`num`/`sub` tables with DuckDB (lazy). Heavy: each quarter is tens of MB — use
sparingly; the download is cached on disk.

Returns None / [] (with a 'note') when duckdb isn't installed. Tier: public.
"""
from __future__ import annotations

import os
from typing import Optional

from . import config

_BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/{q}.zip"


def _cache_dir() -> str:
    d = os.path.join(str(config.CACHE_DIR), "dera_bulk")
    os.makedirs(d, exist_ok=True)
    return d


def download_quarter(quarter: str = "2025q1", *, force: bool = False) -> Optional[str]:
    """Download a DERA dataset ZIP (e.g. '2025q1') to the cache dir; return the local
    path, or None on failure. Cached on disk (skips re-download)."""
    import requests
    dest = os.path.join(_cache_dir(), f"{quarter}.zip")
    if os.path.exists(dest) and os.path.getsize(dest) > 0 and not force:
        return dest
    try:
        r = requests.get(_BASE.format(q=quarter),
                         headers={"User-Agent": config.SEC_USER_AGENT}, timeout=120, stream=True)
        if r.status_code != 200:
            return None
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        return dest
    except Exception:
        return None


def query_num(quarter: str, where: str = "1=1", *, limit: int = 100) -> Optional[list]:
    """Run a SELECT over the quarter's `num.txt` (numeric facts) via DuckDB. `where`
    is a SQL predicate over num columns (adsh, tag, ddate, value, ...). Returns rows
    as dicts, or None if duckdb isn't installed / the dataset is unavailable."""
    path = download_quarter(quarter)
    if not path:
        return None
    try:
        import duckdb  # lazy, optional dep
        con = duckdb.connect()
        sql = (f"SELECT * FROM read_csv('zip://{path}/num.txt', delim='\t', "
               f"header=true, ignore_errors=true) WHERE {where} LIMIT {int(limit)}")
        rows = con.execute(sql).fetchdf().to_dict("records")
        con.close()
        return rows
    except Exception:
        return None


def available() -> dict:
    """Report whether the bulk path is usable (duckdb present)."""
    try:
        import duckdb  # noqa: F401
        return {"duckdb": True, "note": "bulk queries available"}
    except Exception:
        return {"duckdb": False, "note": "pip install duckdb to enable bulk cross-company queries"}
