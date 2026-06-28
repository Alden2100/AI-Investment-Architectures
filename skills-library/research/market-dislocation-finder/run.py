"""market-dislocation-finder: surface valuation gaps across a set of names. Hybrid model skill."""
import argparse
import json as _json
import os
import statistics
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

from imdata import skillkit, estimates, finviz, prices, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "dislocations": {
            "type": "array",
            "description": "Names judged to be genuinely dislocated (rich or cheap) vs the "
                           "peer set, drawn from the computed gaps below.",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "metric": {"type": "string",
                               "description": "Which multiple drives the call (e.g. forward_pe)."},
                    "value": {"type": ["number", "null"], "description": "The name's metric value (quote exactly)."},
                    "peer_median": {"type": ["number", "null"], "description": "Peer median (quote exactly)."},
                    "direction": {"type": "string",
                                  "description": "'cheap' (below median) or 'rich' (above median)."},
                    "note": {"type": "string",
                             "description": "Why this gap is (or isn't) a real dislocation vs a "
                                            "justified difference in quality/growth."},
                },
                "required": ["ticker", "metric", "direction", "note"],
            },
        },
        "summary": {"type": "string", "description": "One-paragraph read on the set."},
    },
    "required": ["dislocations", "summary"],
}

SYSTEM = (
    "You are a valuation analyst hunting for mispricings within a peer set. You are given, "
    "per name, valuation multiples and each multiple's deviation from the PEER MEDIAN "
    "(computed in Python). Quote every supplied figure exactly; do not recompute or invent. "
    "A raw gap is NOT automatically a dislocation: a low multiple can be a value trap and a "
    "high multiple can be deserved by superior growth/quality. Judge which gaps look like "
    "REAL dislocations versus justified differences, and say why. Only list names you "
    "consider genuinely dislocated."
)

# (metric_key, source) — pulled per ticker
_METRICS = [
    ("forward_pe", "consensus"),
    ("trailing_pe", "consensus"),
    ("peg", "consensus"),
    ("P/B", "finviz"),
    ("P/S", "finviz"),
]


def _num(x):
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace("%", "").replace(",", "").strip()
            if x in ("", "-", "N/A"):
                return None
        return float(x)
    except (ValueError, TypeError):
        return None


def _gather(ticker):
    cons = {}
    fv = {}
    try:
        cons = estimates.get_consensus(ticker) or {}
    except Exception:
        cons = {}
    try:
        fv = finviz.key_stats(ticker) or {}
    except Exception:
        fv = {}
    last = None
    try:
        last = prices.last_price(ticker)
    except Exception:
        last = None
    row = {"ticker": ticker.upper(), "last_price": _num(last)}
    for key, src in _METRICS:
        val = cons.get(key) if src == "consensus" else fv.get(key)
        row[key] = _num(val)
    return row


def main(args):
    tickers = [t.upper() for t in (args.tickers or [])]
    if len(tickers) < 2:
        raise ValueError("Provide at least two tickers via --tickers for a peer comparison.")

    rows = [_gather(t) for t in tickers]
    names = {}
    for t in tickers:
        try:
            names[t] = universe.title_for_ticker(t) or t
        except Exception:
            names[t] = t

    # --- peer median per metric, then each name's gap (z-score-ish) -----------
    metric_keys = [k for k, _ in _METRICS]
    medians = {}
    for k in metric_keys:
        vals = [r[k] for r in rows if r.get(k) is not None]
        medians[k] = round(statistics.median(vals), 4) if vals else None

    gaps = []
    for r in rows:
        for k in metric_keys:
            v = r.get(k)
            med = medians.get(k)
            if v is None or med is None or med == 0:
                continue
            pct = round((v - med) / abs(med), 4)
            gaps.append({
                "ticker": r["ticker"],
                "metric": k,
                "value": v,
                "peer_median": med,
                "pct_vs_median": pct,
                "direction": "rich" if v > med else "cheap",
            })

    prompt = (
        f"Peer set: {_json.dumps([{'ticker': t, 'name': names[t]} for t in tickers])}\n\n"
        "Per-name valuation multiples (computed in Python — quote exactly):\n"
        f"{_json.dumps(rows)}\n\n"
        "Peer MEDIAN per metric (computed in Python):\n"
        f"{_json.dumps(medians)}\n\n"
        "Each name's gap vs the peer median (pct_vs_median = (value - median)/|median|):\n"
        f"{_json.dumps(gaps)}\n\n"
        "Judge which gaps are REAL dislocations versus justified by quality/growth. List only "
        "the genuinely dislocated names with the driving metric, value, peer_median, direction, "
        "and a note on why. Then write a summary."
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2400)
    meta = {
        "tickers": tickers,
        "names": names,
        "metrics": rows,
        "peer_medians": medians,
        "gaps": gaps,
    }
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Surface valuation gaps / potential mispricings across a set of names.")
    p.add_argument("--tickers", nargs="+", required=True, help="Two or more tickers to compare.")
    skillkit.run(main, p)
