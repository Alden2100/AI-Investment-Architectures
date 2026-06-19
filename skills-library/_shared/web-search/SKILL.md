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
```

Flags: `--query` (required), `--max` (1–25, default 8).

## Output (JSON)
`{ query, provider, count, results: [{title, url, snippet}], summary }`

When running under Claude, Claude's native web search may be used instead of /
in addition to this skill. See [references/providers.md](references/providers.md).
