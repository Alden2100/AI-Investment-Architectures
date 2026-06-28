"""Stage 3 — text-similarity driver (deterministic, numpy TF-IDF).

Runs ONCE over the survivor set (set-wise IDF), on the MAIN thread, because it both
(a) needs the whole corpus to fit IDF and (b) fetches business descriptions via
`edgar` in-process (only safe on the parent thread — see stages/_cache.py). The
per-company fan-out (Stages 4-6) happens AFTER this, via subprocess skills only.
"""
from __future__ import annotations

import json
import os
import tempfile

from imdata import edgar, skillkit, store

_ANCHORS = ["item 1.", "item 1\n", "business", "overview", "products"]


def business_description(ticker: str, *, max_chars: int = 6000) -> str:
    """Best-effort 10-K business text (Item 1), trimmed. Empty string if unavailable
    (the text-similarity skill flags that as missing_description rather than guessing)."""
    try:
        row = edgar.latest_filing(ticker, "10-K")
        if row is not None:
            acc = row["accession"] if not hasattr(row, "get") else row.get("accession")
            text = edgar.filing_text(acc) if acc else ""
            if text:
                return skillkit.excerpt(text, max_chars=max_chars, anchors=_ANCHORS)
    except Exception:
        pass
    # Fallback: industry label from the snapshot — weak, but better than nothing and
    # still honestly thin (the skill will score it low, not drop it).
    try:
        m = store.company_by_ticker(ticker)
        meta = next((r for r in store.metrics_for_tickers([ticker])), None)
        desc = (meta["sic_description"] if meta and meta["sic_description"] else "") if meta else ""
        title = (m["title"] if m else "") or ""
        return (title + " " + desc).strip()
    except Exception:
        return ""


def _call(mandate: dict, seeds: list, surv: list) -> dict:
    artifact = {"mandate_text": mandate.get("semantic_query") or "",
                "seed_companies": seeds, "survivors": surv}
    fd, path = tempfile.mkstemp(suffix=".json", prefix="stage3_")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(artifact, fh, default=str)
        out = skillkit.call_skill("text-similarity", ["--file", path])
    finally:
        os.unlink(path)
    if out.get("error"):
        raise RuntimeError(f"text-similarity failed: {out['error']}")
    return {"results": out.get("results", [])}


def run(mandate: dict, survivors: list) -> dict:
    """Full pass: fetch each survivor's 10-K business text (Hoberg-Phillips TNIC). Used
    POST-gate on the small kept set, where the per-name fetch cost is bounded."""
    seeds = []
    for t in (mandate.get("seed_tickers") or []):
        d = business_description(t)
        if d:
            seeds.append({"ticker": t, "description": d})
    surv = [{"ticker": s["ticker"], "description": business_description(s["ticker"])}
            for s in survivors]
    return _call(mandate, seeds, surv)


def run_cheap(mandate: dict, survivors: list) -> dict:
    """Cheap pass for the PRE-gate quality composite: score over the snapshot text
    already on hand (sic_description + company title) — NO 10-K fetch — so it can run
    over ALL survivors. Coarser than the full pass but free."""
    surv = [{"ticker": s["ticker"],
             "description": ((s.get("sic_description") or "") + " "
                             + (s.get("company") or s.get("title") or "")).strip()}
            for s in survivors]
    return _call(mandate, [], surv)
