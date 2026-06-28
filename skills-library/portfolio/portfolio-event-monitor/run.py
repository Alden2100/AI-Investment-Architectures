"""portfolio-event-monitor: material news + filings across holdings. Hybrid model skill."""
import argparse
import json
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

from imdata import edgar, news, skillkit, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "type": {"type": "string", "description": "news / filing-<form> / earnings / etc."},
                    "date": {"type": "string"},
                    "headline": {"type": "string"},
                    "materiality": {"type": "string",
                                    "description": "high / medium / low + brief why"},
                },
                "required": ["ticker", "type", "headline", "materiality"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph digest of what matters most."},
    },
    "required": ["events", "summary"],
}

SYSTEM = (
    "You are a buy-side analyst triaging developments across a portfolio. The news headlines "
    "and SEC filings listed were gathered in Python — use only those items; do not invent "
    "events, headlines, or dates. For each item assign a materiality (high/medium/low) with a "
    "brief reason, prioritizing 8-Ks, M&A, guidance changes, management/legal/regulatory news, "
    "and earnings over routine items. Return the events sorted most-material first and a summary."
)

MATERIAL_FORMS = {"8-K", "10-K", "10-Q", "SC 13D", "SC 13G", "DEF 14A", "424B5", "S-1"}


def _load_tickers(args):
    if args.tickers:
        return [t.strip() for t in args.tickers if t.strip()]
    raw = None
    if args.file:
        with open(args.file, "r") as f:
            raw = f.read()
    elif args.holdings:
        raw = args.holdings
    if not raw:
        raise ValueError("Provide --tickers, or --holdings (JSON), or --file (path to JSON).")
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError('Holdings must be a non-empty JSON array of {"ticker",...}.')
    out = [(h.get("ticker") or h.get("symbol") or "").strip() for h in data]
    out = [t for t in out if t]
    if not out:
        raise ValueError("No tickers found in holdings.")
    return out


def main(args):
    tickers = [universe.resolve(t)["ticker"] for t in _load_tickers(args)]
    lookback = args.lookback

    raw_events = []
    notes = []
    for t in tickers:
        try:
            items = news.get_news(t, lookback_days=lookback) or []
        except Exception as e:
            items = []
            notes.append(f"{t} news error: {e}")
        for it in items:
            d = skillkit.as_dict(it)
            raw_events.append({
                "ticker": t,
                "type": "news",
                "date": d.get("published"),
                "headline": d.get("title") or "",
                "source": d.get("source"),
            })
        try:
            filings = edgar.list_filings(t, limit=12) or []
        except Exception as e:
            filings = []
            notes.append(f"{t} filings error: {e}")
        for f in filings:
            fd = skillkit.as_dict(f)
            form = fd.get("form")
            fdate = fd.get("filing_date")
            raw_events.append({
                "ticker": t,
                "type": f"filing-{form}" if form else "filing",
                "date": fdate,
                "headline": f"{form} filed {fdate}" if form else "SEC filing",
                "form": form,
            })

    # Trim the filing list to recent / material forms to keep the prompt focused.
    trimmed = [e for e in raw_events if e["type"] == "news"]
    trimmed += [e for e in raw_events
                if e["type"] != "news" and (e.get("form") in MATERIAL_FORMS)]
    # Cap to keep the prompt bounded.
    trimmed = trimmed[:120]

    prompt = (
        f"Portfolio of {len(tickers)} companies, lookback {lookback} days. "
        f"All items below were gathered in Python — rank only these, do not invent.\n\n"
        f"Events (news headlines and SEC filings):\n{json.dumps(trimmed, indent=2)}\n\n"
        + (("Notes: " + "; ".join(notes) + "\n\n") if notes else "")
        + "Classify each event's materiality (high/medium/low + why) and return them most-material "
        "first, then a portfolio-level summary of what an investor should pay attention to."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=3000)
    meta = {
        "tickers": tickers,
        "lookback_days": lookback,
        "raw_event_count": len(raw_events),
        "notes": notes,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Track material developments across portfolio companies.")
    p.add_argument("--tickers", nargs="+", help="one or more tickers")
    p.add_argument("--holdings", help='JSON array: [{"ticker":..,"weight":..}]')
    p.add_argument("--file", help="path to a JSON file of the same shape")
    p.add_argument("--lookback", type=int, default=30, help="lookback window in days")
    skillkit.run(main, p)
