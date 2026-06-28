"""Stage 7 — opportunity-ranker: aggregate all evidence into a final ranking.

Deterministic aggregation produces a normalized Opportunity Score per name (the model
is not the anchor — the transparent composite is). A SELECTIVE ranking-challenger then
fires ONLY on contested rows (score clustered near the cutoff, or scorecard/qualitative
disagreement); a high-confidence challenge nudges the score within a bounded band and
re-sorts. why_ranked cites figures and carries no recommendation language.

`build()` is pure deterministic (safe anywhere). `challenge()` calls the ranking-challenger
leaf skill and must run on the main thread (it's invoked once over the small final set).
"""
from __future__ import annotations

import json

from imdata import skillkit

_TOL = 0.05            # "near the cutoff" band
_NUDGE = 0.03          # bounded reconcile adjustment for a high-confidence challenge


def _num(x, d=0.0):
    return x if isinstance(x, (int, float)) else d


def _qual_score(lean):
    return {"confirming": 0.65, "balanced": 0.5, "disconfirming": 0.4}.get(lean, 0.5)


def _crit_meta(mandate):
    """id -> (type, weight, text) for ranking reasons by importance."""
    out = {}
    for c in (mandate.get("criteria") or []):
        try:
            w = float(c.get("weight"))
        except (TypeError, ValueError):
            w = 1.0
        out[c.get("id")] = (c.get("type"), (w if w and w > 0 else 1.0), c.get("text"))
    return out


def _top_reasons(crs, cmeta, n=3):
    """Top reasons a name fits, ranked by criterion IMPORTANCE (weight). Only 'meets'
    on the criteria that actually express the mandate's judgment — excludes already-
    enforced hard constraints and portfolio constraints (no boilerplate tautologies)."""
    cand = []
    for cr in crs:
        if cr.get("verdict") != "meets":
            continue
        typ, w, text = cmeta.get(cr.get("criterion_id"), (None, 1.0, None))
        if typ in ("hard_constraint", "portfolio_constraint"):
            continue
        cand.append((w, {"criterion": text or cr.get("criterion_text"),
                         "evidence": cr.get("evidence")}))
    cand.sort(key=lambda x: -x[0])
    return [c for _, c in cand[:n]]


def build(results, fs_by, ts_by, events_by, qual_by, mandate, industry_by=None):
    """Deterministic rows with opportunity_score, confidence, sub-scores, why_ranked."""
    cmeta = _crit_meta(mandate)
    industry_by = industry_by or {}
    rows = []
    for t, sc in results.items():
        fit = _num(sc.get("overall_fit"))
        fs, ts = _num(fs_by.get(t)), _num(ts_by.get(t))
        hard_cats = [e for e in (events_by.get(t) or []) if e.get("hard_event")]
        cat_score = min(1.0, 0.25 * len(hard_cats))
        q = qual_by.get(t) or {}
        lean = q.get("qual_lean", "balanced")
        qs = _qual_score(lean)
        # Phase 2: factor (size-ish) cut 0.20->0.10; text-fit raised 0.10->0.20. Quality
        # (mandate-fit scorecard) stays dominant. Size is a floor, never a driver.
        opp = round(0.45 * fit + 0.10 * fs + 0.20 * ts + 0.10 * cat_score + 0.15 * qs, 4)
        flags = sc.get("flags") or []
        crs = sc.get("criterion_results") or []
        ntot = len(crs)
        nmet = sum(1 for cr in crs if cr.get("verdict") == "meets")
        # Phase 3: confidence from DATA COMPLETENESS, not flag count (the old logic was
        # inverted — a name with no data/no flags scored "high"). Coverage = criteria
        # actually evaluated / total; evidence present = a qualitative debate ran. No
        # evidence or thin coverage => low; data-quality flags cap it at medium.
        evaluated = sum(1 for cr in crs if cr.get("verdict") in ("meets", "partial", "does_not_meet"))
        coverage = (evaluated / ntot) if ntot else 0.0
        has_evidence = bool(q.get("evidence")) or evaluated > 0
        if not has_evidence or coverage < 0.34:
            conf = "low"
        elif coverage < 0.67 or flags:
            conf = "medium"
        else:
            conf = "high"
        cats = [f"{e.get('type')}" + (f" {e.get('date')}" if e.get("date") else "")
                for e in hard_cats][:3]
        risks = [e.get("claim") for e in (q.get("evidence") or [])
                 if e.get("tag") == "disconfirming"][:3]
        rows.append({
            "ticker": t, "company": sc.get("company"),
            "opportunity_score": opp, "confidence": conf, "mandate_fit": fit,
            "factor_score": fs, "text_score": ts, "catalyst_score": cat_score,
            "qual_lean": lean, "qual_score": qs,
            "primary_catalysts": cats, "primary_risks": risks,
            "top_reasons": _top_reasons(crs, cmeta),
            "industry": industry_by.get(t),
            "data_flags": flags,
            "why_ranked": (f"meets {nmet}/{ntot} mandate criteria (fit {fit:.2f}); "
                           f"factor {fs:.2f}, text-fit {ts:.2f}, catalysts {len(hard_cats)}, "
                           f"qualitative lean {lean}. Evidence-based ordering for diligence triage."),
            "evidence_ref": f"evidence:{t}",
        })
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return rows


def _industry_bucket(industry):
    """Coarse industry key for the max-N-per-industry cap: SIC major group (first 2
    digits) when numeric, else the lowercased description / label."""
    s = str(industry or "").strip()
    if s[:2].isdigit():
        return s[:2]
    return s.lower() or "unknown"


def cap_per_industry(rows, max_per):
    """Greedy post-rank pass: keep at most ``max_per`` names per industry bucket (rows
    already sorted best-first). Returns (kept, overflow). Overflow rows carry a
    ``capped_by`` note so the caller can log them — NO SILENT DROPS."""
    if not max_per or max_per <= 0:
        return rows, []
    seen, kept, overflow = {}, [], []
    for r in rows:
        b = _industry_bucket(r.get("industry"))
        if seen.get(b, 0) < max_per:
            seen[b] = seen.get(b, 0) + 1
            kept.append(r)
        else:
            r = dict(r)
            r["capped_by"] = f"max {max_per} per industry ({b})"
            overflow.append(r)
    return kept, overflow


def _is_contested(row, cutoff):
    near = abs(row["opportunity_score"] - cutoff) <= _TOL
    disagree = ((row["mandate_fit"] >= 0.7 and row["qual_lean"] == "disconfirming")
                or (row["mandate_fit"] < 0.5 and row["qual_lean"] == "confirming"))
    return near or disagree


def challenge(rows, top_k):
    """Selective debate: challenge ONLY contested rows; a high-confidence challenge
    nudges the score within ±_NUDGE and we re-sort. Returns (rows, n_challenged)."""
    if not rows:
        return rows, 0
    cutoff = rows[min(top_k, len(rows)) - 1]["opportunity_score"]
    n = 0
    for r in rows:
        if not _is_contested(r, cutoff):
            continue
        n += 1
        slim = {k: r[k] for k in ("ticker", "company", "rank", "opportunity_score",
                                  "mandate_fit", "factor_score", "text_score",
                                  "primary_catalysts", "data_flags") if k in r}
        ch = skillkit.call_skill("ranking-challenger",
                                 ["--row", json.dumps(slim), "--cutoff", cutoff])
        if ch.get("error"):
            continue
        r["challenge"] = {"suggested_direction": ch.get("suggested_direction"),
                          "rationale": ch.get("rationale"), "confidence": ch.get("confidence")}
        if ch.get("confidence") == "high":
            d = ch.get("suggested_direction")
            if d == "down":
                r["opportunity_score"] = round(r["opportunity_score"] - _NUDGE, 4)
            elif d == "up":
                r["opportunity_score"] = round(r["opportunity_score"] + _NUDGE, 4)
            if d in ("up", "down"):
                r["why_ranked"] += f" [challenged {d}: {(ch.get('rationale') or '')[:90]}]"
    rows.sort(key=lambda r: r["opportunity_score"], reverse=True)
    return rows, n
