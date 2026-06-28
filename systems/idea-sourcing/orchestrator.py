"""idea-sourcing v2 orchestrator — the single entry point / controller.

Runs the mandate-matching funnel end to end: Stage 0 (parse) and Stages 1-3
(deterministic filter / factor-rank / text-similarity) once on the main thread, then
fans the per-company Stage 4 scorecard across a bounded worker pool, with per-company
cache-skip, drop-weak gates (logged — NO SILENT DROPS), one bounded retry, and a
routing ledger. Stages 5-7 (catalyst / qualitative+debate / ranking+challenger) land in
later phases; until then the ranking is a transparent blend of the funnel scores.

Concurrency rule (mirrors imdata/articles.py): the MAIN thread owns all parent-process
SQLite (Evidence Store reads/writes); WORKER threads only call leaf skills (subprocesses
with their own WAL connections) and return plain dicts. The orchestrator serializes every
store write back on the main thread.

Usage:
    python orchestrator.py --mandate "Large-cap US software, preferably high margins. Eg MSFT."
    python orchestrator.py --spec-file mandate_spec.json --top-k 6      # skip Stage 0 (reuse a parsed spec)
"""
import _bootstrap  # noqa: F401  (sets env + sys.path before imdata import)

import argparse
import concurrent.futures
import json
import os
import re
import time
import uuid

from imdata import store
from imrouter import orchestration as orch

from stages import _cache, stage7_rank, stage0b_warm
from stages import (stage0_mandate, stage1_universe_filter, stage2_factor_rank,
                    stage3_text_similarity, stage4_scorecard, stage5_catalyst,
                    stage6_qualitative)

SKILL_SCORECARD = "mandate-scorecard"
STAGE_SCORECARD = 4
SKILL_EVENTS = "event-detector"
STAGE_EVENTS = 5
SKILL_QUAL = "qualitative-researcher"
STAGE_QUAL = 6
CATALYST_LOOKBACK = 90


def _scorecard_inputs(mandate: dict, ticker: str) -> dict:
    """The inputs that determine a company's scorecard — same mandate criteria + ticker
    => same inputs_hash => cache hit on re-run. (Filing accession could be folded in once
    we track it per name; mandate+ticker is a stable v1 key over a fixed snapshot.)"""
    return {"ticker": ticker.upper(),
            "criteria": [c.get("id") for c in mandate.get("criteria", [])]}


_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _max_per_industry(mandate):
    """Read a max-N-per-industry portfolio constraint from the mandate, else None."""
    for c in (mandate.get("criteria") or []):
        if (c.get("type") or "") != "portfolio_constraint":
            continue
        txt = (c.get("text") or "").lower()
        if "per industry" in txt or "per sector" in txt:
            m = re.search(r"\b(\d+)\b", txt)
            if m:
                return int(m.group(1))
            for w, n in _WORD_NUM.items():
                if re.search(r"\b" + w + r"\b", txt):
                    return n
    return None


def _company_pipeline(mandate, ticker, factor_score, text_score):
    """WORKER THREAD: leaf-skill calls only (no parent SQLite). One bounded retry."""
    last = None
    for attempt in (1, 2):
        try:
            return stage4_scorecard.run(mandate, ticker,
                                        factor_score=factor_score, text_score=text_score)
        except Exception as e:  # noqa: BLE001 - transport/subprocess failure
            last = str(e)
    return {"ticker": ticker, "error": last or "unknown"}


def main(args):
    try:
        orch.reset_routing_log()
    except Exception:
        pass
    run_id = uuid.uuid4().hex

    # ---- Stage 0: mandate -> MandateSpec (model, once) ----
    if args.spec_file:
        with open(args.spec_file) as fh:
            mandate = json.load(fh)
    else:
        mandate = stage0_mandate.run(args.mandate)
        if mandate.get("_needs_model"):
            return {"error": "mandate-parser needs a model rung (no qwen/Claude available)",
                    "run_id": run_id}
    mandate_hash = mandate.get("mandate_hash", "")
    store.start_run(run_id, mandate_hash, mandate)

    # ---- Stage 0b: mandate-driven universe warming (once, before Stage 1) ----
    # Default ON for a full --mandate run; OFF for --spec-file reruns/tests unless --warm.
    do_warm = (not getattr(args, "no_warm", False)) and (bool(getattr(args, "mandate", None))
                                                         or getattr(args, "warm", False))
    warming = None
    if do_warm:
        warming = stage0b_warm.run(
            mandate,
            max_classify=int(getattr(args, "max_classify", 1500) or 1500),
            warm_cap=int(getattr(args, "warm_cap", 400) or 400))

    # ---- Stage 1: hard-constraint filter (deterministic, once) + reject log ----
    filt = stage1_universe_filter.run(mandate)
    all_survivors = filt.get("survivors", [])
    store.put_rejects(run_id, filt.get("rejects", []))

    # ---- needs_data quarantine: names kept by no-silent-drop but missing a CORE metric
    # (null market cap) can't be scored — route them to a separate bucket so they never
    # enter the gate or the ranked output (vs. landing as fit=0.00 rows). Logged, not silent. ----
    survivors = [s for s in all_survivors if s.get("market_cap") is not None]
    needs_data = [s["ticker"] for s in all_survivors if s.get("market_cap") is None]
    if needs_data:
        store.put_rejects(run_id, [
            {"ticker": t, "removed_by": "needs_data",
             "constraint": "core metric (market_cap) missing — not scorable",
             "value_seen": None} for t in needs_data])

    # ---- Stage 2: factor pre-rank (deterministic, once, never cuts; size demoted) ----
    fr = stage2_factor_rank.run(mandate, survivors)
    ranked = fr.get("ranked", [])
    fs_by = {r["ticker"]: r.get("factor_score") for r in ranked}
    indfit_by = {r["ticker"]: (r.get("sub_scores") or {}).get("industry_fit", 0.5) for r in ranked}
    for r in ranked:
        store.put_score(run_id, r["ticker"], "factor", r.get("factor_score"), r.get("sub_scores"))

    # ---- Stage 3 (cheap, PRE-gate): text-fit over ALL survivors from snapshot text
    # (sic_description + title), no 10-K fetch — so the gate can use mandate fit, not size. ----
    cheap_text_by = {}
    if survivors and (mandate.get("semantic_query") or "").strip():
        ct = stage3_text_similarity.run_cheap(mandate, survivors)
        cheap_text_by = {r["ticker"]: (r.get("text_score") or 0.0) for r in ct.get("results", [])}
    mcap_by = {s["ticker"]: s.get("market_cap") for s in survivors}

    # ---- Gate on a QUALITY composite (text-fit + industry-fit + data-completeness),
    # NOT size. Size is already a hard floor (Stage 1). Drops logged — NO SILENT DROPS. ----
    def _quality(t):
        core = 1.0 if mcap_by.get(t) is not None else 0.0
        return 0.45 * cheap_text_by.get(t, 0.0) + 0.35 * indfit_by.get(t, 0.5) + 0.20 * core
    order = sorted((s["ticker"] for s in survivors), key=lambda t: -_quality(t))
    keep, dropped = order[:args.top_k], order[args.top_k:]
    if dropped:
        store.put_rejects(run_id, [
            {"ticker": t, "removed_by": "gate:quality",
             "constraint": f"quality composite below top-{args.top_k}",
             "value_seen": round(_quality(t), 4)} for t in dropped])

    # ---- Stage 3 (full, POST-gate): 10-K TNIC text-similarity on the small kept set ----
    ts_by = {}
    if keep and (mandate.get("semantic_query") or "").strip():
        ts = stage3_text_similarity.run(mandate, [{"ticker": t} for t in keep])
        ts_by = {r["ticker"]: r.get("text_score") for r in ts.get("results", [])}
        for t, v in ts_by.items():
            store.put_score(run_id, t, "text_sim", v)

    # ---- Stage 4: per-company scorecard — cache-skip on main thread, compute in workers ----
    results, to_compute = {}, []
    for t in keep:
        ih = _cache.inputs_hash(STAGE_SCORECARD, mandate_hash, _scorecard_inputs(mandate, t))
        hit = store.get_cached_evidence(t, STAGE_SCORECARD, SKILL_SCORECARD, ih)
        if hit is not None:
            results[t] = hit          # cache hit: reuse prior evidence, no model call, no new row
        else:
            to_compute.append((t, ih))

    pending_writes = []
    if to_compute:
        max_workers = max(1, int(os.environ.get("IM_MAX_WORKERS", "8")))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_company_pipeline, mandate, t, fs_by.get(t), ts_by.get(t)): (t, ih)
                    for t, ih in to_compute}
            for fut in concurrent.futures.as_completed(futs):
                t, ih = futs[fut]
                sc = fut.result()
                results[t] = sc
                pending_writes.append((t, ih, sc))

    # ---- main-thread SERIALIZED Evidence-Store writes ----
    for t, ih, sc in pending_writes:
        if sc.get("error"):
            continue
        store.put_evidence(run_id, t, STAGE_SCORECARD, SKILL_SCORECARD, sc,
                           sc.get("criterion_results"), ih)
        if isinstance(sc.get("overall_fit"), (int, float)):
            store.put_score(run_id, t, "scorecard", sc["overall_fit"])

    computed = {t for t, _, _ in pending_writes}

    # ---- Stage 5: catalyst-detector — cache-skip per name (by day), then events table ----
    day = time.strftime("%Y-%m-%d", time.gmtime())
    events_by, to_compute5 = {}, []
    for t in keep:
        ih5 = _cache.inputs_hash(STAGE_EVENTS, "global",
                                 {"ticker": t, "lookback": CATALYST_LOOKBACK, "day": day})
        hit = store.get_cached_evidence(t, STAGE_EVENTS, SKILL_EVENTS, ih5)
        if hit is not None:
            events_by[t] = hit.get("events", [])
        else:
            to_compute5.append((t, ih5))
    fresh5 = []
    if to_compute5:
        max_workers = max(1, int(os.environ.get("IM_MAX_WORKERS", "8")))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(stage5_catalyst.run, t, lookback=CATALYST_LOOKBACK): (t, ih5)
                    for t, ih5 in to_compute5}
            for fut in concurrent.futures.as_completed(futs):
                t, ih5 = futs[fut]
                try:
                    evs = fut.result().get("events", [])
                except Exception:
                    evs = []
                events_by[t] = evs
                fresh5.append((t, ih5, evs))
    for t, ih5, evs in fresh5:  # main-thread writes: cache the evidence row once per day
        store.put_evidence(run_id, t, STAGE_EVENTS, SKILL_EVENTS, {"events": evs}, [], ih5)
    for t in keep:  # this run's events table reflects every kept name (cached + fresh)
        if events_by.get(t):
            store.put_events(run_id, t, events_by[t])

    # ---- Stage 6: qualitative-researcher + confirming/disconfirming debate (cache-skip by day) ----
    qual_by, to_compute6 = {}, []
    for t in keep:
        ih6 = _cache.inputs_hash(STAGE_QUAL, mandate_hash, {"ticker": t, "day": day})
        hit = store.get_cached_evidence(t, STAGE_QUAL, SKILL_QUAL, ih6)
        if hit is not None:
            qual_by[t] = hit
        else:
            to_compute6.append((t, ih6))
    fresh6 = []
    if to_compute6:
        max_workers = max(1, int(os.environ.get("IM_MAX_WORKERS", "8")))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(stage6_qualitative.run, mandate, t): (t, ih6)
                    for t, ih6 in to_compute6}
            for fut in concurrent.futures.as_completed(futs):
                t, ih6 = futs[fut]
                try:
                    q = fut.result()
                except Exception as e:  # noqa: BLE001
                    q = {"ticker": t, "evidence": [], "qual_lean": "balanced", "error": str(e)}
                qual_by[t] = q
                fresh6.append((t, ih6, q))
    for t, ih6, q in fresh6:  # main-thread writes
        store.put_evidence(run_id, t, STAGE_QUAL, SKILL_QUAL, q, q.get("evidence"), ih6)
        store.put_score(run_id, t, "qual",
                        {"confirming": 1.0, "balanced": 0.5, "disconfirming": 0.0}.get(q.get("qual_lean"), 0.5))

    # ---- Stage 7: opportunity-ranker (deterministic aggregate) + selective challenger ----
    industry_by = {s["ticker"]: s.get("sic") for s in survivors}
    ranked_rows = stage7_rank.build(results, fs_by, ts_by, events_by, qual_by, mandate,
                                    industry_by=industry_by)
    for i, r in enumerate(ranked_rows, 1):
        r["rank"] = i
    ranked_rows, n_challenged = stage7_rank.challenge(ranked_rows, args.top_k)
    # ---- Portfolio constraint: max-N-per-industry (greedy post-rank; overflow logged) ----
    max_per = _max_per_industry(mandate)
    capped = []
    if max_per:
        ranked_rows, capped = stage7_rank.cap_per_industry(ranked_rows, max_per)
        if capped:
            store.put_rejects(run_id, [
                {"ticker": r["ticker"], "removed_by": "portfolio:max_per_industry",
                 "constraint": r.get("capped_by"), "value_seen": r.get("industry")} for r in capped])
    for i, r in enumerate(ranked_rows, 1):  # re-rank after challenge nudges + industry cap
        r["rank"] = i
    for r in ranked_rows:
        store.put_score(run_id, r["ticker"], "opportunity", r.get("opportunity_score"))
    routing = orch.routing_ledger()
    store.finish_run(run_id, routing)
    try:
        orch.audit("idea-sourcing", "source",
                   ",".join(r["ticker"] for r in ranked_rows[:args.top_k]),
                   f"run {run_id}: {len(survivors)} survivors, {len(ranked_rows)} ranked")
    except Exception:
        pass

    return {
        "system": "idea-sourcing",
        "run_id": run_id,
        "mandate": {"mandate_hash": mandate_hash,
                    "criteria": mandate.get("criteria", []),
                    "seed_tickers": mandate.get("seed_tickers", []),
                    "exclusions": mandate.get("exclusions", [])},
        "coverage": filt.get("coverage"),
        "warming": warming,
        "needs_data": needs_data,
        "n_survivors": len(survivors),
        "n_rejects": len(filt.get("rejects", [])) + len(dropped),
        "ranked": ranked_rows,
        "n_challenged": n_challenged,
        "cache_hits": [t for t in keep if t not in computed],
        "model_routing": routing,
        "summary": (f"{len(survivors)} survivors -> top {len(keep)} scored; "
                    f"ranked {len(ranked_rows)} by opportunity score. "
                    f"Evidence-backed shortlist for diligence triage (not investment advice)."),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="idea-sourcing v2 orchestrator (mandate -> ranked opportunities).")
    p.add_argument("--mandate", help="free-text mandate")
    p.add_argument("--spec-file", help="a pre-parsed MandateSpec JSON (skips Stage 0)")
    p.add_argument("--top-k", type=int, default=6, help="how many survivors enter the expensive stages")
    p.add_argument("--no-warm", action="store_true", help="skip Stage 0b mandate-driven warming")
    p.add_argument("--warm", action="store_true", help="force Stage 0b warming even for a --spec-file run")
    p.add_argument("--max-classify", type=int, default=1500, help="Stage 0b: max names to classify per run (resumable)")
    p.add_argument("--warm-cap", type=int, default=400, help="Stage 0b: max candidates to warm (market cap + liquidity) per run")
    a = p.parse_args()
    if not a.mandate and not a.spec_file:
        raise SystemExit("provide --mandate or --spec-file")
    print(json.dumps(main(a), indent=2, default=str))
