"""filing-change-detector: material changes between two same-type filings.

Deterministic paragraph diff (difflib) + model significance labeling (hybrid).
"""
import argparse
import difflib
import os
import re
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
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "significance": {"type": "string",
                                     "description": "high/medium/low + why"},
                },
                "required": ["section", "significance"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["changes", "summary"],
}

SYSTEM = (
    "You are an equity analyst comparing two SEC filings of the same type. For each "
    "diff block, identify the section it belongs to and rate its significance "
    "(high/medium/low) with a brief reason. Flag genuinely new or removed risk "
    "factors and changed guidance as significant; treat reworded boilerplate, "
    "renumbering, and formatting as low significance. Do not invent content."
)


def _paragraphs(text):
    parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n+", text or "")]
    return [p for p in parts if len(p) > 40]


def _diff_blocks(old_text, new_text, max_blocks):
    old_p, new_p = _paragraphs(old_text), _paragraphs(new_text)
    sm = difflib.SequenceMatcher(a=old_p, b=new_p, autojunk=False)
    blocks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old_chunk = " ".join(old_p[i1:i2]).strip()
        new_chunk = " ".join(new_p[j1:j2]).strip()
        # Skip near-identical churn (tiny edits/whitespace).
        if old_chunk and new_chunk:
            ratio = difflib.SequenceMatcher(a=old_chunk, b=new_chunk).ratio()
            if ratio > 0.92:
                continue
        blocks.append({
            "type": {"replace": "changed", "insert": "added", "delete": "removed"}[tag],
            "old": old_chunk[:600],
            "new": new_chunk[:600],
        })
    raw = len(blocks)
    # Prioritize the largest substantive blocks.
    blocks.sort(key=lambda b: len(b["old"]) + len(b["new"]), reverse=True)
    return blocks[:max_blocks], raw


def _pick(ticker, form, accn):
    edgar.list_filings(ticker, form=form)
    row = store.get_filing(accn)
    if row is None:
        raise ValueError(f"Accession {accn} not found for {ticker}.")
    return row


def main(args):
    info = universe.resolve(args.ticker)
    if args.accession_new and args.accession_old:
        new_row = _pick(args.ticker, args.form, args.accession_new)
        old_row = _pick(args.ticker, args.form, args.accession_old)
    else:
        rows = edgar.list_filings(args.ticker, form=args.form, limit=2)
        if len(rows) < 2:
            raise ValueError(f"Need two {args.form} filings for {args.ticker}; found {len(rows)}.")
        new_row, old_row = rows[0], rows[1]

    new_text = edgar.filing_text(new_row["accession"])
    old_text = edgar.filing_text(old_row["accession"])
    blocks, raw = _diff_blocks(old_text, new_text, args.max_blocks)

    blocks_txt = "\n\n".join(
        f"[{b['type']}]\nOLD: {b['old'] or '(none)'}\nNEW: {b['new'] or '(none)'}"
        for b in blocks
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). Comparing {args.form} filed "
        f"{new_row['filing_date']} (new) vs {old_row['filing_date']} (old).\n\n"
        f"{raw} substantive diff blocks found; top {len(blocks)} shown:\n\n"
        f"{blocks_txt}\n\nClassify each block's section and significance."
    )
    analysis = _route(prompt, task="summarization", system=SYSTEM, schema=SCHEMA, max_tokens=3000)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "form": args.form,
        "new": {"accession": new_row["accession"], "date": new_row["filing_date"]},
        "old": {"accession": old_row["accession"], "date": old_row["filing_date"]},
        "raw_change_count": raw,
        "diff_blocks": blocks,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Detect material changes between two filings.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--form", default="10-K")
    p.add_argument("--accession-new", default=None)
    p.add_argument("--accession-old", default=None)
    p.add_argument("--max-blocks", type=int, default=25)
    skillkit.run(main, p)
