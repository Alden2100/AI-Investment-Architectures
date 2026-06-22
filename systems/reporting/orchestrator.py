#!/usr/bin/env python3
"""reporting orchestrator.

Two deliverables, one entry point:
  --memo TICKER   : gather DCF + comps + moat + fundamentals deterministically, then
                    memo-writer drafts an IC memo from those exact numbers.
  --letter PERIOD : letter-drafter writes an investor/LP letter from supplied
                    performance + holdings.
The drafting skills route the writing step themselves (drafting -> Claude, qwen
fallback), so the final prose is auditable and the numbers are never invented.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys, tempfile, time
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "reporting.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit, estimates, segments, macro   # noqa: E402
from imrouter import orchestration as orch          # noqa: E402


def build_memo(ticker):
    t = ticker.upper()
    dcf = skillkit.call_skill("dcf-valuation", ["--ticker", t])
    comps = skillkit.call_skill("comps-builder", ["--tickers", t, "--target", t])
    scen = skillkit.call_skill("scenario-analyzer", ["--ticker", t])
    moat = skillkit.call_skill("moat-analyzer", ["--ticker", t])
    fund = skillkit.call_skill("fundamentals-fetcher",
                               ["--ticker", t, "--items", "revenue", "net_income",
                                "operating_income", "gross_profit", "operating_cash_flow",
                                "free_cash_flow", "total_debt", "cash"])
    # Feed the drafting model the REAL research material (drivers, peer table, scenario
    # spread, full moat read), not just a handful of scalars — a memo argued from the
    # actual evidence beats one written from three numbers. (Pre-digesting to scalars was
    # the old keyless-9B compromise; the judgment layer now runs on Claude.)
    scn = scen.get("scenarios", {})
    inputs = {
        "price": dcf.get("current_price"),
        "dcf_intrinsic_per_share": dcf.get("intrinsic_value_per_share"),
        "dcf_upside": dcf.get("upside_vs_price"),
        "dcf_assumptions": dcf.get("assumptions"),
        "scenarios": {k: (scn.get(k, {}) or {}).get("intrinsic_value_per_share")
                      for k in ("bull", "base", "bear")},
        "comps_median": comps.get("median"),
        "comps_implied_value": comps.get("target_implied_value") or comps.get("target_value")
        or comps.get("implied_value"),
        "comps_table": comps.get("table", []),
        "margins": moat.get("margins"),
        "moat_assessment": (moat.get("assessment") if isinstance(moat.get("assessment"), str)
                            else moat.get("summary") if isinstance(moat.get("summary"), str) else None),
        "moat_type": moat.get("moat_type"),
        "moat_durability": moat.get("durability") or moat.get("moat_durability"),
        "competitive_quality": moat.get("quality"),
        "financials": fund.get("financials", {}),
        # Street consensus + ownership (free, yfinance) so the memo can frame the
        # thesis against what the market expects, and flag ownership/short risk.
        "consensus": estimates.get_consensus(t),
        "ownership": estimates.get_ownership(t),
        # Segment mix (SEC XBRL) for a sum-of-parts view + macro backdrop (public).
        "segments": {k: v for k, v in segments.segments(t).items()
                     if k in ("business", "geographic") and v},
        "macro": macro.snapshot(),
    }
    # Coherence ANCHOR (prevention): state the directional signal the numbers imply,
    # so the memo's recommendation can't drift into contradicting its own DCF.
    _up = inputs.get("dcf_upside")
    _lean = orch.numeric_lean(dcf_upside=_up)
    if _lean != "neutral":
        _pf = f"{_up * 100:+.1f}%" if isinstance(_up, (int, float)) else "n/a"
        inputs["valuation_signal"] = (
            f"The numbers point {_lean.upper()}: DCF intrinsic vs price is {_pf}. "
            "Your recommendation must be consistent with this unless you explicitly "
            "argue, with evidence, why the DCF understates/overstates value.")
    fd, path = tempfile.mkstemp(suffix=".json", dir=DATA_DIR)
    with os.fdopen(fd, "w") as fh:
        json.dump(inputs, fh, default=str)
    memo = skillkit.call_skill("memo-writer", ["--ticker", t, "--input-file", path])
    os.unlink(path)
    inputs_used = ["dcf", "comps", "moat", "fundamentals"]  # the source skills distilled in
    route = memo.get("_route") or ("claude" if memo.get("_source") in ("api", "cli")
                                   else "local" if memo.get("_source") == "ollama" else "none")
    # Be robust to the local 9B model's schema looseness: memo-writer merges model
    # fields into its result, so sections may arrive under `memo_sections`, flattened
    # at top level, or as raw `text`. Recover the draft however it came back.
    SECT = ["thesis", "business_overview", "financials", "valuation", "risks", "recommendation"]
    sections = memo.get("memo_sections")
    if not (isinstance(sections, dict) and sections):
        flat = {k: memo[k] for k in SECT if isinstance(memo.get(k), str) and memo[k].strip()}
        sections = flat or None
    draft_text = memo.get("text") if not sections else None
    needs = bool(memo.get("_needs_model")) or (not sections and not draft_text)
    summary = (memo.get("summary") if isinstance(memo.get("summary"), str) and memo.get("summary").strip()
               else None) or (f"IC memo dossier for {t} ready — set a model route."
                              if needs else f"IC memo drafted for {t} via {route}.")
    import time as _t
    today = _t.strftime("%Y-%m-%d", _t.gmtime())
    rec = (sections.get("recommendation") if isinstance(sections, dict) else "") or ""
    # Coherence CHECK (detection): flag if the recommendation prose directionally
    # contradicts the DCF/price signal — the bug where a memo says OVERWEIGHT while its
    # own DCF shows -50%. Surfaced in the output + Report Contract, never silently shipped.
    coherence_warning = orch.coherence(orch.numeric_lean(dcf_upside=inputs.get("dcf_upside")), rec)
    med = inputs.get("comps_median") or {}
    pf = lambda x: f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "n/a"
    money = lambda x: f"${float(x):,.2f}" if isinstance(x, (int, float)) else "n/a"
    xm = lambda x: f"{x:.1f}x" if isinstance(x, (int, float)) else "n/a"
    bluf = (f"IC recommendation for {t}: {_first_sentence(rec) or 'see recommendation'}. "
            f"Price {money(inputs.get('price'))} vs DCF intrinsic {money(inputs.get('dcf_intrinsic_per_share'))} "
            f"({pf(inputs.get('dcf_upside'))}); comps median EV/EBITDA {xm(med.get('ev_ebitda'))}.")
    assumptions = [
        {"param": "Price", "value": money(inputs.get("price")), "why": "Latest close (best-effort feed)."},
        {"param": "DCF intrinsic / upside", "value": f"{money(inputs.get('dcf_intrinsic_per_share'))} ({pf(inputs.get('dcf_upside'))})", "why": "House DCF (8% growth, 9% WACC defaults)."},
        {"param": "Comps median (EV/EBITDA · P/E)", "value": f"{xm(med.get('ev_ebitda'))} · {xm(med.get('pe'))}", "why": "Peer-relative cross-check."},
    ]
    provenance = [
        {"figure": "Price", "source": "yfinance → Yahoo → Stooq", "as_of": today},
        {"figure": "DCF / fundamentals / margins", "source": "SEC EDGAR companyfacts (XBRL)", "as_of": "latest annual"},
        {"figure": "Comparable multiples", "source": "SEC EDGAR + market prices", "as_of": today},
        {"figure": "Moat / competitive read", "source": "moat-analyzer (10-K + computed margins)", "as_of": "latest 10-K"},
    ]
    commentary = [
        {"skill": "dcf-valuation", "note": f"Intrinsic {money(inputs.get('dcf_intrinsic_per_share'))}/sh ({pf(inputs.get('dcf_upside'))} vs price)."},
        {"skill": "comps-builder", "note": f"Peer median EV/EBITDA {xm(med.get('ev_ebitda'))}, P/E {xm(med.get('pe'))}."},
        {"skill": "moat-analyzer", "note": "Competitive position + margins fed into the memo."},
        {"skill": "memo-writer", "note": f"Drafted the {len(sections) if isinstance(sections, dict) else 0}-section IC memo from the above (route: {route})."},
    ]
    risks = [_first_sentence(sections.get("risks")) if isinstance(sections, dict) and sections.get("risks") else
             "See Risks section.", "Free-data limitations: single-year base, house DCF defaults, best-effort price."]
    if coherence_warning:
        risks.insert(0, "⚠ " + coherence_warning)
    falsifiers = [f"Thesis breaks if {t}'s earnings/FCF trajectory diverges from the DCF base case, or if it re-rates to peer multiples.",
                  "Re-run the memo on the next 10-K/10-Q."]
    report = orch.report(classification="IC", as_of={"prices": today, "financials": "latest annual"},
                         assumptions=assumptions, provenance=provenance, commentary=commentary,
                         bluf=bluf, risks=[r for r in risks if r], falsifiers=falsifiers)
    return {
        "system": "reporting", "kind": "memo", "ticker": t,
        "inputs_used": inputs_used,
        "metrics": inputs,            # distilled numbers, for a key-metrics table in the PDF
        "memo_sections": sections,
        "draft_text": draft_text,
        "needs_model": needs,
        "coherence_warning": coherence_warning or None,
        **orch.model_meta(memo),
        "report": report,
        "summary": summary,
    }


def _first_sentence(s):
    if not isinstance(s, str) or not s.strip():
        return ""
    s = s.strip()
    for sep in (". ", "; "):
        if sep in s:
            return s.split(sep)[0]
    return s[:160]


def build_letter(args):
    largs = ["--period", args.letter]
    if args.performance: largs += ["--performance", args.performance]
    if args.holdings:    largs += ["--holdings", *args.holdings]
    letter = skillkit.call_skill("letter-drafter", largs)
    route = letter.get("_route") or ("claude" if letter.get("_source") in ("api", "cli")
                                     else "local" if letter.get("_source") == "ollama" else "none")
    draft = letter.get("letter_draft") or letter.get("text")
    needs = bool(letter.get("_needs_model")) or not draft
    summary = (letter.get("summary") if isinstance(letter.get("summary"), str) and letter.get("summary").strip()
               else None) or (f"Letter dossier for {args.letter} ready — set a model route."
                              if needs else f"Investor letter drafted for {args.letter} via {route}.")
    return {
        "system": "reporting", "kind": "letter", "period": args.letter,
        "letter_draft": draft,
        "needs_model": needs,
        **orch.model_meta(letter),
        "summary": summary,
    }


def main(args):
    if args.memo:
        out = build_memo(args.memo)
        orch.audit("reporting", "memo", out["ticker"], f"via {out['model_route']}")
    elif args.letter:
        out = build_letter(args)
        orch.audit("reporting", "letter", out["period"], f"via {out['model_route']}")
    else:
        raise ValueError("Provide --memo TICKER or --letter PERIOD.")
    out["output_path"] = orch.write_output("reporting", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Reporting orchestrator (IC memo / investor letter).")
    p.add_argument("--memo", default=None, metavar="TICKER", help="draft an IC memo for a ticker")
    p.add_argument("--letter", default=None, metavar="PERIOD", help='draft a letter, e.g. "Q2 2026"')
    p.add_argument("--performance", default=None, help="letter: e.g. 'fund=+4.2%,bench=+2.1%'")
    p.add_argument("--holdings", nargs="*", default=None, help="letter: TICKER=weight ...")
    skillkit.run(main, p)
