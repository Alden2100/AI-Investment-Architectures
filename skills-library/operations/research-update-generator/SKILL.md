---
name: research-update-generator
version: 1.0.0
description: Produces periodic ("what's new / so what") updates on portfolio or watchlist companies,
  drawing on recent news, consensus estimates, and price moves. Use when someone asks for a "weekly
  update on my holdings", "what's new with these names", "portfolio monitoring digest", or "catch me
  up on my watchlist".
---
# Research Update Generator

Generates a periodic monitoring digest across one or more tickers. For each name, `run.py`
deterministically pulls recent news (`news.get_news`), analyst consensus (`estimates.get_consensus`),
and the price move over the lookback window (`prices.get_history`); it then routes a drafting step
that writes a "what's new / so what" update per company plus a portfolio-level summary. All figures
are computed in Python and quoted verbatim.

## Hybrid model skill
`run.py` fetches and computes the per-ticker data, then routes the drafting step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --tickers AAPL MSFT --lookback 30
```

## Output (JSON)
`{ updates: [{ticker, whats_new, so_what}], summary }` (plus lookback_days and the per-ticker data)
