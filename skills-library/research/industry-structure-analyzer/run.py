"""industry-structure-analyzer: evaluate industry attractiveness via Porter's five forces. Hybrid model skill."""
import argparse
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
_here = os.path.realpath(__file__)
_root = os.environ.get("IM_LIB_ROOT", "")
if not _root:
    _d = os.path.dirname(_here)
    while _d != os.path.dirname(_d):
        if os.path.isdir(os.path.join(_d, "_shared", "data-fetch")):
            _root = _d
            break
        _d = os.path.dirname(_d)
for _p in ("data-fetch", "router", "web-search"):
    _cand = os.path.join(_root, "_shared", _p)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

import json as _json

from imdata import skillkit, edgar, universe, store
from imrouter import route as _route

_FORCE = {
    "type": "string",
    "description": "high/medium/low + one-sentence rationale grounded in the provided text/peers",
}
SCHEMA = {
    "type": "object",
    "properties": {
        "industry": {"type": "string"},
        "five_forces": {
            "type": "object",
            "properties": {
                "rivalry": _FORCE,
                "new_entrants": _FORCE,
                "substitutes": _FORCE,
                "buyer_power": _FORCE,
                "supplier_power": _FORCE,
            },
            "required": ["rivalry", "new_entrants", "substitutes", "buyer_power", "supplier_power"],
        },
        "attractiveness": {"type": "string",
                           "description": "Overall industry attractiveness (high/medium/low + why)"},
        "structure_notes": {"type": "array", "items": {"type": "string"},
                            "description": "Notable structural features: concentration, "
                                           "capital intensity, regulation, cyclicality, etc."},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["industry", "five_forces", "attractiveness", "summary"],
}

SYSTEM = (
    "You are an equity research analyst evaluating industry structure with Porter's five "
    "forces (competitive rivalry, threat of new entrants, threat of substitutes, buyer "
    "power, supplier power). Reason qualitatively from the 10-K competition and risk-factor "
    "text and from the provided same-SIC peer list. Do not invent figures or peers; the SIC "
    "classification and peer names were derived in Python. Rate each force high/medium/low "
    "with a short rationale, then judge overall industry attractiveness."
)


def _same_sic_peers(ticker, sic, limit=25):
    """Distinct peer (ticker, title) sharing the SIC code, from the snapshot DB."""
    if not sic:
        return []
    peers, seen = [], {ticker.upper()}
    for row in store.all_metrics():
        d = skillkit.as_dict(row)
        if str(d.get("sic") or "") == str(sic) and d.get("ticker") not in seen:
            seen.add(d["ticker"])
            peers.append({"ticker": d["ticker"],
                          "name": d.get("title") or d.get("sic_description")})
            if len(peers) >= limit:
                break
    return peers


def main(args):
    info = universe.resolve(args.ticker)
    meta_co = edgar.company_meta(args.ticker)
    sic = meta_co.get("sic")
    sic_desc = meta_co.get("sic_description")
    peers = _same_sic_peers(args.ticker, sic)

    row = edgar.latest_filing(args.ticker, "10-K")
    if row is None:
        raise ValueError(f"No 10-K found for {args.ticker}.")
    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=55000,
        anchors=[r"compet", r"competitive", r"risk factors", r"item\s*1a",
                 r"industry", r"regulat"],
    )

    peer_summary = (
        f"Industry SIC: {sic} — {sic_desc}.\n"
        f"Same-SIC peers from the screener snapshot ({len(peers)} found, quote exactly):\n"
        f"{_json.dumps(peers) if peers else 'none in local snapshot DB'}\n"
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). 10-K filed {row['filing_date']}.\n\n"
        f"{peer_summary}\n"
        f"10-K text (excerpted around competition / risk factors / industry / regulation):\n"
        f"{clip}\n\n"
        "Evaluate the industry structure using Porter's five forces. Use the peer list to "
        "gauge concentration/rivalry and the risk-factor text for entrants, substitutes, "
        "buyer/supplier power and regulation. Name the industry, rate each of the five "
        "forces (high/medium/low + rationale), list structural notes, and judge overall "
        "attractiveness."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "sic": sic,
        "sic_description": sic_desc,
        "peers": peers,
        "filing_date": row["filing_date"],
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Evaluate industry attractiveness with Porter's five forces.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
