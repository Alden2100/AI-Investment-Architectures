# web-search providers

The skill is provider-pluggable. Selection is by environment, so the same skill
runs keyless on a laptop and keyed in production.

| Provider | Key needed | When used | Notes |
|---|---|---|---|
| **DuckDuckGo** | none | default | HTML endpoint scraped + parsed. No account, no quota. Result wrapping (`/l/?uddg=`) is unwrapped to the real URL. |
| **Brave Search** | `BRAVE_API_KEY` | auto when key present | Cleaner JSON, ranked, generous free tier. Set the key in `.env`. |
| **Claude native search** | (Claude runtime) | when an orchestrator runs under Claude | The model can call its own web search in addition to this skill; this skill guarantees a keyless baseline for local/qwen runs. |

## Adding a provider
Add a `_yourprovider(query, n)` function returning `[{title, url, snippet}]` and
branch on its env key in `main()`. Keep the output contract identical so callers
never change.

## Caching
Every fetch goes through `imdata.store.cached_get`, keyed by URL with a TTL
(`TTL_WEB_SEARCH`, default 6h). The cache lives in the system's SQLite DB, so a
flaky network doesn't break a run that already warmed the cache.
