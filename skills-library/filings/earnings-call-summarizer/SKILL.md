---
name: earnings-call-summarizer
version: 1.0.0
description: Summarize an earnings release, 8-K, or pasted earnings-call transcript into
  guidance, highlights, and surprises. Use whenever someone wants a quarter's earnings
  recapped — "summarize Microsoft's latest earnings", "what did they guide to", "any
  surprises in the print", or when handed a transcript to digest.
---
# Earnings Call Summarizer

Reads an earnings 8-K (default: latest) or a pasted transcript and returns guidance,
highlights, surprises, plus a one-paragraph summary. Do **not** invent figures; only
use what is in the source text and quote numbers exactly as written.

## Hybrid model skill
`run.py` fetches/trims the source, then builds the analysis request:
- If `ANTHROPIC_API_KEY` is set, it calls the model and returns the filled fields
  (`_source: "api"`).
- If not, it returns `{_needs_model: true, system, prompt, schema, ...}`. In that
  case **you (the agent running this skill) must read `prompt` and return a JSON
  object matching `schema`** — that JSON is the skill's structured output.

## Run
```
python run.py --ticker MSFT
python run.py --ticker MSFT --accession 0000950170-25-100235
python run.py --ticker MSFT --transcript-file ./msft_q3_call.txt
```

## Output (JSON)
`{ ticker, company, source, accession?, date?, guidance, highlights: [...],
surprises: [...], summary }`
