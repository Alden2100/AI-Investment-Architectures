"""filing-retriever: structure-aware retrieval over a single SEC filing.

Splits the filing on its Items/sections (keeping tables intact), then does
parent-document retrieval: it matches small child chunks against the query but
returns the larger *parent section* — so you get coherent context, not fragments.
Keyless BM25 by default; dense if OLLAMA_EMBED_MODEL is configured. All math/IR is
deterministic Python; the model (if any) consumes what this returns.
"""
import argparse
import os
import sys

# --- locate the shared library (_shared/) regardless of symlink/standalone ---
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

from imdata import edgar, filing_rag, skillkit, store, universe


def main(args):
    info = universe.resolve(args.ticker)
    if args.accession:
        edgar.list_filings(args.ticker)
        row = store.get_filing(args.accession)
        if row is None:
            raise ValueError(f"Accession {args.accession} not found; fetch filings first.")
    else:
        row = edgar.latest_filing(args.ticker, args.form)
        if row is None:
            raise ValueError(f"No {args.form} found for {args.ticker}.")

    idx = filing_rag.index_filing(row["accession"])

    if args.list_sections:
        secs = filing_rag.get_sections(row["accession"])
        return {
            "ticker": info["ticker"], "form": row["form"], "accession": row["accession"],
            "sections": [{"item": s["item"], "title": s["title"], "chars": len(s["text"])}
                         for s in secs],
            "index": idx,
            "summary": f"{info['ticker']} {row['form']} split into {len(secs)} sections "
                       f"({idx['chunks']} child chunks).",
        }

    if not args.query:
        raise ValueError("Provide --query, or use --list-sections.")
    res = filing_rag.retrieve(row["accession"], args.query, k=args.k,
                              return_parents=not args.chunks)
    matches = res["matches"]
    return {
        "ticker": info["ticker"], "form": row["form"], "accession": row["accession"],
        "query": args.query, "method": res["method"],
        "granularity": "chunk" if args.chunks else "parent-section",
        "matches": [{"item": m["item"], "title": m.get("title"), "score": m.get("score"),
                     "text": m["text"][:args.max_chars]} for m in matches],
        "summary": (f"Retrieved {len(matches)} {'chunk' if args.chunks else 'parent section'}(s) "
                    f"for '{args.query}' from {info['ticker']} {row['form']} "
                    f"via {res['method']}: "
                    + ", ".join(m["item"] for m in matches) + "."),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Structure-aware retrieval over a filing.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--form", default="10-K")
    p.add_argument("--accession", default=None, help="specific filing (else latest of --form)")
    p.add_argument("--query", default=None, help="what to retrieve")
    p.add_argument("--k", type=int, default=4, help="how many sections/chunks to return")
    p.add_argument("--chunks", action="store_true",
                   help="return small child chunks instead of parent sections")
    p.add_argument("--list-sections", action="store_true",
                   help="just list the filing's Item/sections")
    p.add_argument("--max-chars", type=int, default=6000, help="trim each returned section")
    skillkit.run(main, p)
