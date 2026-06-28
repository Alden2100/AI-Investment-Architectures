---
name: footnote-analyzer
version: 1.0.0
description: Reviews the accounting footnotes in a 10-K for important disclosures and hidden risks
  (revenue recognition, contingencies, leases, goodwill, income taxes). Use when someone asks to
  "read the footnotes", "check the notes to the financial statements", "find accounting red flags",
  or "what's buried in the disclosures".
---
# Footnote Analyzer

`run.py` deterministically fetches the latest 10-K filing text from EDGAR and extracts the
footnote sections anchored on the notes to the financial statements (revenue recognition,
contingencies, leases, goodwill, income taxes). The model then reviews each topic for its
disclosure and whether it carries a risk flag. Deterministic part = the footnote text; model
part = the disclosure/risk judgment.

## Hybrid model skill
`run.py` assembles the footnote excerpts in Python, then routes the judgment step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, company, accession, footnotes:[{topic, disclosure, risk_flag}], summary }`
