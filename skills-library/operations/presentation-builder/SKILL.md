---
name: presentation-builder
version: 1.0.0
description: Converts research output into presentation-ready slides (title, bullets,
  presenter notes). Use when someone asks to "build slides from this research", "turn
  this into a deck", "make a presentation", or "create slide bullets from this analysis".
---
# Presentation Builder

Takes research output (free text) and structures it into a presentation-ready slide
outline: per-slide titles, bullets, and presenter notes. No deterministic computation —
figures in the input are quoted verbatim and the model organizes the content into slides.

Pairs with `reporting/deck-updater`, which takes this slide structure and renders it into
an actual `.pptx` file.

## Hybrid model skill
`run.py` assembles the input and routes the drafting step. With a Claude/qwen rung
available it returns filled slides; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --file research.txt --title "MSFT Investment Thesis"
python run.py --text "Thesis: cloud margins expanding. Evidence: ... Risks: ..."
```

## Output (JSON)
`{ slides: [{ title, bullets: [], notes }], summary }`
