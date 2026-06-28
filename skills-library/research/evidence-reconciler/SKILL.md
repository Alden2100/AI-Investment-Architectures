---
name: evidence-reconciler
version: 1.0.0
description: Reconcile materially conflicting confirming vs disconfirming evidence about
  a company into a balanced, evidence-based net read (never a thesis or recommendation).
  Use when the bull/confirming side and the bear/disconfirming side of a debate clash and
  someone asks to "reconcile the evidence", "weigh both sides", "resolve the conflict",
  or wants a balanced net read of opposing evidence. Stage 6 debate-overlay escalation tier.
---
# Evidence Reconciler

Takes two evidence lists — confirming and disconfirming — and, when the sides materially
conflict, has the model weigh both on the figures given, separate genuine conflicts from
superficial ones, and produce a balanced **net read of the evidence**. This is an
escalation overlay: it routes to the high-judgment (opus) rung. The output is strictly
EVIDENCE-BASED — it is **not** a thesis, rating, or buy/sell/recommendation, and contains
no recommendation language.

## Hybrid model skill
`run.py` parses the two evidence lists (deterministic), then routes the reconciliation
judgment (`task="debate_reconcile"` → opus rung):
- If a Claude/opus rung is available, it returns the filled fields (`_source: "cli"`/`"api"`).
- If not, it returns `{_needs_model: true, system, prompt, schema, ...}`. In that case
  **you (the agent running this skill) must read `prompt` and return a JSON object matching
  `schema`** — that JSON is the skill's structured output.

## Run
```
python run.py --ticker AAPL \
  --confirming '[{"tag":"confirming","claim":"74% gross margin","dimension":"financials"}]' \
  --disconfirming '[{"tag":"disconfirming","claim":"decelerating revenue growth","dimension":"growth"}]'
# or pass files instead:
python run.py --ticker AAPL --confirming-file conf.json --disconfirming-file disc.json
```

## Output (JSON)
`{ ticker, company, confirming_count, disconfirming_count, reconciled_view,
unresolved_conflicts: [{topic, confirming_says, disconfirming_says}],
weight_lean: "confirming|disconfirming|balanced", confidence: "high|medium|low", summary }`
