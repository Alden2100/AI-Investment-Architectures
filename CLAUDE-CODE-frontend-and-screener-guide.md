# Build guide — fix mid-cap sourcing, and move the NL front door to Claude Cowork

**Audience:** Claude Code, working in this repo (`AI Investment Architectures/`).
**Author intent:** two architecturally-scoped fixes, already diagnosed. Do **not**
re-diagnose from scratch — the root causes below were traced through the actual code.
Implement against them.

## 0. Orientation — read before touching anything

Two invariants govern this codebase. Preserve both.

1. **"Code for what's exact, model for what's judged."** Every number is computed
   deterministically in Python (the skills / system orchestrators). Models only
   route, extract entities, and write narrative. Never move a calculation into a
   prompt. *Which* model does each step — a three-rung ladder: qwen (simplest) →
   Sonnet (basic) → Opus (advanced) — is itself a first-class policy: see **Part AB**.
2. **One shared fetch+cache spine.** All outbound data calls funnel through
   `skills-library/_shared/data-fetch/imdata` and its SQLite `http_cache` with a
   `fetched_at` TTL. The decision rule (`DATA-SOURCE-MAP.md`): a fetcher used by ≥2
   systems or foundational → lives in `imdata`. **Never duplicate a fetcher into a
   system.** New sources get added to `imdata` + the `sources.py` registry.

System layout: `systems/<name>/orchestrator.py` is a deterministic fan-out that
pins leaf skills via `manifest.yaml`, materialized as symlinks by `link.py`. The
leaf skills live in `skills-library/` and each carry a `SKILL.md` + `run.py`.

The two problems and the committed directions:

| # | Problem | Direction |
|---|---------|-----------|
| A | Idea sourcing can't reach mid-caps — it scans the universe top-down and truncates to the biggest ~160 names before size filters run. | Precompute a **cached, size-aware universe snapshot** (pluggable provider, default keyless SEC+price). Screen over the *full* universe; delete the top-down truncation. |
| B | The terminal NL front end (`ask.py`) fails more often than not — hand-rolled keyword routing + regex entity extraction + a 9B-model fallback. | **Make Claude Cowork the front door.** Package the 7 systems as a Cowork plugin; Cowork's own Claude does the routing. Retire the keyword classifier. |

**Sequencing matters: do Part A first.** Even with perfect routing, a request like
"find mid-cap beverage names" looks broken because the *screener* returns nothing.
Part A must land before Part B can be judged working.

---

## Part A — Size-aware universe (the mid-cap fix)

### A1. Root cause (confirmed in code — do not re-litigate)

- The universe comes from SEC `company_tickers.json` (`imdata/universe.py`), which
  is ordered **roughly by market cap, descending**. The idea-sourcing orchestrator
  comment even relies on this ("companies are ordered by market cap").
- `store.all_companies()` runs `SELECT * FROM companies` with **no `ORDER BY`**, so
  it returns rows in insertion (rowid) order — i.e. that same big→small order.
- `skills-library/.../universe-screener/run.py` truncates **before** the expensive
  filters run:
  ```python
  if wants_expensive and len(base) > args.max_fetch:
      base = base[: args.max_fetch]   # first N == the LARGEST names
  ```
  So size/SIC/ADV filters only ever see the first `max_fetch` rows.
- `systems/idea-sourcing/orchestrator.py::screen()` bumps `--max-fetch` to **160**
  for sector/size screens. Mid-caps sit far below rank 160 by size, so they're never
  fetched. A `--max-mcap` ceiling then filters out 100% of those 160 mega-caps →
  near-empty result.

It is a **traversal-direction** bug, not a tuning bug. Raising `max-fetch` to reach
mid-caps would force thousands of per-name SEC+price fetches per screen (SEC rate
limit ~10 req/s) — which is exactly why the cap exists.

### A2. Principle of the fix

Separate **slow-changing universe metadata** (market cap, SIC, ADV — changes daily
at most) from **screen-time filtering** (must be instant). Today they're conflated:
every screen does live per-name fetches, which forces the fetch cap, which forces
top-down truncation.

Precompute the metadata into a cached snapshot via a bounded batch job. Then
screen-time becomes a filter over the snapshot across the **entire** universe — zero
per-name fetches, no truncation, no top-down bias. Mid-cap, small-cap, any band
become equally reachable.

### A3. Data model — new `company_metrics` table

In `imdata/store.py`, add a table **separate** from `companies` (keep identity vs.
metrics distinct so metrics can be TTL'd/refreshed without touching identity):

```sql
CREATE TABLE IF NOT EXISTS company_metrics (
    ticker          TEXT PRIMARY KEY,
    market_cap      REAL,
    sic             INTEGER,
    sic_description TEXT,
    adv             REAL,        -- avg daily $ volume
    last_px         REAL,
    currency        TEXT,
    source          TEXT,        -- which provider wrote this row
    snapshot_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_mcap ON company_metrics(market_cap);
```

Add store helpers next to the existing company helpers:
`upsert_metrics(rows)`, `metrics_for_tickers(tickers)`, `all_metrics()`,
`metrics_count()`, and `stale_tickers(ttl_seconds, limit)` (tickers whose
`snapshot_at` is missing or older than the TTL, for incremental refresh).

Add `TTL_METRICS` to `config.py` (suggest 7 days for mcap/SIC; ADV/last_px can be
recomputed cheaply from the existing `prices` cache so they need no separate TTL).

### A4. Pluggable snapshot builder — new `imdata/screener.py`

This is a **shared** module (decision rule: it's foundational, ≥2 systems will use
it). It exposes:

```python
def refresh_metrics(tickers=None, provider=None, max_names=500) -> dict:
    """Populate/refresh company_metrics. Defaults to refreshing the stalest
    `max_names` tickers across the universe. Bounded and resumable."""
```

Provider interface (so personal vs. commercial deployments can differ without
touching call sites — mirrors the `sources.py` registry pattern):

```python
class MetricsProvider:
    name: str
    def fetch(self, tickers: list[str]) -> dict[str, dict]: ...
```

Implementations:

- **`SecPriceProvider` (default, keyless).** Reuses what the screener already
  computes per-name today: `edgar.get_concept(ticker, shares_tag)` ×
  `prices.last_price(ticker)` → market cap; `prices.get_history` → ADV;
  `edgar.company_meta` → SIC. The difference from today is **when** it runs: a
  bounded batch refresher, not at screen time. Incremental — refresh up to
  `max_names` stalest names per invocation, so the cache warms over a few runs and
  stays fresh thereafter. Licensing-wise this adds **no new exposure**: SIC/shares
  come from SEC EDGAR (`PUBLIC`, public-domain) and price/volume reuse the exact
  same `prices` feed (`yfinance`, `keyless_unofficial`) that every system in the
  stack already depends on — so it's as commercial-safe as your current baseline,
  no more, no less.
- **`FmpProvider` (optional, free API key).** One `/stock-screener` call returns
  market cap + sector for a whole band server-side. Gate behind `FMP_API_KEY`; use
  automatically when the key is present (it collapses warming from thousands of
  fetches to a handful).
- **`FinvizProvider` (optional, keyless, personal-use only).** `finvizfinance` bulk
  pull. **Must be disabled when `IM_COMMERCIAL_MODE=1`** (it's an unofficial source,
  flagged `planned` in `sources.py` — do not ship it in a resellable plugin).

Provider selection order: explicit `provider=` arg → `FmpProvider` if `FMP_API_KEY`
set → `FinvizProvider` if explicitly enabled and not commercial → `SecPriceProvider`
(default). Register all three in `imdata/sources.py` and respect the existing
commercial-mode gate.

### A5. Screener changes — `universe-screener/run.py`

- Add `--use-snapshot` (**default on**). When expensive filters are requested and
  the snapshot covers the universe, filter market-cap band / SIC / ADV by reading
  `company_metrics` across **all** names — no `base[:max_fetch]`, no truncation.
- Keep the current live-fetch path as the `--no-snapshot` fallback for a cold cache,
  and as the per-name fallback for individual tickers missing from the snapshot
  (bounded by `max_fetch`).
- When ordering by size is wanted, `ORDER BY market_cap DESC` **explicitly** — stop
  relying on insertion order as a size proxy.
- Keep the output JSON shape back-compatible; add a `snapshot_coverage` field
  (fraction of the matched universe served from snapshot vs. live) so callers can
  tell when the cache is still warming. `truncated` should now only ever be true on
  the live fallback path.

### A6. Orchestrator + front-end cleanup

- `systems/idea-sourcing/orchestrator.py::screen()`: **remove the `--max-fetch 160`
  hack** and its comment. Pass the band straight through; rely on the snapshot.
- The size-band mapping in `ask.py` (`extract_mcap`, `_size_to_band`) is already
  correct (`mid-cap → 2e9–2e10`); leave it. It gets retired wholesale in Part B.

### A7. Batch-refresh wiring

- Expose a CLI entry: `python -m imdata.screener --refresh --max-names 500`
  (or a thin `systems/idea-sourcing` maintenance script). On a cold cache, the first
  idea-sourcing run should trigger a bounded warm and report partial coverage rather
  than silently returning few names.
- Schedule it (nightly is plenty for mcap/SIC). In a Cowork deployment this is a
  scheduled task; standalone, it's cron. Document both.

### A8. Acceptance tests — Part A

1. `python skills-library/.../universe-screener/run.py --sic-contains beverage
   --min-mcap 2e9 --max-mcap 2e10` returns genuine mid-cap names **beyond KO/PEP**.
2. `python systems/idea-sourcing/orchestrator.py --sic-contains software
   --min-mcap 2e9 --max-mcap 1e10 --max-candidates 6` returns mid-cap software
   names — not empty, not mega-caps.
3. New `tests/screener_snapshot_test.py`: seed a synthetic `company_metrics` table,
   assert a band filter returns the in-band set across the **full** universe and
   that `truncated` is `False` when the snapshot covers the universe.

---

## Part AB — Model-execution policy: deterministic vs qwen vs Claude

**Read this before Part B — it is the load-bearing decision the front-door pivot
forces.** The policy is a **three-rung model ladder**: the simplest, high-volume work
runs on local qwen (free, private); basic judgment on Claude Sonnet; the hardest,
client-facing judgment on Claude Opus. The rung is chosen **per task**, declared in
each `systems/<name>/router-policy.yaml` and executed by `_shared/router/imrouter`.
The good news: the engine already takes a per-call model, so this is a lookup change,
not new plumbing.

### AB1. How routing works today (confirmed in `imrouter/engine.py`)

`route(prompt, task=...)` looks up `routes[task]` in the system's policy → `local`
or `claude`:

- **`local`** → qwen3.5:9b via `ollama_client` (free, on-box).
- **`claude`** → the **Max-plan Claude Code CLI** (`claude -p` print mode) via
  `claude_client`. It deliberately **refuses `ANTHROPIC_API_KEY`** to keep auth on
  the subscription, not the metered API.
- Fallbacks: `allow_local_fallback` (no Claude → qwen so it still runs keyless),
  `allow_claude_fallback` (Ollama down → Claude), `IM_ALLOW_DEGRADED=1` (let qwen
  stand in for a Claude step). Every decision is logged to `IM_ROUTER_LOG`
  (`router_decisions.jsonl`) with `_source` (`ollama`/`api`) and `_route`.

The task taxonomy is consistent across all 7 systems:

| Task | Today's executor |
|---|---|
| `classification`, `extraction`, `screening`, `summarization` | **local qwen** (high-volume, mechanical) |
| `synthesis`, `reasoning`, `drafting`, `judgment` | **Claude** (the judged work) |

### AB2. The target policy — a three-rung model ladder by task complexity

Replace the binary `local`/`claude` split with an explicit ladder. Cowork's Claude
stays the **front door** (intent routing + presentation); each in-system step then
runs on the cheapest rung that does the job:

| Rung | Use for | Executor | Reached via |
|---|---|---|---|
| 0 | **All figures** — DCF, comps, market-cap band, ADV, returns, KPI thresholds | **Deterministic Python** | the skills; never a prompt |
| 1 — *simplest* | High-volume mechanical text steps: `classification`, `extraction`, `screening`, `summarization` | **qwen3.5:9b (local)** | `ollama_client` |
| 2 — *basic* | Bounded, single-system judgment: ranking a screen, light reasoning, structured synthesis that feeds something else | **Claude Sonnet** | `claude -p --model sonnet` |
| 3 — *advanced* | Hardest / client-facing judgment: IC memos & letters, the multi-lens filing Brief, moat/competitive reasoning, cross-system reconciliation | **Claude Opus** | `claude -p --model opus` |

Above all of it, **Cowork's Claude** does intent routing, entity extraction, and
final presentation — it is not a rung the systems pick; it's the orchestrator that
picks the *skill*. The rungs are what each skill picks *internally, per step*.

### AB3. Task → rung map (default in the engine, overridable per system)

The rung is declared per task, and each system already has its own
`router-policy.yaml`, so the granularity you need already exists: a default ladder
in the engine, overridden per system where a task is unusually hard or easy.

**Engine default** (`DEFAULT_POLICY` in `imrouter/engine.py`):

```yaml
classification: qwen
extraction:     qwen
screening:      qwen
summarization:  qwen
synthesis:      sonnet     # basic judgment by default
reasoning:      sonnet
drafting:       opus       # client-facing prose
judgment:       opus
```

**Per-system overrides** (set these in `systems/<name>/router-policy.yaml`):

- `reporting` → `drafting: opus` (IC memo / investor letter — final, client-facing).
- `filing-intelligence` → `synthesis: opus` (the Brief reconciles three lenses),
  `reasoning: opus` (competitive read).
- `due-diligence` → `reasoning: opus`.
- `idea-sourcing` → `synthesis: sonnet` (ranking a dossier is bounded; let the
  confidence guard in AB5 promote the hard/close ones to opus).
- `valuation`, `portfolio-monitoring`, `governance-audit` → narrative steps
  `synthesis`/`reasoning: sonnet` (the numbers are already deterministic).

Keep back-compat: the engine should read legacy values `local`→`qwen` and
`claude`→`opus`, so any unconverted policy file behaves exactly as today.

### AB4. Engine implementation — small, because the plumbing already exists

`engine.py::route()` **already accepts `model=`** and forwards it to
`claude_client.complete(model=...)`, and `claude_client` **already passes
`--model`**, which accepts the `sonnet`/`opus` aliases on the Max plan. So the change
is mostly a lookup, not new transport:

1. Add a ladder map and resolve the rung → (transport, model):
   ```python
   LADDER = {
       "qwen":   ("local",  os.environ.get("OLLAMA_MODEL",  "qwen3.5:9b")),
       "sonnet": ("claude", os.environ.get("SONNET_MODEL",  "claude-sonnet-4-6")),
       "opus":   ("claude", os.environ.get("OPUS_MODEL",    "claude-opus-4-8")),
   }
   _ALIAS = {"local": "qwen", "claude": "opus"}   # back-compat
   ```
   Resolve `rung = _ALIAS.get(routes[task], routes[task])`, then dispatch by
   `LADDER[rung]` — `ollama_client` for `local`, else `claude_client.complete(...,
   model=LADDER[rung][1])`. The model ids are env-overridable so a client can swap
   them without touching code.
2. Make `HIGH_JUDGMENT` mean "the opus rung" — that's the set that fails loud
   (`_needs_model`) when no Claude session exists, rather than silently degrading.
3. Log the resolved `rung` and `_model` to `router_decisions.jsonl` (the log already
   carries `_model`; just record the rung name beside it).

Auth is unchanged: both Claude rungs go through the **Max-plan `claude -p` CLI**, and
`claude_client` still strips `ANTHROPIC_API_KEY` so nothing silently bills the
metered API. Sonnet and Opus are both on the subscription.

### AB5. Dynamic escalation — promote a step one rung, on a deterministic guard

Most steps stay on their static rung. Two cases genuinely need per-input escalation;
implement both as **deterministic Python guards inside the engine** (never let a
model decide to call a bigger model), so all seven systems inherit them for free:

- **Length guard (pre-call).** Estimate input tokens (a `len(text)//4` proxy is
  fine). If a `qwen` step exceeds `QWEN_MAX_TOKENS` (start ~24k) → promote to
  `sonnet`; if a `sonnet` step exceeds `SONNET_MAX_TOKENS` (start ~150k) → promote to
  `opus`. This is what catches a full 10-K or a long earnings transcript whose
  "summarize" step is nominally cheap but too big for the small model.
- **Confidence / validity guard (post-call).** If the result fails schema parsing,
  comes back empty, or carries a low self-reported confidence, retry **once, one rung
  up** (`qwen→sonnet→opus`). You already do a primitive version of this —
  `allow_claude_fallback` and idea-sourcing's second `synthesize` attempt — so
  generalize it into the engine instead of per-orchestrator.

Both guards **cap at opus**, escalate **one rung at a time**, and log every promotion
with its trigger (`reason: length|low_confidence|invalid_schema`) so escalations are
auditable and you can tune the thresholds from real logs. Thresholds are env-tunable.

### AB6. Reconciling the ladder with the Cowork runtime

Where the Claude rungs actually execute depends on where the skill runs — keep the
`IM_RUNTIME` switch to handle both:

- **`IM_RUNTIME=standalone` (default).** The full ladder runs in-process: qwen via
  Ollama, Sonnet/Opus via `claude -p --model`. This is the headless product a client
  runs on their own box — full, precise control of which rung each step uses.
- **`IM_RUNTIME=cowork`.** qwen steps still run in-process if `OLLAMA_HOST` reaches a
  running Ollama. For the Claude rungs: if the `claude` CLI + subscription auth is
  reachable from the skill's environment, **run the ladder unchanged** (preferred —
  preserves the Sonnet-vs-Opus distinction). If it is *not* reachable, fall back to
  an **`external`/defer** route — the engine returns the step's structured inputs and
  **Cowork's Claude** performs it. Note the one limitation honestly: a single Cowork
  turn runs one model, so under defer the Sonnet/Opus distinction collapses to
  whatever Cowork is on; the engine still records the *intended* rung so you can see
  what it would have used.

`OLLAMA_HOST` must point at a running Ollama from wherever skills execute. Never set
`ANTHROPIC_API_KEY` in-process. Document in each `SKILL.md` that the orchestrator
returns deterministic + qwen-summarized JSON and which steps run on Sonnet vs Opus.

### AB7. Make the ladder verifiable (acceptance)

The router logs every decision, so the policy is testable, not assumed. Over a
representative run assert: mechanical steps log `rung=qwen` (`_source=ollama`);
basic-judgment steps log `rung=sonnet`; client-facing/advanced steps log
`rung=opus`; and every escalation carries a logged `reason`. Add this as a check in
`tests/routing_eval` so a regression (e.g. a step silently sitting on Opus when it
should be qwen, burning money) is caught.

---

## Part B — Claude Cowork as the natural-language front door

### B1. The reframe

Stop maintaining a hand-rolled NL router. `ask.py` (860 lines) fails because *intent
routing* and *entity extraction* are heuristics: `heuristic_system()` keyword
scoring, `extract_tickers()` alias maps + title-prefix matching + uppercase scans,
a `_STOP` word list, plus a 9B-qwen fallback for vague prompts. Novel phrasing,
multi-intent, and ticker/word collisions all break it.

The fix is **not** a better classifier — it's to stop hand-rolling the router. The
`sdk-front-door/` scaffold already proved the principle (move routing onto a
model). Cowork takes it one step further: **Cowork's own Claude is the
orchestrator-model front door.** No gateway, no LiteLLM, no billing plumbing, no
classifier to maintain. You package the systems as Cowork skills; the user just
talks to Cowork.

- **Keep:** deterministic numbers in code — each skill's script is your existing
  orchestrator. JSON outputs remain ground truth.
- **Retire:** `ask.py`'s keyword routing + regex extraction as the primary path, and
  the SDK gateway stack as the *primary* interface (it can survive as an optional
  headless API for clients who want to embed a CLI — see B6).

### B2. Architecture mapping — repo → Cowork plugin

A Cowork plugin is:

```
tensh-investment/
├── .claude-plugin/
│   └── plugin.json              # manifest (name, version, description, author)
├── skills/
│   ├── valuation/SKILL.md
│   ├── idea-sourcing/SKILL.md
│   ├── portfolio-monitoring/SKILL.md
│   ├── filing-intelligence/SKILL.md
│   ├── reporting/SKILL.md
│   ├── due-diligence/SKILL.md
│   ├── governance-audit/SKILL.md
│   └── universe-lookup/SKILL.md  # the one piece of ask.py worth keeping (see B4)
├── lib/imdata/                   # the shared spine, bundled ONCE
└── README.md
```

The mapping is nearly 1:1 with what exists. Your **leaf skills already are Cowork
skills** (`SKILL.md` + `run.py`). Each **system** becomes a "system skill" whose
script is the existing `systems/<name>/orchestrator.py`. The shared `imdata`
library is bundled once at the plugin root and put on `sys.path` by each skill —
**do not duplicate it per skill** (same principle as today's `skills-library`).
Use `${CLAUDE_PLUGIN_ROOT}` for all intra-plugin paths; never hardcode absolutes.

### B3. Why routing becomes robust "for free"

Cowork's Claude selects a skill by reading its `SKILL.md` **description** — the same
mechanism that already routes reliably. So routing quality is now a function of
**description quality**, not regex coverage. This is the main engineering task of
Part B: write rich, disambiguating descriptions.

Each system skill's description must include: a one-line purpose, explicit **trigger
phrases**, 3–5 **example utterances**, and a **"use when / do NOT use when"** clause
to separate overlapping systems (valuation vs. idea-sourcing vs. filing-intelligence
all touch a single ticker). Mirror the style of the bundled leaf skills' frontmatter.
Example for `idea-sourcing`:

```yaml
description: >
  Screen and rank a shortlist of names from a mandate (sector, size band, theme,
  or a ticker list). Use when the user wants to FIND or DISCOVER names — "find
  mid-cap beverage companies", "screen large-cap software", "give me some EV
  ideas", "what mid-caps look cheap in healthcare". Do NOT use when the user names
  ONE company and asks what it's worth (that's valuation) or what changed in its
  filing (that's filing-intelligence).
```

### B4. Skill-ification steps (per system)

For each of the 7 systems:

1. Create `skills/<system>/SKILL.md` with the rich description (B3) and a **Run**
   section that invokes the orchestrator, e.g.
   `python ${CLAUDE_PLUGIN_ROOT}/skills/<system>/orchestrator.py <flags>`, with
   **`IM_RUNTIME=cowork`** in the run environment (see Part AB — this runs the
   qwen/Sonnet/Opus ladder, deferring the Claude rungs to Cowork's Claude only when
   the `claude` CLI isn't reachable from the skill's environment).
   Keep the orchestrator as-is (deterministic fan-out preserved).
2. **Entity extraction moves to the model.** Cowork's Claude reads tickers, weights,
   sector, size band, and form from natural language and passes them as the
   orchestrator's existing CLI flags — replacing `extract_tickers` /
   `extract_positions` / `extract_mcap`. Document the flag contract in each
   `SKILL.md` so the model knows exactly what to pass (reuse the flag list each
   orchestrator's `argparse` already defines).
3. **Keep the one valuable deterministic piece of `ask.py`: universe validation.**
   The model can hallucinate a ticker; the universe can't. Create a tiny
   `skills/universe-lookup` skill wrapping `store.company_by_ticker` and
   `match_company_name` (move those two functions from `ask.py` into `imdata` so
   they're reusable and tested). Its `SKILL.md` tells the orchestrator to resolve /
   confirm a symbol before calling a system skill when the entity is ambiguous.
4. **Presentation.** `ask.py::render()` (formatting JSON → readable text) is no
   longer needed for display — Cowork's Claude reads the orchestrator's JSON and
   presents it, and can render `.docx`/`.pdf` via those skills. **Keep the
   orchestrators emitting structured JSON** (ground truth). Optionally fold the
   nice table layouts from `render()` into each `SKILL.md` as presentation guidance.

### B5. `plugin.json` + packaging

- Write `.claude-plugin/plugin.json`: `name` (kebab-case, e.g. `tensh-investment`),
  `version` (`0.1.0`), `description`, `author`.
- Respect `IM_COMMERCIAL_MODE`: in a resellable build, public-tier sources only and
  the Part-A `FinvizProvider` **off**.
- If this is distributed to clients outside the org, mark external tool dependencies
  generically and add a `CONNECTORS.md` (the Cowork plugin convention). Otherwise
  skip that.
- Package as a `.plugin` bundle for install. (The `create-cowork-plugin` /
  `cowork-plugin-customizer` skills encode the exact packaging + manifest
  conventions — follow them rather than improvising the archive format.)

### B6. Retire / relegate the old front doors

- **`ask.py`:** strip the keyword classifier as the primary NL path. Keep only the
  short-form deterministic dispatch (`ask.py valuation --ticker MSFT ...`) for
  offline/scripted use, clearly marked secondary. **Before deleting anything, move
  the reusable validated extractors** (`extract_positions`, `match_company_name`,
  ticker validation) **into `imdata`** so the `universe-lookup` skill reuses them —
  don't lose that logic.
- **`sdk-front-door/`:** **removed.** Cowork is the sole front door; there is no
  programmatic embed path. The SDK scaffold (LiteLLM gateway + `front_door.py`
  orchestrator + `system_tools.py` tool wrappers) solved the same model-based-routing
  problem Cowork now solves, so it was redundant as an interface and carried its own
  gateway/billing plumbing to maintain. Nothing in the deterministic core depended on
  it. If a headless, embeddable endpoint (client-brings-own-API-key) is ever needed,
  reconstruct it from each orchestrator's argparse contract — the systems and `imdata`
  spine already stand alone.

### B7. Acceptance tests — Part B

1. **Routing eval.** Build `tests/routing_eval.jsonl` with 30–50 NL prompts → the
   expected system, weighted toward the cases that broke `ask.py`: size screens
   ("find mid-cap beverage names"), multi-intent ("value MSFT and check my book"),
   and novel phrasing. Since routing is now model-side, evaluate by issuing each
   prompt to Cowork and checking which skill fired (or use the `skill-creator` eval
   harness for description-triggering accuracy).
2. **End-to-end smoke.** From a natural prompt, each system skill runs and returns
   **real numbers, no fabrication**: "what's MSFT worth vs AAPL and GOOGL",
   "find mid-cap beverage names" (exercises Part A), "is my book ok — NVDA 30%,
   MSFT 20%, AAPL 15%, cap 10%", "what changed in KO's latest 10-K",
   "write an IC memo for NVDA".

---

## Part C — Guardrails & definition of done

**Guardrails (non-negotiable):**

- Never move a calculation out of Python into a prompt. Models route, extract, and
  narrate; they do not compute figures.
- Every new outbound call routes through `imdata` + the `http_cache` TTL. No fetcher
  is ever duplicated into a system or skill (decision rule in `DATA-SOURCE-MAP.md`).
- Orchestrators keep emitting structured JSON as the single source of truth.
- Honor `IM_COMMERCIAL_MODE` for source gating in anything shippable.
- Honor the **model ladder (Part AB)**: figures → Python, simplest → qwen, basic →
  Sonnet, advanced → Opus, with Cowork's Claude routing + presenting. Never let a
  cheap step sit on Opus (burning money) or a client-facing step drop to qwen.

**Definition of done:**

- [ ] `company_metrics` table + store helpers + `TTL_METRICS` added.
- [ ] `imdata/screener.py` with the three providers; default keyless path works with
      no key and no commercial-unsafe source.
- [ ] `universe-screener` filters mid-cap bands across the full universe; the
      `base[:max_fetch]` top-down truncation no longer gates size mandates.
- [ ] `--max-fetch 160` hack removed from the idea-sourcing orchestrator.
- [ ] Part-A acceptance tests pass (mid-cap beverage + mid-cap software return names).
- [ ] `imrouter` resolves the `qwen`/`sonnet`/`opus` ladder (with `local`/`claude`
      back-compat), reusing the existing `model=` + `--model` path; legacy policies
      behave unchanged.
- [ ] Length + confidence escalation guards live in the engine, cap at opus,
      promote one rung, and log a `reason`.
- [ ] `IM_RUNTIME` switch handles standalone (full ladder in-process) vs cowork
      (defer Claude rungs when the CLI/auth isn't reachable).
- [ ] Router log shows the expected rung per task (qwen / sonnet / opus) and a
      logged reason on every escalation (Part AB acceptance).
- [ ] 7 system skills + `universe-lookup` skill with rich descriptions; `imdata`
      bundled once; `plugin.json` valid.
- [ ] Reusable `ask.py` extractors moved into `imdata`; keyword classifier demoted.
- [ ] Routing eval + end-to-end smoke pass, including the prompts that previously
      failed.
```
