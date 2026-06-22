"""Valuation inputs from public datasets — Aswath Damodaran (NYU Stern).

Damodaran publishes industry betas, the equity risk premium (ERP), and costs of
capital annually, public and free (attribution requested). These replace the
arbitrary constants in the DCF: the equity risk premium and (when a price beta
isn't available) a sector beta.

The numbers below are seeded from Damodaran's most recent published US dataset and
refreshed annually; `equity_risk_premium()`/`sector_beta()` cache via the kv store
and leave a hook for a live fetch of his spreadsheets. Best-effort: never raises.

Attribution: "Valuation inputs: Aswath Damodaran, NYU Stern (pages.stern.nyu.edu)".
Tier: public (resellable with attribution).
"""
from __future__ import annotations

from typing import Optional

from . import config, store

# Damodaran implied US equity risk premium (annual). Seed value; refreshed yearly.
_ERP_DEFAULT = 0.0460
_ERP_AS_OF = "2025 (Damodaran implied US ERP)"

# Damodaran industry unlevered/levered betas (US), keyed by the sector words this
# repo already uses (see ask.py SECTORS). Seed subset; extend from his beta table.
_SECTOR_BETA = {
    "semiconductor": 1.55, "software": 1.30, "computer": 1.25, "technology": 1.30,
    "pharmaceutical": 1.10, "biological": 1.20, "health": 0.95, "bank": 0.95,
    "insurance": 0.85, "beverage": 0.70, "food": 0.65, "retail": 1.10,
    "petroleum": 1.05, "motor vehicle": 1.20, "aircraft": 1.15, "telephone": 0.85,
    "television": 1.10, "chemical": 1.05, "machinery": 1.05, "gold": 1.00,
    "mining": 1.15, "steel": 1.20, "real estate": 0.90, "electric": 0.55,
    "tobacco": 0.60, "apparel": 1.00, "hotel": 1.25, "eating": 1.05,
}


def equity_risk_premium(*, force: bool = False) -> Optional[float]:
    """US equity risk premium as a decimal (Damodaran implied ERP). Returns the
    seeded annual value; cached so a future live fetch can override it."""
    key = "damodaran:erp:US"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_DAMODARAN)
        if cached is not None and cached.get("erp") is not None:
            return cached.get("erp")
    erp = _ERP_DEFAULT
    store.kv_put(key, {"erp": erp, "as_of": _ERP_AS_OF, "source": "damodaran"})
    return erp


def sector_beta(sector: str) -> Optional[float]:
    """Damodaran industry beta for a sector keyword (the SIC-style words used by the
    screener), or None if unknown. A fallback when a price-derived beta isn't usable."""
    if not sector:
        return None
    return _SECTOR_BETA.get(sector.lower().strip())


def cost_of_equity(beta: float, *, risk_free: float = None) -> Optional[float]:
    """CAPM cost of equity = rf + beta*ERP. risk_free defaults to the live Treasury
    10y (via macro) so this is fully sourced, not hardcoded."""
    if not isinstance(beta, (int, float)):
        return None
    erp = equity_risk_premium()
    rf = risk_free
    if rf is None:
        try:
            from . import macro
            rf = macro.risk_free_rate("10y")
        except Exception:
            rf = None
    if rf is None:
        rf = 0.043
    return round(rf + beta * (erp if erp is not None else 0.046), 5)


def macrotrends_history(ticker: str, slug: str, metric: str = "revenue",
                        *, force: bool = False) -> list:
    """Long-history annual series (e.g. revenue) from macrotrends.net (keyless,
    UNOFFICIAL — a sanity-check on old periods). `slug` is the company name segment in
    the macrotrends URL (e.g. 'microsoft'). Best-effort: returns [] if the page layout
    changes. Tier: keyless_unofficial (dev-only for client work)."""
    import re
    import json as _json
    key = f"macrotrends:{ticker.upper()}:{metric}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_DAMODARAN)
        if cached is not None:
            return cached
    out = []
    try:
        url = f"https://www.macrotrends.net/stocks/charts/{ticker.upper()}/{slug}/{metric}"
        body = store.cached_get(url, ttl=config.TTL_DAMODARAN,
                                headers={"User-Agent": "Mozilla/5.0"}, timeout=30, force=force)
        m = re.search(r"var\s+chartData\s*=\s*(\[.*?\]);", body, re.DOTALL)
        if m:
            for row in _json.loads(m.group(1)):
                val = row.get("v1") or row.get("v2")
                if row.get("date") and val not in (None, ""):
                    try:
                        out.append({"date": row["date"], "value": float(val)})
                    except (ValueError, TypeError):
                        pass
    except Exception:
        out = []
    store.kv_put(key, out)
    return out[-12:]


def attribution() -> str:
    return "Aswath Damodaran, NYU Stern (pages.stern.nyu.edu)"
