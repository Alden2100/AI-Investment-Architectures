---
name: insider-trading-monitor
version: 1.0.0
description: Monitors insider buying and selling from SEC Form 4 filings and reads the net signal.
  Use when someone asks "are insiders buying or selling", "insider activity", "Form 4 transactions",
  "executives' trades", or "insider sentiment" for a company.
---
# Insider Trading Monitor

`run.py` deterministically aggregates recent Form 4 transactions from EDGAR (open-market buys vs
sells, net dollar flow) and lists the most recent transactions. The model then interprets the
signal in plain English. Deterministic part = the transactions and net flow; model part = the
interpretation.

## Hybrid model skill
`run.py` computes the insider summary in Python, then routes the summarization step. With
ANTHROPIC_API_KEY (or a qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, company, signal, net_open_market_usd, recent, note, summary }`
