---
name: scenario-analyzer
version: 1.0.0
description: Run bull / base / bear DCF scenarios for a company plus a
  growth-by-discount-rate sensitivity table. Use whenever someone wants
  upside/downside cases, a range of fair values, "what if growth or WACC
  changes", best-/worst-case valuation, stress testing a price target, or a
  sensitivity matrix — even if they only say "show me the bull and bear case".
---
# Scenario Analyzer

Replicated unlevered-FCF DCF run under three scenarios with a sensitivity grid.
**All math is in run.py** (the DCF is replicated locally, not imported). Base FCF
defaults to reported `operating_cash_flow − capex`.

Method per scenario: project FCF₍ₜ₎ = base_fcf·(1+g)ᵗ; TV = FCF₍N₎·(1+gₜ)/(r−gₜ);
discount by (1+r)ᵗ; EV = ΣPV(FCF)+PV(TV); equity = EV − net_debt; intrinsic/share
= equity ÷ shares; upside = intrinsic ÷ price − 1. Bull = (g+Δg, r+Δr_bull);
bear = (g+Δg_bear, r+Δr_bear). Sensitivity = intrinsic/share over growth {base±0.02}
× discount_rate {base±0.01}, guarding r > terminal_growth in every cell.

## Run
```
python run.py --ticker MSFT --growth 0.10 --discount-rate 0.09 --terminal-growth 0.03
python run.py --ticker AAPL --bull-growth-delta 0.04 --bear-wacc-delta 0.02
```

Flags: `--ticker` (required), `--base-fcf`, `--growth` (default 0.08),
`--discount-rate` (default 0.09), `--terminal-growth` (default 0.025),
`--years` (default 5), `--net-debt`/`--shares`/`--price` (overrides),
`--bull-growth-delta` (+0.03), `--bear-growth-delta` (−0.03),
`--bull-wacc-delta` (−0.01), `--bear-wacc-delta` (+0.01).

## Output (JSON)
`{ ticker, assumptions, scenarios: {bull, base, bear} each
{growth, discount_rate, intrinsic_value_per_share, upside_vs_price},
sensitivity_table: {row_label, col_label, rows, cols, matrix}, summary }`
