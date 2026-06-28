---
name: crm-note-generator
version: 1.0.0
description: Converts a client interaction (call, meeting, email) into a structured CRM
  record with contact, type, summary note, and follow-ups. Use when someone asks to "log
  this client call in the CRM", "make a CRM note from these meeting notes", or "extract
  follow-ups from this client interaction".
---
# CRM Note Generator

Takes free-text notes from a client interaction and extracts a structured CRM record:
contact, date, interaction type, a summary note, and follow-up action items. This is a
pure extraction task — the model reads only what is stated and uses 'unknown' for missing
fields.

## Hybrid model skill
`run.py` assembles the input and routes the extraction step. With a Claude/qwen rung
available it returns the filled record; otherwise it returns
`{_needs_model: true, system, prompt, schema}` for the calling agent to fulfil.

## Run
```
python run.py --text "Call with Jane Doe 6/20: reviewed Q2, wants ESG options. Send fund list."
python run.py --file meeting_notes.txt
```

## Output (JSON)
`{ contact, date, type, summary_note, follow_ups: [], summary }`
