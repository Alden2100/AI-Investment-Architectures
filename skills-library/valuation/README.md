# valuation drawer

Intrinsic, relative, and scenario valuation. All math is in Python.

| Skill | Kind | Does |
|---|---|---|
| dcf-valuation | deterministic | Unlevered-FCF DCF -> intrinsic value + upside. |
| comps-builder | deterministic | Peer multiples table (EV/EBITDA, P/E, P/S); value off medians. |
| comps-refresher | deterministic | Force-fresh re-pull of a saved comps set. |
| scenario-analyzer | deterministic | Bull/base/bear DCF + growth×WACC sensitivity grid. |

Each skill is documented by its own `SKILL.md`.
