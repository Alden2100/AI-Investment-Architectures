# valuation

Triangulate a company's value across a **DCF**, a **comps** table, and **bull/base/
bear scenarios**, then reconcile into a value range and a buy/hold/sell call.

## Pipeline
```
ticker ─▶ dcf-valuation · comps-builder (target off peer medians)   (deterministic)
       ─▶ scenario-analyzer (bull/base/bear) · fundamentals-fetcher
       ─▶ [router: reasoning] reconcile → {low, base, high} + recommendation  (model)
       ─▶ audit + write output JSON
```
Three independent value estimates, all computed in Python; the model reconciles.

## Run
```bash
python ../../link.py valuation
python orchestrator.py --ticker MSFT --peers AAPL GOOGL
python orchestrator.py --ticker NVDA --peers AMD AVGO --growth 0.15 --discount-rate 0.10
```
Flags: `--ticker` (req), `--peers …`, `--growth`, `--discount-rate`,
`--terminal-growth`. Output: `data/output/valuation-*.json`.

## Routing
DCF/comps/scenarios are pure Python. The one model step — reconciling the three
methods into a range + recommendation — is **reasoning** → **Claude** (qwen
fallback when keyless).

## Manifest
5 skills (dcf-valuation, comps-builder, scenario-analyzer, fundamentals-fetcher,
price-fetcher) + agent `valuation-analyst`.

## Test
```bash
python tests/smoke_test.py     # MSFT vs AAPL/GOOGL
```
