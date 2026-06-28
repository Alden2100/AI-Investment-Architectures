---
name: bull-case-generator
version: 1.0.0
description: Constructs the strongest honest argument FOR owning a stock from its revenue and
  net-income trends, consensus estimates, price target, and last price. Use when someone asks
  for "the bull case", "make the case for <ticker>", "why should I buy this", "upside
  scenario", or "the strongest argument for".
---
# Bull Case Generator

`run.py` deterministically gathers fundamentals — multi-year revenue and net-income series
from XBRL, consensus estimates (`estimates.get_consensus` + `consensus_growth`), and the last
price (`prices.last_price`). The model then constructs the strongest bull thesis. This is a
high-stakes judgment call, so it routes to the `judgment` (opus) rung.

## Hybrid model skill
`run.py` computes the fundamentals in Python, then routes the judgment step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, thesis, key_drivers, upside_scenario, what_must_be_true, summary }`
