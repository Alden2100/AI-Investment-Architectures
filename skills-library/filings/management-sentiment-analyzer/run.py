"""management-sentiment-analyzer: judge management tone/confidence and its shift over time. Hybrid model skill."""
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

from imdata import skillkit, edgar, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "periods": {"type": "array", "items": {"type": "string"},
                    "description": "The filing periods/dates that were compared"},
        "tone": {"type": "string",
                 "description": "Overall tone: optimistic / cautious / defensive / mixed / neutral, with a brief why"},
        "confidence": {"type": "string",
                       "description": "Management confidence level: high / medium / low, with a brief why"},
        "shift": {"type": "string",
                  "description": "How tone/confidence changed across the periods (more/less confident, what changed)"},
        "evidence": {"type": "array", "items": {"type": "string"},
                     "description": "Short quoted phrases from the releases that support the read"},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["ticker", "tone", "confidence", "shift", "summary"],
}

SYSTEM = (
    "You are an equity research analyst evaluating management's tone and confidence from earnings "
    "press releases / prepared remarks. Read the language qualitatively: hedging, superlatives, "
    "guidance posture, framing of misses. Compare the periods to detect a SHIFT (becoming more or "
    "less confident, more defensive, etc.). Quote short phrases as evidence verbatim from the "
    "provided text. Do not invent figures or quotes; use only what appears in the text."
)


def _earnings_periods(ticker, want=3):
    """Collect up to `want` distinct earnings-release texts (newest first) by scanning 8-Ks."""
    info = universe.resolve(ticker)
    rows = edgar.list_filings(ticker, form="8-K", limit=20) or []
    out = []
    seen = set()
    import re
    for row in rows:
        acc = row["accession"]
        if acc in seen:
            continue
        doc = edgar._ex99_doc(info["cik"], acc)
        if not doc:
            continue
        url = edgar._ARCHIVE.format(cik=info["cik"], acc_nodash=acc.replace("-", ""), doc=doc)
        try:
            raw = edgar.store.cached_get(url, ttl=edgar.config.TTL_FILING_TEXT,
                                         headers=edgar._doc_headers(), min_interval=edgar._MIN_INTERVAL)
            text = edgar._html_to_text(raw) if "<" in raw[:2000] else raw
        except Exception:
            continue
        if not text or len(text) <= 400:
            continue
        low = text[:8000].lower()
        if not (re.search(r"quarter|fiscal", low) and
                re.search(r"revenue|earnings per share|net income|diluted|operating income", low)):
            continue
        seen.add(acc)
        out.append({"accession": acc, "filing_date": row["filing_date"], "text": text})
        if len(out) >= want:
            break
    return out


def main(args):
    info = universe.resolve(args.ticker)
    periods = _earnings_periods(args.ticker, want=3)
    if not periods:
        raise ValueError(f"No earnings releases (8-K EX-99.1) found for {args.ticker}.")

    blocks = []
    period_labels = []
    per_chars = max(8000, 36000 // len(periods))
    for p in periods:
        clip = skillkit.excerpt(
            p["text"], max_chars=per_chars,
            anchors=[r"outlook|guidance", r"results", r"revenue",
                     r"chief executive|ceo|commented|said"],
        )
        period_labels.append(p["filing_date"])
        blocks.append(f"--- Earnings release filed {p['filing_date']} (accession {p['accession']}) ---\n{clip}")

    prompt = (
        f"Company: {info['title']} ({info['ticker']}).\n"
        f"Periods compared (newest first): {', '.join(period_labels)}.\n\n"
        + "\n\n".join(blocks)
        + "\n\nAssess management's tone and confidence, and how the messaging has SHIFTED across "
          "these periods. Populate tone, confidence, shift, evidence (short verbatim quotes), and a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "periods": period_labels,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Evaluate management tone/confidence and its shift over recent earnings releases.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
