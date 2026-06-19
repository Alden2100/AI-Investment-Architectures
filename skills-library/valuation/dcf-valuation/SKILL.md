---
name: dcf-valuation
version: 1.0.0
description: Build a discounted cash flow valuation for a public company. Use
  whenever a valuation, intrinsic value, fair value, price target, or "what is it
  worth" is needed, even if the user does not say the word DCF.
---
# DCF Valuation

Unlevered free-cash-flow DCF. **All math is in run.py** — the model only labels
and narrates. Base free cash flow defaults to the company's reported
`operating_cash_flow − capex`; every assumption can be overridden on the CLI.

Method: project FCF₍ₜ₎ = base_fcf·(1+g)ᵗ for the explicit years; terminal value
TV = FCF₍N₎·(1+g_term)/(r−g_term); discount each by (1+r)ᵗ; enterprise value =
ΣPV(FCF) + PV(TV); equity value = EV − net_debt; intrinsic value per share =
equity value ÷ shares; upside = intrinsic ÷ price − 1.

## Run
```
python run.py --ticker MSFT --growth 0.10 --years 5 --discount-rate 0.09 --terminal-growth 0.03
python run.py --ticker AAPL --base-fcf 9.5e10 --growth 0.06 --discount-rate 0.085 --terminal-growth 0.025
```

Flags: `--ticker` (required), `--base-fcf` (override base FCF, USD),
`--growth` (annual FCF growth, default 0.08), `--years` (explicit years, default 5),
`--discount-rate` (WACC, default 0.09), `--terminal-growth` (default 0.025),
`--net-debt`/`--shares`/`--price` (overrides; otherwise pulled from data layer).

## Output (JSON)
`{ ticker, assumptions, projection: [{year, fcf, pv}], terminal_value, pv_terminal,
enterprise_value, equity_value, intrinsic_value_per_share, current_price,
upside_vs_price, summary }`
