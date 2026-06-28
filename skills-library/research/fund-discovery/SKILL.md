---
name: fund-discovery
version: 1.0.0
description: Identifies funds and managers matching an allocator's requirements (strategy,
  asset class, geography, AUM), returning candidates with why-fit reasoning and honest
  caveats. Pulls best-effort news headlines for context and is explicit that there is no
  structured fund database behind it. Use when someone asks "find managers that do ...",
  "shortlist funds for this mandate", "who runs a <strategy> fund", or "fund manager search".
---
# Fund Discovery

`run.py` deterministically pulls best-effort context via `news.keyed_headlines(requirements)`
(often sparse — it is weak signal, not a database), then routes manager shortlisting to the
model. There is no structured fund database in this library, so the skill is built to be
HONEST about that: it always returns a `data_caveat` and attaches per-candidate caveats, and
the model is instructed never to fabricate AUM, returns, or fund terms.

## Hybrid model skill
`run.py` fetches headline context in Python, then routes the reasoning step. With
ANTHROPIC_API_KEY (or a Claude rung available) it returns filled candidates; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --requirements "long/short equity, tech focus, $100M+ AUM, US-based"
```

## Output (JSON)
`{ requirements, headlines, criteria:[], candidates:[{name, strategy, why_fit, caveats}], data_caveat, summary }`
