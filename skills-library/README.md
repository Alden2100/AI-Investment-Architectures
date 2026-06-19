# skills-library

One canonical copy of every reusable **skill** and **agent**, organized into
category drawers plus `_shared/` cross-cutting infrastructure. Systems never copy
these — they symlink the exact versions they need (see `../link.py`).

## Drawers (mapped to the investment process)
| Drawer | Stage | Skills |
|---|---|---|
| [research/](research) | universe, idea sourcing, thesis | universe-screener · catalyst-flagger · moat-analyzer · thesis-recorder |
| [filings/](filings) | due diligence on disclosures | filing-fetcher · filing-summarizer · filing-change-detector · earnings-call-summarizer |
| [market/](market) | market & company data | price-fetcher · news-fetcher · fundamentals-fetcher |
| [valuation/](valuation) | valuation | dcf-valuation · comps-builder · comps-refresher · scenario-analyzer |
| [portfolio/](portfolio) | sizing, monitoring | position-sizer · correlation-analyzer · rebalance-checker · risk-limit-checker · kpi-tracker |
| [reporting/](reporting) | reporting, governance | memo-writer · letter-drafter · deck-updater · audit-logger |
| [_shared/](_shared) | infrastructure | data-fetch (imdata) · router (imrouter) · web-search |
| [agents/](agents) | reusable roles | screening-analyst · filing-analyst · valuation-analyst · portfolio-risk-monitor · report-writer |

## Anatomy of a skill
```
<drawer>/<skill>/
  SKILL.md      # YAML frontmatter (name, version, description) + lean instructions
  run.py        # computes every number; emits one JSON object incl. `summary`
  references/   # (optional) detail kept out of SKILL.md for token efficiency
```
A skill's `SKILL.md` **is** its documentation (frontmatter + how-to-run + output
shape) — there is deliberately no separate per-skill `README.md` to keep the tree
lean and avoid duplication.

### Deterministic vs. hybrid (model) skills
- **Deterministic** skills compute and return numbers directly (dcf, comps, risk,
  correlation, screening, fetchers…).
- **Hybrid (model)** skills do deterministic data-prep, then hand a prepared
  prompt + JSON schema to the **router** (`imrouter.route`), which dispatches to
  qwen or Claude per policy. Any number is still computed in Python and quoted;
  the model only reasons qualitatively. These are: filing-summarizer,
  filing-change-detector, earnings-call-summarizer, catalyst-flagger,
  moat-analyzer, memo-writer, letter-drafter.

## Versioning
Every `SKILL.md`/agent carries a semver `version`. Systems pin versions in their
`manifest.yaml`; `link.py --check` flags any drift between a manifest and the
library.

## The leaf rule
Skills never import or call each other — they're leaves. Composition is the job of
a system's **orchestrator**, which calls skills via `imdata.skillkit.call_skill`
(resolving them through the system's manifest-pinned `.claude/skills`).
