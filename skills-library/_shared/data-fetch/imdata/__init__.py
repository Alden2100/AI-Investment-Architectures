"""Shared data layer for the skill toolbox.

Every skill imports from this package and never touches the internet directly.
All sources are free (SEC EDGAR, yfinance/Stooq, RSS) and everything is cached
in SQLite via `store`.
"""
from . import config, store, universe, edgar, prices, news, estimates  # noqa: F401

__all__ = ["config", "store", "universe", "edgar", "prices", "news", "estimates"]
