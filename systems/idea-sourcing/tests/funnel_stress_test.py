"""Stress tests for the idea-sourcing v2 deterministic funnel (Stages 1-2).

Exercises universe-filter (Stage 1) and factor-ranker (Stage 2) against the warmed
company_metrics snapshot with hand-built MandateSpecs — NO model calls, so it runs fast
and deterministically. The whole point is to prove the invariants the design promises:

  * NO SILENT DROPS: a name is removed ONLY by a hard_constraint it definitively fails;
    soft/qualitative criteria never cut; a missing metric is kept (+noted), never dropped.
  * factor-ranker SCORES, NEVER CUTS; scores in [0,1]; deterministic.

Exit 0 == all pass.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import _bootstrap  # noqa: F401,E402

from imdata import store  # noqa: E402
from stages import stage1_universe_filter as s1, stage2_factor_rank as s2  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def spec(criteria, exclusions=None):
    return {"mandate_id": "stress", "mandate_hash": "stress", "seed_tickers": [],
            "criteria": criteria, "semantic_query": "", "exclusions": exclusions or []}


def hard(cid, field, op, val, text="hard"):
    return {"id": cid, "text": text, "type": "hard_constraint",
            "field": field, "operator": op, "value": val}


def soft(cid, text):
    return {"id": cid, "text": text, "type": "soft_preference",
            "field": None, "operator": None, "value": None}


def main():
    rows = {r["ticker"]: r for r in (dict(x) for x in store.all_metrics())}
    n_universe = len(rows)
    print(f"snapshot: {n_universe} names\n")
    assert n_universe > 0, "snapshot empty — warm it first"

    # ---- Case 1: no hard constraints (only soft) -> nothing is cut ----------
    print("Case 1: soft-only mandate cuts nothing")
    r = s1.run(spec([soft("c1", "preferably high margins")]))
    check("survivors == universe", len(r["survivors"]) == n_universe,
          f"{len(r['survivors'])} != {n_universe}")
    check("zero rejects", len(r["rejects"]) == 0, f"{len(r['rejects'])} rejects")

    # ---- Case 2: market-cap band -> survivors within band, rejects cite cap --
    print("Case 2: market_cap between [1e10, 5e10]")
    r = s1.run(spec([hard("c1", "market_cap", "between", [1e10, 5e10], "mid/large")]))
    surv = r["survivors"]
    in_band = all(1e10 <= rows[s["ticker"]]["market_cap"] <= 5e10
                  for s in surv if rows[s["ticker"]].get("market_cap") is not None)
    check("every survivor with a known cap is in-band", in_band)
    check("all rejects cite the cap criterion", all(x["removed_by"] == "c1" for x in r["rejects"]))
    # no name with a known cap OUTSIDE the band survived
    leaked = [s["ticker"] for s in surv
              if rows[s["ticker"]].get("market_cap") is not None
              and not (1e10 <= rows[s["ticker"]]["market_cap"] <= 5e10)]
    check("no out-of-band leak", not leaked, str(leaked[:5]))

    # ---- Case 3: missing-metric is KEPT, never silently dropped -------------
    print("Case 3: hard country filter keeps NULL-country names (no silent drop)")
    null_country = [t for t, m in rows.items() if m.get("country") in (None, "")]
    r = s1.run(spec([hard("c1", "country", "in", ["US"], "US only")]))
    surv_t = {s["ticker"] for s in surv}
    surv_t = {s["ticker"] for s in r["survivors"]}
    kept_null = [t for t in null_country if t in surv_t]
    check("NULL-country names are kept (treated as unknown, not foreign)",
          len(kept_null) == len(null_country),
          f"{len(kept_null)}/{len(null_country)} kept")
    # any dropped name must have a known, non-US country
    drop_t = {x["ticker"] for x in r["rejects"]}
    bad_drop = [t for t in drop_t if rows.get(t, {}).get("country") in (None, "", "US")]
    check("no name dropped on unknown/US country", not bad_drop, str(bad_drop[:5]))

    # ---- Case 4: impossible hard constraint -> 0 survivors, graceful --------
    print("Case 4: impossible cap (>=1e15) -> 0 survivors, all rejected, no crash")
    r = s1.run(spec([hard("c1", "market_cap", "gte", 1e15, "absurd")]))
    # names with a known cap all fail; NULL-cap names are KEPT (no silent drop)
    known_cap = [t for t, m in rows.items() if m.get("market_cap") is not None]
    check("no known-cap survivor", all(rows[s["ticker"]].get("market_cap") is None
                                       for s in r["survivors"]))
    check("rejects ~ all known-cap names", len(r["rejects"]) == len(known_cap),
          f"{len(r['rejects'])} vs {len(known_cap)}")

    # ---- Case 5: SIC sector filter (restaurants 5812) ----------------------
    print("Case 5: sic in [5812] (restaurants)")
    r = s1.run(spec([hard("c1", "sic", "in", [5812], "restaurants")]))
    rest = r["survivors"]
    ok_sic = all(rows[s["ticker"]].get("sic") == 5812 for s in rest
                 if rows[s["ticker"]].get("sic") is not None)
    check("restaurant survivors all SIC 5812 (where known)", ok_sic)
    check("found at least some restaurants", len(rest) >= 1, f"{len(rest)} found")

    # ---- Case 6: factor-ranker NEVER CUTS, scores in [0,1], deterministic ---
    print("Case 6: factor-ranker invariants")
    base = s1.run(spec([hard("c1", "market_cap", "gte", 1e10, "large")]))
    surv = base["survivors"]
    fr = s2.run(spec([hard("c1", "market_cap", "gte", 1e10), soft("c2", "high margins")]), surv)
    ranked = fr["ranked"]
    check("ranked count == survivor count (never cuts)", len(ranked) == len(surv),
          f"{len(ranked)} vs {len(surv)}")
    check("all factor_scores in [0,1]",
          all(0.0 <= (x.get("factor_score") or 0) <= 1.0 for x in ranked))
    check("sorted descending by factor_score",
          all(ranked[i]["factor_score"] >= ranked[i + 1]["factor_score"]
              for i in range(len(ranked) - 1)))
    fr2 = s2.run(spec([hard("c1", "market_cap", "gte", 1e10), soft("c2", "high margins")]), surv)
    check("deterministic (same input -> same order)",
          [x["ticker"] for x in ranked] == [x["ticker"] for x in fr2["ranked"]])

    # ---- Case 7: exclusions remove the named sector ------------------------
    print("Case 7: exclusion of a sector word")
    r = s1.run(spec([], exclusions=["eating"]))  # exclude restaurants by industry word
    surv_t = {s["ticker"] for s in r["survivors"]}
    rest_left = [t for t in surv_t
                 if "eating" in (rows[t].get("sic_description") or "").lower()]
    check("excluded sector not in survivors", not rest_left, str(rest_left[:5]))

    print()
    if FAILS:
        print(f"STRESS: {len(FAILS)} FAIL(s): {FAILS}")
        raise SystemExit(1)
    print("STRESS: ALL DETERMINISTIC FUNNEL INVARIANTS PASS")


if __name__ == "__main__":
    main()
