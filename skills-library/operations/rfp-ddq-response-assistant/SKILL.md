---
name: rfp-ddq-response-assistant
version: 1.0.0
description: Drafts DDQ/RFP responses grounded in prior firm materials (boilerplate, fact
  sheets, past answers), flagging where human input is still needed. Use when someone asks to
  "draft answers to this RFP", "respond to this DDQ", "fill in these RFP questions from our
  boilerplate", or "help answer a due-diligence questionnaire".
---
# RFP / DDQ Response Assistant

Takes a set of DDQ/RFP questions plus (optionally) firm materials to ground answers in, and
drafts a response per question. Answers are grounded strictly in the supplied materials — no
firm-specific facts are invented; any question the materials cannot answer is marked
`needs_input=true` for a human to complete.

## Hybrid model skill
`run.py` assembles the questions and materials and routes the drafting step. With a
Claude/opus rung available it returns the drafted responses; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --questions-file rfp_questions.txt --materials-file firm_boilerplate.txt
python run.py --questions "Describe your firm's ESG policy. State your AUM." --materials "..."
```

## Output (JSON)
`{ responses: [{ question, draft_answer, needs_input }], summary }`
