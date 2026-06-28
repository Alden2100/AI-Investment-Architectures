---
name: business-model-analyzer
version: 1.0.0
description: Explains how a company generates revenue and creates value, from its 10-K
  business section, parsed revenue segments, and computed margins. Use when someone asks
  "how does <company> make money", "explain its business model", "what are its revenue
  segments", or "how does it create value".
---
# Business Model Analyzer

`run.py` deterministically resolves the company, parses its revenue segments (business /
product / geographic) from the latest 10-K XBRL, computes gross/operating/net margins from
XBRL concepts, and excerpts the 10-K business section anchored on business/revenue/products/
customers. The model then judges the revenue mechanics, value-creation logic, and key
dependencies.

## Hybrid model skill
`run.py` computes segments and margins in Python, then routes the explanation step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, company, segments, revenue_model, value_creation, key_dependencies, summary }`
