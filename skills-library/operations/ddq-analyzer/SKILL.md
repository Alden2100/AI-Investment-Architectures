---
name: ddq-analyzer
version: 1.0.0
description: Reviews a completed due-diligence questionnaire (DDQ) and identifies gaps,
  concerns, inconsistencies, and strengths. Use when someone asks to "analyze this DDQ",
  "review a due-diligence questionnaire", "find gaps in these DDQ answers", or "what should
  I probe in this manager's responses".
---
# DDQ Analyzer

Takes a completed due-diligence questionnaire (questions and answers) and produces an
analytical review: gaps (missing/vague answers), concerns (red flags and inconsistencies to
probe), and strengths. Pure reasoning over the provided text — no facts are invented.

## Hybrid model skill
`run.py` assembles the input and routes the reasoning step. With a Claude/qwen rung
available it returns the filled analysis; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --file manager_ddq.txt
python run.py --text "Q: Describe your risk controls. A: We are careful. Q: AUM? A: (blank)"
```

## Output (JSON)
`{ gaps: [], concerns: [], strengths: [], summary }`
