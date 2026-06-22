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
    # Scan deeper than the screener's default-30 when filtering by sector/size, so a
    # sector screen reaches past the top mega-caps (companies are ordered by market
    # cap, so this stays "large-cap" while finding more than the 2-3 biggest names).
    if (args.sic_contains or args.min_mcap or args.max_mcap) and not args.ticker_in:
        sargs += ["--max-fetch", "160"]
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
    # Keep the ACTUAL flagged catalyst objects ({type, date, confidence, rationale}),
    # grouped per ticker — not just the count. The rationale is what lets the ranking
    # model cite a real driver instead of a tautological "strong catalyst count".
    catalysts_by = {}
    for ev in (flagged.get("catalysts") or []):
        if isinstance(ev, dict) and ev.get("ticker"):
            catalysts_by.setdefault(ev["ticker"].upper(), []).append(ev)
    comps = skillkit.call_skill("comps-builder", ["--tickers", *tickers])
    comp_by = {r["ticker"]: r for r in comps.get("table", [])}
    for c in cands:
        news = skillkit.call_skill("news-fetcher", ["--ticker", c["ticker"], "--lookback", "30"])
        c["catalyst_signals"] = signal_counts.get(c["ticker"], {})
        c["catalysts"] = catalysts_by.get(c["ticker"].upper(), [])
        c["top_headlines"] = [i["title"] for i in news.get("items", [])[:6]]
        dcf = skillkit.call_skill("dcf-valuation", ["--ticker", c["ticker"]])
        c["dcf_upside"] = dcf.get("upside_vs_price")
        c["intrinsic_value_per_share"] = dcf.get("intrinsic_value_per_share")
        c["current_price"] = dcf.get("current_price")
        cm = comp_by.get(c["ticker"], {})
        c["ev_ebitda"], c["pe"], c["ps"] = cm.get("ev_ebitda"), cm.get("pe"), cm.get("ps")
        if not c.get("market_cap"):          # fill from comps when the screen didn't fetch it
            c["market_cap"] = cm.get("market_cap")
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

    # Content-rich view for the ranking model — the ACTUAL catalysts (type/date/
    # rationale) and recent headlines, not counts, so each thesis can name a real
    # driver. Trim catalyst rationales so the payload stays bounded.
    def _cat(c):
        out = []
        for ev in (c.get("catalysts") or [])[:5]:
            out.append({"type": ev.get("type"), "date": ev.get("date"),
                        "confidence": ev.get("confidence"),
                        "rationale": (ev.get("rationale") or "")[:240]})
        return out
    rich = [{"ticker": c["ticker"], "company": c.get("company"),
             "market_cap": c.get("market_cap"),
             "dcf_upside": c.get("dcf_upside"),
             "intrinsic_value_per_share": c.get("intrinsic_value_per_share"),
             "current_price": c.get("current_price"),
             "ev_ebitda": c.get("ev_ebitda"), "pe": c.get("pe"), "ps": c.get("ps"),
             "catalysts": _cat(c),
             "recent_headlines": (c.get("top_headlines") or [])[:6]} for c in cands]
    instr = (
        "Rank these candidates into an investment shortlist. Return an object with "
        "exactly two keys: 'shortlist' (an array of {ticker, rank, thesis, verdict}) "
        "and 'summary' (one sentence). Each candidate includes its ACTUAL flagged "
        "catalysts (with rationale) and recent headlines — your 'thesis' must name a "
        "specific driver (a real catalyst or headline) plus the valuation case "
        "(dcf_upside, cheapness vs comps_median), NOT a count or a tautology. Weigh "
        "mandate fit, catalyst strength, and valuation upside. verdict is one of "
        "pursue/watch/pass. Ground every thesis in the figures and events given for "
        "that name; do not invent.\n\n"
        f"comps_median: {json.dumps(comps_median)}\n")
    rank_system = orch.persona("screening-analyst", audience="a portfolio manager deciding where to spend diligence time")
    ranked = orch.synthesize(instr + f"candidates: {json.dumps(rich, default=str)}",
                             task="synthesis", schema=RANK_SCHEMA, max_tokens=3500,
                             system=rank_system)
    shortlist = ranked.get("shortlist") or orch.first_list(ranked)
    if not ranked.get("_needs_model") and not shortlist:
        ranked = orch.synthesize(
            instr + f"candidates: {json.dumps(rich, default=str)}",
            task="synthesis", schema=RANK_SCHEMA, max_tokens=2500,
            system=orch.persona("screening-analyst",
                                 audience="a portfolio manager deciding where to spend diligence time",
                                 json_only=True))
        shortlist = ranked.get("shortlist") or orch.first_list(ranked)

    # Backfill any candidate the model dropped, so every sourced name is represented
    # (the 9B sometimes ranks only a couple). Missing names are appended in DCF-upside
    # order with a deterministic numeric thesis and a verdict from the numbers.
    if shortlist and not ranked.get("_needs_model"):
        cand_by = {c["ticker"]: c for c in cands}
        present = {s.get("ticker") for s in shortlist if isinstance(s, dict)}
        missing = [c for c in cands if c["ticker"] not in present]
        missing.sort(key=lambda c: (c.get("dcf_upside") is None, -(c.get("dcf_upside") or -9)))
        nxt = len(shortlist)
        for c in missing:
            up = c.get("dcf_upside")
            verdict = ("pursue" if isinstance(up, (int, float)) and up > 0.15
                       else "pass" if isinstance(up, (int, float)) and up < -0.2 else "watch")
            nxt += 1
            shortlist.append({
                "ticker": c["ticker"], "rank": nxt, "verdict": verdict,
                "thesis": (f"DCF upside {up:+.0%}" if isinstance(up, (int, float)) else "DCF n/a")
                + (f", EV/EBITDA {c['ev_ebitda']:.1f}" if isinstance(c.get("ev_ebitda"), (int, float)) else "")
                + " (screened; not individually ranked by the model)."})
    # Attach the computed numbers to every shortlist row (the model schema omits them)
    # so the table's DCF/valuation columns populate in both the terminal and the PDF.
    cand_by = {c["ticker"]: c for c in cands}
    for s in shortlist:
        if isinstance(s, dict) and s.get("ticker") in cand_by:
            c = cand_by[s["ticker"]]
            for fld in ("dcf_upside", "ev_ebitda", "pe", "ps", "current_price",
                        "market_cap", "revenue", "company"):
                s.setdefault(fld, c.get(fld))
            sig = c.get("catalyst_signals")
            s.setdefault("catalysts", sum(sig.values()) if isinstance(sig, dict) else 0)

    if ranked.get("_needs_model"):
        summary = (f"Sourced {len(cands)} candidate(s): "
                   f"{', '.join(c['ticker'] for c in cands)}; dossier ready — "
                   f"set a model route to rank.")
    else:
        summary = orch.text_field(ranked, "summary") or (
            f"Ranked {len(shortlist)} name(s) via {ranked.get('_route')}: "
            f"{', '.join(s.get('ticker', '?') for s in shortlist)}.")
    # ---------- Report Contract envelope ----------------------------------- #
    import time as _t
    today = _t.strftime("%Y-%m-%d", _t.gmtime())
    mandate_bits = []
    if args.sic_contains: mandate_bits.append(f"sector~'{args.sic_contains}'")
    if args.name_contains: mandate_bits.append(f"name~'{args.name_contains}'")
    if args.min_mcap: mandate_bits.append(f"mcap≥{args.min_mcap}")
    if args.max_mcap: mandate_bits.append(f"mcap≤{args.max_mcap}")
    if args.ticker_in: mandate_bits.append("explicit ticker set")
    mandate = ", ".join(mandate_bits) or "unconstrained"
    top = shortlist[0] if shortlist else {}
    n_pursue = sum(1 for s in shortlist if (s.get("verdict") or "").lower() == "pursue")
    bluf = (f"Mandate: {mandate}. Screened to {len(cands)} candidate(s); top pick "
            f"{top.get('ticker', '—')} ({(top.get('verdict') or '').upper()}) — "
            f"{orch.text_field({'t': top.get('thesis')}, 't')[:200]}. "
            f"{n_pursue} name(s) rated PURSUE for full due diligence.")
    funnel = [
        {"param": "Mandate", "value": mandate, "why": "Universe definition (sector / size / tickers)."},
        {"param": "Candidates surviving screen", "value": str(len(cands)), "why": "Names passing the mandate gates."},
        {"param": "Enriched & scored", "value": str(len(shortlist)), "why": "Each given fundamentals, catalysts, DCF, comps."},
        {"param": "Scoring weights", "value": "valuation + catalyst + mandate fit", "why": "Model ranks on cheapness (DCF/comps) and catalyst density."},
    ]
    provenance = [
        {"figure": "Screen (sector/size)", "source": "SEC EDGAR company facts + SIC", "as_of": today},
        {"figure": "Fundamentals", "source": "SEC EDGAR companyfacts (XBRL)", "as_of": "latest annual"},
        {"figure": "Catalysts", "source": "SEC 8-K filings + Google News RSS", "as_of": today},
        {"figure": "DCF upside / comps", "source": "DCF model + SEC XBRL + market prices", "as_of": today},
    ]
    commentary = [
        {"skill": "universe-screener", "note": f"Filtered the US universe to {len(cands)} name(s) for mandate: {mandate}."},
        {"skill": "fundamentals-fetcher", "note": "Pulled revenue/income per name from XBRL."},
        {"skill": "catalyst-flagger / news-fetcher", "note": "Scanned recent 8-Ks and headlines for event-driven catalysts."},
        {"skill": "dcf-valuation / comps-builder", "note": f"Per-name DCF upside and peer multiples; peer median EV/EBITDA {(comps_median or {}).get('ev_ebitda')}x."},
    ]
    risks = ["DCF uses conservative house defaults (8% growth, 9% WACC); high-growth names screen as 'expensive' on this base.",
             "Free-data limitations: single-year fundamentals, no liquidity/ADV screen, prices best-effort."]
    falsifiers = [f"Advance {top.get('ticker', 'the top name')} to full due diligence; the thesis breaks if its catalyst fails to materialise or valuation re-rates to peers.",
                  "Re-screen if the mandate (sector/size) changes."]
    report = orch.report(classification="Internal", as_of={"prices": today, "financials": "latest annual"},
                         assumptions=funnel, provenance=provenance, commentary=commentary,
                         bluf=bluf, risks=risks, falsifiers=falsifiers)

    out = {
        "system": "idea-sourcing",
        "input": {k: v for k, v in vars(args).items() if v},
        "candidates": cands,
        "comps_median": comps_median,
        "shortlist": shortlist,
        **orch.model_meta(ranked),
        "report": report,
        "summary": summary,
    }
    orch.audit("idea-sourcing", "source", ",".join(c["ticker"] for c in cands),
               f"{len(cands)} candidates ranked via {ranked.get('_route', 'none')}")
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
