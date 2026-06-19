# _shared — cross-cutting infrastructure

Three pieces every system leans on. Skills and orchestrators put `_shared/*` on
`sys.path` via a small bootstrap (search up for `_shared/data-fetch`), so imports
work whether a skill runs from its canonical drawer, a system's symlink, or a
standalone bundle.

| Folder | Import as | What it is |
|---|---|---|
| [`data-fetch/`](data-fetch) | `imdata` | The data layer: SEC EDGAR, prices (with fallback chain), news, the company universe, and the SQLite store + cached HTTP. Also `skillkit` (skill harness: arg parsing, JSON output, `call_skill`). |
| [`router/`](router) | `imrouter` | The routing **engine** (mechanism) + thin clients for Claude and the local qwen3.5:9b. Plus `orchestration` helpers for systems. |
| [`web-search/`](web-search) | (skill) | A keyless web-search skill (DuckDuckGo; Brave if keyed). |

## Why these are shared, not per-skill
The data layer and router are *mechanism* — identical everywhere. Keeping one copy
(not vendored per skill) is what lets policy (per-system `router-policy.yaml`) and
manifests (per-system pinned versions) be the only things that vary. That's the
guide's mechanism-vs-policy split, made concrete.
