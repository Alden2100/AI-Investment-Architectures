---
name: valuation-summary-writer
version: 1.0.0
description: Summarizes a stock's valuation picture and the key assumptions behind it, pulling
  multiples, consensus target/growth, the current price, and the risk-free rate. Use when someone asks
  to "summarize the valuation", "write up valuation", "is it cheap or expensive", "what's it worth",
  or "key valuation assumptions".
---
# Valuation Summary Writer

`run.py` deterministically gathers the valuation inputs — finviz multiples (P/E, P/B, P/S, etc.),
the consensus price target and growth, the last traded price, and the 10-year risk-free rate — and
the model writes a concise valuation summary covering methods, key assumptions, and a value range.
Deterministic part = the inputs; model part = the synthesis and assumptions.

## Hybrid model skill
`run.py` assembles the inputs in Python, then routes the reasoning step. With ANTHROPIC_API_KEY
(or a Claude/qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker MSFT
```

## Output (JSON)
`{ ticker, company, inputs, methods, key_assumptions, value_range, summary }`
