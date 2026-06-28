---
name: portfolio-optimizer
version: 1.0.0
description: Evaluates portfolio allocation tradeoffs and recommends trims/adds to reduce
  concentration and move toward risk balance. Computes per-name volatility, the correlation
  matrix, and each holding's marginal risk contribution from price history, then a model
  writes the rebalancing rationale. Use when someone asks to optimize a portfolio, rebalance
  holdings, reduce concentration, balance risk, or suggest position-size adjustments.
---
# Portfolio Optimizer

`run.py` computes the deterministic risk picture in Python: it pulls ~252 trading days of
price history per holding, computes annualized per-name volatility, the return correlation
matrix, the portfolio variance, and each holding's percentage risk contribution
(`w_i * (Σw)_i / portfolio variance`). It then proposes concrete trims/adds that move the
book away from concentration and toward risk balance. The model is only asked to turn those
computed numbers into a readable rebalancing rationale — it never invents figures.

## Hybrid model skill
`run.py` computes volatilities, correlations, and risk contributions in Python, then routes
the judgment step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled
fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling
agent to fulfil.

## Run
```
python run.py --holdings '[{"ticker":"AAPL","weight":0.5},{"ticker":"MSFT","weight":0.5}]'
python run.py --file holdings.json
```

## Output (JSON)
`{ current:[{ticker,weight,vol,risk_contrib}], suggested:[{ticker,from,to,reason}], rationale, summary }`
