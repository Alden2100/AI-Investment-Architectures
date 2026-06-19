# portfolio-monitoring

Positions + targets + thesis KPIs → a status report with green/yellow/red triage
and **breach alerts**.

## Pipeline
```
positions ─▶ price-fetcher (per name) · rebalance-checker (drift)   (deterministic)
          ─▶ risk-limit-checker (weight/gross/net/drawdown) · correlation-analyzer (HHI)
          ─▶ kpi-tracker (vs saved thesis baselines)
          ─▶ breaches computed deterministically  ◀── never model-decided
          ─▶ [router: judgment] triage green/yellow/red + narrate    (model)
          ─▶ audit every breach + write output JSON
```
**The breach list is the deterministic source of truth.** The model only assigns
colors and writes the summary; it cannot flip a limit result.

## Run
```bash
python ../../link.py portfolio-monitoring
python orchestrator.py --positions NVDA=0.30 MSFT=0.20 AAPL=0.15 --max-weight 0.10
python orchestrator.py --positions A=0.1 B=0.1 --targets A=0.08 B=0.12 \
    --kpi "A:rev_growth:revenue:>=:0.10" --max-gross 1.5 --max-drawdown 0.25
```
Flags: `--positions TICKER=weight…` (req), `--targets`, `--kpi
TICKER:name:metric:comparator:target`, `--max-weight`, `--max-gross`,
`--max-drawdown`.

## Routing
All numeric checks are pure Python (not in the policy at all). The only model call
is the triage **judgment** → **Claude** (qwen fallback). Nothing here can override
a deterministic breach.

## Manifest
7 skills (price-fetcher, rebalance-checker, risk-limit-checker,
correlation-analyzer, kpi-tracker, position-sizer, audit-logger) + agent
`portfolio-risk-monitor`.

## Test
```bash
python tests/smoke_test.py     # asserts the max-weight breach fires
```
