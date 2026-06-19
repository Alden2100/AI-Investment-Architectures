---
name: memo-writer
version: 1.0.0
description: Draft an investment-committee (IC) memo for a stock from prior research outputs (DCF, comps, fundamentals, moat) or from grounded basics. Use when the user asks to write/draft an IC memo, investment memo, committee write-up, or pitch for a ticker.
---

# memo-writer

Drafts a concise investment-committee memo for a single ticker. Deterministic prep
resolves the ticker and, if no research file is supplied, pulls latest annual
revenue, net income, and last price to ground the memo. The model writes the prose.

## Hybrid model skill

If the output contains `_needs_model: true`, no `ANTHROPIC_API_KEY` was set. The
calling agent should read `prompt` (and `system`) and return a JSON object matching
`schema`, then merge it with the deterministic `meta` fields. With a key set, the
fields are filled automatically.

The model only writes qualitative text; every figure it quotes comes from the
deterministic `grounding` or the supplied `--input-file`.

## Run

```
python skills/memo-writer/run.py --ticker MSFT
python skills/memo-writer/run.py --ticker MSFT --input-file /tmp/research.json
```

`--input-file` is an optional JSON file holding prior research-skill outputs
(e.g. dcf, comps, fundamentals, moat); when given it is passed into the prompt.

## Output (JSON)

- `ticker`, `company`, `inputs_provided` (bool), `grounding` ({revenue?, net_income?, price?})
- `memo_sections`: {thesis, business_overview, financials, valuation, risks, recommendation}
- `summary`: one-paragraph synopsis
- When unkeyed: `_needs_model`, `system`, `prompt`, `schema`
