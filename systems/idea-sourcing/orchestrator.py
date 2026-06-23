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
def _writable_dir(_p):
    """Use _p if writable, else a per-user cache dir (read-only plugin installs /
    OneDrive-synced trees where SQLite can't open a DB next to the code)."""
    try:
        os.makedirs(_p, exist_ok=True); _t = os.path.join(_p, ".w"); open(_t, "w").close(); os.remove(_t); return _p
    except OSError:
        _a = os.path.join(os.path.expanduser("~"), ".cache", "im-ai-skills", os.path.basename(HERE)); os.makedirs(_a, exist_ok=True); return _a
DATA_DIR = _writable_dir(os.path.join(HERE, "data"))
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
from imdata import skillkit, estimates, ownership    # noqa: E402
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
    if getattr(args, "us_only", False): sargs += ["--us-only"]
    # Sector/size mandates now filter the size-aware snapshot across the whole
    # universe (imdata/screener.py), so the old "--max-fetch 160" top-down hack —
    # which only ever reached the largest names and missed every mid-cap — is gone.
    screened = skillkit.call_skill("universe-screener", sargs)
    matches = screened.get("matches", [])[:int(args.max_candidates)]
    cands = []
    for m in matches:
        f = skillkit.call_skill("fundamentals-fetcher",
                                ["--ticker", m["ticker"], "--items", "revenue",
                                 "net_income", "operating_income", "gross_profit",
                                 "free_cash_flow", "operating_cash_flow", "cash", "total_debt"])
        fin = f.get("financials", {}) or {}
        cands.append({"ticker": m["ticker"], "company": m.get("title"),
                      "market_cap": m.get("market_cap"),
                      "revenue": fin.get("revenue"),
                      "net_income": fin.get("net_income"),
                      "operating_income": fin.get("operating_income"),
                      "gross_profit": fin.get("gross_profit"),
                      "free_cash_flow": fin.get("free_cash_flow") or fin.get("operating_cash_flow"),
                      "cash": fin.get("cash"), "total_debt": fin.get("total_debt")})
    # Carry the screener's coverage/setup signal so a partial-index run isn't read as
    # "no such names" downstream.
    return cands, {"setup_hint": screened.get("setup_hint"),
                   "snapshot_coverage": screened.get("snapshot_coverage")}


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
        # Headlines for context; the REAL article content reaches the model through
        # catalyst-flagger, which now reads direct-source article bodies via web-search.
        news = skillkit.call_skill("news-fetcher", ["--ticker", c["ticker"], "--lookback", "30"])
        c["catalyst_signals"] = signal_counts.get(c["ticker"], {})
        c["catalysts"] = catalysts_by.get(c["ticker"].upper(), [])
        c["top_headlines"] = [i["title"] for i in news.get("items", [])[:6]]
        # Street consensus (free, yfinance): price-target upside + recommendation
        cons = estimates.get_consensus(c["ticker"])
        pt = (cons.get("price_target") or {}) if cons else {}
        c["target_mean"] = pt.get("mean")
        c["recommendation"] = cons.get("recommendation") if cons else None
        c["n_analysts"] = cons.get("n_analysts") if cons else None
        if isinstance(pt.get("mean"), (int, float)) and isinstance(c.get("current_price"), (int, float)) and c["current_price"]:
            c["target_upside"] = round(pt["mean"] / c["current_price"] - 1, 4)
        dcf = skillkit.call_skill("dcf-valuation", ["--ticker", c["ticker"]])
        c["dcf_upside"] = dcf.get("upside_vs_price")
        c["intrinsic_value_per_share"] = dcf.get("intrinsic_value_per_share")
        c["current_price"] = dcf.get("current_price")
        cm = comp_by.get(c["ticker"], {})
        c["ev_ebitda"], c["pe"], c["ps"] = cm.get("ev_ebitda"), cm.get("pe"), cm.get("ps")
        # Growth + margins so the screen rests on more than a single absolute DCF
        # (which is unreliable for hyper-growth names).
        c["revenue_growth"] = cm.get("revenue_growth")
        c["earnings_growth"] = cm.get("earnings_growth")
        c["net_margin"] = cm.get("net_margin")
        c["peg"] = cm.get("peg")
        # Software-relevant quality metrics: gross/operating/FCF margin, Rule-of-40,
        # net cash — the things that actually justify a software multiple. Computed
        # deterministically from the fundamentals pulled in screen().
        rev = c.get("revenue")
        _m = lambda num: (num / rev) if (isinstance(num, (int, float)) and rev) else None
        c["gross_margin"] = _m(c.get("gross_profit"))
        c["operating_margin"] = _m(c.get("operating_income"))
        c["fcf_margin"] = _m(c.get("free_cash_flow"))
        # Rule of 40 = revenue growth % + FCF (or operating) margin %.
        _rg = c.get("revenue_growth")
        _pm = c.get("fcf_margin") if c.get("fcf_margin") is not None else c.get("operating_margin")
        c["rule_of_40"] = (round((_rg + _pm) * 100, 1)
                           if isinstance(_rg, (int, float)) and isinstance(_pm, (int, float)) else None)
        if isinstance(c.get("cash"), (int, float)) or isinstance(c.get("total_debt"), (int, float)):
            c["net_cash"] = (c.get("cash") or 0) - (c.get("total_debt") or 0)
        if not c.get("market_cap"):          # fill from comps when the screen didn't fetch it
            c["market_cap"] = cm.get("market_cap")
        # Insider (Form 4) smart-money signal — net open-market buying/selling.
        ins = ownership.insider_summary(c["ticker"])
        c["insider_signal"] = ins.get("signal")
        c["insider_net_usd"] = ins.get("net_open_market_usd")
        # Data-quality cross-check: flag prices/market caps that disagree with the
        # vendor's own reported figures (share-count mismatch, currency, bad tick).
        c["data_flags"] = estimates.data_quality(
            c["ticker"], used_price=c.get("current_price"), computed_mcap=c.get("market_cap"))
        # Business-model caveat (banks/REITs): EV/EBITDA & DCF mislead — flag so the
        # ranking model and report don't read the multiple as cheap/rich.
        c["valuation_caveat"] = cm.get("valuation_caveat")
        if c["valuation_caveat"]:
            c["data_flags"] = (c["data_flags"] or []) + [c["valuation_caveat"]]
    return comps.get("median", {})


# --------------------------------------------------------------------------- #
# Deterministic composite score — the systemic fix for "the crude DCF leaks out as
# the headline number." Every factor is computed in Python (per the invariant: code
# for what's exact); the model ranks WITH this anchor and explains it, rather than
# inventing an ordering from a +104% single-stage DCF artifact.
# --------------------------------------------------------------------------- #
def _minmax(vals: dict, invert: bool = False) -> dict:
    """ticker->value (None ok) -> ticker->0..1 by min-max across the set; None stays
    None. invert=True for 'lower is better' (cheapness, PEG)."""
    nums = [v for v in vals.values() if isinstance(v, (int, float))]
    if not nums:
        return {k: None for k in vals}
    lo, hi = min(nums), max(nums)
    out = {}
    for k, v in vals.items():
        if not isinstance(v, (int, float)):
            out[k] = None
        else:
            x = 0.5 if hi == lo else (v - lo) / (hi - lo)
            out[k] = (1 - x) if invert else x
    return out


def _blend(*factor_maps):
    """Average the available (non-None) sub-factors per ticker -> ticker->0..1."""
    tickers = factor_maps[0].keys()
    out = {}
    for t in tickers:
        avail = [fm[t] for fm in factor_maps if isinstance(fm.get(t), (int, float))]
        out[t] = sum(avail) / len(avail) if avail else 0.5  # neutral when nothing known
    return out


_SCORE_WEIGHTS = {"value": 0.30, "growth": 0.25, "quality": 0.25,
                  "catalyst": 0.10, "momentum": 0.10}


def score_candidates(cands: list) -> None:
    """Attach per-candidate sub-scores (0-100) + a weighted composite, in place."""
    def col(key):
        return {c["ticker"]: c.get(key) for c in cands}

    def cat_count(c):
        sig = c.get("catalyst_signals") or {}
        base = sum(v for v in sig.values() if isinstance(v, (int, float)))  # next_earnings is a str
        cats = c.get("catalysts") or []
        hard = sum(1 for ev in cats if isinstance(ev, dict) and ev.get("hard_event"))
        return base + len(cats) + hard * 2   # weight concrete events above headline noise

    def insider_pts(c):
        s = (c.get("insider_signal") or "")
        return 1.0 if "buy" in s else 0.0 if "sell" in s else 0.5

    value = _blend(_minmax(col("peg"), invert=True),
                   _minmax(col("ev_ebitda"), invert=True),
                   _minmax(col("target_upside")))
    growth = _blend(_minmax(col("revenue_growth")), _minmax(col("earnings_growth")))
    quality = _blend(_minmax(col("gross_margin")), _minmax(col("operating_margin")),
                     _minmax(col("rule_of_40")), _minmax(col("net_margin")))
    catalyst = _minmax({c["ticker"]: cat_count(c) for c in cands})
    momentum = _blend(_minmax(col("target_upside")),
                      {c["ticker"]: insider_pts(c) for c in cands})
    for c in cands:
        t = c["ticker"]
        sub = {"value": value[t], "growth": growth[t], "quality": quality[t],
               "catalyst": catalyst[t] if catalyst[t] is not None else 0.5, "momentum": momentum[t]}
        composite = sum(_SCORE_WEIGHTS[k] * (sub[k] if sub[k] is not None else 0.5) for k in _SCORE_WEIGHTS)
        c["scores"] = {k: round(v * 100) if isinstance(v, (int, float)) else None for k, v in sub.items()}
        c["composite_score"] = round(composite * 100)


def main(args):
    if not (args.ticker_in or args.name_contains or args.sic_contains
            or args.min_mcap or args.max_mcap):
        raise ValueError("Provide a mandate: --ticker-in and/or --name-contains / "
                         "--sic-contains / --min-mcap / --max-mcap.")
    orch.reset_routing_log()   # so model_routing reflects only this run
    cands, screen_meta = screen(args)
    setup_hint = screen_meta.get("setup_hint")
    if not cands:
        msg = "No names matched the mandate."
        if setup_hint:
            msg = ("No names surfaced, but this is likely a COVERAGE gap, not absence. "
                   + setup_hint)
        return {"candidates": [], "summary": msg,
                "setup_hint": setup_hint, "snapshot_coverage": screen_meta.get("snapshot_coverage")}
    comps_median = enrich(cands)
    score_candidates(cands)   # deterministic composite + sub-scores anchor the ranking

    # Content-rich view for the ranking model — the ACTUAL catalysts (type/date/
    # rationale) and recent headlines, not counts, so each thesis can name a real
    # driver. Trim catalyst rationales so the payload stays bounded.
    def _cat(c):
        out = []
        for ev in (c.get("catalysts") or [])[:5]:
            out.append({"type": ev.get("type"), "date": ev.get("date"),
                        "source": ev.get("source"), "hard_event": ev.get("hard_event"),
                        "confidence": ev.get("confidence"),
                        "rationale": (ev.get("rationale") or "")[:240]})
        return out
    rich = [{"ticker": c["ticker"], "company": c.get("company"),
             "market_cap": c.get("market_cap"),
             "dcf_upside": c.get("dcf_upside"),
             "intrinsic_value_per_share": c.get("intrinsic_value_per_share"),
             "current_price": c.get("current_price"),
             "ev_ebitda": c.get("ev_ebitda"), "pe": c.get("pe"), "ps": c.get("ps"),
             "revenue_growth": c.get("revenue_growth"), "earnings_growth": c.get("earnings_growth"),
             "net_margin": c.get("net_margin"), "gross_margin": c.get("gross_margin"),
             "operating_margin": c.get("operating_margin"), "fcf_margin": c.get("fcf_margin"),
             "rule_of_40": c.get("rule_of_40"), "peg": c.get("peg"),
             "composite_score": c.get("composite_score"), "scores": c.get("scores"),
             "street_target_mean": c.get("target_mean"),
             "street_target_upside": c.get("target_upside"),
             "street_recommendation": c.get("recommendation"),
             "analysts": c.get("n_analysts"),
             "insider_signal": c.get("insider_signal"),
             "data_flags": c.get("data_flags") or [],
             "catalysts": _cat(c),
             "recent_headlines": (c.get("top_headlines") or [])[:6]} for c in cands]
    instr = (
        "Produce a RELATIVE SCREENING shortlist — a ranked list of names worth deeper "
        "diligence, NOT buy/sell investment advice. Return an object with exactly two "
        "keys: 'shortlist' (an array of {ticker, rank, thesis, verdict}) and 'summary' "
        "(one sentence). Each candidate includes its ACTUAL flagged catalysts (with "
        "rationale) and recent headlines — your 'thesis' must name a specific driver (a "
        "real catalyst or headline) plus the relative-valuation case, NOT a count or a "
        "tautology.\n"
        "RANK PRIMARILY on the deterministic 'composite_score' (0-100) and its 'scores' "
        "sub-factors {value, growth, quality, catalyst, momentum} — these already blend "
        "the figures below into one comparable number, so your ordering should track the "
        "composite unless you can argue, with a specific figure, why it's wrong. Each "
        "thesis must name the DRIVING sub-factor (e.g. 'top quality: 78% gross margin + "
        "Rule-of-40 of 52' or 'cheapest: PEG 0.9 vs peers') plus a real catalyst.\n"
        "IMPORTANT valuation guidance: the absolute 'dcf_upside' is a crude single-stage "
        "screen and is UNRELIABLE for high-growth names (it will show deep negatives for "
        "hyper-growth compounders) — do NOT treat it as fair value or lead with it. Anchor "
        "on the composite, growth-adjusted multiples (pe/ev_ebitda vs comps_median, peg), "
        "revenue/earnings growth, margins + Rule-of-40, catalysts, and where the name sits "
        "vs Street consensus (street_target_upside, street_recommendation: cheap on our "
        "numbers but Street already there = crowded; not-yet-consensus = potentially early). If a "
        "candidate has non-empty 'data_flags', explicitly CAVEAT that name's numbers as "
        "possibly unreliable and lower your confidence. 'insider_signal' (SEC Form 4) is a "
        "smart-money tell — recent net insider BUYING supports a name, sustained SELLING is "
        "a mild caution (routine grants/tax sales are not signals). verdict is a screening priority — "
        "one of pursue/watch/pass — not a recommendation. Ground every thesis in the "
        "figures and events given; do not invent.\n"
        + (f"INVESTOR TILT: the user is screening with a '{args.theme}' objective — weight the "
           "ranking toward names that fit that tilt and say in each thesis why it does or "
           "doesn't fit.\n" if getattr(args, "theme", None) else "")
        + f"\ncomps_median: {json.dumps(comps_median)}\n")
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
    # (the 9B sometimes ranks only a couple). Missing names are appended in COMPOSITE-
    # SCORE order with a deterministic thesis citing the score and a verdict from it.
    if shortlist and not ranked.get("_needs_model"):
        cand_by = {c["ticker"]: c for c in cands}
        present = {s.get("ticker") for s in shortlist if isinstance(s, dict)}
        missing = [c for c in cands if c["ticker"] not in present]
        missing.sort(key=lambda c: -(c.get("composite_score") or 0))
        nxt = len(shortlist)
        for c in missing:
            sc = c.get("composite_score")
            verdict = ("pursue" if isinstance(sc, (int, float)) and sc >= 60
                       else "pass" if isinstance(sc, (int, float)) and sc < 35 else "watch")
            nxt += 1
            shortlist.append({
                "ticker": c["ticker"], "rank": nxt, "verdict": verdict,
                "thesis": (f"Composite {sc}/100" if isinstance(sc, (int, float)) else "composite n/a")
                + (f", EV/EBITDA {c['ev_ebitda']:.1f}x" if isinstance(c.get("ev_ebitda"), (int, float)) else "")
                + (f", Rule-of-40 {c['rule_of_40']:.0f}" if isinstance(c.get("rule_of_40"), (int, float)) else "")
                + " (screened; not individually ranked by the model)."})
    # Attach the computed numbers to every shortlist row (the model schema omits them)
    # so the table/PDF columns populate in both the terminal and the PDF.
    cand_by = {c["ticker"]: c for c in cands}
    for s in shortlist:
        if isinstance(s, dict) and s.get("ticker") in cand_by:
            c = cand_by[s["ticker"]]
            for fld in ("dcf_upside", "ev_ebitda", "pe", "ps", "current_price",
                        "market_cap", "revenue", "company",
                        "target_mean", "target_upside", "recommendation",
                        "insider_signal", "insider_net_usd",
                        "composite_score", "scores", "gross_margin", "operating_margin",
                        "fcf_margin", "rule_of_40", "revenue_growth", "net_margin",
                        "peg", "net_cash", "valuation_caveat"):
                s.setdefault(fld, c.get(fld))
            sig = c.get("catalyst_signals") or {}
            s.setdefault("catalysts", sum(v for v in sig.values() if isinstance(v, (int, float))))

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
    # Collect per-name data-quality flags so the report can caveat suspect numbers.
    data_flags = {c["ticker"]: c.get("data_flags") for c in cands if c.get("data_flags")}
    bluf = (f"PROTOTYPE SCREEN (relative ranking for diligence triage — not investment "
            f"advice). Mandate: {mandate}. Screened to {len(cands)} candidate(s); top for "
            f"diligence: {top.get('ticker', '—')} ({(top.get('verdict') or '').upper()}) — "
            f"{orch.text_field({'t': top.get('thesis')}, 't')[:200]}. "
            f"{n_pursue} name(s) flagged PURSUE for deeper work."
            + (f" ⚠ Data-quality flags on: {', '.join(data_flags)}." if data_flags else ""))
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
    risks = ["This is a relative SCREEN for diligence triage, not investment advice — the ranking is not a buy/sell verdict and each name needs full diligence.",
             "Prices/market caps are from a single free vendor (Yahoo via yfinance) and are NOT independently cross-validated; a vendor can be internally consistent yet wrong (see any per-name data-quality flags). Validate the price/share-count join before relying on a level.",
             "The DCF is a crude single-stage screen on house defaults — it materially undervalues hyper-growth names and is used only as a rough sort, not as fair value.",
             "Comps use a simple peer-median multiple across mixed business models; treat the relative read as directional.",
             "Fundamentals are latest-annual (not TTM); no liquidity/ADV screen applied."]
    if data_flags:
        risks.insert(1, "⚠ Data-quality flags raised on " + "; ".join(
            f"{tk}: {', '.join(fl)}" for tk, fl in data_flags.items()) + ".")
    if setup_hint:
        risks.insert(0, "⚠ " + setup_hint)
    falsifiers = [f"Before acting, validate {top.get('ticker', 'each name')}'s price, share count and TTM figures against a second source.",
                  "Advance a name only after diligence confirms the catalyst and the relative-value read holds on TTM/forward numbers.",
                  "Re-screen if the mandate (sector/size) changes."]
    report = orch.report(classification="Prototype screen — not investment advice",
                         as_of={"prices": today, "financials": "latest annual"},
                         assumptions=funnel, provenance=provenance, commentary=commentary,
                         bluf=bluf, risks=risks, falsifiers=falsifiers)

    out = {
        "system": "idea-sourcing",
        "input": {k: v for k, v in vars(args).items() if v},
        "candidates": cands,
        "comps_median": comps_median,
        "shortlist": shortlist,
        "data_flags": data_flags,
        "setup_hint": setup_hint,
        "snapshot_coverage": screen_meta.get("snapshot_coverage"),
        "model_routing": orch.routing_ledger(),   # which rung ran each task (qwen/sonnet/opus)
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
    p.add_argument("--theme", default=None, help="qualitative tilt, e.g. 'growth value'")
    p.add_argument("--us-only", dest="us_only", action="store_true",
                   help="restrict the screen to US filers (exclude foreign issuers / ADRs)")
    p.add_argument("--max-candidates", default="6")
    skillkit.run(main, p)
