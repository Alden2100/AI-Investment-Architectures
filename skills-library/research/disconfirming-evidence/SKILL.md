---
name: disconfirming-evidence
version: 1.0.0
description: Marshals tagged, cited EVIDENCE AGAINST a stock plus its risks — deteriorating
  metrics, threats, and red flags grounded in revenue/net-income trends, consensus estimates,
  target, and last price. Emits evidence objects only, never a thesis or buy/sell recommendation.
  Use when an adversarial idea-sourcing debate needs the disconfirming (case-AGAINST) side,
  "evidence against <ticker>", "what are the risks", or the bear side of a structured debate.
---
# Disconfirming Evidence

`run.py` deterministically gathers the same lightweight evidence base the case generators use —
a multi-year revenue and net-income series from XBRL, consensus estimates
(`estimates.get_consensus` + `consensus_growth`), and the last price (`prices.last_price`). The
model then marshals the DISCONFIRMING side: a list of tagged, cited evidence objects making the
case AGAINST the company plus its risks. This is Stage 6 of idea-sourcing v2 (the adversarial
debate pair). It produces EVIDENCE ONLY — never a thesis, conclusion, or recommendation, and no
buy/sell language.

Each evidence object is `{tag:"disconfirming", claim, citation, dimension, confidence}`, where
`dimension` is one of business/financials/moat/growth/valuation/management/risk and `citation`
points back at a provided figure or filing fact. With `--rebut` (a JSON list of the other side's
evidence) the skill may address those specific points in round 2 — still only as evidence.

## Hybrid model skill
`run.py` computes the fundamentals in Python, then routes the generation step at
`task="debate_generate"` (cheap qwen rung; the engine's confidence guard escalates hard cases).
With a Claude/qwen rung available it returns filled fields; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --ticker AAPL
python run.py --ticker AAPL --round 2 --rebut '[{"tag":"confirming","claim":"...","citation":"...","dimension":"growth"}]'
```

## Output (JSON)
`{ ticker, company, evidence: [ {tag, claim, citation, dimension, confidence} ], round, summary }`
