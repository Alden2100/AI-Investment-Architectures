# idea-sourcing

Mandate → ranked shortlist. Screens the investable universe, enriches each
candidate, and ranks the dossier into names worth deeper work.

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

## Manifest
7 skills (universe-screener, fundamentals-fetcher, catalyst-flagger, news-fetcher,
dcf-valuation, comps-builder, web-search) + agent `screening-analyst`. See
`manifest.yaml`.

## Test
```bash
python tests/smoke_test.py
```
