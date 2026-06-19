"""Shared configuration for the data layer.

All paths and the SEC User-Agent live here so every module agrees on where the
cache lives and how to identify itself to free data sources.
"""
from __future__ import annotations

import os
from pathlib import Path

# Project root = parent of this `data/` package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Everything cached on disk goes here (SQLite DB lives inside).
CACHE_DIR = Path(os.environ.get("TOOLBOX_CACHE_DIR", PROJECT_ROOT / ".cache"))
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


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
