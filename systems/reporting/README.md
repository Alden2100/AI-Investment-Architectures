# reporting

Committee-ready deliverables: an **IC memo** for one name, or a periodic
**investor/LP letter** for the fund.

## Pipeline
```
# memo:
ticker ─▶ dcf-valuation · comps-builder · moat-analyzer · fundamentals-fetcher  (deterministic)
       ─▶ memo-writer [router: drafting] → 6-section IC memo                    (model)
# letter:
period+perf+holdings ─▶ letter-drafter [router: drafting] → investor letter     (model)
       ─▶ audit + write output JSON
```
The drafting skills compose from the exact numbers gathered — they never invent
figures.

## Run
```bash
python ../../link.py reporting
python orchestrator.py --memo MSFT
python orchestrator.py --letter "Q2 2026" --performance "fund=+4.2%,bench=+2.1%" \
    --holdings MSFT=0.20 AAPL=0.15 NVDA=0.10
```
Flags: `--memo TICKER` **or** `--letter PERIOD` (+ `--performance`, `--holdings`).
Output: `data/output/reporting-*.json`.

## Routing
Upstream summarization → qwen; the **drafting** of the memo/letter (highest-judgment,
client-facing) → **Claude** (qwen fallback still yields a usable draft keyless).

## Manifest
8 skills (memo-writer, letter-drafter, dcf-valuation, comps-builder, moat-analyzer,
fundamentals-fetcher, deck-updater, audit-logger) + agent `report-writer`.

## Test
```bash
python tests/smoke_test.py     # drafts an MSFT IC memo end-to-end
```
