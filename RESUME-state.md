# Resume state — output-quality fixes (updated 2026-06-21)

## Done & verified
**Fix #1 — judgment layer on Claude CLI, fail-loud.** COMPLETE.
- `claude_client.py` rewritten: `claude -p --output-format json` subprocess; prompt via
  stdin; strips ANTHROPIC_API_KEY/AUTH_TOKEN (stays on Max subscription); resolves CLI via
  PATH + known dirs + `CLAUDE_CLI`; `available()` detects CLI; parses `.result`; raises on
  non-zero exit.
- `engine.py`: HIGH_JUDGMENT routes FAIL LOUD (`_needs_model` + WARNING) instead of silent
  qwen; stand-in only via `IM_ALLOW_DEGRADED=1`/`allow_degraded`; flagged `_degraded`.
- Surfacing: `orch.model_meta()`; PDF footer + ask.py show actual model + ⚠ DEGRADED.
- Docs (.env.example, router README), tests (`tests/router_cli_test.py`).

**Fix #2 — feed real material, raise tokens, drop terse, personas.** COMPLETE.
- `orchestration.py`: `persona()` + `HOUSE_STANDARD` + `_load_agent()` (loads the agent role
  files that were never loaded before).
- idea-sourcing: keeps the REAL catalysts array (was counts); content-rich ranking input.
- valuation/filing-intelligence/portfolio-monitoring: personas, richer prompts (filing MD&A
  prose added), raised max_tokens, de-tersed.
- reporting + memo-writer: analyst persona/rubric, inputs enriched (scenarios, comps table,
  full moat), max_tokens 3000→5000.
- Verified: theses now cite real drivers (EV/EBITDA vs median, DCF upside) even on qwen.

**Secondary — coherence check + agent-file personas.** COMPLETE.
- `orchestration.py`: `numeric_lean()`, `text_lean()`, `coherence()`.
- reporting: injects `valuation_signal` anchor (prevention) + post-check flags a memo rec that
  contradicts its DCF (detection) → `coherence_warning` in output + Report Contract + ask.py.
- Unit-tested (BUY vs DCF-50% → flagged); prevention confirmed end-to-end.

**Smoke suite 5/5 green; router/coherence tests 19/19 green.**

**Fix #4 — deepen analytics.** COMPLETE & validated on real Claude.
- dcf-valuation: 2-stage DCF (explicit + linear fade → terminal); WACC DERIVED (CAPM Ke with
  beta estimated vs SPY + after-tax Kd from real interest/debt, market-weighted, clamped) — no
  more hardcoded 9%. Carries `wacc_components`, `model`, terminal % of EV in assumptions.
- scenario-analyzer: mirrors the 2-stage math (base scenario == DCF intrinsic, verified);
  bull/bear widths scale to the company (growth band ∝ its growth, WACC band ∝ beta), not ±3%/±1%.
- valuation orchestrator: feeds scenario the DCF-derived inputs (growth, WACC, fade, beta) for coherence.
- comps-builder: adds PEG (growth-adjusted P/E), per-peer earnings growth + net margin, median PEG,
  and a PEG-implied (growth-adjusted) target value. (Forward/consensus multiples deferred → needs #3.)
- moat-analyzer: 5-yr margin TREND + 3-yr ROIC series (NOPAT/invested capital); fed to the model
  as durability evidence. Note: `margins` shape preserved for downstream consumers.
- Fixed the "raw float leaks" (0.3615 in prose): HOUSE_STANDARD + memo-writer now require
  percentages for ratios. Verified: memo financials section reads margins/ROIC correctly.
- Validated: Claude valuation now critiques the DCF's own capex/FCF treatment & beta; memo reads
  the ROIC-compression trend. Full smoke suite 5/5 on **Claude** (route=claude). Unit tests 19/19.

**Fix #3 — widen data (FREE, keyless tier).** DONE & validated on Claude.
- New `imdata/estimates.py` (yfinance, keyless, cached via new `store.kv_get/kv_put`):
  `get_consensus()` (forward EPS/rev estimates, growth, price target, recommendations, fwd PE/PEG),
  `get_ownership()` (float, institutional/insider %, short interest), `consensus_growth()` helper.
- Wired: valuation (DCF growth vs Street growth + value vs price target → differentiated view),
  reporting memo (consensus + ownership in inputs), idea-sourcing (target upside + recommendation
  per candidate), portfolio-monitoring (short-interest/crowding context in triage).
- Validated: Claude valuation now argues vs the 55-analyst consensus & $561 target; the
  "gap vs consensus" the brief said was missing now exists.

### #3 remaining — DEFERRED (need a NEW dependency; ask user before adding)
- SEGMENT KPIs: needs `edgartools` or Arelle (XBRL dimensional parse); companyfacts has NO
  segment dimensions. ~med effort once dep approved.
- NEWS ARTICLE BODIES: needs `trafilatura` (best keyless extractor). Google News RSS desc is junk.
- TRANSCRIPTS: no genuinely free programmatic source; closest free = EDGAR 8-K EX-99.1 earnings
  releases (could add via existing edgar infra, no new dep) — not yet built.

## Notes
`claude` CLI installed at ~/.local/bin/claude (v2.1.185), on subscription auth. Real path validated.
High-judgment FAILS LOUD without a session; `IM_ALLOW_DEGRADED=1` for qwen-only local testing.
Nothing committed — all in working tree.
