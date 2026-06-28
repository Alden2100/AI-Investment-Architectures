---
name: factor-ranker
version: 1.0.0
description: Stage 2 of the opportunity funnel. Scores Stage-1 survivors on
  soft_preference criteria that map to cheap snapshot metrics (size, liquidity,
  industry_fit), min-max normalized and mandate-weighted into a 0..1 factor_score.
  Use when someone wants to rank or sort filtered candidates by mandate fit,
  prioritize a survivor list, or produce factor sub-scores before deeper analysis.
---
# Factor Ranker

Deterministic Stage-2 ranker for the `opportunity/` drawer. It takes a **MandateSpec**
and the survivor list emitted by `universe-filter`, then scores each survivor on the
factors computable from the `company_metrics` snapshot:

- **size** — market_cap percentile across the survivor set
- **liquidity** — adv (avg daily $ volume) percentile across the survivor set
- **industry_fit** — 1.0 when a soft/qualitative industry word matches the row's
  `sic_description`, else 0.5

Each factor is min-max normalized to `[0,1]` across the survivors (missing metrics
score a neutral 0.5). The `factor_score` is a mandate-weighted blend using each matched
soft criterion's `weight` (equal weights if the mandate names no mappable soft factor).
No model calls.

**SCORES, NEVER CUTS.** Every survivor appears in `ranked`, stably sorted by
`factor_score` descending. Richer fundamentals-based factors (margins, growth,
leverage) are intentionally **not** computed here — they are evaluated per-name in
Stage 4 (`mandate-scorecard`).

## Run
```
python run.py --mandate-file mandate.json --survivors-file survivors.json
python run.py --mandate-json '{...}' --survivors-json '[{"ticker":"MSFT","market_cap":3e12,"adv":1e10,"sic_description":"services-prepackaged software"}]'
```
`--survivors-file` accepts either a bare JSON list of survivor dicts or the full
`universe-filter` output object (the `survivors` key is unwrapped automatically).

## Output (JSON)
`{ mandate_hash, ranked:[{ticker, company, factor_score, sub_scores:{size, liquidity, industry_fit}}],
factor_weights, note, summary }`
