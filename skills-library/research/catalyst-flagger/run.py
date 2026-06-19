"""catalyst-flagger: surface event-driven / thematic setups from recent filings and news. Hybrid model skill."""
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

from imdata import skillkit, edgar, news, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "catalysts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "type": {"type": "string",
                             "description": "Catalyst type, e.g. earnings / M&A / "
                                            "product / guidance / regulatory / management / macro"},
                    "date": {"type": "string", "description": "Relevant/expected date or 'unknown'"},
                    "confidence": {"type": "number",
                                   "description": "0..1 confidence this is a real catalyst"},
                    "rationale": {"type": "string",
                                  "description": "Why, citing the specific filing or headline"},
                },
                "required": ["ticker", "type", "confidence", "rationale"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph cross-ticker takeaway"},
    },
    "required": ["catalysts", "summary"],
}

SYSTEM = (
    "You are an event-driven equity analyst. From the provided signals (recent 8-K "
    "filings and news headlines per ticker), identify and label potential catalysts. "
    "Only use the supplied signals; do not invent events or figures. Assign each "
    "catalyst a type, a date if stated, a 0..1 confidence, and a rationale that cites "
    "the specific filing date/form or headline it is based on."
)


def main(args):
    blocks = []
    signal_counts = {}
    for tk in args.tickers:
        info = universe.resolve(tk)
        ticker = info["ticker"]
        filings = skillkit.as_dicts(edgar.list_filings(ticker, form="8-K", limit=5) or [])
        news_rows = skillkit.as_dicts(news.get_news(ticker, lookback_days=args.lookback) or [])
        signal_counts[ticker] = {"filings": len(filings), "news": len(news_rows)}

        lines = [f"### {info['title']} ({ticker})"]
        lines.append("Recent 8-K filings:")
        if filings:
            for f in filings:
                lines.append(f"- {f['filing_date']} {f['form']} (accession {f['accession']})")
        else:
            lines.append("- none")
        lines.append("Recent news headlines:")
        if news_rows:
            for n in news_rows[:15]:
                lines.append(f"- {n.get('published','')} [{n.get('source','')}] {n.get('title','')}")
        else:
            lines.append("- none")
        blocks.append("\n".join(lines))

    signals = "\n\n".join(blocks)
    prompt = (
        f"Signals gathered over the last {args.lookback} days for "
        f"{', '.join(args.tickers)}.\n\n{signals}\n\n"
        "Flag potential catalysts as structured objects, then give a cross-ticker summary."
    )

    analysis = _route(prompt, task="classification", system=SYSTEM, schema=SCHEMA, max_tokens=3000)
    meta = {
        "tickers": [t.upper() for t in args.tickers],
        "lookback_days": args.lookback,
        "signal_counts": signal_counts,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Flag event-driven catalysts from filings and news.")
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--lookback", type=int, default=30)
    skillkit.run(main, p)
