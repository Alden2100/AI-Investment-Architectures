# Handoff brief for Claude Code — fix the "childish imitation" output quality

*Diagnosis + chosen direction + prioritized work. Evidence cited by file path. This supersedes `DIAGNOSIS-output-quality.md`.*

## Context for you, Claude Code

The architecture of this repo is sound (mechanism/policy router, code-for-exact / model-for-judged, deterministic checks, clean XBRL/RAG/caching plumbing). **Do not rearchitect those.** The problem is that the *output* — memos, valuation calls, filing briefs — reads like a childish imitation rather than analyst-grade work. There are four compounding causes below, in priority order. Cause #1 is decisive and has a specific chosen solution; #2–#4 cap the quality ceiling and still need work even after #1 is fixed.

**Decision already made:** for the model layer we are going with **Option 2 — route the high-judgment model step through the Claude Code CLI on the user's Max plan (OAuth subscription), NOT the raw Anthropic API.** Implement to that decision. Details in #1.

---

## #1 — The decisive fix: the judgment layer must run on Claude (via Claude Code), and must stop silently degrading to the 9B model

### The current broken state (verified, not hypothesized)

The design routes all reasoning/synthesis/drafting/judgment to Claude (`claude-opus-4-8` is the pinned default in `skills-library/_shared/router/imrouter/claude_client.py`). But:

- `claude_client.available()` is literally `return bool(os.environ.get("ANTHROPIC_API_KEY"))` — the *only* gate.
- No key is ever set: there is no `.env` (only `.env.example` with the line commented), `ask.py:32` loads `.env` only `if os.path.exists(...)`, and nothing is exported in the shell.
- With `allow_local_fallback: true` in every `systems/*/router-policy.yaml`, the engine (`engine.py`) silently resolves every "claude" task to local `qwen3.5:9b`.

This is proven by the decision logs: **all ~77 entries across every system** read
```
{"task":"reasoning","desired":"claude","chosen":"local","fell_back":true,"model":"qwen3.5:9b","result":"ok"}
```
(`systems/*/data/router_decisions.jsonl`). Every output PDF footer says *"narrative via model route 'local'."* A 9B model has written every memo, logged as `result:"ok"`. Fingerprints in the artifacts:
- `reporting.pdf` recommends **OVERWEIGHT MSFT** while its own DCF shows **−49.7%** to intrinsic, and the **valuation** system rates the same stock **SELL** the same day.
- Raw floats leak into prose: *"net margin of 0.3615"*, *"operating income of $128,528,000,000"* (the Python table on the same page correctly shows 36.1%).
- `filing-intelligence.pdf` **hallucinated a "$190 billion AI infrastructure spend"** lifted from a news headline title, not the filing.

### Why not just set an API key

A Max subscription does **not** include API access — the subscription (web/desktop/Claude Code) and the developer API are separate products with separate, pay-per-token billing. We don't want metered API charges on top of the Max plan, so we route through Claude Code instead, which runs on the Max OAuth login.

### What to implement (Option 2)

Replace the transport in the "claude" route so that instead of `requests.post` to `https://api.anthropic.com/v1/messages` with an `x-api-key`, it **invokes the Claude Code CLI in headless/print mode**, authenticated by the user's Max-plan OAuth session.

Specifics and constraints (verify exact current CLI flags before relying on them):

1. **Transport.** In `claude_client.py`, swap the HTTP call for a subprocess call to the `claude` CLI in non-interactive print mode (`claude -p`, with a JSON output format and a `--model` selector, and `--system-prompt` / `--append-system-prompt` for the persona). Pass the prompt via **stdin or a temp file**, not as an argv string — filing text and dossiers will blow past arg-length limits.
2. **Auth must stay on the subscription.** If `ANTHROPIC_API_KEY` is present in the environment, Claude Code uses the API key (billed) instead of the Max subscription. So this path must run with that variable **unset/stripped** from the child env. Document that the user must `claude login` with their Max plan once (and confirm via `claude` `/status` that it shows subscription auth, not an API key).
3. **Structured output.** The old code got schema-bound JSON via forced tool use. In CLI print mode, instruct the model to emit a single JSON object matching the schema and parse it robustly — reuse the existing `_extract_json()` approach from `ollama_client.py`, then validate against the schema in Python. (Don't trust free-text.)
4. **Detection.** Rewrite `available()` to detect a usable Claude Code session (CLI on PATH + authenticated), not the presence of an env var.
5. **Fail loud, don't degrade silently.** This is the deeper design bug. For the high-judgment routes (`reasoning/synthesis/drafting/judgment`), a missing/broken Claude Code session should **error or emit a loud warning**, not quietly fall back to qwen with `result:"ok"`. Keep qwen fallback only for genuinely local-tier tasks (classification/extraction/screening/summarization), or gate it behind an explicit `--allow-degraded` flag. At minimum, surface the chosen model in the output header/footer so a qwen run is never mistaken for a Claude run.
6. **Note the SDK limitation.** The Claude Agent SDK does **not** currently support Max-plan billing (API key only), so the subscription path is the **CLI subprocess specifically**. This is for the user's own individual use.
7. **Practical caveats to handle:** subprocess spin-up adds seconds per call and the orchestrators make several model calls per run — consider concurrency, a persistent/streaming session, or simply accept the latency; and add a sane timeout + retry.

---

## #2 — Even on Claude, the model is starved of substance and boxed into a 2–3 sentence slot

Fixing #1 raises the floor but #2 sets the ceiling. The orchestrators deliberately strip rich skill output down to a few scalars *before* the model sees it, explicitly to suit the weak model:

- `reporting/orchestrator.py`: *"Distill to a compact, high-signal block — the model writes a sharper memo from clean numbers than from four full raw skill dumps (and the 9B handles it keyless)."*
- `idea-sourcing/orchestrator.py`: the ranking model gets a `slim` list reduced to `{ticker, dcf_upside, ev_ebitda, pe, catalysts:<count>, headlines:<count>}` — the actual catalyst/headline **text is discarded, only the count survives.** Result: tautological theses (*"Only candidate with positive DCF upside…strong catalyst count of 121"*).
- `valuation/orchestrator.py`: model gets the numeric dossier + *"rationale (2-3 sentences)… Use only these numbers."* No 10-K text, no business context.
- `filing-intelligence/orchestrator.py`: model sees difflib change-blocks truncated to **4500 chars** + 4 headline titles, never the MD&A/risk prose.

The deliverable is then **~90% Python f-string template** (`_shared/router/imrouter/orchestration.py::report()` plus hardcoded BLUF/assumptions/risks/falsifiers in each orchestrator). The model fills a thesis paragraph and a rationale that's sliced to `[:240]` chars. **Python writes the document; the model fills one small blank** — structurally incapable of a connected argument. Length caps compound it: synthesis `max_tokens` is **1000–1800** in most orchestrators, and every system prompt demands *"terse / brief / concise / one sentence."*

**Direction:** feed the model the real material (filing text, full catalyst/headline bodies, full skill JSON), let *it* compose the document instead of f-string templates, raise `max_tokens`, and drop the "terse/brief" instructions for client-facing drafting.

---

## #3 — The data is backward-looking and headline-thin (caps the ceiling)

The store (`_shared/data-fetch/imdata/store.py`) has 8 tables: `companies, filings, facts, prices, news, http_cache, theses, audit_log`. A grep for `estimate|consensus|analyst|guidance|forecast|insider|institutional|short interest|segment` returns **zero hits** anywhere in the data layer.

- **No estimates / consensus / forward Street numbers** — a real note lives on the gap between consensus and the analyst's own forecast; there's nothing here to be differentiated against.
- **News is titles only** (`news.py` Google News RSS + SEC Atom, keeping `title/published/source/url`, no body). `catalyst-flagger` hands the model bare *"date + headline"* strings and asks it to "cite the specific filing" from a date.
- **No transcripts / guidance / segment KPIs / ownership / float / borrow.** `earnings-call-summarizer` only works if the *user* supplies a transcript file.
- Prices are free-tier single-vendor (yfinance→Yahoo→Stooq) — fine for vol/correlation, nothing else.

**Direction:** widen the inputs (estimates/consensus, transcripts, segment data, article bodies). Biggest effort; needed to clear the top of the ceiling.

---

## #4 — The analytics are textbook-toy with company-agnostic hardcoded assumptions

- **DCF** (`valuation/dcf-valuation/run.py`): single-stage **flat growth** (`fcf_t = base_fcf*(1+g)**t`), Gordon terminal, base FCF = `OCF − capex` from **one** 10-K year. No multi-stage fade, margin path, explicit tax/working-capital, or reinvestment/ROIC link. WACC is **hardcoded 9%**, never derived from beta/structure.
- **Scenarios** (`scenario-analyzer`): bull/bear = base **± fixed ±3% growth / ±1% WACC**, identical for every company.
- **Comps** (`comps-builder`): flat single-year median of EV/EBITDA, P/E, P/S; crude EBITDA = `OperatingIncome + D&A`; no growth-adjustment (PEG), forward multiples, or peer-quality normalization; peers are just whatever tickers were passed.
- **Moat** (`moat-analyzer`): three single-year margins + a truncated 10-K excerpt. No multi-year trend, ROIC, or pricing-power evidence.
- **Memo grounding** (`memo-writer/run.py`): with no `--input-file`, an entire six-section IC memo is grounded on `{revenue, net_income, price}` — **three numbers** — with "do not introduce numbers not present." Guaranteed generic prose.
- The advertised *"rich detail lives in `references/`"* progressive-disclosure layer **does not exist** for 24 of 26 skills — the thin templated `summary` really is all there is.

**Direction:** multi-stage DCF, derived WACC, business-specific scenarios, growth-adjusted/forward comps, multi-year moat; make skill JSON carry drivers/evidence/citations, not just numbers.

---

## Secondary — persona / standards / agents

System prompts are one-liners (*"You are a valuation analyst. Decisive, brief."*) with no audience (IC? LP? PM?), no rubric, no worked example, no house style. The `skills-library/agents/*.md` role files are ~25-line "Contract only" stubs **that are never loaded into any prompt** — documentation, not behavior. There's no cross-system coherence check, which is why valuation says SELL while reporting says OVERWEIGHT on the same name the same day.

**Direction:** give each drafting step a real analyst persona + named audience + quality rubric; actually load the agent role files into the system prompt; add a coherence check so the valuation call and the memo recommendation can't contradict.

---

## What is NOT the problem (don't spend effort here)

- The high-level architecture (mechanism/policy router split, code-for-exact/model-for-judged, deterministic checks) is sound.
- The engineering plumbing (caching, XBRL parsing, filing RAG, audit logging) is clean. The Python isn't unsophisticated *as software* — the weakness is the **financial formulas** (#4) and the **over-templated document assembly** (#2), not code quality.
- The routing *logic* works as designed; the bug is that "graceful fallback" silently masks the missing model (fixed in #1).

---

## Suggested execution order

1. **#1 — Reroute the model step through the Claude Code CLI (Option 2) and make high-judgment routes fail loud instead of silently dropping to qwen.** Highest leverage; everything else is judged against a real model afterward.
2. **#2 — Stop pre-digesting inputs to scalars; feed real source material and let the model write the document.** Raise `max_tokens`, drop "terse/brief," replace f-string templating with model-authored prose.
3. **Secondary — personas, audiences, rubrics, load the agent files, add the cross-system coherence check.**
4. **#4 — Deepen the analytics** (multi-stage DCF, derived WACC, business-specific scenarios, forward/growth-adjusted comps, multi-year moat; richer skill JSON).
5. **#3 — Widen the data** (estimates/consensus, transcripts, segments, article bodies). Largest effort, needed to fully clear the ceiling.
