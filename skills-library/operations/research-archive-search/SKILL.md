---
name: research-archive-search
version: 1.0.0
description: Retrieves relevant historical research, memos, and notes from the local research
  archive by keyword and returns ranked, relevance-explained snippets. Use when someone asks "have
  we looked at X before", "find our old notes on Y", "search the research archive", or "what did
  we write about this name".
---
# Research Archive Search

Searches the firm's local research artifacts for a query. `run.py` deterministically globs the
systems output directories (`systems/*/data/output/*.json` and `*.md` research files) plus, on a
best-effort basis, any `thesis` table in the imdata store, scoring each by keyword frequency. It
then routes an extraction step that ranks the candidate hits and explains relevance. It never
fabricates sources — it only ranks what was actually retrieved, and reports an empty result
cleanly when the archive has no matches.

## Hybrid model skill
`run.py` gathers and scores candidate hits in Python, then routes the ranking/relevance step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --query "switching costs in payments"
```

## Output (JSON)
`{ query, results: [{source, snippet, ref}], scope_note, summary }`
