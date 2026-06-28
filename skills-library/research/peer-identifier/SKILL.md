---
name: peer-identifier
version: 1.0.0
description: Given a ticker, identifies direct competitors, substitutes, and valuation
  comparables. Resolves the company's SIC industry from EDGAR and gathers same-SIC public
  names from the metrics store as candidates, then the model sorts them into peer groups.
  Use when someone asks "who are <ticker>'s competitors", "build a peer set for ...",
  "comps for <ticker>", or "what are the substitutes for this company".
---
# Peer Identifier

`run.py` deterministically resolves the target via `universe.resolve` and `edgar.company_meta`
(for SIC + description), then pulls same-SIC public companies from `store.all_metrics()`
(largest market cap first) as a candidate list. The model refines those candidates into
direct competitors, substitutes, and comparables, dropping SIC neighbors that are not real
peers. It is instructed to quote candidate tickers exactly and not invent tickers.

If the metrics store is unwarmed (no same-SIC candidates), the candidate list is empty and
the model reasons from the SIC industry alone — the deterministic SIC fields are always returned.

## Hybrid model skill
`run.py` computes the SIC and candidate list in Python, then routes the reasoning step. With
ANTHROPIC_API_KEY (or a Claude rung available) it returns filled peer groups; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, company, sic, sic_description, candidates:[{ticker, name, market_cap, sic_description}], peers:{direct:[], substitutes:[], comparables:[]}, summary }`
