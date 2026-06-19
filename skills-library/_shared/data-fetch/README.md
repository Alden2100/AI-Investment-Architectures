# data-fetch (`imdata`) — the shared data layer

Every skill imports `imdata` and never touches the network directly. All sources
are **free / keyless**; everything is cached in SQLite so flaky sources don't break
runs. The DB is the regenerable "cake" — git-ignored, rebuilt from sources.

## Modules
| Module | Provides |
|---|---|
| `config` | Paths, SEC User-Agent, cache TTLs. Honors `TOOLBOX_DB_PATH` / `TOOLBOX_CACHE_DIR` (a system points these at its own `data/`). |
| `store` | The SQLite schema + all reads/writes, and the cached HTTP layer (`cached_get`, GET or POST, TTL'd, rate-limited). Tables: companies, filings, facts, prices, news, theses, audit_log, http_cache. |
| `universe` | Ticker ↔ CIK ↔ company resolution from SEC's company list. |
| `edgar` | SEC EDGAR: submissions, company facts (XBRL), filing text. |
| `prices` | Price history with a fallback chain: **yfinance → Yahoo chart API → Stooq**, all cached, so a broken yfinance doesn't stop a run. |
| `news` | Recent headlines + SEC filing alerts from free RSS/Atom. |
| `skillkit` | The skill harness: arg parsing, single-JSON output (`run`, `emit`), `excerpt`, `model_output`, and `call_skill` (orchestrator → leaf skill). |

## yfinance resilience
`prices.refresh_prices` tries yfinance first, then a key-free Yahoo chart JSON path,
then Stooq CSV — and serves cache when all live sources are down. This is the
"the API is flaky, build it resiliently" requirement, made concrete.

## One DB per system
A system's orchestrator sets `TOOLBOX_DB_PATH` to `systems/<name>/data/<name>.db`,
so each app owns its own companies/prices/fundamentals/theses/KPIs/audit store.
