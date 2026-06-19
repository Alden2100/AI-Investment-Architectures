# filing-retriever — retrieval internals

## Why structure-aware, not fixed-length
A 10-K is deeply structured (Items → sub-sections → tables). Fixed-length chunking
cuts across Item boundaries and through tables, so a retrieved chunk is often half a
risk factor glued to half a table footnote. Splitting on Items and keeping tables
whole preserves the unit of meaning.

## Parent-document retrieval
Two granularities are indexed:
- **child chunks** (~1.1k chars, prose; tables are atomic regardless of size) — small
  enough to match a query precisely;
- **parent sections** (the whole Item) — large enough to give the model coherent
  context.

Retrieval matches children (precision) then returns their **deduplicated parent
sections** (context). This beats returning the raw matched fragment, and — for
filing work — matters more than any reranker.

## Ranking routes
| Route | When | Notes |
|---|---|---|
| **BM25** (default) | always, keyless | Pure-Python Okapi BM25 over the filing's own chunks. Strong baseline for the keyword/entity-heavy filing domain; no model, no downloads. |
| **Dense (cosine)** | `OLLAMA_EMBED_MODEL` set | Embeds query + chunks via Ollama `/api/embed` and ranks by cosine. Pull e.g. `ollama pull nomic-embed-text` and set `OLLAMA_EMBED_MODEL=nomic-embed-text`. |

## Late chunking (upgrade path)
True *late chunking* embeds the **whole document first**, then mean-pools token spans
into per-chunk vectors, so each chunk vector carries full-document context. That needs
a long-context embedding model (e.g. `jina-embeddings-v3`, 8k+ context) exposing
token-level embeddings. The retrieval interface here is model-agnostic — slot such a
model into the dense route and `retrieve()` uses it unchanged. The current dense route
embeds each chunk independently (classic dense retrieval), which is the practical
keyless-ish option until a long-context embedder is available locally.

## Caching
`index_filing(accession)` splits + chunks once and stores `filing_sections` /
`filing_chunks` in SQLite. Re-querying the same filing is index-free.
