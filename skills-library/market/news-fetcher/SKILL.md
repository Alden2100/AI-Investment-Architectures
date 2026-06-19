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
```

Flags: `--ticker` (required), `--lookback` (calendar days, default 30),
`--no-google` (SEC filing alerts only).

## Output (JSON)
`{ ticker, items: [{ title, date, source, url }], count, summary }`
Items are sorted newest-first.
