# Build-phase guide — get the system to a better spot

**Audience:** Claude Code, working in this repo (`AI Investment Architectures/`).
**Goal:** improve the *running system* so development can continue from a stronger
base. This is **not** the productization pass — anything that exists only to ship a
sellable plugin to clients is **explicitly out of scope** (see "Deferred" below).
**Author intent:** root causes are already traced through the code. Implement against
them; do not re-diagnose.

## Scope

**In scope (do these now):**
1. Fix the mid-cap sourcing bug (the screener traversal). *Part 1.*
2. Implement the qwen → Sonnet → Opus model ladder, running in-process. *Part 2.*
3. Refactor the brittle front-end logic: lift the reusable, validated pieces out of
   `ask.py` into `imdata`; demote the keyword classifier. *Part 3.*

**Deferred (do NOT build now — these are for the eventual product):**
- Packaging into a distributable Cowork `.plugin` (manifest for distribution, `.plugin`
  archive, bundling `imdata` for shipping, `${CLAUDE_PLUGIN_ROOT}` restructure,
  `CONNECTORS.md`).
- `IM_COMMERCIAL_MODE` source gating, the FMP/Finviz snapshot providers, "resellable
  build" concerns.
- The `IM_RUNTIME=cowork` defer-to-Cowork runtime and the standalone-vs-Cowork
  duality.
- Removing/rebuilding `sdk-front-door/` as a headless product endpoint. Leave it on
  disk; just stop treating it as the interface.

If a change starts to require any deferred item to proceed, stop and leave a TODO
rather than pulling the product work forward.

## Two invariants to preserve

1. **Code for what's exact, model for what's judged.** Every number is computed
   deterministically in Python. Models only route, extract entities, and narrate.
   Never move a calculation into a prompt.
2. **One shared fetch+cache spine.** All outbound calls funnel through
   `skills-library/_shared/data-fetch/imdata` and its SQLite `http_cache` (TTL'd). A
   fetcher used by ≥2 systems or foundational lives in `imdata` + the `sources.py`
   registry — never duplicated into a system.

**Sequencing: Part 1 first.** Until the screener can return mid-caps, everything
downstream of a size mandate looks broken regardless of other work.

---

## Part 1 — Fix mid-cap sourcing (size-aware universe)

### 1.1 Root cause (confirmed in code — do not re-litigate)

- The universe comes from SEC `company_tickers.json` (`imdata/universe.py`), ordered
  **roughly by market cap, descending**.
- `store.all_companies()` runs `SELECT * FROM companies` with **no `ORDER BY`**, so
  rows come back in insertion (≈ size) order.
- `universe-screener/run.py` truncates **before** the expensive filters run:
  ```python
  if wants_expensive and len(base) > args.max_fetch:
      base = base[: args.max_fetch]   # first N == the LARGEST names
  ```
- `systems/idea-sourcing/orchestrator.py::screen()` bumps `--max-fetch` to **160** for
  sector/size screens. Mid-caps sit far below rank 160, so they're never fetched; a
  `--max-mcap` ceiling then filters out 100% of those mega-caps → near-empty result.

It's a **traversal-direction** bug. Raising `max-fetch` to reach mid-caps means
thousands of per-name SEC+price fetches per screen (SEC ~10 req/s) — which is why the
cap exists.

### 1.2 The fix — precompute a size-aware snapshot, screen over the whole universe

Separate **slow-changing universe metadata** (market cap, SIC, ADV) from
**screen-time filtering** (must be instant). Cache the metadata via a bounded batch
job; then a screen is a filter over the snapshot across the **entire** universe — zero
per-name fetches at screen time, no truncation, no top-down bias.

### 1.3 Data model — new `company_metrics` table

In `imdata/store.py`, add a table **separate** from `companies` so metrics can be
refreshed without touching identity:

```sql
CREATE TABLE IF NOT EXISTS company_metrics (
    ticker          TEXT PRIMARY KEY,
    market_cap      REAL,
    sic             INTEGER,
    sic_description TEXT,
    adv             REAL,        -- avg daily $ volume
    last_px         REAL,
    currency        TEXT,
    source          TEXT,
    snapshot_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_metrics_mcap ON company_metrics(market_cap);
```

Add helpers next to the existing company helpers: `upsert_metrics(rows)`,
`metrics_for_tickers(tickers)`, `all_metrics()`, `metrics_count()`, and
`stale_tickers(ttl_seconds, limit)`. Add `TTL_METRICS` to `config.py` (7 days for
mcap/SIC is fine; ADV/last_px recompute cheaply from the existing `prices` cache).

### 1.4 Snapshot builder — new `imdata/screener.py` (keyless only, for now)

Shared module (foundational → belongs in `imdata`). Expose:

```python
def refresh_metrics(tickers=None, max_names=500) -> dict:
    """Populate/refresh company_metrics for the stalest `max_names` tickers.
    Bounded and resumable."""
```

Implement **one** provider now — the keyless `SecPriceProvider`: reuse exactly what
the screener computes per-name today — `edgar.get_concept(ticker, shares_tag)` ×
`prices.last_price(ticker)` → market cap; `prices.get_history` → ADV;
`edgar.company_meta` → SIC. The only change is *when* it runs: a bounded batch
refresher, not at screen time. It adds no new data exposure (SEC EDGAR + the same
`prices` feed every system already uses).

> Keep the function signature open to a `provider=` argument later, but **do not**
> build the FMP or Finviz providers or any commercial gating now — that's product
> work. A single keyless provider is enough to unblock mid-cap sourcing.

### 1.5 Screener changes — `universe-screener/run.py`

- Add `--use-snapshot` (**default on**). When expensive filters are requested and the
  snapshot covers the universe, filter market-cap band / SIC / ADV by reading
  `company_metrics` across **all** names — no `base[:max_fetch]`, no truncation.
- Keep the live-fetch path as the `--no-snapshot` fallback (cold cache) and as the
  per-name fallback for tickers missing from the snapshot (bounded by `max_fetch`).
- When size ordering is wanted, `ORDER BY market_cap DESC` **explicitly** — stop using
  insertion order as a size proxy.
- Keep the output JSON shape back-compatible; add a `snapshot_coverage` field.
  `truncated` should now only be true on the live fallback path.

### 1.6 Orchestrator cleanup

- `systems/idea-sourcing/orchestrator.py::screen()`: **remove the `--max-fetch 160`
  hack** and its comment. Pass the band straight through; rely on the snapshot.
- Leave `ask.py`'s size-band mapping (`extract_mcap`, `_size_to_band`) alone for now —
  it's correct; Part 3 handles the front end.

### 1.7 Warm the cache

- Add a CLI entry: `python -m imdata.screener --refresh --max-names 500`.
- On a cold cache, the first idea-sourcing run should trigger a bounded warm and
  report partial coverage rather than silently returning few names. (Scheduling the
  refresh is a deployment concern — skip it; a manual/CLI warm is enough for now.)

### 1.8 Acceptance — Part 1

1. `python skills-library/research/universe-screener/run.py --sic-contains beverage
   --min-mcap 2e9 --max-mcap 2e10` returns genuine mid-cap names **beyond KO/PEP**.
2. `python systems/idea-sourcing/orchestrator.py --sic-contains software
   --min-mcap 2e9 --max-mcap 1e10 --max-candidates 6` returns mid-cap software names —
   not empty, not mega-caps.
3. New `tests/screener_snapshot_test.py`: seed a synthetic `company_metrics` table;
   assert the band filter returns the in-band set across the **full** universe and that
   `truncated == False` when the snapshot covers it.

---

## Part 2 — The qwen → Sonnet → Opus model ladder (in-process)

Goal: stop sending everything to one model. Simplest, high-volume steps run on local
qwen (free); basic judgment on Sonnet; the hardest/client-facing judgment on Opus.
The rung is chosen **per task**. This runs **in-process** via the existing
`claude -p` CLI on your Max plan — no gateway, no runtime switch.

### 2.1 How routing works today (confirmed in `imrouter/engine.py`)

`route(prompt, task=...)` looks up `routes[task]` → `local` (qwen via `ollama_client`)
or `claude` (the Max-plan `claude -p` CLI via `claude_client`, which refuses
`ANTHROPIC_API_KEY` to stay on the subscription). It already accepts a `model=` arg and
forwards it; `claude_client` already passes `--model`, which takes `sonnet`/`opus`
aliases. Decisions log to `IM_ROUTER_LOG` (`router_decisions.jsonl`).

### 2.2 The ladder — a lookup change, not new plumbing

In `engine.py`:

```python
LADDER = {
    "qwen":   ("local",  os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")),
    "sonnet": ("claude", os.environ.get("SONNET_MODEL", "claude-sonnet-4-6")),
    "opus":   ("claude", os.environ.get("OPUS_MODEL",   "claude-opus-4-8")),
}
_ALIAS = {"local": "qwen", "claude": "opus"}   # back-compat: old policies still work
```

Resolve `rung = _ALIAS.get(routes[task], routes[task])`, dispatch by `LADDER[rung]`
(`ollama_client` for `local`, else `claude_client.complete(..., model=LADDER[rung][1])`).
Make `HIGH_JUDGMENT` mean "the opus rung" (the set that fails loud with `_needs_model`
when no Claude session exists). Log the resolved `rung` next to `_model`.

### 2.3 Task → rung map

**Engine default** (`DEFAULT_POLICY`):

```yaml
classification: qwen
extraction:     qwen
screening:      qwen
summarization:  qwen
synthesis:      sonnet
reasoning:      sonnet
drafting:       opus
judgment:       opus
```

**Per-system overrides** in `systems/<name>/router-policy.yaml`:
- `reporting` → `drafting: opus` (memo / letter).
- `filing-intelligence` → `synthesis: opus`, `reasoning: opus`.
- `due-diligence` → `reasoning: opus`.
- `idea-sourcing` → `synthesis: sonnet` (let the confidence guard promote hard ones).
- `valuation`, `portfolio-monitoring`, `governance-audit` → narrative steps `sonnet`.

### 2.4 Dynamic escalation — promote one rung on a deterministic guard

Implement both in the engine (never let a model decide to escalate), so all systems
inherit them:
- **Length guard (pre-call):** estimate tokens (`len(text)//4`). `qwen` over
  `QWEN_MAX_TOKENS` (~24k) → `sonnet`; `sonnet` over `SONNET_MAX_TOKENS` (~150k) →
  `opus`. Catches a full 10-K / long transcript whose "summarize" step is nominally
  cheap but too big for the small model.
- **Confidence/validity guard (post-call):** if the result fails schema parsing, is
  empty, or is low-confidence, retry **once, one rung up**. Generalize the existing
  `allow_claude_fallback` + idea-sourcing's second-attempt into the engine.

Both cap at opus, move one rung at a time, and log the trigger
(`reason: length|low_confidence|invalid_schema`).

### 2.5 Acceptance — Part 2

Run a system with `IM_ROUTER_LOG` set; parse the log and assert mechanical steps log
`rung=qwen`, basic-judgment `rung=sonnet`, client-facing `rung=opus`, and each
escalation carries a `reason`. Add a cost guard: no `classification/extraction/
screening/summarization` task ever logs a paid rung.

> Note: this assumes you run with `claude login` (Max plan) so the Claude rungs work.
> With no Claude session, opus-rung tasks fail loud (`_needs_model`) unless
> `IM_ALLOW_DEGRADED=1`, which lets qwen stand in for local testing.

---

## Part 3 — Front-end cleanup (lift the good parts out of `ask.py`)

Don't package anything. The aim here is just to stop depending on the brittle keyword
router and to make its one genuinely-valuable piece reusable.

### 3.1 Move the validated logic into `imdata`

`ask.py`'s entity *resolution against the real universe* is the part worth keeping (a
model can hallucinate a ticker; the universe can't). Move these into `imdata` (e.g.
`imdata/universe.py` or a small `imdata/entities.py`) so they're reusable and testable
on their own:
- `match_company_name` (name → ticker via universe titles),
- `extract_positions` (`TICKER=weight` parsing),
- the ticker-validation helper (`valid_ticker` / `store.company_by_ticker`).

Add a unit test covering a few resolutions (e.g. "Micron" → MU, "Coca-Cola" → KO) and
a couple of `_STOP`-word collisions.

### 3.2 Demote the keyword classifier

- Stop treating `ask.py`'s `heuristic_system()` keyword routing as the primary path.
  Keep the short-form deterministic dispatch (`ask.py valuation --ticker MSFT ...`) for
  scripted/offline runs; mark the natural-language keyword path clearly secondary
  (or behind a flag). Do not delete it until the replacement front end exists.
- Leave `sdk-front-door/` on disk untouched — just don't invest in it. (Removing it is
  product-cleanup, deferred.)

### 3.3 Optional — drive the systems through Cowork locally (no packaging)

If you want to start steering the systems by natural language during development, give
each `systems/<name>/` a `SKILL.md` with a rich, disambiguating description (purpose +
trigger phrases + example utterances + "use when / not when") and load them via the
local dev loop (`--plugin-dir` / skills directory, `/reload-plugins`) — **no `.plugin`
build, no manifest-for-distribution.** This is genuinely useful for testing routing,
but it's optional for this pass; the packaging itself stays deferred.

---

## Guardrails & build-phase definition of done

**Guardrails:**
- No calculation moves into a prompt; orchestrators keep emitting structured JSON as
  ground truth.
- Every new outbound call goes through `imdata` + the `http_cache` TTL; no duplicated
  fetchers.
- Honor the ladder: figures → Python, simplest → qwen, basic → Sonnet, advanced →
  Opus. Never let a cheap step sit on a paid rung.
- Don't pull deferred (product) work forward. Leave a TODO instead.

**Done when:**
- [ ] `company_metrics` table + helpers + `TTL_METRICS` added.
- [ ] `imdata/screener.py` with the keyless `SecPriceProvider`; refresh CLI works.
- [ ] `universe-screener` filters bands across the full universe; `base[:max_fetch]`
      truncation no longer gates size mandates; `--max-fetch 160` hack removed.
- [ ] Part 1 acceptance passes (mid-cap beverage + mid-cap software return names).
- [ ] `imrouter` resolves the `qwen`/`sonnet`/`opus` ladder with `local`/`claude`
      back-compat; legacy policies behave unchanged.
- [ ] Length + confidence escalation guards live in the engine, cap at opus, log a
      `reason`.
- [ ] Router log shows the expected rung per task; cost guard passes.
- [ ] `match_company_name` / `extract_positions` / ticker validation moved into
      `imdata` with a unit test; keyword classifier demoted (not deleted).
