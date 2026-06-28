"""meeting-prep-assistant: build a briefing + discussion points before a meeting. Hybrid model skill."""
import argparse
import json as _json
import os
import sys

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

from imdata import skillkit, universe, news, estimates
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "briefing": {"type": "string", "description": "Short briefing paragraph for the meeting"},
        "talking_points": {"type": "array", "items": {"type": "string"},
                           "description": "Points to raise / land"},
        "questions": {"type": "array", "items": {"type": "string"},
                      "description": "Sharp questions to ask"},
        "summary": {"type": "string", "description": "One-line takeaway"},
    },
    "required": ["briefing", "talking_points", "questions", "summary"],
}

SYSTEM = (
    "You are an investment analyst preparing for a meeting. Produce a crisp briefing, concrete "
    "talking points, and sharp questions. Use the provided context and any market data exactly "
    "as given; quote figures verbatim and do not invent news, estimates, or dates."
)


def _read_context(args):
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    if getattr(args, "context", None):
        return args.context
    if getattr(args, "text", None):
        return args.text
    return ""


def main(args):
    context = _read_context(args)
    data_lines = []
    meta = {"ticker": None, "context_chars": len(context)}

    if getattr(args, "ticker", None):
        info = universe.resolve(args.ticker)
        meta["ticker"] = info.get("ticker", args.ticker)
        meta["company"] = info.get("title")

        headlines = []
        for r in (news.get_news(args.ticker, lookback_days=30) or [])[:8]:
            d = skillkit.as_dict(r)
            headlines.append({"title": d.get("title"), "published": d.get("published")})
        cons = estimates.get_consensus(args.ticker) or {}
        next_earn = estimates.next_earnings_date(args.ticker)
        meta["next_earnings_date"] = next_earn
        meta["consensus"] = {
            "price_target": cons.get("price_target"),
            "recommendation": cons.get("recommendation"),
            "n_analysts": cons.get("n_analysts"),
            "forward_eps": cons.get("forward_eps"),
            "forward_pe": cons.get("forward_pe"),
        }

        data_lines.append(
            f"Company: {meta.get('company')} ({meta['ticker']}).\n"
            f"Next earnings date: {next_earn}.\n"
            f"Consensus (quote exactly, do not recompute): {_json.dumps(meta['consensus'], default=str)}\n"
            f"Recent headlines (last 30d): {_json.dumps(headlines, default=str)}"
        )

    ctx_clip = skillkit.excerpt(context, max_chars=20000) if context else "(none provided)"
    prompt = (
        "Prepare for an upcoming meeting. Build a briefing, talking points, and questions.\n\n"
        + ("MARKET DATA (computed in Python — quote exactly):\n" + "\n\n".join(data_lines) + "\n\n"
           if data_lines else "")
        + "MEETING CONTEXT:\n" + ctx_clip
    )
    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build briefing materials and discussion points before a meeting.")
    p.add_argument("--ticker")
    p.add_argument("--context")
    p.add_argument("--text")
    p.add_argument("--file")
    skillkit.run(main, p)
