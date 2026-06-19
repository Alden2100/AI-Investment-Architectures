---
name: thesis-recorder
version: 1.0.0
description: Save an investment thesis and its KPI watchlist so research links to
  ongoing monitoring. Use when someone says "record my thesis", "save this
  investment case", "log my view on TICKER", "set up KPIs to track", "create a
  thesis with targets", or wants to persist a buy/sell rationale plus the metrics
  that would confirm or break it. The saved thesis is later read by kpi-tracker.
---
# Thesis Recorder

Deterministic write - the spine that links research to monitoring. **All logic
is in run.py.** Parses KPIs, persists via `store.save_thesis`, then reads back
with `store.get_thesis` to confirm the round-trip.

A KPI is `name:metric:comparator:target`. Metrics: `revenue`, `net_income`,
`operating_income`, `eps_diluted`, `price`, `return_1y`. Comparators: `>=`,
`<=`, `>`, `<`, `==`. If `--thesis-id` is omitted it is generated as
`TICKER-YYYYMMDD-<6hex>` (sha1 of ticker+title+body).

## Run
```
python run.py --ticker MSFT --title "Cloud compounder" \
  --body "Azure-led growth" \
  --kpi rev_floor:revenue:>=:3.0e11 --kpi stay_up:return_1y:>=:0.0
python run.py --ticker MSFT --title "Cloud compounder" --body-file thesis.md
```

Flags: `--ticker` (required), `--title` (required), `--body` or `--body-file`
(path), `--kpi` (repeatable name:metric:comparator:target), `--thesis-id`
(optional; else deterministic).

## Output (JSON)
`{ thesis_id, ticker, title, kpis:[...], created_at, summary }`
