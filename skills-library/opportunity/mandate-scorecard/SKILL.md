---
name: mandate-scorecard
version: 1.0.0
description: Score ONE company against an investment mandate, criterion by criterion, with a
  per-criterion verdict (meets / partial / does_not_meet), filing-cited evidence, and an overall
  fit score. Covers hard, soft, and qualitative criteria. Use when someone asks "does this name
  fit the mandate", "score TICKER against my mandate", "which criteria does it fail", a mandate
  fit check, or a per-criterion scorecard — the stage that guarantees a candidate matches the mandate.
---
# Mandate Scorecard

Stage 4 of idea-sourcing v2. For a single company and a `MandateSpec` (criteria with id / text /
type / field / operator / value / weight), `run.py` gathers a deterministic evidence base — company
name, computed margins and their multi-year trend, trimmed 10-K business/competition/risk text, and
best-effort consensus estimates — then routes a per-criterion fit judgment to the model. Each
criterion gets a verdict (`meets` / `partial` / `does_not_meet`), a short evidence string that cites
a provided figure or a quote from the provided filing text, and a confidence (high / medium / low).

This is fit assessment, NOT a recommendation or thesis. The margins and figures are computed in
Python from XBRL and must be quoted exactly; the model never invents numbers.

## Hybrid model skill
`run.py` computes the evidence base (margins, trend, filing excerpt, consensus) in Python, then routes
the scoring step at `task="reasoning"` (high-stakes per-criterion judgment that escalates on low
confidence). With ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled criterion
results; otherwise it returns `{_needs_model: true, system, prompt, schema}` for the calling agent to
fulfil. The deterministic `factor_score` / `text_score` (if passed in) are attached either way.

## Run
```
python run.py --ticker MSFT --mandate-file /path/to/spec.json
# or inline:
python run.py --ticker MSFT --mandate-json '{"criteria":[...]}'
# optionally attach upstream deterministic scores:
python run.py --ticker MSFT --mandate-file spec.json --factor-score 0.7 --text-score 0.6
```

`MandateSpec`: `{ "criteria": [ {id, text, type, field, operator, value, weight} ] }`.

## Output (JSON)
`{ ticker, company, overall_fit, criterion_results:[{criterion_id, criterion_text, verdict, evidence, confidence}], flags:[criterion ids marked does_not_meet], factor_score, text_score, margins:{gross,operating,net,period_end}, summary }`
