"""Sanctions / watchlist screening from PRIMARY government lists (public domain).

Defaults to the official OFAC SDN list (US Treasury) — public-domain and resellable,
so it's safe for client deliverables. EU/UN/UK consolidated lists are registered and
fetched best-effort. OpenSanctions (aggregated, fuzzy-matched) is a keyed upgrade with
a NON-COMMERCIAL license, so it's used only when a key is present AND the run is NOT in
IM_COMMERCIAL_MODE.

screen(name) returns any matches with the source + tier, so a governance report can
footnote which list a hit came from. Best-effort; never raises.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from . import config, store

_OFAC_SDN = "https://www.treasury.gov/ofac/downloads/sdn.csv"
_OFAC_CONS = "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def _load_ofac(*, force: bool = False) -> list:
    """Return a list of {name, type, program} from the OFAC SDN list (cached)."""
    cached = store.kv_get("sanctions:ofac_sdn", ttl=config.TTL_SANCTIONS)
    if cached is not None and not force:
        return cached
    rows = []
    try:
        import csv
        import io
        body = store.cached_get(_OFAC_SDN, ttl=config.TTL_SANCTIONS,
                                headers={"User-Agent": config.SEC_USER_AGENT}, timeout=60, force=force)
        # SDN CSV columns: ent_num, SDN_Name, SDN_Type, Program, Title, ...
        for r in csv.reader(io.StringIO(body)):
            if len(r) >= 4 and r[1] and r[1] != "-0-":
                rows.append({"name": r[1], "type": r[2], "program": r[3], "norm": _norm(r[1])})
    except Exception:
        rows = []
    store.kv_put("sanctions:ofac_sdn", rows)
    return rows


def _opensanctions(name: str) -> list:
    """Keyed OpenSanctions match (aggregated, fuzzy). Non-commercial license: gated
    behind a key AND IM_COMMERCIAL_MODE being OFF."""
    api = os.environ.get("OPENSANCTIONS_API_KEY")
    if not api or config.COMMERCIAL_MODE:
        return []
    try:
        url = "https://api.opensanctions.org/search/default?q=" + re.sub(r"\s+", "%20", name)
        data = store.cached_get_json(url, ttl=config.TTL_SANCTIONS,
                                     headers={"Authorization": f"ApiKey {api}"}, timeout=30)
        out = []
        for hit in (data.get("results") or [])[:10]:
            out.append({"name": hit.get("caption"), "source": "OpenSanctions",
                        "tier": "free_key_noncommercial", "score": hit.get("score"),
                        "topics": hit.get("properties", {}).get("topics")})
        return out
    except Exception:
        return []


def screen(name: str, *, force: bool = False) -> dict:
    """Screen a name (company or person) against the sanctions lists. Returns
    {query, hits:[{name, source, tier, program?}], clear: bool, lists_checked}."""
    q = _norm(name)
    hits = []
    checked = []
    if q and len(q) >= 3:
        checked.append("OFAC SDN")
        for row in _load_ofac(force=force):
            # substring either direction (handles "ACME CORP" vs "ACME CORPORATION LLC")
            if q in row["norm"] or (len(row["norm"]) >= 4 and row["norm"] in q):
                hits.append({"name": row["name"], "type": row.get("type"),
                             "program": row.get("program"), "source": "OFAC SDN (US Treasury)",
                             "tier": "public"})
                if len(hits) >= 15:
                    break
        os_hits = _opensanctions(name)
        if os_hits:
            checked.append("OpenSanctions")
            hits += os_hits
    return {"query": name, "hits": hits, "clear": not hits, "lists_checked": checked}
