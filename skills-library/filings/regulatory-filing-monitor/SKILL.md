---
name: regulatory-filing-monitor
version: 1.0.0
description: Tracks a company's newly filed SEC documents over a lookback window and highlights what
  changed or is worth attention. Use when someone asks "what has this company filed recently",
  "any new filings", "monitor SEC filings", "what changed in the last 90 days", or "recent regulatory activity".
---
# Regulatory Filing Monitor

`run.py` deterministically lists a company's recent EDGAR filings, filters to those within the
lookback window across all form types, and the model summarizes the activity and highlights the
notable items. Deterministic part = which filings landed and when; model part = the plain-English
highlights and what merits attention.

## Hybrid model skill
`run.py` builds the recent-filings table in Python, then routes the summarization step. With
ANTHROPIC_API_KEY (or a qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker TSLA --lookback 90
```

## Output (JSON)
`{ ticker, company, lookback_days, filings:[{form, date, accession, note}], highlights, summary }`
