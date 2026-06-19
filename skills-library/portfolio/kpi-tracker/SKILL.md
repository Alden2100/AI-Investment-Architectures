---
name: kpi-tracker
version: 1.0.0
description: Check whether a stock's current fundamentals and price still satisfy
  the target KPIs of an investment thesis, and flag any breaches. Use when someone
  asks to "monitor my thesis", "are my KPIs still met", "check the watchlist
  targets", "did revenue/EPS/price hit the target", track thesis metrics, or
  verify thesis assumptions against current data. Pulls targets inline via --kpi
  or from a saved thesis via --thesis-id.
---
# KPI Tracker

Monitoring calculator. **All math is in run.py.** Resolves each KPI's current
value, then compares it to the target with the KPI's comparator.

A KPI is `name:metric:comparator:target`. Metrics: `revenue`, `net_income`,
`operating_income`, `eps_diluted` (latest annual 10-K XBRL value), `price`
(last close), `return_1y` (365d close[-1]/close[0]-1). Comparators: `>=`, `<=`,
`>`, `<`, `==` (approx). Status is `ok`, `breach`, or `unknown` (value missing).

## Run
```
python run.py --ticker MSFT --kpi rev_floor:revenue:>=:3.0e11
python run.py --ticker MSFT --kpi rev_floor:revenue:>=:3.0e11 --kpi up_1y:return_1y:>=:0.0
python run.py --thesis-id MSFT-20260614-abc123
python run.py --thesis-id MSFT-20260614-abc123 --kpi extra_price:price:<=:600
```

Flags: `--ticker` (required unless `--thesis-id` given), `--thesis-id` (loads
KPIs + ticker from the store), `--kpi` (repeatable, `name:metric:comparator:target`).

## Output (JSON)
`{ ticker, thesis_id?, kpis:[{name,metric,comparator,target,current,status}],
breaches:[names], summary }`
