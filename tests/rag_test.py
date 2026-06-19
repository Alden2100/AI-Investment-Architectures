#!/usr/bin/env python3
"""Test structure-aware chunking + parent-document retrieval on a real 10-K. Keyless.

    .venv/bin/python tests/rag_test.py
"""
import os, sys

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "data-fetch"))
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(REPO, ".cache", "rag_test.db"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", os.path.join(REPO, ".cache"))

from imdata import edgar, filing_rag


def run(ticker="KO", form="10-K"):
    row = edgar.latest_filing(ticker, form)
    assert row, f"no {form} for {ticker}"
    acc = row["accession"]
    info = filing_rag.index_filing(acc, force=True)
    secs = filing_rag.get_sections(acc)
    items = {s["item"] for s in secs}

    # 1. structure-aware split found the real Items, not fixed-length blocks
    assert info["sections"] >= 8, f"too few sections: {info['sections']}"
    assert any("1A" in i for i in items), f"no Risk Factors section: {sorted(items)}"
    assert any(i in ("Item 7", "Item 2", "Item 8") for i in items), "missing core items"

    # 2. tables kept intact (atomic table chunks exist)
    chunks = filing_rag._chunks(acc)
    assert any(c["kind"] == "table" for c in chunks), "no table chunks preserved"

    # 3. parent-document retrieval: match small, return the larger parent section
    res = filing_rag.retrieve(acc, "climate change water scarcity environmental risk", k=2)
    assert res["matches"], "retrieval returned nothing"
    top = res["matches"][0]
    parent = next(s for s in secs if s["item"] == top["item"])
    assert len(top["text"]) == len(parent["text"]), "did not return the full parent section"
    assert res["child_hits"], "no child-level hits recorded"

    print(f"PASS rag: {ticker} {form} -> {info['sections']} sections, {info['chunks']} chunks, "
          f"{sum(c['kind'] == 'table' for c in chunks)} tables intact")
    print(f"     retrieval('environmental risk') -> {res['method']}: "
          + ", ".join(m['item'] for m in res['matches']))


if __name__ == "__main__":
    run()
