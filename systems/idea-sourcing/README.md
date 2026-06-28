# idea-sourcing

Mandate → ranked shortlist. Screens the investable universe, enriches each
candidate, and ranks the dossier into names worth deeper work.

> **Agent contract (read before driving this system).** RUN the orchestrator as a
> subprocess and relay its JSON. It routes its own model calls **per task** —
> catalyst tagging on qwen, ranking on Sonnet, escalating to Opus on low-confidence —
> and reports the mix in `model_routing`. Do **not** screen, rank, or write theses
> yourself: doing the judgment in the driving model collapses the qwen→sonnet→opus
> ladder to a single model (and silently pays Opus for cheap steps). If `model_routing`
> shows one model for everything, the ladder didn't engage — you judged inline.
> (The qwen rung needs a local Ollama; without it, cheap tasks fall back to Sonnet,
> logged with `reason: local_unavailable`.)

## Pipeline
```
mandate ─▶ universe-screener ─▶ fundamentals-fetcher        (deterministic fan-out)
            └▶ per candidate: catalyst-flagger · news-fetcher · dcf-valuation · comps-builder
        ─▶ [router: synthesis] rank into shortlist + 1-line thesis + verdict   (model)
        ─▶ audit + write output JSON
```
Every number is computed by a skill; the model only ranks and writes the thesis.

## Run
```bash
python ../../link.py idea-sourcing          # once, to materialize skills
python orchestrator.py --ticker-in MSFT AAPL NVDA --max-candidates 3
python orchestrator.py --sic-contains 7372 --min-mcap 1e10 --max-candidates 6   # software, >$10B
```
Flags: `--ticker-in`, `--name-contains`, `--sic-contains`, `--min-mcap`,
`--max-mcap`, `--max-candidates`. Output: `data/output/idea-sourcing-*.json`.

## Routing (router-policy.yaml)
screening / classification / summarization → **qwen3.5:9b** (local, free); the
ranking **synthesis** → **Claude** (falls back to qwen when no API key, so it runs
keyless).

### Speed profile (reversible)
The current profile favors wall-clock while keeping all three models in use
(qwen + Sonnet + Opus): `debate_generate` is based at **sonnet** (it escalated
>50% of the time on qwen, so basing it higher halves the calls), `QWEN_MAX_TOKENS`
defaults to **32000** (fewer length-guard escalations), and per-company fan-out runs
**`IM_MAX_WORKERS=8`**. To revert to the token-thrifty profile: set
`debate_generate: qwen` in `router-policy.yaml`, `QWEN_MAX_TOKENS=24000`, and
`IM_MAX_WORKERS=6` (see `.env.example`).

## Manifest
7 skills (universe-screener, fundamentals-fetcher, catalyst-flagger, news-fetcher,
dcf-valuation, comps-builder, web-search) + agent `screening-analyst`. See
`manifest.yaml`.

## Test
```bash
python tests/smoke_test.py
```
