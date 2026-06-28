---
name: compliance-review
version: 1.0.0
description: Reviews communications and documents for compliance concerns — performance-claim
  rules, return guarantees, misleading statements, and potential MNPI. Use when someone asks
  to "compliance-check this", "review this email/marketing for compliance", "flag regulatory
  issues", or "is this client communication compliant".
---
# Compliance Review

Reviews a communication or document and flags regulatory concerns: unsupported or
uncontextualized performance claims, return guarantees / "no risk" language, misleading or
unbalanced statements, omitted material risks, and potential use or disclosure of material
non-public information (MNPI). High-stakes judgment, so it routes to the opus rung.

## Hybrid model skill
`run.py` assembles the input and routes the judgment step. With a Claude/opus rung
available it returns the filled review; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil. This is the
high-judgment tier — it fails loud (`_needs_model`) rather than silently degrading.

## Run
```
python run.py --text "Our fund guarantees 20% annual returns with no risk."
python run.py --file client_email.txt
```

## Output (JSON)
`{ flags: [{ issue, severity, excerpt, rule }], overall_risk, summary }`
