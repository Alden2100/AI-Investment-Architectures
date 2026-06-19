---
name: audit-logger
version: 1.0.0
description: Record what was done and why as a timestamped audit entry, and list
  recent entries. Use when someone says "log this", "record this decision", "add
  an audit entry", "note that I did X", "keep a paper trail", "show the audit
  log", or wants an immutable, timestamped record of actions (trades, thesis
  edits, overrides) with actor/action/target/detail. Writes persist across runs.
---
# Audit Logger

Deterministic write. **All logic is in run.py.** Without `--list`, appends an
entry via `store.append_audit` and returns it (with its `id` and server `ts`).
With `--list`, returns the most recent entries via `store.list_audit`.

## Run
```
python run.py --actor analyst --action rebalance --target MSFT --detail "trimmed to 5%"
python run.py --action note --detail "reviewed thesis"
python run.py --list --limit 20
```

Flags: `--actor` (default "analyst"), `--action` (required unless `--list`),
`--target` (default ""), `--detail` (default ""), `--list` (return recent entries
instead of writing), `--limit` (default 20).

## Output (JSON)
Write: `{ id, ts, actor, action, target, detail, summary }`.
List: `{ entries:[...], count, summary }`.
