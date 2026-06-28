---
name: client-report-generator
version: 1.0.0
description: Creates a client-facing investment report / summary with executive summary,
  performance, positioning, and outlook sections. Use when someone asks to "generate a
  client report", "write an investment summary for a client", or "turn portfolio data
  into a client-ready report".
---
# Client Report Generator

Takes notes or structured portfolio JSON and drafts a structured, client-facing report.
No deterministic computation — figures supplied in the input are quoted verbatim and the
model writes the surrounding report sections.

## Hybrid model skill
`run.py` assembles the input and routes the drafting step. With a Claude/qwen rung
available it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --text "YTD +8.1%, defensive tilt, overweight healthcare."
python run.py --file portfolio_notes.txt
python run.py --portfolio '{"ytd":0.081,"tilt":"defensive"}'
```

## Output (JSON)
`{ report: { summary, performance, positioning, outlook }, summary }`
