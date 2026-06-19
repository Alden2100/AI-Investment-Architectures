---
name: price-fetcher
version: 1.0.0
description: Get a public company's price history plus basic stats (last price,
  return, annualized volatility). Use whenever someone needs a stock's price, how
  it has performed, its return over a period, or its volatility — even a casual
  "how's the stock done this year" or "what's it trading at".
---
# Price Fetcher

Returns daily price history and summary statistics, cached locally. Source chain:
yfinance → Yahoo chart API → Stooq. Deterministic — all stats (returns, volatility)
are computed in Python with numpy.

## Run
```
python run.py --ticker MSFT --lookback 365
python run.py --ticker AAPL --lookback 90 --no-series   # stats only, omit daily series
```

Flags: `--ticker` (required), `--lookback` (calendar days, default 365),
`--no-series` (omit the per-day series, return stats only).

## Output (JSON)
`{ ticker, last, return_period, return_1y, annualized_volatility, max_drawdown,
trading_days, source, prices: [{date, close}], summary }`
Returns are simple (close/close − 1); volatility is annualized stdev of daily log
returns (×√252).
