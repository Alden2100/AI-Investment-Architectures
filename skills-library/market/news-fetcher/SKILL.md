---
name: news-fetcher
version: 1.0.0
description: Get recent news headlines and SEC filing alerts for a public company.
  Use whenever someone wants the latest news, headlines, recent developments, or
  filing activity for a stock — even a casual "what's the latest on Microsoft" or
  "any news on this name".
---
# News Fetcher

Returns recent news (Google News RSS) and SEC filing alerts (EDGAR Atom feed),
cached locally. Deterministic retrieval — no model reasoning.

## Run
```
python run.py --ticker MSFT --lookback 30
python run.py --ticker AAPL --lookback 7 --no-google   # filing alerts only
python run.py --ticker MSFT --full --full-max 5         # try to attach article bodies
```

Flags: `--ticker` (required), `--lookback` (calendar days, default 30),
`--no-google` (SEC filing alerts only), `--full` (attempt to fetch + extract the
article BODY for the top items), `--full-max` (default 5), `--full-timeout`
(per-URL seconds, default 10).

## Output (JSON)
`{ ticker, items: [{ title, date, source, url, body? }], count, bodies_extracted, summary }`
Items are sorted newest-first.

`--full` adds a `body` field where the page is openly fetchable (keyless,
trafilatura). **Caveat:** Google News RSS links are redirect/consent pages and SEC
Atom links are filing-index pages, so most items here won't yield a body — for real
article text prefer `web-search --full` (direct publisher URLs). Bodies cache to the
store (7-day TTL); failures are skipped, never fatal.
