---
name: ic-summary-generator
version: 1.0.0
description: Creates a structured summary of an investment-committee discussion — decision,
  rationale, dissent, and action items. Use when someone asks to "write up the IC notes",
  "summarize the investment committee", "what did the committee decide", or "draft the IC minutes".
---
# IC Summary Generator

Turns the raw notes/transcript of an investment-committee meeting into a clean decision record.
No market data: `run.py` reads the discussion text and routes a single summarization step that
captures the decision, rationale, dissent, and follow-up action items. It records only what was
discussed and quotes figures exactly.

## Hybrid model skill
`run.py` reads the input deterministically (`--file`, else `--text`, else stdin), then routes the
judgment step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields;
otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --file ic_meeting.txt
echo "IC discussion..." | python run.py
```

## Output (JSON)
`{ decision, rationale, dissent: [], action_items: [{task, owner, due}], summary }`
