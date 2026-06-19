"""earnings-call-summarizer: structured guidance/highlights/surprises from an 8-K or transcript. Hybrid model skill."""
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

from imdata import skillkit, edgar, universe, store
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "guidance": {"type": "string",
                     "description": "Forward guidance/outlook quoted from the source, or '' if none"},
        "highlights": {"type": "array", "items": {"type": "string"},
                       "description": "Key quarter highlights (results, segment notes, commentary)"},
        "surprises": {"type": "array", "items": {"type": "string"},
                      "description": "Notable surprises vs expectations or prior commentary"},
        "summary": {"type": "string", "description": "One-paragraph plain-English summary"},
    },
    "required": ["highlights", "summary"],
}

SYSTEM = (
    "You are an equity research analyst summarizing an earnings release / 8-K or an "
    "earnings call transcript. Extract guidance, highlights, and surprises into the "
    "requested structured fields. Do not invent figures; use only what appears in the "
    "provided text and quote numbers exactly as written."
)


def main(args):
    info = universe.resolve(args.ticker)

    if args.transcript_file:
        with open(args.transcript_file, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        source = "transcript"
        row = None
    else:
        if args.accession:
            edgar.list_filings(args.ticker)  # ensure filings indexed
            row = store.get_filing(args.accession)
            if row is None:
                raise ValueError(f"Accession {args.accession} not found; fetch filings first.")
        else:
            row = edgar.latest_filing(args.ticker, "8-K")
            if row is None:
                raise ValueError(f"No 8-K found for {args.ticker}.")
        text = edgar.filing_text(row["accession"])
        source = "8-K"

    clip = skillkit.excerpt(
        text, max_chars=50000,
        anchors=[r"outlook|guidance", r"results of operations", r"revenue",
                 r"earnings per share|eps", r"prepared remarks|operator"],
    )
    if source == "transcript":
        header = f"Company: {info['title']} ({info['ticker']}). Source: earnings call transcript."
    else:
        header = (f"Company: {info['title']} ({info['ticker']}). "
                  f"Source: {row['form']} filed {row['filing_date']}.")
    prompt = (
        f"{header}\n\nEarnings text (excerpted):\n{clip}\n\n"
        "Produce the structured earnings summary (guidance, highlights, surprises, summary)."
    )

    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "source": source,
    }
    if row is not None:
        meta["accession"] = row["accession"]
        meta["date"] = row["filing_date"]
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Summarize an earnings release/8-K or transcript.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--accession", default=None)
    p.add_argument("--transcript-file", default=None)
    skillkit.run(main, p)
