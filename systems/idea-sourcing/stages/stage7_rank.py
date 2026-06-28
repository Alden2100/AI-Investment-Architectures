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

# Opportunity-score component weights (sum to 1.0). Business quality dominates so a great
# business at a fair price outranks a mediocre one with catalysts (P10). Exposed in every
# row's score_breakdown so the score is fully reproducible (P3).
_WEIGHTS = {
    "business_quality": 0.45,   # mandate-fit roll-up (core-principle weighted)
    "semantic_fit":     0.20,   # text/business-description alignment to the mandate
    "qualitative":      0.15,   # confirming/disconfirming evidence lean
    "catalysts":        0.10,
    "financial_factor": 0.10,   # size/liquidity factor (a floor signal, smallest weight)
}


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


# Only these categories are positive REASONS to own a company. Avoiding a red flag
# (negative_constraint) or passing a hard requirement is never a "top reason".
_POSITIVE_TYPES = {"core_principle", "positive_preference", "soft_preference", "qualitative"}


def _top_reasons(crs, cmeta, n=3):
    """Top reasons a name fits, ranked by criterion IMPORTANCE (weight). Only 'meets' on
    POSITIVE categories (core_principle / positive_preference) — never hard constraints
    (tautologies), portfolio constraints, or negative constraints ('avoid X' is not a
    reason to own a company). Core principles outrank preferences via their higher weight."""
    cand = []
    for cr in crs:
        if cr.get("verdict") != "meets":
            continue
        typ, w, text = cmeta.get(cr.get("criterion_id"), (None, 1.0, None))
        if typ not in _POSITIVE_TYPES and typ is not None:
            continue
        # core principles get a tiebreak bump so they lead the reasons list
        bump = 1.0 if typ == "core_principle" else 0.0
        cand.append((w + bump, {"criterion": text or cr.get("criterion_text"),
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
        flags = sc.get("flags") or []
        # ---- Reproducible weighted breakdown (P3). Business quality dominates (P10). ----
        comps = [("Business Quality (mandate fit)", _WEIGHTS["business_quality"], fit),
                 ("Semantic / Text Fit",            _WEIGHTS["semantic_fit"],     ts),
                 ("Qualitative Evidence",           _WEIGHTS["qualitative"],      qs),
                 ("Catalysts",                      _WEIGHTS["catalysts"],        cat_score),
                 ("Factor (size / liquidity)",      _WEIGHTS["financial_factor"], fs)]
        breakdown = [{"component": name, "weight_pct": round(w * 100, 1),
                      "score_0_100": round(s * 100, 1), "contribution": round(w * s * 100, 2)}
                     for name, w, s in comps]
        positive = sum(w * s for _, w, s in comps)
        # Risk adjustment: data-quality flags + a disconfirming evidence lean (P10/P11).
        risk_pen = min(0.20, 0.04 * len(flags) + (0.06 if lean == "disconfirming" else 0.0))
        risk_rating = "high" if risk_pen > 0.12 else ("medium" if risk_pen >= 0.05 else "low")
        breakdown.append({"component": "Risk adjustment", "weight_pct": "penalty",
                          "score_0_100": risk_rating, "contribution": round(-risk_pen * 100, 2)})
        # Quality gate: a poor business (low mandate fit) can't be rescued by catalysts —
        # the whole score scales down below a quality floor.
        gate = min(1.0, fit / 0.40) if fit < 0.40 else 1.0
        opp = round(max(0.0, positive - risk_pen) * gate, 4)
        if gate < 1.0:
            breakdown.append({"component": "Quality-gate multiplier", "weight_pct": "x",
                              "score_0_100": round(gate, 2),
                              "contribution": f"scaled (business quality below floor)"})
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
            "opportunity_score": opp, "opportunity_score_100": round(opp * 100, 1),
            "confidence": conf, "mandate_fit": fit,
            "business_quality": round(fit * 100, 1), "catalyst_strength": round(cat_score * 100, 1),
            "risk_rating": risk_rating,
            "factor_score": fs, "text_score": ts, "catalyst_score": cat_score,
            "qual_lean": lean, "qual_score": qs,
            "score_breakdown": breakdown,
            "primary_catalysts": cats, "primary_risks": risks,
            "top_reasons": _top_reasons(crs, cmeta),
            "industry": industry_by.get(t),
            "data_flags": flags,
            "why_ranked": (f"meets {nmet}/{ntot} mandate criteria (business quality {fit*100:.0f}/100); "
                           f"semantic-fit {ts*100:.0f}, catalysts {len(hard_cats)}, "
                           f"qualitative lean {lean}, risk {risk_rating}. "
                           f"Evidence-based ordering for diligence triage."),
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
