---
name: analyst-estimate-monitor
version: 1.0.0
description: Tracks Wall Street consensus expectations (EPS/revenue estimates, price target, growth,
  recommendation mix) and any revision trend. Use when someone asks "what's the consensus", "analyst
  estimates", "price target", "are estimates being revised", "Street expectations", or "consensus growth".
---
# Analyst Estimate Monitor

`run.py` deterministically pulls analyst consensus from yfinance (price target, EPS/revenue
estimates, recommendation, analyst count) plus a best-effort stockanalysis.com cross-check and the
next-FY consensus growth, and the recommendation-trend table when available. The model then
summarizes the expectations and any revision signal. Deterministic part = the numbers; model part =
the readout. If no revision history is available, the result says so in `note`.

## Hybrid model skill
`run.py` gathers the consensus in Python, then routes the summarization step. With ANTHROPIC_API_KEY
(or a qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker NVDA
```

## Output (JSON)
`{ ticker, company, consensus, recommendation, n_analysts, growth, note, summary }`
