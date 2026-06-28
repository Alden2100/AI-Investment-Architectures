"""peer-identifier: find direct competitors, substitutes, and comparables for a ticker. Hybrid model skill."""
import argparse
import json as _json
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

from imdata import skillkit, edgar, universe, store
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "peers": {
            "type": "object",
            "description": "Refined peer groups drawn from the candidate list and your "
                           "knowledge. Use tickers/names; prefer candidates supplied below.",
            "properties": {
                "direct": {"type": "array", "items": {"type": "string"},
                           "description": "Direct competitors selling close substitutes into "
                                          "the same end markets."},
                "substitutes": {"type": "array", "items": {"type": "string"},
                                "description": "Alternatives that satisfy the same customer "
                                               "need via a different product/technology."},
                "comparables": {"type": "array", "items": {"type": "string"},
                                "description": "Valuation/structural comps (similar size, "
                                               "margins, or business model) even if not direct rivals."},
            },
            "required": ["direct", "substitutes", "comparables"],
        },
        "summary": {"type": "string", "description": "One-paragraph rationale for the grouping."},
    },
    "required": ["peers", "summary"],
}

SYSTEM = (
    "You are an equity research analyst building a peer set. You are given a target company, "
    "its SIC industry, and a candidate list of same-SIC public companies (computed from a "
    "metrics store). Sort the relevant names into DIRECT competitors, SUBSTITUTES, and "
    "valuation/structural COMPARABLES, and drop irrelevant SIC neighbors. Prefer names from "
    "the supplied candidate list (quote their tickers exactly); you may add a well-known "
    "peer the list misses, but do not invent tickers. Be concise and justify the grouping."
)


def _candidates_for_sic(sic, exclude_ticker, limit=60):
    """Same-SIC names from the metrics store, biggest first (market cap)."""
    if sic is None:
        return []
    target = str(sic).strip()
    rows = []
    try:
        rows = store.all_metrics() or []
    except Exception:
        rows = []
    out = []
    for r in rows:
        d = dict(r)
        if d.get("ticker", "").upper() == exclude_ticker.upper():
            continue
        if str(d.get("sic") or "").strip() != target:
            continue
        out.append({
            "ticker": d.get("ticker"),
            "name": d.get("title") or d.get("sic_description"),
            "market_cap": d.get("market_cap"),
            "sic_description": d.get("sic_description"),
        })
    out.sort(key=lambda x: (x["market_cap"] is not None, x["market_cap"] or 0), reverse=True)
    return out[:limit]


def main(args):
    info = universe.resolve(args.ticker)
    meta_sec = {}
    try:
        meta_sec = edgar.company_meta(args.ticker) or {}
    except Exception:
        meta_sec = {}
    sic = meta_sec.get("sic")
    sic_desc = meta_sec.get("sic_description")

    candidates = _candidates_for_sic(sic, info["ticker"])

    cand_line = (
        f"Candidate same-SIC public companies from the metrics store "
        f"({len(candidates)} found, largest first — quote tickers exactly):\n"
        f"{_json.dumps(candidates)}\n" if candidates else
        "Candidate same-SIC companies: NONE found in the metrics store (it may be unwarmed). "
        "Rely on your knowledge of the industry instead, and do not invent tickers.\n"
    )

    prompt = (
        f"Target company: {info['title']} ({info['ticker']}).\n"
        f"SIC code: {sic}  |  SIC description: {sic_desc}\n\n"
        f"{cand_line}\n"
        "Group the relevant names into direct competitors, substitutes, and "
        "valuation/structural comparables. Drop SIC neighbors that are not genuine peers. "
        "Then write a summary explaining the grouping."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2000)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "sic": sic,
        "sic_description": sic_desc,
        "candidates": candidates,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Identify competitors, substitutes, and comparables for a ticker.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
