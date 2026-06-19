---
name: filing-retriever
version: 1.0.0
description: Structure-aware retrieval over a single SEC filing. Splits a 10-K/10-Q
  on its Items/sections (keeping tables intact) and does parent-document retrieval —
  match small chunks, return the larger parent section. Use to pull the relevant part
  of a filing for a question ("what does the 10-K say about supply-chain risk?")
  instead of dumping the whole document into a prompt.
---
# filing-retriever

**Structure-aware RAG for filings.** Fixed-length chunking mangles 10-Ks; this
splits on the real document structure and retrieves coherent context.

- **Split on Items/sections** — Item 1 Business, Item 1A Risk Factors, Item 7 MD&A,
  … (the table-of-contents cluster is discarded).
- **Tables kept intact** — a contiguous run of tabular/numeric lines is never split
  across chunks.
- **Parent-document retrieval** — indexes small child chunks for precise matching,
  returns the larger *parent section* they belong to.
- **Keyless** — BM25 over the filing's own chunks by default; upgrades to dense
  cosine retrieval automatically if `OLLAMA_EMBED_MODEL` is set. (See
  [references/retrieval.md](references/retrieval.md) for late-chunking / dense.)

All IR is deterministic Python; results cache to SQLite (rebuildable).

## Run
```
python run.py --ticker KO --form 10-K --query "climate and water scarcity risk"
python run.py --ticker MSFT --form 10-Q --query "cloud revenue growth drivers" --k 3
python run.py --ticker KO --list-sections          # show the Item/section map
python run.py --ticker KO --query "litigation" --chunks   # small chunks, not parents
```

Flags: `--ticker` (req), `--form` (10-K), `--query`, `--k`, `--accession`,
`--chunks`, `--list-sections`, `--max-chars`.

## Output (JSON)
`{ ticker, form, accession, query, method, granularity,
matches: [{item, title, score, text}], summary }`
