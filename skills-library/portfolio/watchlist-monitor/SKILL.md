---
name: watchlist-monitor
version: 1.0.0
description: Tracks prospective investments on a watchlist and alerts on developments — notable
  recent price moves, fresh news headlines, and upcoming earnings dates. Use when someone asks
  to monitor a watchlist, watch tickers they don't yet own, get alerts on prospective buys,
  flag big moves or upcoming catalysts, or surface what changed on names they're tracking.
---
# Watchlist Monitor

`run.py` computes the deterministic alert feed in Python: for each watchlist ticker it measures
the recent percent price move over the lookback window (`prices.get_history`), pulls recent news
headlines (`news.get_news`), and looks up the next scheduled earnings date
(`estimates.next_earnings_date`). It flags notable moves and near-term earnings. The model is
asked only to summarize and prioritize the gathered alerts — it never invents data.

## Hybrid model skill
`run.py` computes price moves, gathers news, and finds earnings dates per ticker in Python, then
routes the summarization step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it
returns filled fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for
the calling agent to fulfil.

## Run
```
python run.py --tickers AAPL MSFT NVDA --lookback 30
```

## Output (JSON)
`{ alerts:[{ticker,trigger,detail}], summary }`
