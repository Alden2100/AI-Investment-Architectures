# portfolio-monitoring — example prompts

Each maps to a run of `orchestrator.py --positions …`.

## Basic
1. **"Is my book within limits? NVDA 30%, MSFT 20%, AAPL 15%, cap 10% per name."**
   → `--positions NVDA=0.30 MSFT=0.20 AAPL=0.15 --max-weight 0.10`. *Expect three
   red flags (all exceed the cap) with a deterministic breach list.*
2. **"How concentrated is a portfolio of NVDA, MSFT, AAPL, GOOGL?"**
   → equal weights. *Surfaces HHI + average pairwise correlation; expect a
   concentration read even with no limits set.*

## Intermediate
3. **"Check drift: I'm at A 10% / B 10% but target A 8% / B 12% — what do I trade?"**
   → `--positions A=0.10 B=0.10 --targets A=0.08 B=0.12`. *rebalance-checker yields
   the exact buy/sell trades; the report flags the drifted names yellow.*
4. **"Run a pre-trade risk review with gross ≤ 1.5 and max drawdown 25%."**
   → add `--max-gross 1.5 --max-drawdown 0.25`. *Exercises the exposure + drawdown
   limits; expect a clear pass/breach per limit.*

## Advanced
5. **"Monitor my book against both risk limits and thesis KPIs, and alert me only on real breaches."**
   → positions + `--kpi "NVDA:dc_rev:revenue:>=:1e11"` etc. *Combines limit checks
   with thesis-KPI tracking; red = hard-limit or KPI breach. Every breach is logged
   to the audit trail for governance.*
6. **"Triage the portfolio green/yellow/red and tell me the one position to act on first."**
   → any positions set. *Pushes the judgment step to prioritize among breaches —
   the model ranks severity but cannot invent or suppress a breach.*

> The triage colors are model judgment; the breaches themselves are computed and
> auditable. Re-running appends to the same SQLite audit log.
