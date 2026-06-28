"""kpi-extractor: extract company-specific operating KPIs from filings/transcripts. Hybrid model skill."""
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

SCHEMA = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "kpis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "KPI name, e.g. 'Paid memberships', 'ARPU', 'Same-store sales growth'"},
                    "value": {"type": "string", "description": "The reported value, quoted exactly as written"},
                    "unit": {"type": "string", "description": "Unit, e.g. 'millions', '%', 'USD', 'subscribers'"},
                    "period": {"type": "string", "description": "Period the value covers, e.g. 'FY2024', 'Q3 2024'"},
                    "source": {"type": "string", "description": "Where in the text it appeared, e.g. 'MD&A', 'segment results'"},
                },
                "required": ["name", "value"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph plain-English summary of the KPI picture"},
    },
    "required": ["ticker", "kpis", "summary"],
}

SYSTEM = (
    "You are a financial analyst extracting company-SPECIFIC operating KPIs (not generic GAAP lines "
    "like revenue or net income) from a filing or transcript. Focus on the operating metrics that "
    "matter for THIS business: subscribers, units sold, ARPU, bookings, backlog, same-store sales, "
    "DAU/MAU, churn, take rate, store count, etc. Quote values, units, and periods exactly as they "
    "appear. Do not invent any figure; if a unit or period is not stated, leave it blank."
)


def main(args):
    company = None
    ticker = (args.ticker or "").upper()
    source = "pasted"

    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    elif args.text:
        text = args.text
    elif args.ticker:
        info = universe.resolve(args.ticker)
        ticker = info["ticker"]
        company = info["title"]
        row = edgar.latest_filing(args.ticker, "10-K")
        used = "10-K"
        q = edgar.latest_filing(args.ticker, "10-Q")
        # Prefer whichever is newer so KPIs reflect the latest reported period.
        if q and (row is None or (q.get("filing_date") or "") > (row.get("filing_date") or "")):
            row, used = q, "10-Q"
        if row is None:
            raise ValueError(f"No 10-K/10-Q found for {args.ticker}.")
        text = edgar.filing_text(row["accession"])
        source = f"{used} filed {row['filing_date']} (accession {row['accession']})"
    else:
        text = sys.stdin.read()

    if not text or not text.strip():
        raise ValueError("No source text: provide --ticker, --text, --file, or pipe text on stdin.")

    clip = skillkit.excerpt(
        text, max_chars=55000,
        anchors=[r"key (operating |business )?metrics", r"management.?s discussion",
                 r"results of operations", r"segment", r"members|subscribers|users|units|bookings|backlog"],
    )

    header = f"Company: {company or ticker or 'unknown'}"
    if ticker:
        header += f" ({ticker})"
    header += f". Source: {source}."
    prompt = (
        f"{header}\n\nSource text (excerpted):\n{clip}\n\n"
        "Extract the company-specific operating KPIs into the structured list, then write a summary."
    )

    analysis = _route(prompt, task="extraction", system=SYSTEM, schema=SCHEMA, max_tokens=2500)
    meta = {"ticker": ticker, "source": source}
    if company:
        meta["company"] = company
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Extract company-specific operating KPIs from a filing or transcript.")
    p.add_argument("--ticker")
    p.add_argument("--text", default=None)
    p.add_argument("--file", default=None)
    skillkit.run(main, p)
