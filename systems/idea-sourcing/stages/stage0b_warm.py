"""Stage 0b — mandate-driven universe warming (runs once, main thread, before Stage 1).

Cheap classification (SIC + country) over the FULL universe narrows ~10k names to a
mandate-relevant candidate set; only those candidates get the expensive market-cap +
liquidity warm. So Stage 1 filters a populated, mandate-relevant snapshot instead of
"whatever happened to be cached." Bounded + resumable: classification persists and grows
across runs (first run slow on the SEC fetch, later runs fast). NO SILENT DROPS — names
outside the candidate set are just not warmed this run; they stay classified + queryable.
"""
from __future__ import annotations

from imdata import screener


def run(mandate: dict, *, max_classify: int = 1500, warm_cap: int = 400) -> dict:
    pre = screener.prescreen_universe(mandate, max_classify=max_classify)
    candidates = pre.get("candidates", [])
    warm = {}
    if candidates:
        warm = screener.refresh_metrics(tickers=candidates[:warm_cap], max_names=warm_cap)
    return {
        "classified_total": pre.get("classified_total"),
        "newly_classified": pre.get("newly_classified"),
        "preferred_sectors": pre.get("preferred"),
        "avoid_sectors": pre.get("avoid"),
        "countries": pre.get("countries"),
        "candidates": len(candidates),
        "warmed": warm.get("refreshed", 0),
        "snapshot_coverage": warm.get("snapshot_coverage"),
    }
