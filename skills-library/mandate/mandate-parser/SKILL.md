---
name: mandate-parser
version: 1.0.0
description: Turn a raw investment mandate (free text) into a structured MandateSpec, classifying
  every criterion as core_principle, positive_preference, hard_constraint, negative_constraint, or
  portfolio_constraint. Use when someone hands you a
  mandate, an IPS, a screening brief, or a "find me companies that ..." paragraph and you need it
  parsed into machine-actionable constraints, seed tickers, and a semantic query. This is Stage 0 of
  idea-sourcing v2 — it produces the spec the downstream screener/ranker consume.
---
# Mandate Parser

`run.py` reads a mandate from `--file`, `--text`, or stdin and turns it into a structured
**MandateSpec**. The model's job is **classification**: every criterion is tagged
`hard_constraint` (binary, mandate-EXPLICIT — country, market-cap floor/ceiling, explicit
sector inclusion/exclusion), `soft_preference` (a numeric/directional preference), or
`qualitative` (moat, management, business-model fit). Directional language
("preferably", "strong", "ideally", "lean toward", "high-quality") is NEVER a hard constraint.
Only `hard_constraint` rows carry a structured `{field, operator, value}`.

Deterministically (in Python, never the model) the skill assigns a `mandate_id`, computes a
stable `mandate_hash` (sha256 over the sorted criteria + exclusions), normalizes criterion ids
to `c1, c2, ...`, and validates any example/seed tickers against the SEC universe — dropping the
unresolvable ones and noting it.

## Hybrid model skill
`run.py` parses the mandate text in Python, then routes the classification step with
`task="reasoning"` (high-stakes, runs once per mandate; the router escalates on low confidence).
With `ANTHROPIC_API_KEY` (or a Claude/qwen rung available) it returns filled criteria;
otherwise it returns a `{_needs_model: true, system, prompt, schema}` envelope for the calling
agent to fulfil. Either way the deterministic fields (`mandate_id`, `mandate_hash`, resolved
`seed_tickers`) are present.

## Run
```
python run.py --file mandate.txt
python run.py --text "Large-cap US software, preferably high gross margins and a durable moat; exclude China. Examples: MSFT, ADBE."
echo "..." | python run.py
```

## Output (JSON)
`{ mandate_id, mandate_hash, seed_tickers[], criteria[ {id,text,type,field,operator,value,weight,rationale} ], semantic_query, exclusions[], summary }`
