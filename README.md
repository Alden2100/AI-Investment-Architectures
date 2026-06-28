# AI Investment Architectures

Production architecture for an AI investment-consulting firm: a **library** of
composable, versioned skills and agents, and a set of **systems** (apps) that wire
them into runnable, auditable investment workflows. Built on the design principles
of the *AI Investment OS* field guide.

## The two governing principles

1. **Code for what's exact, model for what's judged.** Every number — DCF math,
   XBRL parsing, drift, exposure, correlation, KPI checks — is computed in Python
   and quoted exactly. The model is used only where judgment is the product:
   ranking a shortlist, reconciling a value range, triaging risk, writing a memo.
   Auditable checks (risk limits, eligibility, breaches) are **always**
   deterministic and never decided by a model.

2. **Commit the recipe, regenerate the cake.** Git holds only the source of truth:
   skill code, agent contracts, manifests, orchestrators, policies. Everything
   derivable — the SQLite databases, fetched data, outputs, and the materialized
   `.claude/skills` symlinks — is git-ignored and rebuilt on demand (`link.py`
   re-creates the symlinks from each manifest; the DB rebuilds from free sources).

Two more from the guide run through every decision:

- **Mechanism vs. policy.** One router *engine* (`_shared/router`) is identical
  everywhere; each system's `router-policy.yaml` is the only thing that differs —
  it decides which work goes to the local **qwen3.5:9b** (cheap, on-box) and which
  goes to **Claude** (heavy reasoning, synthesis, final drafting, judgment).
- **The orchestration spectrum.** Orchestrators are deterministic by default; they
  delegate one bounded judgment to the model where it earns its cost, then resume
  code — and every model-made decision is logged for audit.

## Layout

```
AI-Investment-Architectures/
├── skills-library/              # one canonical copy of every reusable piece
│   ├── _shared/                 # cross-cutting infrastructure
│   │   ├── data-fetch/imdata/   # SEC EDGAR · prices · news · universe · SQLite store
│   │   ├── router/imrouter/     # the routing ENGINE (Claude + qwen clients)
│   │   └── web-search/          # keyless DuckDuckGo search skill (Brave if keyed)
│   └── research/  filings/  market/  valuation/  portfolio/  reporting/  operations/  mandate/  opportunity/   # drawers
├── agents-library/             # reusable agent role files (contracts only) — its own top-level library
├── systems/                     # each subfolder is one app
│   ├── idea-sourcing/  filing-intelligence/  portfolio-monitoring/
│   ├── valuation/  reporting/                       # ← 5 full, runnable + tested
│   └── due-diligence/  governance-audit/            # ← scaffolded (real skills, stub synth)
├── link.py                      # materialize each manifest into .claude symlinks
├── requirements.txt · SETUP.md · .env.example
```

### Building blocks (the guide's four)
- **Skill** — a folder with `SKILL.md` (YAML frontmatter: `name`, `version`,
  `description`) + `run.py` (+ optional `references/`). One job; computes its own
  numbers; emits one JSON object with a `summary`. Lean by design — detail lives in
  `references/` (progressive disclosure).
- **Agent** — a single `.md` role file: mandate, instructions, allowed skills, and
  an input/output **contract only**. No hard-coded handoffs — wiring is the
  orchestrator's job — so agents are reusable across systems.
- **Orchestrator** — a Python file per system: deterministic control flow + the
  bounded model step (routed per policy, logged) + an entry point.
- **Router** — the mechanism that dispatches each model call to Claude or qwen.

## Quickstart

```bash
./setup.sh                       # venv + deps  (or: see SETUP.md)
python link.py                   # materialize every system's symlinks from its manifest
# run a full system end-to-end (keyless — uses local qwen for the model step):
.venv/bin/python systems/idea-sourcing/orchestrator.py --ticker-in MSFT AAPL NVDA
.venv/bin/python systems/valuation/orchestrator.py --ticker MSFT --peers AAPL GOOGL
.venv/bin/python systems/portfolio-monitoring/orchestrator.py \
    --positions NVDA=0.30 MSFT=0.20 AAPL=0.15 --max-weight 0.10
```

Each system has its own `README.md` (pipeline + how to run + manifest) and
`prompts.md` (tiered example prompts). See [SETUP.md](SETUP.md) for Ollama + qwen +
venv + keys, and [skills-library/README.md](skills-library/README.md) for the library.

### Prompt it like an LLM (`ask.py` / the `im` command)
`ask.py` is a natural-language front door: it interprets your request into
*(system, args)* — the judged part, via keyword heuristics + the router — and
dispatches to the orchestrator with exact CLI args — the exact part. It always
prints the plan before running.

```bash
python ask.py "what's Microsoft worth versus Apple and Google?"   # → valuation
python ask.py "any catalysts in large-cap software?"              # → idea-sourcing
python ask.py "is my book ok - NVDA 30%, MSFT 20%, cap 10%?"      # → portfolio-monitoring
python ask.py "what changed in Coca-Cola's latest 10-K?"          # → filing-intelligence
python ask.py "write an IC memo for Nvidia"                       # → reporting
python ask.py -n "..."     # dry-run: print the plan only
python ask.py valuation --ticker MSFT --peers AAPL GOOGL          # short form still works
```

For a permanent shortcut runnable from anywhere, add an `im` shell function (one
line in `~/.zshrc`):
```bash
im() { ( cd "/path/to/AI Investment Architectures" && ./.venv/bin/python ask.py "$@" ) }
# then:  im "is NVDA cheap vs AMD and AVGO?"
```

### Branded PDF output (only when you ask for it)
Any system can emit a clean, slide-deck-ready **PDF** in the Tensh Consulting Group brand —
but **only when the prompt explicitly asks for one** (default output stays plain text):
```bash
im "what's MSFT worth vs AAPL and GOOGL — export as a pdf"
im "memo for Nvidia, as a pdf"
im valuation --ticker MSFT --peers AAPL GOOGL --pdf      # short form
```
The PDF lands in `systems/<system>/data/output/`. Theme + palette live in
[skills-library/_shared/branding/](skills-library/_shared/branding/) (engine:
`imbrand`, colors from the vendored `colors.json`).

## How this maps to the field guide
| Guide concept | Here |
|---|---|
| Code vs. model | deterministic skills/orchestrator math + routed model steps |
| Commit the recipe, regenerate the cake | git tracks code/manifests; `data/`, `*.db`, symlinks are ignored & rebuilt |
| Mechanism vs. policy | one `imrouter` engine + per-system `router-policy.yaml` |
| Four building blocks | skills · agents · orchestrators · router |
| Orchestration spectrum | deterministic fan-out → one bounded routed judgment → resume code, all logged |
| Process stages | drawers: research → filings/market → valuation → portfolio → reporting; governance via audit log |

## Status
5 systems full (runnable + smoke-tested, keyless via qwen3.5:9b); 2 scaffolded.
25 library skills + 5 agents. See the closing summary in the repo or run
`python link.py --check` to validate every manifest against the library.
