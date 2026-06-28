---
name: stock-screener-builder
version: 1.0.0
description: Converts a natural-language investment mandate into a structured screening
  filter spec compatible with the universe-screener flags (sic_contains, name_contains,
  min/max market cap, min ADV, us_only) plus a ready-to-run CLI line. Use when someone
  says "build me a screen for ...", "turn this mandate into filters", "what screener
  settings match ...", or wants to translate criteria into universe-screener flags.
---
# Stock Screener Builder

`run.py` does no deterministic data fetch — the mandate text is the only input. It routes
the parsing step to the model with a strict schema so the output maps cleanly onto the
universe-screener CLI flags. The model converts verbal sizes/liquidity/geography/industry
into structured filters and pushes anything it cannot express (growth, valuation, momentum)
into the rationale rather than inventing a threshold.

Note: `sic_contains` matches the SIC DESCRIPTION text, not the numeric code (use "eating"
for restaurants, "software" for software).

## Hybrid model skill
`run.py` builds the prompt in Python, then routes the extraction step. With ANTHROPIC_API_KEY
(or a qwen/Claude rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --query "liquid US large-cap software companies"
```

## Output (JSON)
`{ query, filters:{sic_contains, name_contains, min_mcap, max_mcap, min_adv, us_only}, rationale, suggested_command, summary }`
