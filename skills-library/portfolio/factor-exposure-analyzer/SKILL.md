---
name: factor-exposure-analyzer
version: 1.0.0
description: Measures a portfolio's exposure to systematic factors — size, value, momentum, and
  quality — by computing each holding's factor metrics and weight-aggregating into portfolio
  tilts. Pulls market cap and P/E, P/B from finviz, 12-month price return from price history,
  and margins/ROIC from EDGAR, then a model interprets the tilts. Use when someone asks about
  factor exposure, style tilts, whether a book is value/growth/momentum, or size and quality bias.
---
# Factor Exposure Analyzer

`run.py` computes a per-holding factor snapshot in Python: size (market cap from finviz
key stats), value (P/E and P/B from finviz key stats), momentum (12-month price return from
price history), and quality (operating/net margins and a rough ROIC from EDGAR concepts). It
weight-aggregates these into portfolio-level factor tilts. The model only interprets what the
computed tilts imply about the portfolio's style — it never invents the numbers.

## Hybrid model skill
`run.py` computes the per-holding factor metrics and weighted portfolio tilts in Python, then
routes the interpretation step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it
returns filled fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for
the calling agent to fulfil.

## Run
```
python run.py --holdings '[{"ticker":"AAPL","weight":0.6},{"ticker":"KO","weight":0.4}]'
python run.py --file holdings.json
```

## Output (JSON)
`{ factors:{size,value,momentum,quality}, by_holding:[...], summary }`
