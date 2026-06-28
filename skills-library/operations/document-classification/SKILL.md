---
name: document-classification
version: 1.0.0
description: Organizes and tags research documents — assigns a document type, filing tags, and
  named entities for storage and retrieval. Use when someone asks to "classify this document",
  "tag this for filing", "what kind of document is this", or "organize these research files".
---
# Document Classification

Classifies and tags a research document so it can be filed and retrieved. No market data: `run.py`
reads the document text (and an optional `--filename` hint) and routes a single classification step
on a cheap model rung that returns the doc type, filing tags, and named entities. It judges only
from the provided content.

## Hybrid model skill
`run.py` reads the input deterministically (`--file`, else `--text`, else stdin), then routes the
classification step. With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled
fields; otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling agent
to fulfil.

## Run
```
python run.py --file memo.txt --filename "acme_2026_note.txt"
echo "document text..." | python run.py
```

## Output (JSON)
`{ doc_type, tags: [], entities: [], confidence, summary }`
