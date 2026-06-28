---
name: universe-filter
version: 1.0.0
description: Stage 1 of the opportunity funnel. Applies ONLY the hard_constraint
  criteria of a MandateSpec (plus exclusions) against the company_metrics snapshot
  and emits survivors + a verbatim reject log with no silent drops. Use when someone
  wants to apply a mandate's hard rules to the universe, narrow names by country /
  market-cap / SIC sector, or get an auditable pass/reject list before ranking.
---
# Universe Filter

Deterministic Stage-1 screen for the `opportunity/` drawer. It takes a **MandateSpec**
JSON and tests every criterion whose `type == "hard_constraint"` (and that has a
mappable `field` + `operator` + `value`) against the size-aware `company_metrics`
snapshot, then applies the mandate's `exclusions[]` as hard removals. There are no
model calls — every decision is reproducible from the snapshot and the mandate.

**NO SILENT DROPS.** A name is removed only when a hard constraint *definitively*
fails. If the metric a hard field needs is NULL/missing/non-comparable, the name is
**kept** and a per-name entry is added to `kept_notes`. Soft-preference and qualitative
criteria are never applied here — those flow to Stage 2 (`factor-ranker`) and Stage 4
(`mandate-scorecard`).

## Field & operator support
- Fields: `country`→country, `market_cap`/`mcap`→market_cap, `sic`/`sector`/`industry`→sic,
  `adv`/`liquidity`→adv.
- Operators: `in`, `not_in`, `gte`, `lte`, `gt`, `lt`, `between`, `eq`, `ne`.
- `sic` with `in`/`not_in` matches `int(sic)` for numeric values AND case-insensitive
  substrings of `sic_description` for word values (e.g. value `"software"`).
- `exclusions[]` entries remove by exact ticker or by an industry word found in
  `sic_description`.

## Run
```
python run.py --mandate-file mandate.json
python run.py --mandate-json '{"criteria":[{"id":"c1","type":"hard_constraint","field":"market_cap","operator":"gte","value":1e10}]}'
```

## Output (JSON)
`{ mandate_hash, survivors:[{ticker, company, market_cap, sic, sic_description, adv, country}],
rejects:[{ticker, removed_by, constraint, value_seen}], kept_notes:[{ticker, criterion, note}],
applied_constraints, coverage:{snapshot_names, universe}, summary }`
