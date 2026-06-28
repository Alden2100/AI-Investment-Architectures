"""stock-screener-builder: turn a natural-language mandate into a universe-screener filter spec. Hybrid model skill."""
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

from imdata import skillkit
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "filters": {
            "type": "object",
            "description": "Screening filters compatible with the universe-screener CLI. "
                           "Only include a key when the mandate text justifies it; omit or "
                           "null otherwise.",
            "properties": {
                "sic_contains": {"type": ["string", "null"],
                                 "description": "SIC DESCRIPTION substring (matches the "
                                                "industry description text, not the numeric "
                                                "code), e.g. 'software', 'eating'."},
                "name_contains": {"type": ["string", "null"],
                                  "description": "Company-name substring filter."},
                "min_mcap": {"type": ["number", "null"], "description": "Min market cap, USD."},
                "max_mcap": {"type": ["number", "null"], "description": "Max market cap, USD."},
                "min_adv": {"type": ["number", "null"],
                            "description": "Min average daily dollar volume, USD (liquidity floor)."},
                "us_only": {"type": ["boolean", "null"],
                            "description": "Restrict to US-domiciled filers."},
            },
        },
        "rationale": {"type": "string",
                      "description": "Short plain-English explanation mapping mandate phrases "
                                     "to the filters chosen, and noting anything that could NOT "
                                     "be expressed as a structured filter."},
        "suggested_command": {"type": "string",
                              "description": "The universe-screener CLI line, e.g. "
                                             "'python run.py --sic-contains software --min-mcap 2000000000 --us-only'."},
    },
    "required": ["filters", "rationale", "suggested_command"],
}

SYSTEM = (
    "You are a quantitative screening analyst. Translate a natural-language investment "
    "mandate into a STRUCTURED screening filter spec for the universe-screener tool. "
    "Only emit a filter field when the mandate text directly justifies it; never invent a "
    "threshold the user did not imply. IMPORTANT: sic_contains matches the SIC DESCRIPTION "
    "TEXT, not the numeric code (use 'eating' for restaurants, 'software' for software). "
    "Convert verbal sizes to USD numbers ('large-cap' ~ min_mcap 10000000000; 'mid-cap' ~ "
    "2000000000-10000000000; 'small-cap' ~ max_mcap 2000000000; 'billion' = 1000000000). "
    "Express any criterion you cannot map to a filter (growth, valuation, momentum, sector "
    "nuance) in the rationale instead of forcing it into a field. Build suggested_command "
    "from exactly the filters you emit, using flags --sic-contains, --name-contains, "
    "--min-mcap, --max-mcap, --min-adv, --us-only."
)


def main(args):
    query = (args.query or "").strip()
    if not query:
        raise ValueError("Provide a mandate string via --query.")

    prompt = (
        "Investment mandate (natural language):\n"
        f"{skillkit.excerpt(query, max_chars=8000)}\n\n"
        "Produce a screening filter spec. Map sizes/liquidity/geography/industry to the "
        "structured filters where justified; put everything else in the rationale. The "
        "universe-screener flags are: --sic-contains <desc-substring>, --name-contains "
        "<substring>, --min-mcap <usd>, --max-mcap <usd>, --min-adv <usd>, --us-only. "
        "Return suggested_command as the literal CLI line using only the filters you set."
    )

    analysis = _route(prompt, task="extraction", system=SYSTEM, schema=SCHEMA, max_tokens=1200)
    meta = {"query": query}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Convert a natural-language mandate into a universe-screener filter spec.")
    p.add_argument("--query", required=True, help="Natural-language investment criteria.")
    skillkit.run(main, p)
