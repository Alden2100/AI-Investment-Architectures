# filings drawer

Reading SEC disclosures: retrieval, summarization, and year-over-year change.

| Skill | Kind | Does |
|---|---|---|
| filing-fetcher | deterministic | Fetch a filing (10-K/10-Q/8-K) or its full text from EDGAR. |
| filing-retriever | deterministic | **Structure-aware RAG**: split on Items, keep tables intact, parent-document retrieval (match small chunks → return parent sections). |
| filing-summarizer | hybrid | Structured key takeaways from a 10-K/10-Q (uses filing-retriever for context). |
| filing-change-detector | hybrid | Material changes between two filings of the same type. |
| earnings-call-summarizer | hybrid | Guidance / highlights / surprises from a release or transcript. |

Each skill is documented by its own `SKILL.md`.

### Why structure-aware retrieval (not fixed-length chunking)
Fixed-length chunking cuts across Items and through tables, so retrieved context is
fragmentary. `filing-retriever` (engine: `imdata.filing_rag`) splits a 10-K/10-Q on
its real structure (Item 1, 1A, 7, …), keeps tables atomic, and does **parent-document
retrieval** — index small child chunks for precise matching, return the larger parent
section for coherent context. Keyless BM25 by default; dense / late-chunking is a
pluggable upgrade (`OLLAMA_EMBED_MODEL`). See the skill's `references/retrieval.md`.
