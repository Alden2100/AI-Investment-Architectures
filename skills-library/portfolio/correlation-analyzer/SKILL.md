---
name: correlation-analyzer
version: 1.0.0
description: Measure how correlated a set of holdings are and how concentrated a
  portfolio is. Use whenever someone asks if positions move together, whether a
  book is diversified or too concentrated, "are these stocks correlated", hidden
  overlap / clustered risk, correlation matrix, or Herfindahl/concentration —
  even if they just list a few tickers and ask "is this risky together?".
---
# Correlation Analyzer

Pairwise return correlations and concentration metrics across holdings.
**All math is in run.py (numpy).** Daily log returns are aligned on the
intersection of trading dates before correlating.

Method: per ticker pull price history over the lookback, drop names with too
little data (noted in the summary), align on common dates, compute the Pearson
correlation matrix (`np.corrcoef`). Flags: pairs with |corr| ≥ `--corr-threshold`,
positions with weight ≥ `--weight-threshold`, and the Herfindahl index Σwᵢ²
(weights renormalized over surviving holdings).

## Run
```
python run.py --tickers MSFT AAPL GOOGL NVDA
python run.py --tickers MSFT AAPL GOOGL --weights 0.5 0.3 0.2 --corr-threshold 0.7
```

Flags: `--tickers` (2+, required), `--weights` (optional, same count; else
equal-weight), `--lookback` (days, default 365), `--corr-threshold` (default 0.8),
`--weight-threshold` (default 0.25).

## Output (JSON)
`{ tickers, weights, kept_tickers, lookback_days, overlapping_days,
correlation_matrix (ticker->ticker->float), avg_pairwise_correlation,
herfindahl_index, concentration_flags: [...], summary }`
