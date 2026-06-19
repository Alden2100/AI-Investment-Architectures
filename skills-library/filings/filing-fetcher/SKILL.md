---
name: filing-fetcher
version: 1.0.0
description: Fetch a public company's SEC filings (10-K, 10-Q, 8-K, etc.) or a
  specific filing's full text. Use whenever someone needs a company's filings, the
  latest annual or quarterly report, an 8-K, or the actual text of a filing to read
  or analyze — even a casual "pull up Apple's 10-K" or "what did they file recently".
---
# Filing Fetcher

Returns SEC filings for a ticker from EDGAR (cached locally). Deterministic — no
model reasoning, no computed numbers; it only retrieves and shapes data.

## Run
```
python run.py --ticker MSFT --form 10-K --limit 1 --with-text
python run.py --ticker AAPL --form 10-Q --start 2023-01-01 --end 2024-12-31
python run.py --ticker MSFT          # most recent filings of any form
```

Flags: `--ticker` (required), `--form` (e.g. 10-K, 10-Q, 8-K), `--start`/`--end`
(YYYY-MM-DD), `--limit` (default 10), `--with-text` (fetch full plain text of each
returned filing — omit for metadata only, since filing text is large).

## Output (JSON)
`{ ticker, filings: [{ form, date, accession, url, text? }], count, summary }`
