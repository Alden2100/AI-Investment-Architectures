---
name: rebalance-checker
version: 1.0.0
description: Compare a portfolio's current weights to target weights, flag which
  holdings have drifted past tolerance, and produce the buy/sell trades to fix
  it. Use whenever someone wants to rebalance, check drift from targets, "am I
  overweight/underweight", what to buy or sell to get back to target, or how far
  positions have wandered — even if they just give current vs desired weights.
---
# Rebalance Checker

Drift detection and trade generation from current vs target weights.
**All math is in run.py.** Weights are fractions (0..1).

Method: union of tickers (missing side = 0); drift = current − target; a holding
breaches when |drift| > `--tolerance`; trade weight = target − current
(positive = buy, negative = sell). With `--portfolio-value`, each trade also gets
`dollar_change = weight_change · portfolio_value`.

## Run
```
python run.py --current MSFT=0.40 AAPL=0.25 GOOGL=0.35 --target MSFT=0.30 AAPL=0.30 GOOGL=0.40
python run.py --current MSFT=0.40 --target MSFT=0.30 --tolerance 0.02 --portfolio-value 1e7
```

Flags: `--current` (repeatable TICKER=weight), `--target` (repeatable
TICKER=weight), `--tolerance` (default 0.02), `--portfolio-value` (USD, optional;
adds dollar trade sizes).

## Output (JSON)
`{ tolerance, drift: [{ticker, current, target, drift, breach}],
trades: [{ticker, action, weight_change, dollar_change?}], breaches_count,
summary }`
