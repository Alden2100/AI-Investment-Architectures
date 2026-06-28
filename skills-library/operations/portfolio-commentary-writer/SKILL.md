---
name: portfolio-commentary-writer
version: 1.0.0
description: Drafts client-ready portfolio commentary and performance updates from
  performance and holdings notes. Use when someone asks to "write portfolio commentary",
  "draft a performance update", "explain this quarter's returns to clients", or
  "turn these holdings notes into client commentary".
---
# Portfolio Commentary Writer

Takes performance and holdings notes (free text or structured JSON) and drafts a
client-ready performance update: commentary, attribution, and outlook. There is no
deterministic computation here — the skill quotes the figures you provide and the
model writes the narrative around them.

## Hybrid model skill
`run.py` assembles the input (figures quoted verbatim) and routes the drafting step.
With a Claude/qwen rung available it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --text "Q3 return +4.2% vs +3.1% benchmark; top contributor MSFT, detractor NKE."
python run.py --file notes.txt
python run.py --performance '{"period":"Q3 2025","return":0.042,"benchmark":0.031}'
```

## Output (JSON)
`{ commentary, attribution_notes, outlook, summary }`
