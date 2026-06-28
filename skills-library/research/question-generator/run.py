"""question-generator: generate diligence questions for management/expert calls. Hybrid model skill."""
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

from imdata import skillkit, universe, news, estimates
from imrouter import route as _route

_QLIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "object",
            "properties": {
                "management": _QLIST,
                "financial": _QLIST,
                "competitive": _QLIST,
                "risk": _QLIST,
            },
            "required": ["management", "financial", "competitive", "risk"],
        },
        "summary": {"type": "string", "description": "One-paragraph framing of the question set"},
    },
    "required": ["questions", "summary"],
}

SYSTEM = (
    "You are a buy-side analyst preparing for a management or expert-network call. Write "
    "sharp, specific diligence questions that probe what is genuinely uncertain — not "
    "softballs. Ground questions in the provided context (recent news, consensus estimates, "
    "topic) where given; do not invent facts or figures, but you may ask about them. Group "
    "the questions into management, financial, competitive, and risk buckets."
)


def main(args):
    ticker = (args.ticker or "").strip().upper() or None
    topic = (args.topic or "").strip() or None
    if not ticker and not topic:
        raise ValueError("Provide --ticker and/or --topic.")

    context_parts = []
    meta = {"ticker": ticker, "topic": topic}

    if ticker:
        info = universe.resolve(ticker)
        meta["company"] = info["title"]
        context_parts.append(f"Company: {info['title']} ({info['ticker']}).")

        cons = estimates.get_consensus(ticker)
        if cons:
            growth = estimates.consensus_growth(cons)
            cons_brief = {
                "price_target": cons.get("price_target"),
                "recommendation": cons.get("recommendation"),
                "n_analysts": cons.get("n_analysts"),
                "forward_pe": cons.get("forward_pe"),
                "forward_eps": cons.get("forward_eps"),
                "implied_growth": growth,
            }
            meta["consensus"] = cons_brief
            context_parts.append(
                "Analyst consensus (computed/fetched — quote exactly, do not invent):\n"
                + _json.dumps(cons_brief)
            )

        rows = news.get_news(ticker, lookback_days=45)
        heads = []
        for r in skillkit.as_dicts(rows)[:12]:
            t = r.get("title")
            if t:
                heads.append({"title": t, "published": r.get("published"),
                              "source": r.get("source")})
        if heads:
            meta["headlines"] = heads
            context_parts.append("Recent headlines (last 45 days):\n" + _json.dumps(heads))

    if topic:
        context_parts.append(f"Focus topic for this call: {topic}")

    context = "\n\n".join(context_parts) if context_parts else "(no ticker context; topic-only)"
    prompt = (
        f"{context}\n\n"
        "Generate a diligence question set for an upcoming management or expert call. "
        "Make each question specific and answerable on a call — reference the consensus "
        "and recent news where relevant to surface what bulls/bears disagree about. "
        "Populate four buckets: management (strategy, incentives, execution), financial "
        "(margins, capital allocation, guidance), competitive (market share, moat, "
        "pricing), and risk (key dependencies, regulation, downside)."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate diligence questions for management/expert calls.")
    p.add_argument("--ticker")
    p.add_argument("--topic")
    skillkit.run(main, p)
