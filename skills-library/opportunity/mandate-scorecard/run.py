"""mandate-scorecard: score ONE company against an investment mandate, criterion by criterion. Hybrid model skill."""
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

from imdata import skillkit, edgar, universe, estimates
from imrouter import route as _route

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
GROSS_PROFIT_TAGS = ["GrossProfit"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
NET_INCOME_TAGS = ["NetIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "criterion_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {"type": "string"},
                    "criterion_text": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["meets", "partial", "does_not_meet"]},
                    "evidence": {"type": "string",
                                 "description": "Short string citing a provided figure or a "
                                                "quote from the provided filing text."},
                    "confidence": {"type": "string",
                                   "enum": ["high", "medium", "low"]},
                },
                "required": ["criterion_id", "verdict", "evidence", "confidence"],
            },
        },
        "flags": {"type": "array", "items": {"type": "string"},
                  "description": "criterion ids marked does_not_meet"},
    },
    "required": ["criterion_results", "flags"],
}

# overall_fit is computed DETERMINISTICALLY in Python from the per-criterion verdicts
# (the model only judges each criterion). meets=1, partial=0.5, does_not_meet=0.
_VERDICT_VAL = {"meets": 1.0, "partial": 0.5, "does_not_meet": 0.0}


def _crit_weight(c):
    try:
        w = float(c.get("weight"))
        return w if w > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _rollup_overall_fit(results, criteria):
    """Weight-aware roll-up over the criteria that actually express the mandate's
    judgment — EXCLUDING hard_constraint (already enforced in Stage 1) and
    portfolio_constraint (enforced in Stage 7). Falls back to all criteria if none qualify."""
    meta = {c.get("id"): (c.get("type"), _crit_weight(c)) for c in criteria}
    num = den = 0.0
    for r in results:
        typ, w = meta.get(r.get("criterion_id"), (None, 1.0))
        if typ in ("hard_constraint", "portfolio_constraint"):
            continue
        v = _VERDICT_VAL.get(r.get("verdict"))
        if v is None:
            continue
        num += w * v
        den += w
    if den <= 0:  # no soft/qualitative criteria — fall back to all scored verdicts
        for r in results:
            v = _VERDICT_VAL.get(r.get("verdict"))
            if v is None:
                continue
            w = meta.get(r.get("criterion_id"), (None, 1.0))[1]
            num += w * v
            den += w
    return round(num / den, 4) if den > 0 else 0.0

SYSTEM = (
    "You are scoring a company against an investment mandate. For EACH criterion give a verdict "
    "(meets / partial / does_not_meet), a short evidence string that cites a provided figure or "
    "a quote from the provided filing text, and a confidence (high / medium / low). Quote the "
    "provided numbers exactly and never invent figures or facts not in the evidence base; if the "
    "evidence is insufficient for a criterion, mark confidence low and lean toward partial. "
    "This is a FIT assessment, NOT a recommendation or investment thesis."
)


def _latest_annual(ticker, tags):
    """First 10-K row (newest-first) with a non-None value across the given tags."""
    for tag in tags:
        rows = edgar.get_concept(ticker, tag)
        for r in rows:
            if r["form"] == "10-K" and r["value"] is not None:
                return float(r["value"]), r["period_end"]
    return None, None


def _annual_map(ticker, tags, n=6):
    """period_end -> value for the last n annual (10-K) periods (deduped)."""
    for tag in tags:
        rows = [r for r in edgar.get_concept(ticker, tag)
                if r["value"] is not None and r["form"] == "10-K" and r["period_end"]]
        if rows:
            m = {}
            for r in sorted(rows, key=lambda x: x["period_end"], reverse=True):
                if r["period_end"] not in m:
                    m[r["period_end"]] = float(r["value"])
                if len(m) >= n:
                    break
            return m
    return {}


def _round(x):
    return round(x, 4) if x is not None else None


def _load_mandate(args):
    if args.mandate_file:
        with open(args.mandate_file, "r") as f:
            spec = json.load(f)
    elif args.mandate_json:
        spec = json.loads(args.mandate_json)
    else:
        raise ValueError("Provide --mandate-file <path> or --mandate-json <json>.")
    criteria = spec.get("criteria") if isinstance(spec, dict) else spec
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("MandateSpec has no criteria[].")
    return criteria


def main(args):
    criteria = _load_mandate(args)
    # portfolio_constraint criteria (max-N-per-industry, liquidity, sizing) are enforced
    # at the portfolio level (Stage 7), not scored per company — drop them here.
    scoring_criteria = [c for c in criteria if (c.get("type") or "") != "portfolio_constraint"]
    info = universe.resolve(args.ticker)

    # --- DETERMINISTIC: margins (latest + trend) -----------------------------
    revenue, rev_end = _latest_annual(args.ticker, REVENUE_TAGS)
    gross, _ = _latest_annual(args.ticker, GROSS_PROFIT_TAGS)
    op_inc, _ = _latest_annual(args.ticker, OPERATING_INCOME_TAGS)
    net_inc, _ = _latest_annual(args.ticker, NET_INCOME_TAGS)

    gross_margin = _round(gross / revenue) if (gross is not None and revenue) else None
    operating_margin = _round(op_inc / revenue) if (op_inc is not None and revenue) else None
    net_margin = _round(net_inc / revenue) if (net_inc is not None and revenue) else None
    margins = {
        "gross": gross_margin,
        "operating": operating_margin,
        "net": net_margin,
        "period_end": rev_end,
    }

    rev_map = _annual_map(args.ticker, REVENUE_TAGS)
    gp_map = _annual_map(args.ticker, GROSS_PROFIT_TAGS)
    oi_map = _annual_map(args.ticker, OPERATING_INCOME_TAGS)
    ni_map = _annual_map(args.ticker, NET_INCOME_TAGS)
    margin_trend = []
    for y in sorted(rev_map, reverse=True)[:5]:
        rev = rev_map.get(y)
        if not rev:
            continue
        margin_trend.append({
            "period_end": y,
            "gross": _round(gp_map[y] / rev) if y in gp_map else None,
            "operating": _round(oi_map[y] / rev) if y in oi_map else None,
            "net": _round(ni_map[y] / rev) if y in ni_map else None,
        })

    # --- DETERMINISTIC: trimmed 10-K business/competition/risk text -----------
    row = edgar.latest_filing(args.ticker, "10-K")
    filing_date = None
    clip = ""
    if row is not None:
        filing_date = row["filing_date"]
        text = edgar.filing_text(row["accession"])
        clip = skillkit.excerpt(
            text, max_chars=55000,
            anchors=[r"item\s*1\b", r"business", r"compet", r"risk factors"],
        )

    # --- DETERMINISTIC: consensus (best-effort, tolerate {}) ------------------
    consensus = {}
    growth = None
    target_mean = None
    try:
        consensus = estimates.get_consensus(args.ticker) or {}
        growth = estimates.consensus_growth(consensus)
        pt = consensus.get("price_target") or {}
        target_mean = pt.get("mean")
    except Exception:
        consensus = {}

    # --- build the evidence base + prompt ------------------------------------
    evidence_lines = (
        "EVIDENCE BASE (computed in Python from XBRL / filings — quote exactly, do not invent):\n"
        f"Latest annual margins (period_end {rev_end}): gross {gross_margin}, "
        f"operating {operating_margin}, net {net_margin}.\n"
        f"Latest annual revenue: {revenue}.\n"
        f"Margin TREND (last {len(margin_trend)} annual periods, newest first): "
        f"{json.dumps(margin_trend)}\n"
        f"Consensus (best-effort): expected growth {growth}, mean price target {target_mean}, "
        f"recommendation {consensus.get('recommendation')}, n_analysts {consensus.get('n_analysts')}.\n"
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). "
        f"10-K filed {filing_date}.\n\n"
        f"{evidence_lines}\n"
        f"10-K text (excerpted around business / competition / risk factors):\n{clip}\n\n"
        "MANDATE CRITERIA to score (each has id / text / type / field / operator / value / weight):\n"
        f"{json.dumps(scoring_criteria, default=str)}\n\n"
        "For EACH criterion above, produce a result with criterion_id, criterion_text (echo the "
        "criterion's text), verdict (meets / partial / does_not_meet), an evidence string that "
        "cites a provided figure or quotes the provided filing text, and confidence. Hard "
        "criteria (numeric field/operator/value) should be judged against the provided figures; "
        "soft and qualitative criteria from the filing text and consensus. List in flags every "
        "criterion_id you marked does_not_meet. (Do NOT compute an overall score — that is "
        "rolled up deterministically downstream.)"
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=3000)

    factor_score = args.factor_score if args.factor_score is not None else None
    text_score = args.text_score if args.text_score is not None else None
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "factor_score": factor_score,
        "text_score": text_score,
        "margins": margins,
    }
    out = skillkit.model_output(analysis, meta)
    if not out.get("_needs_model"):
        out["overall_fit"] = _rollup_overall_fit(out.get("criterion_results") or [], scoring_criteria)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Score one company against an investment mandate, criterion by criterion.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--mandate-file", help="Path to a MandateSpec JSON file.")
    p.add_argument("--mandate-json", help="Inline MandateSpec JSON string.")
    p.add_argument("--factor-score", type=float, default=None,
                   help="Optional deterministic factor score from an upstream stage.")
    p.add_argument("--text-score", type=float, default=None,
                   help="Optional deterministic text score from an upstream stage.")
    skillkit.run(main, p)
