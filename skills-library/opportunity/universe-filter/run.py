"""universe-filter: Stage 1 of the opportunity drawer. Deterministic, no model calls.

Applies ONLY hard_constraint criteria from a MandateSpec against the
company_metrics snapshot, plus mandate exclusions. Emits survivors + a verbatim
reject log. NO SILENT DROPS: a name is removed only when a hard constraint
DEFINITIVELY fails; a missing/NULL metric is never grounds for removal.
"""
import argparse
import json
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
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

from imdata import skillkit, store

# Mandate field name -> company_metrics column. Only these are screenable in
# Stage 1; richer fundamentals are judged per-name in Stage 4 (mandate-scorecard).
FIELD_TO_COL = {
    "country": "country",
    "market_cap": "market_cap",
    "marketcap": "market_cap",
    "mcap": "market_cap",
    "sic": "sic",
    "sic_code": "sic",
    "sector": "sic",
    "industry": "sic",
    "adv": "adv",
    "liquidity": "adv",
}


def _load_mandate(args):
    if args.mandate_json:
        return json.loads(args.mandate_json)
    if args.mandate_file:
        with open(args.mandate_file) as f:
            return json.load(f)
    raise ValueError("provide --mandate-file <path> or --mandate-json <inline json>")


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def _is_number(v):
    return _to_float(v) is not None and not (isinstance(v, str) and not v.strip())


# Sector/SIC matching lives in the shared imdata.sectors module so this Stage-1 filter
# and the Stage-0b prescreen (screener.py) use ONE implementation + synonym map.
from imdata import sectors  # noqa: E402

SECTOR_SYNONYMS = sectors.SECTOR_SYNONYMS  # back-compat alias


def _sic_token_match(value, sic, sic_desc):
    return sectors.sic_token_match(value, sic, sic_desc)


def _test(operator, col, metric, value):
    """Return one of: True (passes), False (definitively fails), None (indeterminate
    because the needed metric is missing -> caller must NOT remove)."""
    op = (operator or "").lower().strip()

    # sic membership: compare int(sic) and/or sic_description text
    if col == "sic" and op in ("in", "not_in", "notin", "not in"):
        # handled by caller which has both sic + sic_description; signalled here
        return "SIC_MEMBERSHIP"

    if metric is None:
        return None  # NO SILENT DROPS: indeterminate, keep the name

    if op in ("in",):
        opts = [str(x).lower() for x in _as_list(value)]
        return str(metric).lower() in opts
    if op in ("not_in", "notin", "not in"):
        opts = [str(x).lower() for x in _as_list(value)]
        return str(metric).lower() not in opts

    # numeric comparisons
    mv = _to_float(metric)
    if mv is None:
        return None  # metric not numeric -> indeterminate
    if op in ("gte", ">=", "min"):
        thr = _to_float(value)
        return None if thr is None else mv >= thr
    if op in ("lte", "<=", "max"):
        thr = _to_float(value)
        return None if thr is None else mv <= thr
    if op in ("gt", ">"):
        thr = _to_float(value)
        return None if thr is None else mv > thr
    if op in ("lt", "<"):
        thr = _to_float(value)
        return None if thr is None else mv < thr
    if op in ("between", "range"):
        bounds = _as_list(value)
        if len(bounds) != 2:
            return None
        lo, hi = _to_float(bounds[0]), _to_float(bounds[1])
        if lo is None or hi is None:
            return None
        if lo > hi:
            lo, hi = hi, lo
        return lo <= mv <= hi
    if op in ("eq", "==", "equals"):
        thr = _to_float(value)
        if thr is not None:
            return mv == thr
        return str(metric).lower() == str(value).lower()
    if op in ("ne", "!=", "not_equals"):
        thr = _to_float(value)
        if thr is not None:
            return mv != thr
        return str(metric).lower() != str(value).lower()
    # unknown operator -> can't apply, keep the name
    return None


def _usable_hard(c):
    """A hard_constraint is applicable only if it has a mappable field + operator + value."""
    if (c.get("type") or "").lower() != "hard_constraint":
        return False
    field = (c.get("field") or "").lower().strip()
    if field not in FIELD_TO_COL:
        return False
    if not (c.get("operator") or "").strip():
        return False
    if c.get("value") in (None, ""):
        return False
    return True


def _exclusion_hit(rec, excl):
    """An exclusion removes a name when it matches a ticker (exact) or an industry
    word (substring of sic_description). Returns the matched value or None."""
    e = excl
    if isinstance(excl, dict):
        e = excl.get("ticker") or excl.get("industry") or excl.get("value") or excl.get("text") or ""
    e = str(e).strip()
    if not e:
        return None
    if e.upper() == str(rec.get("ticker") or "").upper():
        return f"ticker={rec.get('ticker')}"
    desc = (rec.get("sic_description") or "").lower()
    if e.lower() in desc and desc:
        return f"sic_description~'{e}'"
    return None


_DERIV_SUFFIX = (".WS", "-WS", "/WS", ".W", "-W", ".U", "-U", ".R", "-R", ".RT", "-RT")


def _non_common_equity(ticker, sic):
    """Identify non-common-equity instruments the mandate doesn't want: blank-check
    SPACs (SIC 6770), and warrants/units/rights via explicit suffix or the Nasdaq
    5th-letter convention (e.g. ABLVW, AACBU). Single/short tickers like 'U' (Unity)
    are NOT caught (the 5th-letter rule needs a 5-char alpha base). Returns a reason or None."""
    t = (ticker or "").upper()
    if str(sic).strip() == "6770":
        return "blank-check/SPAC (SIC 6770)"
    for suf in _DERIV_SUFFIX:
        if t.endswith(suf):
            return f"warrant/unit/right suffix {suf}"
    if len(t) == 5 and t.isalpha() and t[-1] in ("W", "U", "R"):
        return f"Nasdaq 5th-letter '{t[-1]}' (warrant/unit/right)"
    return None


def main(args):
    mandate = _load_mandate(args)
    mandate_hash = mandate.get("mandate_hash") or mandate.get("mandate_id") or ""
    criteria = mandate.get("criteria") or []
    exclusions = mandate.get("exclusions") or []
    hard = [c for c in criteria if _usable_hard(c)]

    rows = skillkit.as_dicts(store.all_metrics())
    survivors, rejects = [], []
    notes = []

    for m in rows:
        rec = {
            "ticker": m.get("ticker"),
            "company": m.get("title") or m.get("ticker"),
            "market_cap": m.get("market_cap"),
            "sic": m.get("sic"),
            "sic_description": m.get("sic_description"),
            "adv": m.get("adv"),
            "country": m.get("country"),
        }

        # 0) instrument hygiene (default ON): drop non-common-equity — SPACs / warrants /
        #    units / rights. The mandate wants operating common stock. Logged, not silent.
        if not getattr(args, "keep_non_common", False):
            nc = _non_common_equity(rec["ticker"], rec.get("sic"))
            if nc:
                rejects.append({"ticker": rec["ticker"], "removed_by": "instrument_hygiene",
                                "constraint": "non-common-equity instrument", "value_seen": nc})
                continue

        removed = False
        # 1) exclusions are hard removals
        for excl in exclusions:
            hit = _exclusion_hit(rec, excl)
            if hit:
                rejects.append({
                    "ticker": rec["ticker"],
                    "removed_by": "exclusion",
                    "constraint": json.dumps(excl) if isinstance(excl, dict) else str(excl),
                    "value_seen": hit,
                })
                removed = True
                break
        if removed:
            continue

        # 2) hard_constraint criteria
        for c in hard:
            col = FIELD_TO_COL[(c.get("field") or "").lower().strip()]
            metric = rec.get(col)
            res = _test(c.get("operator"), col, metric, c.get("value"))
            if res == "SIC_MEMBERSHIP":
                op = (c.get("operator") or "").lower().strip()
                hitp = _sic_token_match(c.get("value"), rec.get("sic"), rec.get("sic_description"))
                if op == "in":
                    res = hitp
                else:  # not_in
                    res = not hitp
            if res is None:
                # NO SILENT DROPS: needed metric missing/indeterminate -> keep + note
                notes.append({
                    "ticker": rec["ticker"],
                    "criterion": c.get("id"),
                    "note": (f"kept despite hard constraint '{c.get('text') or c.get('id')}' "
                             f"because metric '{col}' is missing/indeterminate "
                             f"(value_seen={metric!r})"),
                })
                continue
            if res is False:
                rejects.append({
                    "ticker": rec["ticker"],
                    "removed_by": c.get("id"),
                    "constraint": c.get("text") or f"{c.get('field')} {c.get('operator')} {c.get('value')}",
                    "value_seen": metric,
                })
                removed = True
                break
        if removed:
            continue
        survivors.append(rec)

    # Largest first for a stable, intuitive ordering.
    survivors.sort(key=lambda r: (r.get("market_cap") is None, -(r.get("market_cap") or 0)))

    coverage = {
        "snapshot_names": store.metrics_count(),
        "universe": store.companies_count(),
    }
    applied = [{"id": c.get("id"), "text": c.get("text"),
                "field": c.get("field"), "operator": c.get("operator"),
                "value": c.get("value")} for c in hard]
    summary = (f"{len(survivors)} survivor(s), {len(rejects)} rejected by "
               f"{len(hard)} hard constraint(s) + {len(exclusions)} exclusion(s) "
               f"over {coverage['snapshot_names']} snapshot names. NO SILENT DROPS: "
               f"{len(notes)} name(s) kept on indeterminate metrics.")
    return {
        "mandate_hash": mandate_hash,
        "survivors": survivors,
        "rejects": rejects,
        "kept_notes": notes,
        "applied_constraints": applied,
        "coverage": coverage,
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Stage 1 opportunity filter: apply hard_constraint mandate criteria "
                    "to the company_metrics snapshot (deterministic, no silent drops).")
    p.add_argument("--mandate-file", default=None, help="path to a MandateSpec JSON file")
    p.add_argument("--mandate-json", default=None, help="inline MandateSpec JSON string")
    p.add_argument("--keep-non-common", action="store_true",
                   help="disable instrument hygiene (keep SPACs/warrants/units/rights)")
    skillkit.run(main, p)
