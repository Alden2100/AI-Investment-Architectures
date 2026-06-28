# Claude Code — idea-sourcing improvement plan

**Repo:** `AI-Investment-Architectures` (origin: `github.com/Alden2100/AI-Investment-Architectures`, branch `main`)
**Target system:** `systems/idea-sourcing/` + shared `skills-library/_shared/`
**Goal:** turn the funnel from "filter whatever happened to be cached" into the intended "broad universe → hard cuts → soft cuts," fix the ranking/calibration bugs, and apply a temporary speed profile to routing. Push all changes to GitHub.

This brief is ordered by leverage. **Phases 1–2 deliver ~80% of the quality improvement.** Phase 6 (speed) is independent config and can be landed first as a quick win.

---

## Ground rules (do not violate)

- **Never commit data.** `*.db`, `data/`, `.cache/`, `output/` are gitignored — keep it that way. The 1.1 GB SQLite DB must never enter git. Run `git status` before every commit and confirm no `.db` is staged.
- **Preserve auditability.** The "no silent drops" principle stays — names are *re-routed to a `needs_data` bucket*, not deleted, and every rejection stays queryable in `reject_log`.
- **Preserve the architecture invariant:** deterministic skills compute numbers; the model only judges. Phase 4 actually strengthens this.
- **Keep multi-model routing.** Phase 6 rebalances the ladder for speed but must NOT collapse to a single model — qwen, sonnet, and opus all remain in use.
- **Tests gate commits.** `tests/run_smoke_tests.py` and the system's `systems/idea-sourcing/tests/` must pass before each push.

---

## Phase 0 — Setup & baseline

1. Branch: `git checkout -b improve/idea-sourcing-funnel`.
2. Capture a baseline so changes are measurable: run the original mandate (the concentrated-compounders spec) through `orchestrator.py --spec-file <spec> --top-k 20` and save the JSON output as `baseline_run.json` *outside* git (e.g. in `data/`). Record: survivor count, snapshot coverage, the top-20 tickers, and wall-clock.
3. Confirm the test suite is green before changing anything.

---

## Phase 1 — Mandate-driven universe warming  *(dominant fix)*

**Problem.** `universe-filter/run.py` screens `store.all_metrics()` (the 179-row `company_metrics` table), not the 10,433-row `companies` table. `companies` holds only `ticker/cik/title` — nothing screenable — so hard constraints can only touch pre-warmed names. Warming exists (`screener.refresh_metrics`) but is stale-ordered and never invoked by the orchestrator.

**Fix — tier the hard constraints by data cost, warm only what survives the cheap cuts.**

1. **Cheap pre-screen on the full universe (industry + geography).** SIC and country come from one SEC submissions call per name (`edgar.company_meta`), no price/quote fetch. Add `screener.prescreen_universe(mandate)`:
   - Iterate the full `companies` list; for each, fetch/cached `company_meta` → `sic`, `sic_description`, `country`.
   - Persist these so the classification is reused across runs. Either add `sic`, `sic_description`, `country` columns to `companies`, or add a light `company_classification` table keyed by ticker. (Prefer the latter to keep `companies` as a clean identifier table.)
   - Apply only the *cheap* hard constraints + exclusions here: preferred industries, avoid-list industries, North America / W. Europe. Reuse the existing `SECTOR_SYNONYMS` + `_sic_token_match` logic from `universe-filter/run.py` (factor it into a shared helper so both stages use one implementation).
   - Output: a candidate ticker list (expect a few hundred to ~2,000).
2. **Warm only the candidates.** Call `screener.refresh_metrics(tickers=candidates)` to compute `market_cap` + `adv` for that reduced set. Bounded + resumable; respect `SEC_MAX_RPS` (8). Show progress.
3. **Wire it into the orchestrator** ahead of Stage 1, behind a flag (default on) so a run first ensures its mandate-relevant slice is warmed, then Stage 1 filters a populated snapshot. The expensive `mcap ≥ $2B` + liquidity cuts now run in Stage 1 as today.

**Files:** `skills-library/_shared/data-fetch/imdata/screener.py` (prescreen + mandate-driven warm), `imdata/store.py` (classification storage + a "tickers needing classification" query), `imdata/edgar.py` (reuse `company_meta`), `systems/idea-sourcing/orchestrator.py` (call warm before Stage 1), maybe a new `stages/stage0b_warm.py` driver.

**Acceptance:** for a software/medtech/fintech mandate, post-run `company_metrics` count is in the hundreds–thousands (not 179); survivors include names from the mandate's *preferred* industries; the coverage line reads like "1,840 classified → 540 warmed → 210 survivors." First run is slow (one-time SEC fetch), subsequent runs fast (cached, 7-day TTL).

---

## Phase 2 — Gate on quality, not size

**Problem.** `orchestrator.py` gates `top_k` on the Stage-2 `factor_score`, which is size/liquidity/industry_fit. So entry into the expensive stages is decided by market cap → mega-caps dominate. Worse, Stage 3 text-similarity (the cheapest, most direct mandate-fit proxy) runs *after* the gate.

**Fix.**

1. **Move Stage 3 text-similarity before the gate.** Run it over all survivors (it's numpy TF-IDF, cheap, no API).
2. **Gate on a quality composite**, not size: blend text-fit + industry_fit + "core-metrics-present" and take `top_k` on that. Log the gate drops exactly as today (no silent drops).
3. **Demote size to a floor.** In `factor-ranker/run.py`, treat market cap as pass/fail at the mandate's floor; drop or heavily down-weight the size *percentile* in `factor_score`. For a compounder mandate, bigger is not better.
4. **Reweight the opportunity score** in `stage7_rank.build`: cut `0.20·factor` to ~`0.10`, raise text/qual. Ideally make the weights mandate-aware (a quality mandate → near-zero size weight).

**Files:** `orchestrator.py` (reorder Stage 3 ahead of the gate; gate on composite), `skills-library/opportunity/factor-ranker/run.py`, `stages/stage7_rank.py`.

**Acceptance:** mega-caps no longer top a quality-compounder mandate; the set entering the scorecard correlates with text/industry fit, not market cap.

---

## Phase 3 — Quarantine incomplete names + fix confidence

**Problem.** Names with null market cap pass Stage 1 (no-silent-drop), clear the size-blind gate, and land in the ranked top-20 with `fit=0.00` and no evidence. And confidence is inverted: `conf = "low" if len(flags) >= 2 else ... else "high"` — so a name with *zero data* (no flags) shows **high** confidence while fully-evaluated names show **low**.

**Fix.**

1. **`needs_data` bucket.** In `universe-filter/run.py` (and carried through the orchestrator), route names missing a core metric (null `market_cap`) to a separate `needs_data` list that never enters the gate or the ranked output. Report them in their own report section (the PDF already has a "data-incomplete" area — feed it from this bucket).
2. **Confidence from data completeness.** In `stage7_rank.build`, derive confidence from coverage (criteria evaluated / total, evidence present), not flag count. No evidence ⇒ `low`. A clean, fully-evaluated name ⇒ `high`.

**Files:** `universe-filter/run.py`, `orchestrator.py`, `stage7_rank.py`, the PDF/report builder.

**Acceptance:** zero `fit=0.00` rows in the ranked top-20; no "data-incomplete + high confidence" rows anywhere; incomplete names appear only in their own section.

---

## Phase 4 — Scorecard integrity + honest "reasons"

**Problem.** `overall_fit` (the 0.45-weight component) is produced *by the model* as a free-form roll-up; trivial already-enforced hard constraints get re-scored as "meets" and inflate it; the "top 3 reasons" surface tautologies ("publicly listed," "'Inc.' implies US"); and portfolio-construction constraints (max-2-per-industry) are mis-scored as per-company criteria.

**Fix.**

1. **Deterministic `overall_fit`.** The model returns only per-criterion `verdict` + `evidence` + `confidence`. Python computes `overall_fit` as the weight-aware roll-up (`meets=1, partial=0.5, does_not_meet=0`). Remove `overall_fit` from the model's output schema in `mandate-scorecard/run.py`.
2. **Exclude already-enforced hard constraints** from the fit roll-up so it reflects the qualitative/financial criteria that actually express the mandate (moat, ROIC>15%, recurring revenue, founder-led), not boilerplate already guaranteed by Stage 1.
3. **Reasons by importance.** The "top 3 reasons" selector should rank by criterion weight/importance, surfacing the mandate's core qualitative criteria when met — not the first/easiest "meets."
4. **Type portfolio constraints in Stage 0.** `mandate-parser` tags portfolio-construction criteria (max-2-per-industry, ADV liquidity) as `portfolio_constraint` so they route to Stage 7 enforcement, not the per-company scorecard. Then **enforce max-2-per-industry** with a greedy post-rank pass in `stage7_rank`.

**Files:** `skills-library/opportunity/mandate-scorecard/run.py`, `skills-library/mandate/mandate-parser/`, `stage7_rank.py`, report builder.

**Acceptance:** reasons cite qualitative/financial criteria; "max 2 per industry" never appears as a per-company reason; the final ranked list respects ≤2 names per industry.

---

## Phase 5 — Universe hygiene

**Problem.** SPACs (AAC) and warrants (ABLVW, 'W' suffix) reached the top 8; the mandate wants operating common equity.

**Fix.** In `universe-filter/run.py`, screen out non-common-equity instruments: warrants (`W`/`WS` suffix), units (`U` suffix), and blank-check/SPACs (SIC `6770`). Make it a default-on hygiene filter, logged to `reject_log`.

**Acceptance:** no SPACs/warrants/units in survivors.

---

## Phase 6 — Routing speed profile  *(your explicit ask: faster now, still multi-model)*

**Context.** The ladder is qwen (local 9B) → sonnet → opus, with a confidence guard that re-runs a cheap call on a higher rung when output is low-confidence/invalid. The baseline run shows `debate_generate` ran on qwen ×20 **and then escalated to sonnet ×16** — i.e. most cheap calls are paid for twice and serialized. Token-preservation (`QWEN_MAX_TOKENS=24000` + prompt truncation to fit the cheap window) is what forces many of those escalations and retries.

**Goal:** lower wall-clock now, be less strict on token preservation, **keep three distinct models in use.** Make it reversible ("for the time being") via env/config.

1. **Kill the double-pass on hot escalation-prone routes (biggest win).** In `systems/idea-sourcing/router-policy.yaml`, promote the route that escalates >50% of the time to its escalation rung at the base: `debate_generate: sonnet` (was `qwen`). Net effect: ~36 calls → ~20, and the slow local-qwen pass is skipped on that path. qwen still owns `classification`, `extraction`, `screening`, `summarization`; opus still owns `judgment`, `drafting`, `debate_reconcile`. **The ladder is preserved.**
2. **Relax token preservation.** Raise `QWEN_MAX_TOKENS` (24000 → ~32000) and reduce prompt truncation in the scorecard/debate prompt builders so fewer calls trip the length-guard or return low-confidence and re-run. Less trimming = fuller context = fewer redo passes.
3. **Raise fan-out concurrency.** `IM_MAX_WORKERS` 6 → 8–10 for the per-company stages (bounded by `SEC_MAX_RPS` and Claude-CLI throughput; back off if you see SEC 429s or CLI timeouts).
4. **Make it a named, reversible profile.** Drive 2–3 via env vars and document a "speed" profile block (e.g. in `.env.example` and the README) so it can be reverted to the token-thrifty profile later. Keep `default: opus` and the fallback flags as-is.

**Files:** `systems/idea-sourcing/router-policy.yaml`, `skills-library/_shared/router/imrouter/engine.py` (env defaults), prompt builders in `mandate-scorecard` / Stage 6, `.env.example`, README.

**Acceptance:** the router ledger still shows ≥2 (ideally 3) distinct models per run; total model calls per run drop (fewer double-passes); wall-clock per run drops; output quality not visibly worse on the baseline mandate.

---

## Phase 7 — Data architecture split  *(optional, do after 1–6 land)*

**Problem.** One 1.1 GB SQLite file welds a disposable, regenerable cache (`http_cache`, `facts`, `prices`, `filings`, `news`, `company_metrics` ≈ 99% of size) to precious, non-regenerable output (`runs`, `scores`, `evidence`, `reject_log`, `events`, `theses`, `audit_log` ≈ a few MB).

**Fix (incremental, low-risk).** Split into `cache.db` + `results.db` and `ATTACH` both on one connection so existing JOINs keep working. Move the cache tables to `cache.db`, keep output tables in `results.db`. Optionally, later, migrate `facts` to DuckDB/Parquet for ~10× compression (the architecture already contemplates this in `DATA-SOURCE-MAP.md`).

**Acceptance:** `results.db` is a few MB and portable per-mandate/per-client; `cache.db` is fully rebuildable from sources; all tests still pass via ATTACH.

---

## Git workflow & push (required)

- Do all work on `improve/idea-sourcing-funnel`.
- Commit **per phase** with messages matching the repo's convention (`feat(idea-sourcing): …`, `fix(idea-sourcing): …`, `feat(router): …`, `refactor(store): …`).
- Before each commit: `git status` — confirm no `*.db`, `data/`, `.cache/`, or `output/` is staged.
- After each phase's tests pass: `git push -u origin improve/idea-sourcing-funnel`.
- When the branch is green end-to-end, open a PR (or fast-forward `main` and push `main`) — your call on review. The deliverable is satisfied when the work is pushed to `origin`.
- Note: pushing requires the GitHub credentials on the local machine, which Claude Code has and this planning session does not — so the push happens during Claude Code execution.

---

## Verification (overall)

- Re-run the original mandate and diff the top-20 against `baseline_run.json`. Expect: preferred-industry compounders rising, mega-caps falling, no `fit=0` rows, ≤2 per industry.
- Add/extend unit tests under `systems/idea-sourcing/tests/`: `needs_data` quarantine, confidence calibration, deterministic `overall_fit`, max-2-per-industry, instrument-type hygiene, gate-ordering, and a router-ledger assertion that ≥2 models still fire under the speed profile.
- Run `tests/run_smoke_tests.py` + the system tests before the final push.
- Recommended: a final read-through pass (fresh agent or a careful diff review) confirming the new top names are genuinely quality compounders in the mandate's preferred industries, and that the provenance/evidence trail is intact.

---

## Suggested sequencing

1. **Phase 6** first — pure config, immediate speed win, independent of the rest.
2. **Phase 1 + Phase 2** — the core quality fix (broad → hard → soft; gate on quality).
3. **Phase 3 + Phase 5** — clean the output (quarantine, hygiene, confidence).
4. **Phase 4** — scorecard integrity + honest reasons + max-2-per-industry.
5. **Phase 7** — data split, when convenient.
