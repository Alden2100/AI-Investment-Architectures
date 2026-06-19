"""filing-summarizer: structured key takeaways from a 10-K/10-Q. Hybrid model skill.

run.py does deterministic data prep (fetch + trim filing) and builds the analysis
request; the reasoning is done by the model (via API if a key is set, else by the
orchestrating agent per SKILL.md). No numbers are computed here.
"""
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

from imdata import edgar, skillkit, store, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "business": {"type": "string", "description": "What the company does, segments"},
        "drivers": {"type": "array", "items": {"type": "string"},
                    "description": "Key growth/value drivers"},
        "risks": {"type": "array", "items": {"type": "string"},
                  "description": "Most material risk factors"},
        "guidance": {"type": "string", "description": "Forward guidance/outlook, or '' if none"},
        "summary": {"type": "string", "description": "One-paragraph plain-English summary"},
    },
    "required": ["business", "drivers", "risks", "summary"],
}

SYSTEM = (
    "You are an equity research analyst. Summarize the SEC filing into the requested "
    "structured fields. Do not invent figures; use only what appears in the filing "
    "text, and quote numbers exactly as written. Be specific about segments, growth "
    "drivers, and the most material risks."
)


def main(args):
    info = universe.resolve(args.ticker)
    if args.accession:
        edgar.list_filings(args.ticker)  # ensure filings indexed
        row = store.get_filing(args.accession)
        if row is None:
            raise ValueError(f"Accession {args.accession} not found; fetch filings first.")
    else:
        row = edgar.latest_filing(args.ticker, args.form)
        if row is None:
            raise ValueError(f"No {args.form} found for {args.ticker}.")

    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=70000,
        anchors=[r"item\s*1\b", r"risk factors", r"management.s discussion",
                 r"results of operations", r"outlook|guidance"],
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). Filing: {row['form']} "
        f"filed {row['filing_date']}.\n\nFiling text (excerpted):\n{clip}\n\n"
        "Produce the structured summary."
    )
    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "form": row["form"],
        "accession": row["accession"],
        "date": row["filing_date"],
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Summarize a 10-K/10-Q into key takeaways.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--form", default="10-K")
    p.add_argument("--accession", default=None)
    skillkit.run(main, p)
