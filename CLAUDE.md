# AI Investment Architectures — operating instructions

This repo is **seven orchestrated systems** (idea-sourcing, valuation, reporting,
filing-intelligence, portfolio-monitoring, due-diligence, governance-audit) built on a
shared skill/data library. Each system has a Python **orchestrator** that runs the
whole pipeline deterministically and makes its own model calls through a router.

## Run the orchestrator — do NOT hand-orchestrate the leaf skills

When a request maps to one of the systems (source/screen/shortlist ideas; value a
stock; write an IC memo/letter; analyze a filing; check a portfolio; due diligence;
governance audit), **run that system's orchestrator as a subprocess and relay its JSON
output.** Do not run `universe-screener` / `dcf-valuation` / `comps-builder` /
`catalyst-flagger` etc. individually and assemble the answer yourself, and do not
screen, curate a ticker list, score, rank, or draft in your own context.

Why this matters: the **composite score and the per-task model routing
(qwen → sonnet → opus) live inside the orchestrator's `main()`**, not in the leaf
skills. If you do the judgment yourself you silently collapse the model ladder to a
single model and drop the deterministic scoring — the output looks fine but bypasses
the system.

### How to run (repo root, venv active: `source .venv/bin/activate`)

```bash
# Natural language front door — routes intent, runs the right orchestrator, writes a
# PDF when asked. Prefer this:
python ask.py "find mid-cap US software companies and export the shortlist as a PDF"

# Or call a system orchestrator directly, e.g.:
python systems/idea-sourcing/orchestrator.py --sic-contains software --min-mcap 2e9 --max-mcap 1e10 --us-only
python systems/reporting/orchestrator.py --memo MSFT
python systems/portfolio-monitoring/orchestrator.py --positions NVDA=0.3 MSFT=0.2 --max-weight 0.1
```

Cold machine, first sector/size screen: warm the universe index once (then cached):
`python -m imdata.screener --refresh --max-names 3000` (repeat to page the universe).

### Present + verify

Relay the orchestrator's JSON (shortlist/scores/theses, `data_flags`, `setup_hint`)
and the PDF path it prints. **Always surface `model_routing`** and confirm the ladder
engaged — e.g. `classification→qwen; synthesis→sonnet`. If `model_routing` shows one
model for everything or is absent, you judged inline: re-run the orchestrator instead
of analyzing the names yourself. (qwen needs a local Ollama; without it cheap steps log
`local_unavailable` and fall back to sonnet — that's expected, not a bug.)
