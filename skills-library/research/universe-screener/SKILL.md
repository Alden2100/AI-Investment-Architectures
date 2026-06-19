---
name: universe-screener
version: 1.0.0
description: Filter the investable universe of US public companies by mandate
  criteria — sector/industry (SIC), market-cap band, and liquidity. Use whenever
  someone wants to screen, filter, or build a list of stocks matching criteria, find
  candidates in a sector, or narrow the universe to a watchlist — even "give me
  large-cap software names" or "what companies match this mandate".
---
# Universe Screener

Filters the SEC universe (ticker↔CIK from `company_tickers.json`), cached locally.
Deterministic — all thresholds compared in Python.

Two tiers of filters:
- **Cheap** (run over the whole ~8k-name universe): name/title substring, explicit
  ticker list.
- **Expensive** (per-company SEC/price fetches; bounded by `--max-fetch`): SIC
  sector code/description, market-cap band, average daily dollar volume (liquidity).
  Market cap = latest reported shares outstanding × last price.

If expensive filters are requested on more than `--max-fetch` candidates, the
candidate set is truncated to that many (cheapest-filtered first) and the summary
says so — keeping the skill fast and free.

## Run
```
python run.py --name-contains "software" --limit 25
python run.py --ticker-in MSFT AAPL NVDA GOOGL --min-mcap 5e11
python run.py --ticker-in MSFT AAPL KO PEP --sic-contains beverage
```

Flags: `--name-contains`, `--ticker-in` (list), `--sic` (exact code),
`--sic-contains` (description substring), `--min-mcap`/`--max-mcap` (USD),
`--min-adv` (avg daily $ volume), `--max-fetch` (default 30), `--limit` (default 50).

## Output (JSON)
`{ criteria, matches: [{ticker, title, sic_description?, market_cap?, adv?}],
count, truncated, summary }`
