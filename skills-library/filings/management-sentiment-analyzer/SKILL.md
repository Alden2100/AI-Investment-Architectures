---
name: management-sentiment-analyzer
version: 1.0.0
description: Evaluates management tone, confidence, and how their messaging is changing across recent
  earnings releases. Use when someone asks to "gauge management sentiment", "is management confident",
  "how has the tone changed", "read management's tone", or compare commentary across quarters.
---
# Management Sentiment Analyzer

`run.py` deterministically pulls the latest two to three earnings press releases (8-K EX-99.1
prepared-remarks/release text) from EDGAR and trims them around outlook/results language. The
model then judges qualitative tone, confidence, and the shift in messaging period over period.
Deterministic part = which filings and what text; model part = the sentiment judgment.

## Hybrid model skill
`run.py` gathers the period excerpts in Python, then routes the judgment step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker MSFT
```

## Output (JSON)
`{ ticker, company, periods, tone, confidence, shift, evidence, summary }`
