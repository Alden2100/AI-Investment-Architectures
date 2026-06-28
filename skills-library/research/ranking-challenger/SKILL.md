---
name: ranking-challenger
version: 1.0.0
description: Challenges whether a contested ranked name's RANK POSITION is justified by its
  scores and evidence, so a reconciler can re-check borderline placements. Use when someone
  says "challenge this ranking", "is this name ranked too high/too low", "contest the rank",
  "debate this placement", or runs a selective debate overlay over a ranked shortlist. This is
  about diligence ORDERING, never a buy/sell call.
---
# Ranking Challenger

Stage 7 selective debate overlay. Given ONE contested row from a ranked shortlist, it argues
that the row's RANK POSITION may be wrong — too high or too low — so a reconciler can re-examine
borderline placements. It challenges where the name sits in the research-ordering, NOT whether to
buy or sell it. No recommendation language is allowed (buy/sell/recommend/attractive/overweight/
underweight/price target).

`run.py` computes the deterministic framing in Python: how the row's `opportunity_score` sits
relative to the score `cutoff` (so the model can see it is genuinely borderline) and surfaces the
adjacent rows for cohort context. The model then judges the strongest single argument that the
rank is wrong, citing the provided sub-scores exactly.

## Hybrid model skill
`run.py` builds the comparison context in Python, then routes the challenge step on the cheap
`debate_generate` rung (qwen; the engine escalates a rung on low confidence). With a model
available it returns the filled fields; otherwise it returns `{_needs_model: true, system,
prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --row '{"ticker":"NET","company":"Cloudflare","rank":1,"opportunity_score":0.73,"mandate_fit":0.92,"factor_score":0.66,"text_score":0.25,"data_flags":[]}'
python run.py --row-file row.json --cutoff 0.70 --neighbors '[{"ticker":"DDOG","rank":2,"opportunity_score":0.71}]'
```
Input is the ranked row as a JSON object (`--row`, `--row-file`, or stdin): `{ticker, company,
rank, opportunity_score, mandate_fit, factor_score, text_score, primary_catalysts, data_flags,
why_ranked}`. Optional `--cutoff <float>` (the score boundary it sits near) and `--neighbors`
(JSON list of adjacent rows).

## Output (JSON)
`{ ticker, company, rank, opportunity_score, cutoff, cutoff_gap, challenge, suggested_direction
(up|down|hold), rationale, confidence (high|medium|low), summary }`
