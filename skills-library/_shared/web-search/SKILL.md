---
name: web-search
version: 1.0.0
description: Keyless-by-default web search for current information (news, recent
  events, anything not in filings/prices). Use when a system needs fresh context
  from the open web. Defaults to DuckDuckGo (no key); uses Brave if BRAVE_API_KEY
  is set. Returns ranked {title, url, snippet} results as JSON.
---
# web-search

Model-agnostic web search. **Deterministic retrieval** — the script fetches and
parses results; the calling model interprets them. Keyless by default
(DuckDuckGo HTML endpoint), with an optional keyed upgrade (Brave) when a key is
present. Results cache to the shared SQLite store (`TTL_WEB_SEARCH`, default 6h)
so repeated queries don't re-hit the network.

## Run
```
python run.py --query "NVIDIA data center revenue guidance 2025" --max 8
python run.py --query "Microsoft Azure AI revenue" --full --full-max 5   # + article bodies
```

Flags: `--query` (required), `--max` (1–25, default 8), `--full` (fetch + extract
the main article BODY text for the top results), `--full-max` (max bodies, default
5), `--full-timeout` (per-URL seconds, default 10).

## Output (JSON)
`{ query, provider, count, bodies_extracted, results: [{title, url, snippet, text?, site?, published?}], summary }`

`--full` adds a `text` field (the extracted article body) to results whose page is
openly fetchable. It is **additive** — without `--full` the shape is unchanged.
Body extraction is keyless (trafilatura) and best-effort: paywalled, JS-rendered,
or redirect-only pages (e.g. Google News links) come back without `text` rather
than failing. Bodies cache to the store (7-day TTL). For real article bodies this
search path is the reliable one (direct publisher URLs); the news-fetcher's Google
News links are mostly redirects and usually won't extract.

When running under Claude, Claude's native web search may be used instead of /
in addition to this skill. See [references/providers.md](references/providers.md).
