---
name: portfolio-event-monitor
version: 1.0.0
description: Tracks material developments affecting the companies in a portfolio. Pulls recent
  news headlines and recent SEC filings for each holding, then a model ranks each event's
  materiality. Use when someone asks what's happening to their holdings, to monitor portfolio
  companies for news or filings, surface material developments, or get a portfolio news digest.
---
# Portfolio Event Monitor

`run.py` gathers the deterministic event feed in Python: for each holding (or ticker) it pulls
recent news headlines (`news.get_news`) and recent SEC filings (`edgar.list_filings`) within the
lookback window. The model is asked only to classify and rank the materiality of those gathered
events — it never invents headlines or filings.

## Hybrid model skill
`run.py` gathers news and filings per ticker in Python, then routes the ranking step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --tickers AAPL MSFT --lookback 30
python run.py --holdings '[{"ticker":"AAPL","weight":0.5},{"ticker":"MSFT","weight":0.5}]'
python run.py --file holdings.json
```

## Output (JSON)
`{ events:[{ticker,type,date,headline,materiality}], summary }`
