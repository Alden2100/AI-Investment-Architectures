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

from imdata import skillkit, edgar, estimates, news, universe
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
                    "source": {"type": "string", "enum": ["sec_filing", "analyst", "news", "price_action", "other"],
                               "description": "Where it came from: an SEC 8-K (sec_filing), a "
                                              "sell-side action (analyst), a news event (news), pure "
                                              "price/sentiment like 'oversold'/'52-wk low' (price_action), else other"},
                    "hard_event": {"type": "boolean",
                                   "description": "True only for a concrete corporate EVENT (earnings, "
                                                  "guidance, M&A, contract win, buyback, management change, "
                                                  "regulatory action). False for opinion/sentiment/price-action."},
                    "date": {"type": "string", "description": "Relevant/expected date or 'unknown'"},
                    "confidence": {"type": "number",
                                   "description": "0..1 confidence this is a real catalyst"},
                    "rationale": {"type": "string",
                                  "description": "Why, citing the specific filing or headline"},
                },
                "required": ["ticker", "type", "source", "hard_event", "confidence", "rationale"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph cross-ticker takeaway"},
    },
    "required": ["catalysts", "summary"],
}

SYSTEM = (
    "You are an event-driven equity analyst. From the provided signals (recent 8-K "
    "filings, news headlines, and any known upcoming earnings date per ticker), label "
    "potential catalysts. Only use the supplied signals; do not invent events or figures.\n"
    "Classify each by `source` and set `hard_event` TRUE only for a concrete corporate "
    "event (earnings, guidance, M&A, contract win, buyback, management change, regulatory "
    "action — usually an 8-K). Set it FALSE for opinion/sentiment/price-action: an analyst "
    "blog/'thesis' piece, 'oversold'/'52-week-low'/'momentum' framing, or a generic news "
    "mention — these are NOT catalysts; give them low confidence and source price_action/"
    "news/analyst. Prefer hard events; a known upcoming earnings date is a real forward "
    "catalyst. Give each a type, date if stated, 0..1 confidence, and a rationale citing "
    "the specific filing date/form or headline."
)


def main(args):
    blocks = []
    signal_counts = {}
    for tk in args.tickers:
        info = universe.resolve(tk)
        ticker = info["ticker"]
        filings = skillkit.as_dicts(edgar.list_filings(ticker, form="8-K", limit=5) or [])
        news_rows = skillkit.as_dicts(news.get_news(ticker, lookback_days=args.lookback) or [])
        try:
            earn_date = estimates.next_earnings_date(ticker)
        except Exception:
            earn_date = None
        signal_counts[ticker] = {"filings": len(filings), "news": len(news_rows),
                                 "next_earnings": earn_date}

        lines = [f"### {info['title']} ({ticker})"]
        if earn_date:
            lines.append(f"Known upcoming earnings date (forward catalyst): {earn_date}")
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

        # Real article CONTENT to flag catalysts from (not just headlines). The Google
        # News RSS links above are redirect pages that don't extract, so we pull a few
        # DIRECT publisher articles via web-search --full instead. Best-effort/guarded.
        try:
            web = skillkit.call_skill(
                "web-search", ["--query", f"{info['title']} stock news",
                               "--max", "6", "--full", "--full-max", "4"])
            excerpts = [(r.get("title"), r.get("text")) for r in (web.get("results") or [])
                        if r.get("text")][:3]
            if excerpts:
                lines.append("Article excerpts (direct sources):")
                for title, text in excerpts:
                    lines.append(f"- {title}: {text[:700]}")
        except Exception:
            pass
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
