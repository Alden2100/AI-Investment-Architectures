---
name: question-generator
version: 1.0.0
description: Generates a sharp diligence question set (management / financial / competitive /
  risk) for management or expert-network calls, optionally grounded in a ticker's recent news
  and consensus estimates. Use when someone asks "what should I ask management", "diligence
  questions for the call", "expert call questions", or "questions for an earnings call".
---
# Question Generator

`run.py` deterministically gathers context when a ticker is supplied: recent news
(`news.get_news`) and consensus estimates (`estimates.get_consensus` + `consensus_growth`).
A `--topic` can focus the call. The model then writes specific, call-ready questions grouped
into four buckets.

## Hybrid model skill
`run.py` assembles the context in Python, then routes the question-writing step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker NVDA
python run.py --ticker NVDA --topic "data center capacity"
python run.py --topic "semiconductor cycle"
```

## Output (JSON)
`{ questions:{management, financial, competitive, risk}, summary }`
