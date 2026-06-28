---
name: meeting-note-summarizer
version: 1.0.0
description: Converts a raw meeting transcript or rough notes into concise structured notes
  (attendees, topics, decisions, notes, summary). Use when someone asks to "summarize this
  meeting", "clean up my meeting notes", "turn this transcript into notes", or "what were the
  takeaways from this call".
---
# Meeting Note Summarizer

Takes a meeting transcript (or rough notes) and produces concise structured notes. There is no
market data here — `run.py` reads the input text and routes a single summarization step to the
model, which extracts attendees, topics, decisions, and a summary. It records only what is
actually stated and quotes any numbers exactly.

## Hybrid model skill
`run.py` reads the input deterministically (`--file`, else `--text`, else stdin), then routes the
judgment step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields;
otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --file meeting.txt
python run.py --text "Met with Acme CEO. Agreed to follow up next week."
echo "transcript..." | python run.py
```

## Output (JSON)
`{ attendees, topics, decisions, notes, summary }`
