---
name: bear-case-generator
version: 1.0.0
description: Constructs the strongest honest argument AGAINST owning a stock from its revenue
  and net-income trends, consensus estimates, price target, and last price. Use when someone
  asks for "the bear case", "make the case against <ticker>", "why should I avoid/short this",
  "downside scenario", or "the strongest argument against".
---
# Bear Case Generator

`run.py` deterministically gathers fundamentals — multi-year revenue and net-income series
from XBRL, consensus estimates (`estimates.get_consensus` + `consensus_growth`), and the last
price (`prices.last_price`). The model then constructs the strongest bear thesis (the mirror
of bull-case-generator). This is a high-stakes judgment call, so it routes to the `judgment`
(opus) rung.

## Hybrid model skill
`run.py` computes the fundamentals in Python, then routes the judgment step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, thesis, key_risks, downside_scenario, what_could_break, summary }`
