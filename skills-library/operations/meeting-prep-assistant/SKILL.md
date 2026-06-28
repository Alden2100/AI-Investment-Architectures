---
name: meeting-prep-assistant
version: 1.0.0
description: Produces briefing materials, talking points, and sharp questions before a meeting,
  optionally enriched with live news, consensus estimates, and the next earnings date for a ticker.
  Use when someone asks to "prep me for this meeting", "what should I ask the CEO", "get me ready
  for the call with X", or "build a briefing before I meet management".
---
# Meeting Prep Assistant

Builds pre-meeting briefing materials. When a `--ticker` is supplied, `run.py` deterministically
pulls recent news (`news.get_news`), analyst consensus (`estimates.get_consensus`), and the next
earnings date (`estimates.next_earnings_date`); it then routes a reasoning step that turns the
context plus that data into a briefing, talking points, and questions. With no ticker it works
purely from the supplied `--context`/`--text`/`--file`.

## Hybrid model skill
`run.py` fetches the market data (if a ticker is given) and reads the context deterministically,
then routes the judgment step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns
filled fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling
agent to fulfil.

## Run
```
python run.py --ticker MSFT --context "Quarterly check-in with IR."
python run.py --context "Intro call with a new GP." 
```

## Output (JSON)
`{ briefing, talking_points: [], questions: [], summary }` (plus ticker/consensus/next_earnings_date when a ticker is given)
