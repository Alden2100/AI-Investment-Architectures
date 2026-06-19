---
name: fundamentals-fetcher
version: 1.0.0
description: Get a public company's structured financials (revenue, margins, EPS,
  cash flow, balance sheet) from SEC XBRL data. Use whenever someone needs a
  company's numbers, financial statements, fundamentals, or a specific line item
  like revenue, net income, EBIT, or free cash flow — even a casual "what are
  Microsoft's financials" or "how much does Apple earn".
---
# Fundamentals Fetcher

Returns structured financials from SEC's free XBRL `companyfacts` data, cached
locally. Deterministic — values are reported figures pulled straight from filings,
never computed by a model. Handles XBRL tag drift by trying several candidate tags
per line item (companies change the tag a line item is reported under over time).

## Run
```
python run.py --ticker MSFT                       # all standard line items, latest annual
python run.py --ticker AAPL --items revenue net_income eps_diluted
python run.py --ticker MSFT --periods 5           # last 5 annual values per item
```

Flags: `--ticker` (required), `--items` (subset of the line items below; default
all), `--periods` (how many trailing annual periods to include, default 4).

Line items: revenue, cost_of_revenue, gross_profit, operating_income, net_income,
eps_basic, eps_diluted, shares_diluted, total_assets, total_liabilities,
stockholders_equity, cash, total_debt, operating_cash_flow, capex,
depreciation_amortization, ebitda (computed = operating_income + D&A).

## Output (JSON)
`{ ticker, financials: {item: latest_value}, detail: {item: {value, period_end, fy,
tag, unit}}, periods: [{item, series: [{period_end, value}]}], summary }`
