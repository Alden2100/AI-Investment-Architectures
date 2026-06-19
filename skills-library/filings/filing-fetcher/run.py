"""filing-fetcher: retrieve SEC filings (and optionally their text) for a ticker.

Deterministic wrapper over the shared data layer. Emits JSON to stdout.
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

from imdata import edgar, skillkit, universe


def main(args):
    info = universe.resolve(args.ticker)
    rows = edgar.list_filings(
        args.ticker,
        form=args.form,
        start=args.start,
        end=args.end,
        limit=args.limit,
    )
    filings = []
    for r in rows:
        item = {
            "form": r["form"],
            "date": r["filing_date"],
            "report_date": r["report_date"],
            "accession": r["accession"],
            "url": r["url"],
        }
        if args.with_text:
            item["text"] = edgar.filing_text(r["accession"])
        filings.append(item)

    form_label = args.form or "any form"
    summary = (
        f"{info['title']} ({info['ticker']}): {len(filings)} {form_label} filing(s)"
        + (f" from {args.start or '?'} to {args.end or 'now'}" if (args.start or args.end) else "")
        + (". Full text included." if args.with_text else ". Metadata only.")
    )
    return {
        "ticker": info["ticker"],
        "company": info["title"],
        "filings": filings,
        "count": len(filings),
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Fetch SEC filings for a ticker.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--form", default=None, help="e.g. 10-K, 10-Q, 8-K")
    p.add_argument("--start", default=None, help="YYYY-MM-DD")
    p.add_argument("--end", default=None, help="YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--with-text", action="store_true", help="include full filing text")
    skillkit.run(main, p)
