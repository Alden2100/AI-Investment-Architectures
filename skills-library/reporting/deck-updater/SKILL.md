---
name: deck-updater
version: 1.0.0
description: Update a PowerPoint (.pptx) deck with the latest numbers by replacing {{KEY}} tokens, and save a new file. Use when the user asks to update a deck/slides/presentation with fresh figures, fill template tokens, or refresh a pitch deck's numbers.
---

# deck-updater

Opens a .pptx template (or builds a simple 2-slide base deck if none is given) and
replaces every `{{KEY}}` token in all shapes' text with the provided VALUE using
python-pptx, then saves to `--output`. The count of replacements is reported. Only
the JSON summary is printed (never binary).

When building from scratch, it creates a title slide with `{{TITLE}}` and a content
slide listing each provided `KEY: {{KEY}}` pair, so the mechanism is demonstrated.

## Run

```
python skills/deck-updater/run.py --values TITLE="MSFT Update" REVENUE="$281.7B" \
  --output /tmp/deck_test.pptx
python skills/deck-updater/run.py --template base.pptx --values-file vals.json \
  --output updated.pptx
```

`--values` is repeatable KEY=VALUE; `--values-file` is a JSON object of {KEY: VALUE};
both merge (CLI values win).

## Output (JSON)

- `template` (path or null if built from scratch)
- `output`: absolute path of the saved .pptx
- `replacements_made`: total tokens replaced
- `keys_applied`: keys that matched at least one token
- `slides`: slide count
- `summary`
