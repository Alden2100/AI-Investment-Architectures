"""industry-theme-generator: generate investable themes from macro/tech/industry trends. Hybrid model skill."""
import argparse
import json as _json
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

from imdata import skillkit, macro
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "description": "Investable themes, most compelling first.",
            "items": {
                "type": "object",
                "properties": {
                    "theme": {"type": "string", "description": "Short theme name."},
                    "drivers": {"type": "array", "items": {"type": "string"},
                                "description": "Structural drivers pushing the theme."},
                    "beneficiaries": {"type": "array", "items": {"type": "string"},
                                      "description": "Company types/sub-industries that benefit "
                                                     "(name public tickers only if confident)."},
                    "risks": {"type": "array", "items": {"type": "string"},
                              "description": "What would invalidate or stall the theme."},
                    "time_horizon": {"type": "string",
                                     "description": "Rough horizon, e.g. 'near-term (0-12m)', "
                                                    "'multi-year (2-5y)', 'secular (5y+)'."},
                },
                "required": ["theme", "drivers", "beneficiaries", "risks", "time_horizon"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph synthesis across themes."},
    },
    "required": ["themes", "summary"],
}

SYSTEM = (
    "You are a thematic equity strategist. Generate investable themes grounded in durable "
    "macro, technology, and industry trends. Use the provided macro snapshot (rates, yield "
    "curve, inflation) as backdrop and quote those figures exactly when you reference them; "
    "do not invent macro numbers. For each theme give concrete structural drivers, the kinds "
    "of companies that benefit, the risks that could invalidate it, and a realistic time "
    "horizon. Prefer a few high-conviction themes over a long shallow list."
)


def main(args):
    snap = {}
    try:
        snap = macro.snapshot() or {}
    except Exception:
        snap = {}

    focus = (args.prompt or "").strip()
    sector = (args.sector or "").strip()

    macro_line = (
        "Macro backdrop (computed/fetched — quote exactly, do not invent):\n"
        f"{_json.dumps(snap)}\n" if snap else
        "Macro backdrop: unavailable (no live macro snapshot); reason from general regime "
        "without quoting specific numbers.\n"
    )
    focus_line = f"Requested focus: {focus}\n" if focus else ""
    sector_line = f"Requested sector lens: {sector}\n" if sector else ""

    prompt = (
        f"{macro_line}"
        f"{focus_line}{sector_line}\n"
        "Generate investable themes. Anchor each in structural drivers (technology shifts, "
        "demographics, regulation, capex cycles, the rate/inflation regime above). For each "
        "theme list drivers, beneficiary company types, risks, and a time_horizon. If a focus "
        "or sector lens is given, keep every theme relevant to it. Then write a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2600)
    meta = {"macro_snapshot": snap,
            "focus": focus or None,
            "sector": sector or None}
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Generate investable themes from macro/tech/industry trends.")
    p.add_argument("--prompt", default=None, help="Optional focus for the themes.")
    p.add_argument("--sector", default=None, help="Optional sector lens.")
    skillkit.run(main, p)
