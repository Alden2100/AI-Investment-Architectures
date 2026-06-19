# filing-intelligence

One SEC filing → a **Filing Intelligence Brief** (What changed → Why it matters →
What to watch).

## Pipeline
```
ticker+form ─▶ filing-fetcher (text + excerpt)                  (deterministic)
            ─▶ filing-change-detector (diff vs prior period)
            ─▶ moat-analyzer (margins) + news-fetcher (context)
            ─▶ [router: synthesis] write the Brief                (model)
            ─▶ audit + write output JSON
```
The diff and margins are computed; the model judges significance and writes prose.

## Run
```bash
python ../../link.py filing-intelligence
python orchestrator.py --ticker KO --form 10-K
python orchestrator.py --ticker MSFT --form 10-Q
```
Flags: `--ticker` (required), `--form` (default `10-K`). Output:
`data/output/filing-intelligence-*.json`.

## Routing
filing/earnings summarization → **qwen** (high volume, cheap); the multi-lens Brief
**synthesis** and competitive reasoning → **Claude** (qwen fallback when keyless).

## Manifest
7 skills (filing-fetcher, filing-change-detector, filing-summarizer,
earnings-call-summarizer, moat-analyzer, news-fetcher, web-search) + agent
`filing-analyst`.

## Test
```bash
python tests/smoke_test.py     # KO 10-K, end-to-end
```
