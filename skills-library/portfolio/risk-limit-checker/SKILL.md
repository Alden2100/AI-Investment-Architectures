---
name: risk-limit-checker
version: 1.0.0
description: Check a portfolio's position weights, gross/net exposure, and trailing
  drawdown against risk limits, and flag any breaches. Use when someone asks to
  "check my risk limits", "am I over my position cap", "is the book too gross/too
  levered", "what's my drawdown", concentration check, exposure check, or pre-trade
  risk review on a set of positions. Takes positions as TICKER=weight pairs.
---
# Risk Limit Checker

Deterministic risk check (numpy). **All math is in run.py.** Weights are the
given exposures. `gross_exposure = sum(|weight|)`, `net_exposure = sum(weight)`.

A weighted portfolio index is built from each ticker's price history, aligned on
the intersection of dates: `index_t = sum_i weight_i * close_i_t/close_i_0`.
Max drawdown is `min(index/running_max - 1)` (a negative number); reported as a
positive magnitude.

Breaches: any position weight > `--max-weight`; `gross_exposure > --max-gross`;
`|max_drawdown| > --max-drawdown`.

## Run
```
python run.py --positions MSFT=0.40 --max-weight 0.10
python run.py --positions MSFT=0.05 --positions AAPL=0.05 --positions NVDA=0.04
python run.py --positions MSFT=0.30 --positions AAPL=0.30 --max-gross 0.50 --max-drawdown 0.15
```

Flags: `--positions` (repeatable TICKER=weight, fractions), `--lookback` (days,
default 365), `--max-weight` (default 0.10), `--max-drawdown` (positive magnitude,
default 0.25), `--max-gross` (default 1.5).

## Output (JSON)
`{ positions, exposures:{by_ticker}, gross_exposure, net_exposure, max_drawdown,
limits:{...}, breaches:[{type,detail}], summary }`
