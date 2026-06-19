---
name: comps-builder
version: 1.0.0
description: Build a comparable-company multiples table (EV/EBITDA, P/E, P/S) for a
  peer set, and optionally value a target off the peer medians. Use whenever someone
  wants comps, trading multiples, relative valuation, "how does it compare to
  peers", or a peer-implied price.
---
# Comps Builder

Deterministic. For each peer it computes market cap (price × shares), enterprise
value (market cap + net debt), and the multiples EV/EBITDA, P/E, P/S from reported
XBRL financials and live prices. Takes the median of each multiple. With a
`--target`, it applies the peer medians to the target's own metrics to derive an
implied value per share.

EBITDA = reported operating income + D&A (D&A reconstructed from Depreciation +
Amortization when no combined tag is filed). All numbers computed in Python.

## Run
```
python run.py --tickers MSFT GOOGL ORCL ADBE
python run.py --tickers MSFT GOOGL ORCL --target CRM
```

Flags: `--tickers` (peer set, required), `--target` (optional ticker to value off
the peer medians).

## Output (JSON)
`{ peers, table: [{ticker, market_cap, ev, ev_ebitda, pe, ps}], median:
{ev_ebitda, pe, ps}, target_implied_value: {by_ev_ebitda, by_pe, by_ps, average},
summary }`
