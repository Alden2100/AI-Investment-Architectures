"""moat-analyzer: assess competitive advantage / moat from a 10-K plus computed margins. Hybrid model skill."""
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

from imdata import skillkit, edgar, universe
from imrouter import route as _route

REVENUE_TAGS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]
GROSS_PROFIT_TAGS = ["GrossProfit"]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
NET_INCOME_TAGS = ["NetIncomeLoss"]

SCHEMA = {
    "type": "object",
    "properties": {
        "moat_type": {"type": "string",
                      "description": "Primary moat: network effects / switching costs / "
                                     "scale / brand / cost advantage / intangibles / none"},
        "durability": {"type": "string",
                       "description": "high/medium/low plus a brief why"},
        "threats": {"type": "array", "items": {"type": "string"},
                    "description": "Key threats to the moat / competitive position"},
        "summary": {"type": "string", "description": "One-paragraph plain-English assessment"},
    },
    "required": ["moat_type", "durability", "summary"],
}

SYSTEM = (
    "You are an equity research analyst assessing a company's competitive advantage "
    "(economic moat) and industry position. Reason qualitatively from the 10-K business, "
    "competition, and risk-factor text, using the provided margin metrics as supporting "
    "evidence. Do not compute or invent figures; the margins given were computed in Python "
    "and must be quoted exactly as provided. Classify the moat type and judge its durability."
)


def _latest_annual(ticker, tags):
    """First 10-K row (newest-first) with a non-None value across the given tags."""
    for tag in tags:
        rows = edgar.get_concept(ticker, tag)
        for r in rows:
            if r["form"] == "10-K" and r["value"] is not None:
                return float(r["value"]), r["period_end"]
    return None, None


def _round(x):
    return round(x, 4) if x is not None else None


def main(args):
    info = universe.resolve(args.ticker)

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

    row = edgar.latest_filing(args.ticker, "10-K")
    if row is None:
        raise ValueError(f"No 10-K found for {args.ticker}.")
    text = edgar.filing_text(row["accession"])
    clip = skillkit.excerpt(
        text, max_chars=60000,
        anchors=[r"item\s*1\b", r"compet", r"risk factors",
                 r"business", r"intellectual property"],
    )

    margin_lines = (
        f"Computed margins for the latest annual period (period_end {rev_end}), "
        "computed in Python from XBRL — quote exactly, do not recompute:\n"
        f"- gross_margin: {gross_margin}\n"
        f"- operating_margin: {operating_margin}\n"
        f"- net_margin: {net_margin}\n"
    )
    prompt = (
        f"Company: {info['title']} ({info['ticker']}). 10-K filed {row['filing_date']}.\n\n"
        f"{margin_lines}\n"
        f"10-K text (excerpted around business/competition/risk):\n{clip}\n\n"
        "Assess the economic moat: classify moat_type, judge durability (high/medium/low + why), "
        "list threats, and write a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {
        "ticker": info["ticker"],
        "company": info["title"],
        "margins": margins,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Assess a company's competitive moat and position.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
