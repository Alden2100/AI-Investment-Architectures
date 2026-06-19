---
name: moat-analyzer
version: 1.0.0
description: Assess a company's competitive advantage (economic moat) and industry
  position from its 10-K, backed by Python-computed margins. Use when someone asks
  "does this company have a moat", "how durable is its competitive advantage", "what
  protects this business", or wants a moat/competitive-position write-up.
---
# Moat Analyzer

Pulls the latest 10-K (business, competition, risk-factor sections) and computes
gross/operating/net margins in Python from XBRL, then has the model classify the
moat type and judge its durability. Do **not** invent or recompute figures; the
margins are computed in Python and must be quoted exactly.

## Hybrid model skill
`run.py` fetches/trims the 10-K and computes the margins, then builds the request:
- If `ANTHROPIC_API_KEY` is set, it calls the model and returns the filled fields
  (`_source: "api"`).
- If not, it returns `{_needs_model: true, system, prompt, schema, ...}`. In that
  case **you (the agent running this skill) must read `prompt` and return a JSON
  object matching `schema`** — that JSON is the skill's structured output.

## Run
```
python run.py --ticker MSFT
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, company, margins: {gross, operating, net, period_end}, moat_type,
durability, threats: [...], summary }`
