"""footnote-analyzer: review 10-K accounting footnotes for disclosures and risks. Hybrid model skill."""
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
        "footnotes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Footnote topic, e.g. 'Revenue recognition', 'Contingencies'"},
                    "disclosure": {"type": "string", "description": "What the footnote discloses, summarized from the text"},
                    "risk_flag": {"type": "string", "description": "none / low / medium / high — degree of concern, with a brief why"},
                },
                "required": ["topic", "disclosure", "risk_flag"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment of the footnotes"},
    },
    "required": ["ticker", "footnotes", "summary"],
}

SYSTEM = (
    "You are a forensic-minded equity/credit analyst reading the notes to the financial statements "
    "in a 10-K. For each major topic (revenue recognition, contingencies/legal, leases, goodwill & "
    "intangibles, income taxes, and any other notable note), summarize the disclosure and assign a "
    "risk_flag (none/low/medium/high) for things like aggressive recognition, large contingencies, "
    "goodwill concentration / impairment risk, off-balance-sheet items, or tax exposure. Base every "
    "statement on the provided text; do not invent figures."
)


def main(args):
    info = universe.resolve(args.ticker)
    row = edgar.latest_filing(args.ticker, "10-K")
    if row is None:
        raise ValueError(f"No 10-K found for {args.ticker}.")
    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=60000,
        anchors=["notes to", "revenue recognition", "contingencies",
                 "leases", "goodwill", "income taxes"],
    )

    prompt = (
        f"Company: {info['title']} ({info['ticker']}). 10-K filed {row['filing_date']} "
        f"(accession {row['accession']}).\n\n"
        f"Footnote / notes text (excerpted around the key topics):\n{clip}\n\n"
        "Review the accounting footnotes. For each topic give the disclosure and a risk_flag, "
        "then write a summary of the overall picture."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2800)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "accession": row["accession"],
        "date": row["filing_date"],
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Review 10-K accounting footnotes for disclosures and risks.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
