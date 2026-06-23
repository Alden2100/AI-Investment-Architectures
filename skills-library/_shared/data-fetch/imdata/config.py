"""Shared configuration for the data layer.

All paths and the SEC User-Agent live here so every module agrees on where the
cache lives and how to identify itself to free data sources.
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root = parent of this `data/` package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_cache_dir() -> Path:
    """A writable, LOCAL (non-synced) per-user cache.

    Never default to the package tree: when the project is installed as a Cowork
    plugin (read-only) or lives on OneDrive/iCloud (a synced virtual filesystem
    where SQLite can't create its WAL/SHM files), writing the DB next to the code
    fails with 'read-only file system' / 'disk I/O error'. ``TOOLBOX_CACHE_DIR``
    still overrides for tests/sandboxes."""
    env = os.environ.get("TOOLBOX_CACHE_DIR")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return Path(base) / "im-ai-skills"


# Everything cached on disk goes here (SQLite DB lives inside).
CACHE_DIR = _default_cache_dir()
DB_PATH = Path(os.environ.get("TOOLBOX_DB_PATH", CACHE_DIR / "toolbox.db"))

# SEC requires a descriptive User-Agent with contact info. Override via env if
# you fork this for another shop.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "IM-AI-Skills research (alden.c.mehta@gmail.com)",
)

# SEC asks callers to stay under 10 requests/second. We aim well under.
SEC_MAX_RPS = float(os.environ.get("SEC_MAX_RPS", "8"))

# Default cache TTLs (seconds).
TTL_SUBMISSIONS = int(os.environ.get("TTL_SUBMISSIONS", str(24 * 3600)))
TTL_COMPANYFACTS = int(os.environ.get("TTL_COMPANYFACTS", str(24 * 3600)))
TTL_FILING_TEXT = int(os.environ.get("TTL_FILING_TEXT", str(30 * 24 * 3600)))
TTL_PRICES = int(os.environ.get("TTL_PRICES", str(12 * 3600)))
TTL_NEWS = int(os.environ.get("TTL_NEWS", str(2 * 3600)))
TTL_UNIVERSE = int(os.environ.get("TTL_UNIVERSE", str(7 * 24 * 3600)))
# Size-aware screener snapshot (imdata/screener.py): market cap / SIC change slowly,
# so a 7-day snapshot is fine; ADV / last_px recompute cheaply from the prices cache.
TTL_METRICS = int(os.environ.get("TTL_METRICS", str(7 * 24 * 3600)))
# Broadened-coverage sources (see imdata/sources.py).
TTL_MACRO = int(os.environ.get("TTL_MACRO", str(12 * 3600)))
TTL_DAMODARAN = int(os.environ.get("TTL_DAMODARAN", str(30 * 24 * 3600)))   # annual dataset
TTL_OWNERSHIP = int(os.environ.get("TTL_OWNERSHIP", str(24 * 3600)))
TTL_SANCTIONS = int(os.environ.get("TTL_SANCTIONS", str(7 * 24 * 3600)))
TTL_ESTIMATES = int(os.environ.get("TTL_ESTIMATES", str(24 * 3600)))

# Commercial-license gating. When IM_COMMERCIAL_MODE is set, only `public`-tier
# (government / public-domain, resellable) sources are used; non-public fetchers
# are skipped. See imdata/sources.py::allowed(). Off by default (all sources usable
# for development).
COMMERCIAL_MODE = os.environ.get("IM_COMMERCIAL_MODE", "") not in ("", "0", "false", "False")


def ensure_cache_dir() -> None:
    """Create the cache dir, falling back to a temp dir if it isn't writable (last-
    ditch so the data layer never hard-crashes on a locked filesystem)."""
    global CACHE_DIR, DB_PATH
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _probe = CACHE_DIR / ".write-test"
        _probe.touch()
        _probe.unlink()
    except OSError:
        if os.environ.get("TOOLBOX_DB_PATH"):
            return  # caller pinned an explicit DB path; respect it
        import tempfile
        CACHE_DIR = Path(tempfile.gettempdir()) / "im-ai-skills"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        DB_PATH = CACHE_DIR / "toolbox.db"
