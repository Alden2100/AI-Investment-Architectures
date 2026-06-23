---
name: idea-sourcing
version: 1.0.0
description: >
  Source investable equity ideas END TO END — screen the universe by mandate
  (sector / market-cap band / US-only), enrich each name, score it, and RANK into a
  shortlist with a one-line thesis + catalyst per name. Use whenever someone wants to
  find / screen / shortlist ideas or names in a sector, size band, or theme — "mid-cap
  US software ideas", "screen utilities", "give me a clean-energy shortlist", "what
  names look interesting in X". Prefer this over invoking universe-screener /
  dcf-valuation / comps-builder individually: this runs the whole pipeline as ONE
  routed command and is the source of truth for a shortlist.
---
# Idea Sourcing (orchestrated system)

**RUN THE ORCHESTRATOR. Do not hand-orchestrate the leaf skills, and do not screen,
curate, score, or rank in your own context.** The pipeline runs
screen → enrich → score → rank as a single subprocess that:

- screens the size-aware universe snapshot (no hand-curated ticker list needed),
- computes a **deterministic composite score** (value · growth · quality · catalyst ·
  momentum) that is the ranking anchor — the crude DCF is *not* the headline,
- **routes each model step per task** — catalyst tagging → qwen, ranking → sonnet,
  escalating to opus — and records the mix in the output's `model_routing`,
- writes the branded PDF.

If you do the judgment yourself, you bypass the qwen→sonnet→opus router (everything
silently becomes one model) **and** lose the composite score. That is the failure to
avoid.

## How to run

From the repo root, with the venv active (`source .venv/bin/activate`):

```bash
# Natural language (recommended) — routes intent, runs this orchestrator, writes a PDF
# when the request asks for one:
python ask.py "find mid-cap US software companies and export the shortlist as a PDF"

# Or call the orchestrator directly:
python systems/idea-sourcing/orchestrator.py \
    --sic-contains software --min-mcap 2e9 --max-mcap 1e10 --us-only --max-candidates 6
```

Mandate flags: `--sic-contains <sector>` (synonyms like `software`, `biotech`, `reit`,
`defense` map to the right SIC set), `--min-mcap` / `--max-mcap` (USD), `--us-only`,
`--ticker-in T1 T2 …`, `--theme "value"`, `--max-candidates N`.

First run on a cold machine: warm the universe index once (then it's cached):
`python -m imdata.screener --refresh --max-names 3000` (repeat to page the universe).

## What to present

Relay the orchestrator's JSON shortlist (ticker, rank, verdict, `composite_score` +
`scores`, thesis, catalyst) and the PDF path it printed. Surface any `data_flags`,
`setup_hint`, and the `model_routing`.

## Verify routing (every run)

The output includes `model_routing`. Confirm it shows e.g.
`classification→qwen; synthesis→sonnet` (opus appears only on an escalation; qwen needs
a local Ollama, else it logs `local_unavailable` and falls back to sonnet). **If it
shows one model for everything or is absent, you judged inline — re-run the orchestrator
command above instead of analysing the names yourself.**
