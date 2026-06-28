---
name: kpi-extractor
version: 1.0.0
description: Extracts company-specific operating KPIs (subscribers, units, ARPU, bookings, same-store
  sales, etc.) from the latest filing or a pasted transcript. Use when someone asks to "pull the KPIs",
  "extract operating metrics", "what are the key metrics", or "find the non-GAAP/operating numbers" for a company.
---
# KPI Extractor

`run.py` deterministically fetches the latest 10-K or 10-Q filing text from EDGAR (or uses
`--text`/`--file` if provided) and trims it. The model then extracts the company-specific operating
KPIs into a structured list with value, unit, period, and source. Deterministic part = the source
text; model part = identifying and structuring the KPIs.

## Hybrid model skill
`run.py` assembles the source text in Python, then routes the extraction step. With ANTHROPIC_API_KEY
(or a qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker NFLX
python run.py --ticker NFLX --file transcript.txt
```

## Output (JSON)
`{ ticker, company, source, kpis:[{name, value, unit, period, source}], summary }`
