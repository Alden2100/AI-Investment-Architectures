"""letter-drafter: draft an investor / LP letter from performance and holdings. Hybrid model skill.

run.py parses performance and holdings deterministically and computes simple stats
(e.g. excess return) in Python; the model writes the letter prose, quoting the
Python-computed figures exactly.
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

from imdata import skillkit
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "letter_draft": {"type": "string", "description": "The full letter body"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["letter_draft", "summary"],
}

SYSTEM = (
    "You are a portfolio manager writing a quarterly letter to investors / limited "
    "partners. Be candid, professional, and concise. Use only the data provided; do "
    "not invent figures or holdings. Quote performance numbers exactly as given."
)


def _parse_holdings(items):
    holdings = []
    for it in items or []:
        if "=" not in it:
            raise ValueError(f"--holdings entry '{it}' must be TICKER=weight")
        tk, w = it.split("=", 1)
        holdings.append({"ticker": tk.strip().upper(), "weight": float(w)})
    return holdings


def main(args):
    perf = {}
    if args.performance_file:
        with open(args.performance_file) as f:
            perf = json.load(f)
    if args.performance:
        perf.update(json.loads(args.performance))

    holdings = _parse_holdings(args.holdings)

    computed = {}
    r = perf.get("return")
    b = perf.get("benchmark_return")
    if r is not None and b is not None:
        computed["excess_return"] = round(float(r) - float(b), 6)

    prompt = (
        f"Period: {args.period}.\n\n"
        f"Performance (JSON):\n{json.dumps(perf, indent=2, default=str)}\n\n"
        f"Python-computed stats:\n{json.dumps(computed, indent=2, default=str)}\n\n"
        f"Holdings:\n{json.dumps(holdings, indent=2, default=str)}\n\n"
        "Draft the full investor/LP letter body in `letter_draft`, a short list of "
        "`key_points`, and a one-paragraph `summary`. Quote the figures above exactly; "
        "do not introduce any number not present in the data."
    )

    analysis = _route(prompt, task="drafting", system=SYSTEM, schema=SCHEMA, max_tokens=3000)
    meta = {
        "period": args.period,
        "performance": perf,
        "holdings": holdings,
        "computed": computed,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Draft an investor/LP letter.")
    p.add_argument("--period", required=True, help='e.g. "Q2 2026"')
    p.add_argument("--performance-file", default=None,
                   help="JSON file: {return, benchmark_return, ...}")
    p.add_argument("--performance", default=None,
                   help="inline JSON string of performance data")
    p.add_argument("--holdings", nargs="*", default=None,
                   help="repeatable TICKER=weight")
    skillkit.run(main, p)
