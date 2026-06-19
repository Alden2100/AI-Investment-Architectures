---
name: filing-summarizer
version: 1.0.0
description: Turn a 10-K or 10-Q into structured key takeaways (business, drivers,
  risks, guidance). Use whenever someone wants a filing read, summarized, or its key
  points pulled out — even a casual "what's in this 10-K" or "summarize Microsoft's
  annual report".
---
# Filing Summarizer

Reads a filing and returns four structured sections plus a one-paragraph summary.
Do **not** invent figures; only use what is in the filing. Quote numbers exactly
as written.

## Hybrid model skill
`run.py` fetches and trims the filing, then builds the analysis request:
- If `ANTHROPIC_API_KEY` is set, it calls the model and returns the filled fields
  (`_source: "api"`).
- If not, it returns `{_needs_model: true, system, prompt, schema, ...}`. In that
  case **you (the agent running this skill) must read `prompt` and return a JSON
  object matching `schema`** — that JSON is the skill's structured output.

## Run
```
python run.py --ticker MSFT --form 10-K
python run.py --ticker AAPL --form 10-Q
python run.py --accession 0000950170-25-100235 --ticker MSFT
```

## Output (JSON)
`{ ticker, form, accession, date, business, drivers: [...], risks: [...], guidance,
summary }`
