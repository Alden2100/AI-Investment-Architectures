"""business-model-analyzer: explain how a company generates revenue and creates value. Hybrid model skill."""
import argparse
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

import json as _json

from imdata import skillkit, edgar, universe, segments
from imrouter import route as _route

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
GROSS_PROFIT_TAGS = ["GrossProfit"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
NET_INCOME_TAGS = ["NetIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "company": {"type": "string"},
        "segments": {"type": "string",
                     "description": "Plain-English summary of the company's business segments "
                                    "and how revenue is split across them"},
        "revenue_model": {"type": "string",
                          "description": "How the company actually earns money: what it sells, "
                                         "to whom, and the economic mechanics (one-time vs "
                                         "recurring, transaction vs subscription, etc.)"},
        "value_creation": {"type": "string",
                           "description": "How the business creates value for customers and "
                                          "captures economic value for itself"},
        "key_dependencies": {"type": "array", "items": {"type": "string"},
                             "description": "Critical inputs the model depends on: suppliers, "
                                            "platforms, key customers, regulation, talent, etc."},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["ticker", "company", "revenue_model", "value_creation", "summary"],
}

SYSTEM = (
    "You are an equity research analyst explaining a company's business model: how it "
    "generates revenue and creates value. Reason qualitatively from the 10-K business "
    "section, the parsed revenue segments, and the supplied margin metrics. Do not compute "
    "or invent figures; segment splits and margins were computed in Python and must be "
    "quoted exactly as provided. Describe the revenue mechanics, the value-creation logic, "
    "and the model's key dependencies."
)


def _latest_annual(ticker, tags):
    for tag in tags:
        rows = edgar.get_concept(ticker, tag)
        for r in rows:
            if r["form"] == "10-K" and r["value"] is not None:
                return float(r["value"]), r["period_end"]
    return None, None


def _round(x):
    return round(x, 4) if x is not None else None


def _segment_lines(seg):
    """Summarize parsed segment rows into compact text + a structured list."""
    out = {}
    for kind in ("business", "product", "geographic"):
        rows = seg.get(kind) or []
        items = []
        for r in rows:
            label = r.get("member") or r.get("label")
            val = r.get("value")
            if label is not None and val is not None:
                items.append({"name": label, "value": float(val)})
        if items:
            out[kind] = items
    return out


def main(args):
    info = universe.resolve(args.ticker)

    seg = segments.segments(args.ticker)
    seg_struct = _segment_lines(seg)

    revenue, rev_end = _latest_annual(args.ticker, REVENUE_TAGS)
    gross, _ = _latest_annual(args.ticker, GROSS_PROFIT_TAGS)
    op_inc, _ = _latest_annual(args.ticker, OPERATING_INCOME_TAGS)
    net_inc, _ = _latest_annual(args.ticker, NET_INCOME_TAGS)

    margins = {
        "gross": _round(gross / revenue) if (gross is not None and revenue) else None,
        "operating": _round(op_inc / revenue) if (op_inc is not None and revenue) else None,
        "net": _round(net_inc / revenue) if (net_inc is not None and revenue) else None,
        "period_end": rev_end,
    }

    row = edgar.latest_filing(args.ticker, "10-K")
    if row is None:
        raise ValueError(f"No 10-K found for {args.ticker}.")
    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=55000,
        anchors=[r"item\s*1\b", r"business", r"revenue", r"products?", r"customers?",
                 r"how we (make|generate)"],
    )

    seg_summary = (
        f"Revenue segments parsed from the latest 10-K XBRL (quote exactly, do not recompute):\n"
        f"{_json.dumps(seg_struct) if seg_struct else 'none parsed'}\n"
    )
    margin_summary = (
        f"Latest annual margins (period_end {rev_end}): gross {margins['gross']}, "
        f"operating {margins['operating']}, net {margins['net']}. "
        f"Latest annual revenue: {revenue}.\n"
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). 10-K filed {row['filing_date']}.\n\n"
        f"{seg_summary}\n{margin_summary}\n"
        f"10-K business-section text (excerpted around business/revenue/products/customers):\n"
        f"{clip}\n\n"
        "Explain the business model. Describe the segments (using the parsed splits above), "
        "the revenue model (what is sold, to whom, recurring vs transactional), how the "
        "company creates and captures value (cite the margins as evidence of pricing power "
        "or cost structure), and list the key dependencies the model relies on. "
        "Set ticker and company in your answer."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "segments": seg_struct,
        "margins": margins,
        "revenue": revenue,
        "filing_date": row["filing_date"],
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Explain how a company generates revenue and creates value.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
