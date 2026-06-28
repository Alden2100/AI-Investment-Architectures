---
name: action-item-extractor
version: 1.0.0
description: Identifies tasks, owners, deadlines, and follow-ups from meeting notes, emails, or
  transcripts and returns them as a structured to-do list. Use when someone asks "what are the
  action items", "pull the to-dos from this", "who owns what after this meeting", or "list the
  follow-ups".
---
# Action Item Extractor

Reads notes/transcripts/email text and extracts the action items — each with a task, owner, due
date, and priority. No market data: `run.py` reads the input and routes a single extraction step
to a cheap model rung. It captures only tasks that are stated or clearly implied and never invents
owners or dates.

## Hybrid model skill
`run.py` reads the input deterministically (`--file`, else `--text`, else stdin), then routes the
judgment step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields;
otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --text "John to send the model by Friday; Maria will book the follow-up."
python run.py --file notes.txt
echo "notes..." | python run.py
```

## Output (JSON)
`{ action_items: [{task, owner, due, priority}], summary }`
