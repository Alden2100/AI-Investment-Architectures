---
name: position-sizer
version: 1.0.0
description: Suggest how big a position to take given conviction, a risk budget,
  and the stock's volatility. Use whenever someone asks "how much should I buy",
  "what size", "how many shares/dollars", position sizing, sizing a trade, or how
  to scale a position to risk — even if they don't say "volatility" or "risk
  budget". Higher-volatility names get smaller weights for the same risk.
---
# Position Sizer

Volatility-targeted sizing. **All math is in run.py.** If `--volatility` is
omitted but `--ticker` is given, annualized vol is computed from daily log
returns over the lookback window.

Method: `weight = (risk_budget · conviction) / volatility`, floored at 0 and
capped at `--max-weight`; `dollar_size = weight · portfolio_value`. Doubling
volatility halves the weight (when below the cap).

## Run
```
python run.py --ticker MSFT --conviction 0.7 --risk-budget 0.02
python run.py --conviction 0.7 --risk-budget 0.02 --volatility 0.20
python run.py --conviction 0.7 --risk-budget 0.02 --volatility 0.40 --portfolio-value 5e6
```

Flags: `--conviction` (0..1, required), `--risk-budget` (fraction, required),
`--ticker` (optional; derives vol if `--volatility` omitted),
`--volatility` (annualized decimal, optional), `--portfolio-value` (USD, default 1e7),
`--max-weight` (cap, default 0.10), `--lookback` (days, default 365).

## Output (JSON)
`{ ticker, conviction, risk_budget, volatility, weight, dollar_size, capped,
rationale, summary }`
