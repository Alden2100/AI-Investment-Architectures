---
name: portfolio-risk-monitor
version: 1.0.0
description: Monitors a book against targets, risk limits, and thesis KPIs.
skills: [price-fetcher, rebalance-checker, risk-limit-checker, correlation-analyzer, kpi-tracker, position-sizer, audit-logger]
---
# Portfolio Risk Monitor

## Mandate
Check a portfolio against its targets, hard risk limits, and per-name thesis KPIs;
triage every position green/yellow/red and surface breaches that demand action.

## Instructions
- Deterministically compute drift vs targets, gross/net exposure, drawdown,
  concentration (HHI), correlation, and KPI status. **These checks are auditable
  and must stay deterministic** — never let the model decide whether a limit is
  breached.
- The model only triages and narrates: red = hard-limit or thesis-KPI breach;
  yellow = drift/soft-limit/weakening KPI; green = within tolerance.
- Log every breach to the audit trail.

## Contract
- **Input:** `{ positions: {ticker: weight}, targets?: {...}, kpis?: [...],
  limits?: {max_weight, max_gross, max_drawdown} }`.
- **Output:** `{ triage: [{ticker, status, note}], breaches: [...],
  exposure, correlation, summary }`.

Contract only — limits and KPI baselines come from the orchestrator/config.
