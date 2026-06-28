---
name: industry-theme-generator
version: 1.0.0
description: Generates investable themes from macro, technology, and industry trends, each
  with structural drivers, beneficiary company types, risks, and a time horizon. Pulls a live
  macro snapshot (rates, yield curve, inflation) for context. Use when someone asks "what
  themes should I be playing", "give me investable themes for ...", "thematic ideas in
  <sector>", or wants top-down theme generation.
---
# Industry Theme Generator

`run.py` deterministically pulls `macro.snapshot()` (10y/3m Treasury rates, yield-curve
slope, CPI YoY, ECB rate) as the macro backdrop, then routes theme generation to the model.
Optional `--prompt` focus and `--sector` lens narrow the output. The model anchors each
theme in structural drivers and must quote the supplied macro figures exactly rather than
invent numbers.

## Hybrid model skill
`run.py` fetches the macro snapshot in Python, then routes the reasoning step. With
ANTHROPIC_API_KEY (or a Claude rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --prompt "energy transition" --sector Industrials
```

## Output (JSON)
`{ macro_snapshot, focus, sector, themes:[{theme, drivers:[], beneficiaries:[], risks:[], time_horizon}], summary }`
