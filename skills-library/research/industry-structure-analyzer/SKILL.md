---
name: industry-structure-analyzer
version: 1.0.0
description: Evaluates industry attractiveness and competitive dynamics using Porter's five
  forces, from a company's 10-K competition/risk text and its same-SIC peer set. Use when
  someone asks for a "five forces analysis", "is this a good industry", "industry structure",
  "competitive dynamics", or "how attractive is this industry".
---
# Industry Structure Analyzer

`run.py` deterministically resolves the company, reads its SIC industry classification, finds
same-SIC peers from the screener snapshot DB (`store.all_metrics`), and excerpts the 10-K
competition and risk-factor sections. The model then rates Porter's five forces and judges
overall industry attractiveness.

## Hybrid model skill
`run.py` derives the SIC code, peers, and competition text in Python, then routes the
five-forces judgment. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns
filled fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for the
calling agent to fulfil.

## Run
```
python run.py --ticker MSFT
```

## Output (JSON)
`{ industry, five_forces:{rivalry, new_entrants, substitutes, buyer_power, supplier_power},
attractiveness, structure_notes, summary }`
