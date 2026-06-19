#!/usr/bin/env python3
"""idea-sourcing orchestrator.

Deterministic fan-out: mandate -> screen the universe -> enrich each candidate with
fundamentals, catalysts/news, a DCF, and peer multiples. Then ONE bounded model
step (routed per policy, logged) ranks the dossier into a shortlist with a one-line
thesis per name. Math is always the skills'; the model only judges and ranks.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.realpath(__file__))
_d, LIB = HERE, None
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "skills-library")):
        LIB = os.path.join(_d, "skills-library"); break
    _d = os.path.dirname(_d)
DATA_DIR = os.path.join(HERE, "data"); os.makedirs(DATA_DIR, exist_ok=True)
_envf = os.path.join(os.path.dirname(LIB), ".env")
if os.path.exists(_envf):
    for _ln in open(_envf):
        _ln = _ln.strip()
        if _ln and not _ln.startswith("#") and "=" in _ln:
            _k, _v = _ln.split("=", 1); os.environ.setdefault(_k.strip(), _v.strip().strip('"'))
os.environ.setdefault("IM_LIB_ROOT", LIB)
os.environ.setdefault("IM_SKILLS_DIR", os.path.join(HERE, ".claude", "skills"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", DATA_DIR)
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "idea-sourcing.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit                         # noqa: E402
from imrouter import orchestration as orch          # noqa: E402

RANK_SCHEMA = {
    "type": "object",
    "properties": {
        "shortlist": {"type": "array", "items": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "rank": {"type": "integer"},
            "thesis": {"type": "string"},
            "verdict": {"type": "string", "enum": ["pursue", "watch", "pass"]},
        }, "required": ["ticker", "rank", "thesis", "verdict"]}},
        "summary": {"type": "string"},
    }, "required": ["shortlist", "summary"],
}


def screen(args):
    sargs = ["--limit", int(args.max_candidates)]
    if args.ticker_in:   sargs += ["--ticker-in", *args.ticker_in]
    if args.name_contains: sargs += ["--name-contains", args.name_contains]
    if args.sic_contains:  sargs += ["--sic-contains", args.sic_contains]
    if args.min_mcap:      sargs += ["--min-mcap", args.min_mcap]
    if args.max_mcap:      sargs += ["--max-mcap", args.max_mcap]
    screened = skillkit.call_skill("universe-screener", sargs)
    matches = screened.get("matches", [])[:int(args.max_candidates)]
    cands = []
    for m in matches:
        f = skillkit.call_skill("fundamentals-fetcher",
                                ["--ticker", m["ticker"], "--items", "revenue",
                                 "net_income", "operating_income"])
        cands.append({"ticker": m["ticker"], "company": m.get("title"),
                      "market_cap": m.get("market_cap"),
                      "revenue": f.get("financials", {}).get("revenue"),
                      "net_income": f.get("financials", {}).get("net_income")})
    return cands


def enrich(cands):
    tickers = [c["ticker"] for c in cands]
    flagged = skillkit.call_skill("catalyst-flagger", ["--tickers", *tickers, "--lookback", "30"])
    signal_counts = flagged.get("signal_counts", {})
    comps = skillkit.call_skill("comps-builder", ["--tickers", *tickers])
    comp_by = {r["ticker"]: r for r in comps.get("table", [])}
    for c in cands:
        news = skillkit.call_skill("news-fetcher", ["--ticker", c["ticker"], "--lookback", "30"])
        c["catalyst_signals"] = signal_counts.get(c["ticker"], {})
        c["top_headlines"] = [i["title"] for i in news.get("items", [])[:4]]
        dcf = skillkit.call_skill("dcf-valuation", ["--ticker", c["ticker"]])
        c["dcf_upside"] = dcf.get("upside_vs_price")
        c["intrinsic_value_per_share"] = dcf.get("intrinsic_value_per_share")
        c["current_price"] = dcf.get("current_price")
        cm = comp_by.get(c["ticker"], {})
        c["ev_ebitda"], c["pe"], c["ps"] = cm.get("ev_ebitda"), cm.get("pe"), cm.get("ps")
    return comps.get("median", {})


def main(args):
    if not (args.ticker_in or args.name_contains or args.sic_contains
            or args.min_mcap or args.max_mcap):
        raise ValueError("Provide a mandate: --ticker-in and/or --name-contains / "
                         "--sic-contains / --min-mcap / --max-mcap.")
    cands = screen(args)
    if not cands:
        return {"candidates": [], "summary": "No names matched the mandate."}
    comps_median = enrich(cands)

    # compact, high-signal view of each candidate for the ranking model
    slim = [{"ticker": c["ticker"], "dcf_upside": c.get("dcf_upside"),
             "ev_ebitda": c.get("ev_ebitda"), "pe": c.get("pe"),
             "catalysts": sum((c.get("catalyst_signals") or {}).values())
             if isinstance(c.get("catalyst_signals"), dict) else 0,
             "headlines": len(c.get("top_headlines") or [])} for c in cands]
    instr = (
        "Rank these candidates into an investment shortlist. Return an object with "
        "exactly two keys: 'shortlist' (an array of {ticker, rank, thesis, verdict}) "
        "and 'summary' (one sentence). Weigh mandate fit, catalyst strength, and "
        "valuation upside (dcf_upside and cheapness vs comps_median). verdict is one of "
        "pursue/watch/pass. Use only the numbers given.\n\n"
        f"comps_median: {json.dumps(comps_median)}\n")
    ranked = orch.synthesize(instr + f"candidates: {json.dumps(slim, default=str)}",
                             task="synthesis", schema=RANK_SCHEMA, max_tokens=1800,
                             system="You are a disciplined buy-side analyst. Be terse and specific.")
    shortlist = ranked.get("shortlist") or orch.first_list(ranked)
    if not ranked.get("_needs_model") and not shortlist:
        ranked = orch.synthesize(
            instr + f"candidates: {json.dumps([s['ticker'] for s in slim])}",
            task="synthesis", schema=RANK_SCHEMA, max_tokens=1400,
            system="Buy-side analyst. Output only the JSON object with 'shortlist' and 'summary'.")
        shortlist = ranked.get("shortlist") or orch.first_list(ranked)
    if ranked.get("_needs_model"):
        summary = (f"Sourced {len(cands)} candidate(s): "
                   f"{', '.join(c['ticker'] for c in cands)}; dossier ready — "
                   f"set a model route to rank.")
    else:
        summary = orch.text_field(ranked, "summary") or (
            f"Ranked {len(shortlist)} name(s) via {ranked.get('_route')}: "
            f"{', '.join(s.get('ticker', '?') for s in shortlist)}.")
    out = {
        "system": "idea-sourcing",
        "input": {k: v for k, v in vars(args).items() if v},
        "candidates": cands,
        "comps_median": comps_median,
        "shortlist": shortlist,
        "model_route": ranked.get("_route", "none"),
        "summary": summary,
    }
    orch.audit("idea-sourcing", "source", ",".join(c["ticker"] for c in cands),
               f"{len(cands)} candidates ranked via {ranked.get('_route', 'none')}")
    out["output_path"] = orch.write_output("idea-sourcing", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Idea sourcing orchestrator.")
    p.add_argument("--ticker-in", nargs="*", default=None)
    p.add_argument("--name-contains", default=None)
    p.add_argument("--sic-contains", default=None)
    p.add_argument("--min-mcap", default=None)
    p.add_argument("--max-mcap", default=None)
    p.add_argument("--max-candidates", default="6")
    skillkit.run(main, p)
