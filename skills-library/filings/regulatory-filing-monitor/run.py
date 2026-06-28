"""regulatory-filing-monitor: track newly filed SEC documents and highlight changes. Hybrid model skill."""
import argparse
import datetime as _dt
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

from imdata import skillkit, edgar, universe
from imrouter import route as _route

# Plain-English notes for the common forms so the deterministic table is useful on its own.
_FORM_NOTES = {
    "10-K": "Annual report", "10-Q": "Quarterly report", "8-K": "Material event / current report",
    "4": "Insider transaction (Form 4)", "3": "Initial insider ownership", "5": "Annual insider statement",
    "DEF 14A": "Proxy statement", "DEFA14A": "Additional proxy materials",
    "SC 13D": ">5% activist stake", "SC 13D/A": ">5% activist stake (amended)",
    "SC 13G": ">5% passive stake", "SC 13G/A": ">5% passive stake (amended)",
    "S-1": "IPO/registration statement", "S-3": "Shelf registration", "S-8": "Employee stock plan",
    "424B5": "Prospectus (offering)", "11-K": "Employee benefit plan", "6-K": "Foreign issuer report",
    "20-F": "Foreign annual report", "SD": "Specialized disclosure", "144": "Proposed insider sale",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "filings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "form": {"type": "string"},
                    "date": {"type": "string"},
                    "accession": {"type": "string"},
                    "note": {"type": "string", "description": "What this filing is / why it matters"},
                },
                "required": ["form", "date"],
            },
        },
        "highlights": {"type": "array", "items": {"type": "string"},
                       "description": "The most notable items in the window (material 8-Ks, ownership changes, offerings)"},
        "summary": {"type": "string", "description": "One-paragraph plain-English summary of recent filing activity"},
    },
    "required": ["ticker", "filings", "highlights", "summary"],
}

SYSTEM = (
    "You are a compliance/research analyst monitoring a company's recent SEC filings. Summarize the "
    "filing activity in the window and surface the items that matter most (material 8-Ks, large/insider "
    "ownership changes, equity offerings, proxy/governance items). Use only the provided filings list; "
    "do not invent filings, dates, or accession numbers."
)


def main(args):
    info = universe.resolve(args.ticker)
    lookback = int(args.lookback)
    cutoff = (_dt.date.today() - _dt.timedelta(days=lookback)).isoformat()

    rows = edgar.list_filings(args.ticker, limit=300) or []
    recent = []
    for r in rows:
        fd = r.get("filing_date") or ""
        if fd and fd >= cutoff:
            form = r.get("form") or ""
            recent.append({
                "form": form,
                "date": fd,
                "accession": r.get("accession"),
                "note": _FORM_NOTES.get(form, ""),
            })
    recent.sort(key=lambda x: x["date"], reverse=True)

    if not recent:
        # Deterministic-only result: nothing in window, no need to spend a model call.
        return {
            "ticker": info["ticker"],
            "company": info["title"],
            "lookback_days": lookback,
            "filings": [],
            "highlights": [],
            "summary": f"No SEC filings for {info['title']} ({info['ticker']}) in the last {lookback} days "
                       f"(since {cutoff}).",
        }

    import json as _json
    counts = {}
    for f in recent:
        counts[f["form"]] = counts.get(f["form"], 0) + 1
    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n"
        f"Lookback: last {lookback} days (since {cutoff}).\n"
        f"Form counts in window: {_json.dumps(counts)}\n\n"
        f"Filings in window (newest first):\n{_json.dumps(recent, indent=2)}\n\n"
        "Summarize the recent filing activity, fill each filing's note (keep the provided ones, "
        "improve where blank), and list the highlights (the items most worth attention)."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "lookback_days": lookback,
        "filings": recent,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Track newly filed SEC documents over a lookback window.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--lookback", type=int, default=90, help="Lookback window in days (default 90).")
    skillkit.run(main, p)
