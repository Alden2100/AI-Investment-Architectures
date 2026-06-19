---
name: catalyst-flagger
version: 1.0.0
description: Surface event-driven / thematic catalysts for one or more tickers from
  recent 8-K filings and news headlines. Use when someone asks "any catalysts coming
  up", "what's moving these names", "flag event-driven setups", or wants recent
  filings/news scanned for actionable events across a watchlist.
---
# Catalyst Flagger

Deterministically gathers recent 8-K filings (last ~5) and news headlines (lookback
window) per ticker, assembles a compact signals block, and has the model label
potential catalysts with type, date, confidence, and rationale. Only the supplied
signals are used; the model does not invent events or figures.

## Hybrid model skill
`run.py` gathers the filing/news signals, then builds the analysis request:
- If `ANTHROPIC_API_KEY` is set, it calls the model and returns the filled fields
  (`_source: "api"`).
- If not, it returns `{_needs_model: true, system, prompt, schema, ...}`. In that
  case **you (the agent running this skill) must read `prompt` and return a JSON
  object matching `schema`** — that JSON is the skill's structured output.

## Run
```
python run.py --tickers MSFT AAPL
python run.py --tickers NVDA --lookback 14
```

## Output (JSON)
`{ tickers: [...], lookback_days, signal_counts: {ticker: {filings, news}},
catalysts: [{ticker, type, date, confidence, rationale}], summary }`
