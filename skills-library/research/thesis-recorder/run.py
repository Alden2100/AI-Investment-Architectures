"""thesis-recorder: save an investment thesis and its KPI watchlist to the store."""
import argparse
import hashlib
import json
import os
import sys
import time

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

from imdata import skillkit, store, universe

# metric spec shared concept: a KPI is name:metric:comparator:target.
_METRICS = {"revenue", "net_income", "operating_income", "eps_diluted",
            "price", "return_1y"}
_COMPARATORS = {">=", "<=", ">", "<", "=="}


def _parse_kpi(spec):
    parts = spec.split(":")
    if len(parts) != 4:
        raise ValueError(f"Bad --kpi {spec!r}; expected name:metric:comparator:target")
    name, metric, comparator, target = parts
    if metric not in _METRICS:
        raise ValueError(f"Unknown metric {metric!r} in --kpi {spec!r}")
    if comparator not in _COMPARATORS:
        raise ValueError(f"Unknown comparator {comparator!r} in --kpi {spec!r}")
    return {
        "name": name,
        "metric": metric,
        "comparator": comparator,
        "target": float(target),
    }


def main(args):
    ticker = universe.resolve(args.ticker)["ticker"]
    if not args.title:
        raise ValueError("--title is required.")

    if args.body_file:
        with open(args.body_file, "r", encoding="utf-8") as fh:
            body = fh.read()
    else:
        body = args.body or ""

    kpis = [_parse_kpi(s) for s in (args.kpi or [])]

    thesis_id = args.thesis_id
    if not thesis_id:
        h = hashlib.sha1(f"{ticker}{args.title}{body}".encode("utf-8")).hexdigest()[:6]
        thesis_id = f"{ticker}-{time.strftime('%Y%m%d')}-{h}"

    store.save_thesis(thesis_id, ticker, args.title, body, json.dumps(kpis))

    # Read back to confirm the round-trip.
    row = store.get_thesis(thesis_id)
    if row is None:
        raise RuntimeError(f"Thesis {thesis_id!r} did not persist.")
    saved_kpis = json.loads(row["kpis_json"] or "[]")

    summary = (
        f"Saved thesis {thesis_id} for {ticker}: \"{row['title']}\" with "
        f"{len(saved_kpis)} KPI(s). Round-trip confirmed via store.get_thesis "
        f"(created_at {row['created_at']})."
    )
    return {
        "thesis_id": row["thesis_id"],
        "ticker": row["ticker"],
        "title": row["title"],
        "kpis": saved_kpis,
        "created_at": row["created_at"],
        "summary": summary,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Save an investment thesis and its KPI watchlist to the store."
    )
    p.add_argument("--ticker", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", default=None, help="thesis text")
    p.add_argument("--body-file", default=None, help="path to a text/markdown file")
    p.add_argument("--kpi", action="append", default=None,
                   help="repeatable name:metric:comparator:target")
    p.add_argument("--thesis-id", default=None,
                   help="optional; else generated deterministically")
    skillkit.run(main, p)
