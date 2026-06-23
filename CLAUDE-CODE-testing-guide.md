# Testing guide — how to test the system as you build

**Audience:** you + Claude Code, working in `AI Investment Architectures/`.
**Companion to:** `CLAUDE-CODE-frontend-and-screener-guide.md` (what to build).
This is the loop for *proving it works* while you build it.

## 0. Five principles, tailored to this repo

1. **Test in layers that mirror the architecture.** Most of the value is at the
   bottom (the numbers), least at the top (the narrative). Don't test a memo's prose;
   test that the figures inside it are exact.
2. **Hard vs. soft assertions** — the split your `tests/data_sources_test.py` already
   uses. Deterministic logic (a band filter, a registry, a comps median) is **hard**:
   it must pass. A live-network fetch is **soft**: `None` is acceptable on a transient
   failure, so upstream flakiness never fails your build.
3. **Keep models out of the fast loop.** Every number must be testable with **no
   model and no live network**. Run the bulk of your tests keyless/offline on qwen or
   no-model; exercise the paid Sonnet/Opus rungs rarely (pre-release). This is both
   cost discipline and reproducibility.
4. **Isolate every test's cache.** Point `TOOLBOX_DB_PATH` and `TOOLBOX_CACHE_DIR` at
   a tempdir (the `data_sources_test.py` pattern) so a test never pollutes your dev
   cache or another test.
5. **Make the model policy assertable, not eyeballed.** The qwen/Sonnet/Opus ladder is
   verified by reading `router_decisions.jsonl`, not by watching output scroll by.

---

## 1. The test pyramid (six layers)

### Layer 1 — Deterministic core (the math). *Most of your tests live here.*

Run a skill directly and assert the numbers and shape:

```bash
.venv/bin/python skills-library/research/universe-screener/run.py \
    --sic-contains beverage --min-mcap 2e9 --max-mcap 2e10
```

Add pytest-style unit tests for the pure functions (market-cap band filter, ADV,
comps median, DCF) on a **seeded cache** (see §3) — no model, no network. For the
Part A screener fix specifically: seed a synthetic `company_metrics` table, then
assert the band filter returns the in-band names across the **full** universe and
that `truncated == False` when the snapshot covers it. This is the regression test
that locks the mid-cap bug shut.

### Layer 2 — Skill contract.

For each leaf skill: given known args, the `run.py` returns JSON with the documented
keys, correct types, and no nulls where a value is required. A tiny per-skill schema
assertion catches a broken contract before any orchestrator consumes it.

### Layer 3 — System orchestrators (smoke).

Your existing pattern (`systems/<name>/tests/smoke_test.py`): subprocess the
orchestrator on a fixed mandate and assert the **structural** fields, e.g.

```python
proc = subprocess.run([sys.executable, ORCH, "--ticker", "KO", "--form", "10-K"], ...)
d = json.loads(proc.stdout)
assert d["system"] == "filing-intelligence"
assert d.get("filing", {}).get("accession"), "no filing retrieved"
```

`tests/run_smoke_tests.py` runs these end-to-end, keyless, with `IM_ALLOW_DEGRADED=1`
so qwen narrates the high-judgment steps. **Extend `FULL`** to add `due-diligence`
and `governance-audit` once they're past scaffold, so all seven are covered.

### Layer 4 — The model ladder (qwen / Sonnet / Opus). *Assert via the router log.*

Point the log at a temp file, run a system, parse the decisions, assert each task hit
its expected rung:

```python
env = {**os.environ, "IM_ROUTER_LOG": logpath, "TOOLBOX_DB_PATH": tmpdb}
subprocess.run([sys.executable, ORCH, "--ticker-in", "MSFT", ...], env=env)
rows = [json.loads(l) for l in open(logpath)]
by_task = {r["task"]: r for r in rows}
assert by_task["summarization"]["rung"] == "qwen"      # simplest stays cheap
assert by_task["drafting"]["rung"]       == "opus"      # client-facing stays strong
# Cost guard — nothing cheap silently sits on a paid rung:
assert all(r["rung"] == "qwen" for r in rows if r["task"] in
           {"classification","extraction","screening","summarization"})
```

**Fallback matrix** — stub `ollama_client.available()` and `claude_client.available()`
to cover the four states (ollama up/down × Claude up/down) and assert the engine
promotes/demotes/`needs_model` correctly. **Escalation guards** — feed an oversized
input and assert a logged `reason: length` promotion; feed a schema-breaking case and
assert a one-rung retry. (See AB4–AB5 of the build guide.)

### Layer 5 — NL routing (the front door). *This is what was failing — test it explicitly.*

Build `tests/routing_eval.jsonl`: 30–50 natural prompts → expected system, weighted
toward the breakers that motivated the rebuild —

```json
{"prompt": "find mid-cap beverage names", "expect": "idea-sourcing"}
{"prompt": "value MSFT and check my book — NVDA 30%, MSFT 20%", "expect": ["valuation","portfolio-monitoring"]}
{"prompt": "what's different in KO's new 10-K", "expect": "filing-intelligence"}
```

Because Cowork's Claude routes by skill **description**, evaluate by issuing each
prompt and checking which skill fired (or use the `skill-creator` eval harness for
description-triggering accuracy). Track accuracy as a number; a drop is a failing
test. Re-run this whenever you edit a `SKILL.md` description.

### Layer 6 — Cowork integration (the live loop). *Manual, with a checklist.*

Load from your repo **without installing** (no repackage per change):

- Claude Code: `--plugin-dir <repo>` to load straight from the folder, or keep it in
  your skills directory to auto-load each session; run `/reload-plugins` after edits.
- Then run the canonical prompts and verify routing + exact numbers + presentation:
  "what's MSFT worth vs AAPL and GOOGL", "find mid-cap beverage names" (exercises
  Part A), "is my book ok — NVDA 30%, MSFT 20%, AAPL 15%, cap 10%", "write an IC memo
  for NVDA".

---

## 2. The env switches that set test mode

| Env var | Effect | Use it to… |
|---|---|---|
| `IM_ALLOW_DEGRADED=1` | qwen stands in for a Claude rung | run the full pipeline keyless/free |
| `IM_DISABLE_CLAUDE=1` | force "no Claude session" | test fail-loud + fallback paths |
| `IM_ROUTER_LOG=<tmp>` | capture every routing decision | assert the ladder (Layer 4) |
| `TOOLBOX_DB_PATH` / `TOOLBOX_CACHE_DIR=<tmp>` | isolated cache/DB | offline, non-polluting tests |
| `IM_RUNTIME=standalone\|cowork` | execution mode | test both ladder-in-process and defer |
| `OLLAMA_HOST` (unreachable) | simulate qwen down | test promote-to-Sonnet fallback |
| `CLAUDE_MODEL` / `SONNET_MODEL` / `OPUS_MODEL` | pin rung model ids | point rungs at test/cheaper models |
| `IM_COMMERCIAL_MODE=1` | public-tier sources only | test the resale source gate |

---

## 3. Offline determinism — the cache fixture

Your data layer caches every GET in the SQLite `http_cache` with a TTL. Exploit that
for tests:

- Commit a small **fixture cache** (`tests/fixtures/cache.db`) covering a handful of
  tickers — a couple of mega-caps (MSFT, AAPL), a stable name (KO), and **one or two
  mid-caps** so the Part A path is exercised. Copy it to a tempdir per test and point
  `TOOLBOX_DB_PATH` at the copy. Now Layer 1–4 tests run **offline, fast, and
  identical every time** — no SEC rate limits, no Yahoo flakiness.
- Keep one **live** test that actually hits the network with **soft** asserts, to
  catch upstream API drift (a tag renamed, an endpoint moved). Run it occasionally,
  not on every change.

This is the single highest-leverage testing investment: it turns "did the network
cooperate today" into a deterministic, free, second-long loop.

---

## 4. What to run, when

| Trigger | Run | Cost / speed |
|---|---|---|
| **Every code change** | `link.py --check`; Layer 1–2 unit tests on the seeded cache (no model) | seconds, free |
| **Before commit** | `.venv/bin/python tests/run_smoke_tests.py` (keyless, degraded) + Layer 4 ladder-log assertions | ~minutes, free |
| **Before a release / ship to clients** | live-network soft tests; the **real** Sonnet/Opus rungs on a few prompts (`claude login`); Layer 5 routing eval; the packaging build | slower, paid |

`link.py --check` is your cheapest gate — it validates every system's manifest
against the library (catches a renamed/removed skill) before any test runs.

---

## 5. Starter commands (copy/paste)

```bash
# 0. validate manifests (no network, no model)
.venv/bin/python link.py --check

# 1. one skill, deterministic
.venv/bin/python skills-library/research/universe-screener/run.py \
    --sic-contains software --min-mcap 2e9 --max-mcap 1e10

# 2. one system, keyless end-to-end (qwen narrates)
IM_ALLOW_DEGRADED=1 .venv/bin/python systems/idea-sourcing/orchestrator.py \
    --sic-contains beverage --min-mcap 2e9 --max-mcap 2e10 --max-candidates 6

# 3. all systems, smoke
.venv/bin/python tests/run_smoke_tests.py

# 4. inspect the ladder after a run
IM_ROUTER_LOG=/tmp/rt.jsonl IM_ALLOW_DEGRADED=1 \
    .venv/bin/python systems/idea-sourcing/orchestrator.py --ticker-in MSFT AAPL
cat /tmp/rt.jsonl | python -m json.tool
```

---

## 6. Definition of "tested" — by what you changed

- **A number / a skill** → Layer 1–2 on the seeded cache + the affected system's smoke test.
- **The screener / snapshot (Part A)** → the synthetic-`company_metrics` band test (`truncated == False`) + a mid-cap mandate returning names.
- **The router engine / a `router-policy.yaml`** → Layer 4 ladder-log assertions + the four-state fallback matrix + the two escalation guards.
- **A `SKILL.md` description** → re-run the Layer 5 routing eval; accuracy must not drop.
- **Packaging / a release** → Layer 6 live loop + the build that materializes real files (no symlinks) and installs clean.

The through-line: the deterministic core is tested constantly, offline, and free; the
paid models are exercised deliberately and rarely; and the model policy is proven by
the log, not by inspection.
