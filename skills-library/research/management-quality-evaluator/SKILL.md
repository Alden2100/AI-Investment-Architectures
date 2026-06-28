---
name: management-quality-evaluator
version: 1.0.0
description: Assesses management's track record of execution and capital allocation from
  multi-year XBRL series — diluted share count, buybacks, dividends, long-term debt, and
  ROIC. Use when someone asks "how good is management", "evaluate capital allocation", "are
  the buybacks accretive", "is management diluting shareholders", or "management quality".
---
# Management Quality Evaluator

`run.py` deterministically pulls multi-year annual (10-K) series for diluted shares
(`WeightedAverageNumberOfDilutedSharesOutstanding`), buybacks
(`PaymentsForRepurchaseOfCommonStock`), dividends (`PaymentsOfDividendsCommon` /
`PaymentsOfDividends`), and long-term debt, and computes a multi-year ROIC series
(NOPAT / invested capital, the same method as moat-analyzer). The model then judges the
capital-allocation track record and flags risks.

## Hybrid model skill
`run.py` computes every series in Python, then routes the judgment step. With
ANTHROPIC_API_KEY (or a Claude/qwen rung available) it returns filled fields; otherwise it
returns `{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
```

## Output (JSON)
`{ ticker, capital_allocation:{buybacks, dividends, debt_trend, shares_trend}, roic_series,
track_record, red_flags, summary }`
