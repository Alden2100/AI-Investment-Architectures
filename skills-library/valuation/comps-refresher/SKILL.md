---
name: comps-refresher
version: 1.0.0
description: Re-pull and refresh an existing comparable-company multiples table with force-fresh prices and financials for a saved peer set. Use when the user asks to refresh comps, update a comps table, re-pull peer multiples, or get the latest comps numbers.
---

# comps-refresher

Rebuilds a comps multiples table for a peer set, forcing fresh data first:
`edgar.refresh_facts(ticker)` and `prices.refresh_prices(ticker, force=True)` are
called before any value is read. All numbers are computed in Python.

Per ticker it computes market_cap (last_price x shares), EV (market_cap + net_debt,
net_debt = debt - cash), EV/EBITDA, P/E (mcap/net_income), P/S (mcap/revenue), then
medians across peers. With `--target`, an implied per-share value is derived from
the peer medians (by_ev_ebitda, by_pe, by_ps, average).

## Run

```
python skills/comps-refresher/run.py --tickers MSFT GOOGL ORCL
python skills/comps-refresher/run.py --tickers MSFT GOOGL ORCL --target MSFT
```

## Output (JSON)

- `peers`, `refreshed` (always true)
- `table`: [{ticker, market_cap, ev, ev_ebitda, pe, ps}]
- `median`: {ev_ebitda, pe, ps}
- `target`, `target_current_price`, `target_implied_value` (when `--target` given)
- `summary` (notes that data was force-refreshed)
