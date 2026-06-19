# portfolio drawer

Sizing and monitoring. The risk/limit/KPI checks here are deterministic and
auditable — they are never decided by a model.

| Skill | Kind | Does |
|---|---|---|
| position-sizer | deterministic | Size a position to a risk budget given conviction + volatility. |
| correlation-analyzer | deterministic | Correlation matrix + HHI concentration. |
| rebalance-checker | deterministic | Drift vs targets + the trades to fix it. |
| risk-limit-checker | deterministic | Weight / gross / net / drawdown vs limits; breaches. |
| kpi-tracker | deterministic | Check current fundamentals/price vs a thesis KPI watchlist. |

Each skill is documented by its own `SKILL.md`.
