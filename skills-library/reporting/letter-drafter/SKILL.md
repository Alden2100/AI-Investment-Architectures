---
name: letter-drafter
version: 1.0.0
description: Draft an investor / limited-partner (LP) letter for a period from fund performance and holdings. Use when the user asks to write/draft a quarterly investor letter, LP letter, shareholder letter, or fund update.
---

# letter-drafter

Drafts an investor/LP letter for a stated period. Deterministic prep parses the
performance JSON and TICKER=weight holdings and computes simple stats (excess return
= return - benchmark_return when both are present) in Python. The model writes the
letter prose, quoting the Python-computed figures exactly.

## Hybrid model skill

If the output contains `_needs_model: true`, no `ANTHROPIC_API_KEY` was set. The
calling agent should read `prompt` (and `system`) and return JSON matching `schema`,
then merge with the deterministic `meta`. With a key set, fields fill automatically.

## Run

```
python skills/letter-drafter/run.py --period "Q2 2026" \
  --performance '{"return":0.084,"benchmark_return":0.061}' \
  --holdings MSFT=0.12 GOOGL=0.09
python skills/letter-drafter/run.py --period "Q2 2026" --performance-file /tmp/perf.json
```

`--performance-file` (JSON) and `--performance` (inline JSON) merge; `--holdings`
is repeatable TICKER=weight.

## Output (JSON)

- `period`, `performance` ({...}), `holdings` ([{ticker, weight}]), `computed` ({excess_return?})
- `letter_draft`: full letter body
- `key_points`: array of strings
- `summary`: one-paragraph synopsis
- When unkeyed: `_needs_model`, `system`, `prompt`, `schema`
