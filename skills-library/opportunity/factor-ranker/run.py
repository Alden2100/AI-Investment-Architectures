"""factor-ranker: Stage 2 of the opportunity drawer. Deterministic, no model calls.

Scores Stage-1 survivors on soft_preference criteria that map to cheaply-available
snapshot metrics (size, liquidity, industry_fit). SCORES, NEVER CUTS — every
survivor appears in the ranked output. Richer fundamentals-based factors
(margins, growth, leverage) are NOT computed here; they are judged per-name in
Stage 4 (mandate-scorecard).
"""
import argparse
import json
import os
import sys

# --- locate the shared library (_shared/) ------------------------------------
_here = os.path.realpath(__file__)
_root = os.environ.get("IM_LIB_ROOT", "")
if not _root:
    _d = os.path.dirname(_here)
    while _d != os.path.dirname(_d):
        if os.path.isdir(os.path.join(_d, "_shared", "data-fetch")):
            _root = _d
            break
        _d = os.path.dirname(_d)
for _p in ("data-fetch", "router", "web-search"):
    _cand = os.path.join(_root, "_shared", _p)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from imdata import skillkit, sectors  # noqa: F401  (skillkit for run/emit; sectors for industry_fit)

# Soft-criterion field/word -> the snapshot factor it influences.
FACTOR_FIELDS = {
    "market_cap": "size", "marketcap": "size", "mcap": "size", "size": "size",
    "adv": "liquidity", "liquidity": "liquidity", "volume": "liquidity",
    "sic": "industry_fit", "sector": "industry_fit", "industry": "industry_fit",
}
FACTORS = ("size", "liquidity", "industry_fit")


def _load_json(inline, path, what):
    if inline:
        return json.loads(inline)
    if path:
        with open(path) as f:
            return json.load(f)
    raise ValueError(f"provide --{what}-file <path> or --{what}-json <inline json>")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _minmax(values):
    """Return a function mapping a raw value -> [0,1]. None-valued names get 0.5
    (neutral) so a missing metric never pushes a name to the bottom or top."""
    nums = [v for v in values if v is not None]
    if not nums:
        return lambda x: 0.5
    lo, hi = min(nums), max(nums)
    if hi == lo:
        return lambda x: 0.5 if x is None else 1.0
    return lambda x: 0.5 if x is None else (x - lo) / (hi - lo)


def _industry_words(soft_criteria):
    """Collect industry words from soft/qualitative criteria for industry_fit."""
    words = []
    for c in soft_criteria:
        field = (c.get("field") or "").lower().strip()
        if field in ("sic", "sector", "industry"):
            for elem in (c.get("value") if isinstance(c.get("value"), list) else [c.get("value")]):
                if elem and _to_float(elem) is None:
                    words.append(str(elem).lower().strip())
        # also harvest free-text words that name an industry are not reliable; we
        # stick to explicitly-fielded industry criteria for determinism.
    return [w for w in words if w]


def main(args):
    mandate = _load_json(args.mandate_json, args.mandate_file, "mandate")
    survivors = _load_json(args.survivors_json, args.survivors_file, "survivors")
    if isinstance(survivors, dict) and "survivors" in survivors:
        survivors = survivors["survivors"]

    criteria = mandate.get("criteria") or []
    soft = [c for c in criteria
            if (c.get("type") or "").lower() in ("soft_preference", "qualitative")]

    # Which factors does the mandate actually care about, and at what weight?
    factor_weight = {}
    for c in soft:
        field = (c.get("field") or "").lower().strip()
        fac = FACTOR_FIELDS.get(field)
        if fac:
            w = _to_float(c.get("weight"))
            factor_weight[fac] = factor_weight.get(fac, 0.0) + (w if w is not None else 1.0)
    # Fallback: if the mandate names no mappable soft factor, weight all equally.
    if not factor_weight:
        factor_weight = {f: 1.0 for f in FACTORS}
    # Phase 2: demote size. Market cap is already a HARD floor in Stage 1; for a quality
    # mandate bigger is not better, so size is a near-floor tiebreaker, never the driver.
    # Guarantee industry_fit carries weight so entry into the funnel tracks mandate fit.
    factor_weight["industry_fit"] = max(factor_weight.get("industry_fit", 0.0), 1.0)
    if "size" in factor_weight:
        factor_weight["size"] = min(factor_weight["size"], 0.15)
    total_w = sum(factor_weight.values()) or 1.0

    ind_words = _industry_words(soft)

    # Raw factor inputs across the survivor set.
    size_raw = [_to_float(s.get("market_cap")) for s in survivors]
    liq_raw = [_to_float(s.get("adv")) for s in survivors]
    size_norm = _minmax(size_raw)
    liq_norm = _minmax(liq_raw)

    def industry_fit(rec):
        if not ind_words:
            return 0.5  # neutral when the mandate names no industry preference
        # synonym/SIC-aware match (so "fintech"/"medical devices"/etc. resolve), not raw substring
        return 1.0 if sectors.matches_any(ind_words, rec.get("sic"), rec.get("sic_description")) else 0.5

    ranked = []
    for s in survivors:
        subs = {
            "size": round(size_norm(_to_float(s.get("market_cap"))), 6),
            "liquidity": round(liq_norm(_to_float(s.get("adv"))), 6),
            "industry_fit": round(industry_fit(s), 6),
        }
        blend = sum(factor_weight.get(f, 0.0) * subs[f] for f in FACTORS) / total_w
        ranked.append({
            "ticker": s.get("ticker"),
            "company": s.get("company") or s.get("title") or s.get("ticker"),
            "factor_score": round(blend, 6),
            "sub_scores": subs,
        })

    # Stable sort by score desc (Python's sort is stable; survivor order breaks ties).
    ranked.sort(key=lambda r: -r["factor_score"])

    note = ("Factors are min-max normalized to [0,1] across the survivor set; "
            "missing metrics score a neutral 0.5 (never cut). factor_score is a "
            "mandate-weighted blend of {weights}. NEVER CUTS — every survivor is "
            "ranked. Fundamentals (margins/growth/leverage) are evaluated per-name "
            "in Stage 4 (mandate-scorecard).").format(weights=factor_weight)
    summary = (f"Ranked {len(ranked)} survivor(s) on factors "
               f"{list(factor_weight.keys())}.")
    return {
        "mandate_hash": mandate.get("mandate_hash") or mandate.get("mandate_id") or "",
        "ranked": ranked,
        "factor_weights": factor_weight,
        "note": note,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Stage 2 opportunity ranker: score survivors on snapshot factors "
                    "(size, liquidity, industry_fit). Deterministic, never cuts.")
    p.add_argument("--mandate-file", default=None, help="path to a MandateSpec JSON file")
    p.add_argument("--mandate-json", default=None, help="inline MandateSpec JSON string")
    p.add_argument("--survivors-file", default=None,
                   help="path to a JSON list of survivor dicts (from universe-filter), "
                        "or the full universe-filter output object")
    p.add_argument("--survivors-json", default=None, help="inline survivors JSON")
    skillkit.run(main, p)
