---
name: market-dislocation-finder
version: 1.0.0
description: Surfaces valuation gaps and potential mispricings across a set of names by
  computing each one's multiples (forward/trailing P/E, PEG, P/B, P/S) versus the peer
  median, then letting the model judge which gaps are real dislocations vs justified
  quality/growth differences. Use when someone asks "find mispricings across these names",
  "which of these is cheap/rich vs peers", "spot valuation dislocations", or "relative-value
  screen for <tickers>".
---
# Market Dislocation Finder

`run.py` deterministically pulls per-ticker valuation multiples from `estimates.get_consensus`
(forward/trailing P/E, PEG) and `finviz.key_stats` (P/B, P/S) plus `prices.last_price`,
computes the peer median for each metric, and the percentage gap of each name vs that median
(a z-score-ish relative-value measure). The model then judges which gaps are genuine
dislocations versus differences justified by quality or growth, quoting the computed figures
exactly.

## Hybrid model skill
`run.py` computes the multiples and peer-median gaps in Python, then routes the judgment step.
With ANTHROPIC_API_KEY (or a Claude rung available) it returns filled dislocations; otherwise
it returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --tickers AAPL MSFT GOOGL
```

## Output (JSON)
`{ tickers, names, metrics:[...per-ticker multiples...], peer_medians, gaps:[...], dislocations:[{ticker, metric, value, peer_median, direction, note}], summary }`
