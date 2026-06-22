#!/usr/bin/env python3
"""valuation orchestrator.

Deterministic triangulation: a base-case DCF, a peer comps table (target valued off
peer medians), and a bull/base/bear scenario spread — all computed in Python. Then
ONE bounded model step reconciles them into a value range and a buy/hold/sell lean.
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "valuation.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit, estimates              # noqa: E402
from imrouter import orchestration as orch          # noqa: E402

# The value range is MATH (bracket of the three methods) — computed in code, not by
# the model. The model judges only the call + rationale (code-for-exact, model-for-judged).
VAL_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string", "enum": ["buy", "hold", "sell"]},
        "rationale": {"type": "string"},
        "summary": {"type": "string"},
    }, "required": ["recommendation", "rationale", "summary"],
}


def _m(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _b(v):
    """Abbreviated big-money ($71.6B / $1.1T) for aggregates — keeps tables and
    commentary readable rather than printing $71,611,000,000.00."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "n/a"
    a = abs(x)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"${x / div:,.1f}{suf}"
    return f"${x:,.0f}"


def main(args):
    t = args.ticker.upper()
    dcf_args = ["--ticker", t]
    if args.growth:         dcf_args += ["--growth", str(args.growth)]
    if args.discount_rate:  dcf_args += ["--discount-rate", str(args.discount_rate)]
    if args.terminal_growth: dcf_args += ["--terminal-growth", str(args.terminal_growth)]
    dcf = skillkit.call_skill("dcf-valuation", dcf_args)

    peers = [t] + [p.upper() for p in (args.peers or [])]
    comps = skillkit.call_skill("comps-builder", ["--tickers", *peers, "--target", t])
    # Run scenarios off the SAME derived inputs as the DCF (growth, derived WACC, fade,
    # base FCF, net debt, shares, beta) so the base scenario equals the DCF intrinsic and
    # the bull/bear band is scaled to this company (beta + its own growth), not a flat ±3%.
    _a = dcf.get("assumptions", {}) or {}
    scen_args = ["--ticker", t]
    for flag, key in (("--growth", "growth"), ("--discount-rate", "discount_rate"),
                      ("--terminal-growth", "terminal_growth"), ("--base-fcf", "base_fcf"),
                      ("--net-debt", "net_debt"), ("--shares", "shares")):
        if isinstance(_a.get(key), (int, float)):
            scen_args += [flag, repr(_a[key])]
    if isinstance(_a.get("fade_years"), int):
        scen_args += ["--fade-years", str(_a["fade_years"])]
    _beta = (_a.get("wacc_components") or {}).get("beta")
    if isinstance(_beta, (int, float)):
        scen_args += ["--beta", repr(_beta)]
    scen = skillkit.call_skill("scenario-analyzer", scen_args)
    fund = skillkit.call_skill("fundamentals-fetcher",
                               ["--ticker", t, "--items", "revenue", "net_income",
                                "operating_income", "gross_profit"])

    # Price independently of the DCF, so it's always present even when the DCF can't
    # be built (e.g. banks/financials have no clean free cash flow).
    price = dcf.get("current_price")
    if not isinstance(price, (int, float)):
        px = skillkit.call_skill("price-fetcher", ["--ticker", t, "--lookback", "10", "--no-series"])
        price = px.get("last")
    scenarios = scen.get("scenarios", {})
    fin = fund.get("financials", {})
    rev = fin.get("revenue")
    margins = {}
    if isinstance(rev, (int, float)) and rev:
        for k, lbl in (("gross_profit", "gross"), ("operating_income", "operating"),
                       ("net_income", "net")):
            if isinstance(fin.get(k), (int, float)):
                margins[lbl] = round(fin[k] / rev, 4)
    # comps-builder returns implied value as {by_pe, by_ps, average} — take the average
    _ci = comps.get("target_implied_value")
    comps_implied = _ci.get("average") if isinstance(_ci, dict) else _ci
    comps_implied_detail = _ci if isinstance(_ci, dict) else None
    dossier = {
        "ticker": t, "current_price": price,
        "dcf_intrinsic": dcf.get("intrinsic_value_per_share"),
        "dcf_upside": dcf.get("upside_vs_price"),
        "dcf_assumptions": dcf.get("assumptions", {}),
        "enterprise_value": dcf.get("enterprise_value"),
        "equity_value": dcf.get("equity_value"),
        "comps_median": comps.get("median"),
        "comps_implied": comps_implied,
        "comps_implied_detail": comps_implied_detail,
        "comps_table": comps.get("table", []),
        "scenarios": {k: scenarios.get(k, {}).get("intrinsic_value_per_share")
                      for k in ("bull", "base", "bear")},
        "scenario_detail": scenarios,
        "sensitivity": scen.get("sensitivity_table"),
        "fundamentals": fin,
        "margins": margins,
    }
    # Street consensus (free, yfinance) — what a real note differentiates AGAINST:
    # our DCF growth vs Street growth, our value vs the Street price target.
    consensus = estimates.get_consensus(t)
    if consensus:
        dossier["consensus"] = consensus
        cg = estimates.consensus_growth(consensus)
        og = (dossier.get("dcf_assumptions") or {}).get("growth")
        if isinstance(cg, (int, float)) and isinstance(og, (int, float)):
            dossier["growth_vs_consensus"] = (
                f"Our DCF stage-1 growth {og:.1%} vs Street next-FY ~{cg:.1%}; "
                + ("we are BELOW consensus (conservative)." if og < cg - 0.01
                   else "we are ABOVE consensus (aggressive)." if og > cg + 0.01
                   else "roughly in line with consensus."))
    # Reconciliation (DCF vs comps vs price) — the analytical payoff
    di, ci = dossier["dcf_intrinsic"], comps_implied
    if isinstance(di, (int, float)) and isinstance(ci, (int, float)) and isinstance(price, (int, float)):
        diverge = ("comps above DCF — the market prices in faster growth or higher terminal "
                   "multiples than our base case" if ci > di else
                   "DCF above comps — our cash-flow case is richer than peer multiples imply")
        dossier["reconciliation"] = (f"DCF intrinsic {_m(di)} vs comps-implied {_m(ci)} vs price {_m(price)}; "
                                     f"{diverge}.")
    elif not isinstance(di, (int, float)) and isinstance(ci, (int, float)):
        dossier["reconciliation"] = (f"DCF not meaningful for this company; comps-implied {_m(ci)} vs "
                                     f"price {_m(price)} anchors the call.")
    # --- deterministic value range -----------------------------------------
    # Use the DCF/scenario spread (a single consistent method) so the range is tight
    # and defensible; comps-implied is reported separately as a cross-check in the
    # reconciliation, not folded into the band (it can be a wild outlier).
    bear = scenarios.get("bear", {}).get("intrinsic_value_per_share")
    bull = scenarios.get("bull", {}).get("intrinsic_value_per_share")
    base = dossier["dcf_intrinsic"]
    value_range = None
    if isinstance(bear, (int, float)) and isinstance(bull, (int, float)):
        lo, hi = sorted((bear, bull))
        b = base if isinstance(base, (int, float)) and lo <= base <= hi else round((lo + hi) / 2, 2)
        value_range = {"low": round(lo, 2), "base": round(b, 2), "high": round(hi, 2)}
    elif isinstance(comps_implied, (int, float)):   # financials: no DCF → comps band ±15%
        value_range = {"low": round(comps_implied * 0.85, 2), "base": round(comps_implied, 2),
                       "high": round(comps_implied * 1.15, 2)}

    instr = (
        "Give a buy/hold/sell call on this stock and explain it. Return keys "
        "'recommendation' (buy/hold/sell), 'rationale', and 'summary'. The 'rationale' "
        "is a tight argument (3-6 sentences) that connects the DCF, comps, scenarios and "
        "price to the call — not a list of numbers. Compare the value_range to "
        "current_price (buy well below the range, sell well above it); reconcile where the "
        "methods disagree and say which you weight and why; name the assumption that would "
        "flip the call. Position the call against the Street: compare our DCF growth to the "
        "consensus growth and our value to the analyst price target, and say where your view "
        "DIFFERS from consensus and why (a call with no edge vs consensus isn't worth making). "
        "The 'summary' is one decisive sentence. Ground every claim in the figures below — do "
        "not invent numbers.\n\n"
        f"value_range: {json.dumps(value_range)}\n")
    KEYS = ("recommendation", "rationale", "summary")
    val, vfields = orch.synthesize_fields(
        instr + json.dumps(dossier, default=str), KEYS, task="reasoning", schema=VAL_SCHEMA,
        max_tokens=3000,
        system=orch.persona("valuation-analyst", audience="the investment committee"),
        retry_prompt=instr + json.dumps({k: dossier[k] for k in
            ("current_price", "dcf_intrinsic", "scenarios", "comps_implied", "reconciliation")}, default=str),
        retry_system=orch.persona("valuation-analyst", audience="the investment committee", json_only=True))
    has = bool(vfields and any(vfields.values()))
    valuation = {"value_range": value_range,
                 "recommendation": vfields.get("recommendation") if has else None,
                 "rationale": vfields.get("rationale") if has else None}
    rec = str((valuation.get("recommendation") or "n/a")).upper()
    summary = (orch.text_field({"summary": vfields.get("summary")} if has else {}, "summary")
               or (f"{t}: value range {_m(value_range['low'])}–{_m(value_range['high'])} vs price "
                   f"{_m(price)} → {rec}." if value_range else
                   f"{t}: dossier built; set a model route for the call."))
    # ---------- Report Contract envelope (mostly deterministic) -------------- #
    today = time.strftime("%Y-%m-%d", time.gmtime())
    a = dossier["dcf_assumptions"] or {}
    pf = lambda x: f"{x * 100:+.1f}%" if isinstance(x, (int, float)) else "n/a"
    pg = lambda x: f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "n/a"
    xm = lambda x: f"{x:.1f}x" if isinstance(x, (int, float)) else "n/a"
    dcf_ok = isinstance(dossier["dcf_intrinsic"], (int, float))
    if dcf_ok:
        assumptions = [
            {"param": "FCF growth (explicit)", "value": pg(a.get("growth")), "why": f"{a.get('years', 5)}-yr explicit horizon; base case."},
            {"param": "Discount rate (WACC)", "value": pg(a.get("discount_rate")), "why": "Unlevered cost of capital."},
            {"param": "Terminal growth", "value": pg(a.get("terminal_growth")), "why": "Gordon-growth perpetuity."},
            {"param": "Base FCF", "value": _b(a.get("base_fcf")), "why": a.get("base_fcf_note", "reported OCF − capex")},
            {"param": "Net debt", "value": _b(a.get("net_debt")), "why": "EV→equity bridge."},
            {"param": "Shares out.", "value": f"{a.get('shares'):,.0f}" if isinstance(a.get("shares"), (int, float)) else "—", "why": "Per-share conversion."},
        ]
    else:
        assumptions = [
            {"param": "Method", "value": "Relative multiples (comps)", "why": "No clean free cash flow (financial) — DCF inapplicable."},
            {"param": "Peer set", "value": ", ".join(p.upper() for p in (args.peers or [])) or "—", "why": "Comparable banks/financials."},
            {"param": "Implied-value basis", "value": "median P/E & P/S × target metrics", "why": "Comps-implied fair value."},
            {"param": "Value band", "value": "±15% around comps-implied", "why": "Uncertainty band on the multiple."},
        ]
    provenance = [
        {"figure": "Current price", "source": "yfinance → Yahoo chart → Stooq (fallback chain)", "as_of": today},
        {"figure": "DCF inputs (OCF, capex, debt, shares)", "source": "SEC EDGAR companyfacts (XBRL)", "as_of": "latest annual filing"},
        {"figure": "Comparable multiples", "source": "SEC EDGAR (XBRL) + market prices", "as_of": today},
        {"figure": "Scenario / sensitivity grid", "source": "DCF model (deterministic, growth×WACC)", "as_of": "this run"},
    ]
    nteer = len(dossier.get("comps_table") or [])
    med = dossier.get("comps_median") or {}
    commentary = [
        {"skill": "dcf-valuation", "note": (f"Unlevered-FCF DCF: base FCF {_b(a.get('base_fcf'))}, "
            f"EV {_b(dossier.get('enterprise_value'))}, intrinsic {_m(dossier['dcf_intrinsic'])}/sh ({pf(dossier['dcf_upside'])} vs price)."
            if dcf_ok else "DCF not meaningful — no clean free cash flow (typical for banks/financials); relied on comps.")},
        {"skill": "comps-builder", "note": f"{nteer}-peer multiples table; median EV/EBITDA {xm(med.get('ev_ebitda'))}, P/E {xm(med.get('pe'))}; peer-implied value {_m(dossier.get('comps_implied'))}."},
        {"skill": "scenario-analyzer", "note": "Bull/base/bear cases plus a growth×WACC sensitivity grid (see exhibit)."},
        {"skill": "fundamentals-fetcher", "note": f"Profitability: gross {pg((dossier.get('margins') or {}).get('gross'))}, operating {pg((dossier.get('margins') or {}).get('operating'))}, net {pg((dossier.get('margins') or {}).get('net'))}."},
    ]
    vr = value_range or {}
    if value_range and price:
        loc = "above" if price > vr["high"] else "below" if price < vr["low"] else "within"
        bluf = (f"We rate {t} {rec}. At {_m(price)}, {t} trades {loc} our fair-value range of "
                f"{_m(vr['low'])}–{_m(vr['high'])} (base {_m(vr['base'])}; DCF {pf(dossier['dcf_upside'])}). "
                + (orch.text_field({"r": valuation.get("rationale")}, "r")[:600] if valuation.get("rationale") else
                   ("Bank/financial — DCF not applicable, so the call rests on relative multiples." if not dcf_ok else "")))
    else:
        bluf = summary
    risks, falsifiers = [], []
    if dcf_ok:
        risks.append(f"Value is sensitive to the {pg(a.get('growth'))} FCF growth and {pg(a.get('discount_rate'))} WACC assumptions — a +2pt WACC or −2pt growth materially lowers it (see sensitivity grid).")
        falsifiers.append(f"Revisit the call if realised FCF growth diverges from {pg(a.get('growth'))} by more than ~2pts, or if price exits the {_m(vr.get('low'))}–{_m(vr.get('high'))} band.")
    else:
        risks.append("DCF inapplicable (no clean free cash flow); the call rests on comps, which assume peer multiples persist — sector de-rating is the key downside.")
        falsifiers.append("Revisit if the peer multiple set re-rates materially or the company's earnings trajectory breaks from peers.")
    risks.append("Free-data limitations: a single fiscal-year base, no segment-level model, prices on a best-effort feed.")
    report = orch.report(classification="Internal", as_of={"prices": today, "financials": "latest annual filing"},
                         assumptions=assumptions, provenance=provenance, commentary=commentary,
                         bluf=bluf, risks=risks, falsifiers=falsifiers)

    out = {
        "system": "valuation", "ticker": t, "current_price": price,
        "dossier": dossier,
        "valuation": valuation,
        **orch.model_meta(val),
        "report": report,
        "summary": summary,
    }
    orch.audit("valuation", "valuation", t,
               f"rec={out.get('valuation', {}).get('recommendation') if out.get('valuation') else 'n/a'} "
               f"via {val.get('_route', 'none')}")
    out["output_path"] = orch.write_output("valuation", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Valuation triangulation orchestrator.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--peers", nargs="*", default=None, help="peer tickers for comps")
    p.add_argument("--growth", default=None)
    p.add_argument("--discount-rate", default=None)
    p.add_argument("--terminal-growth", default=None)
    skillkit.run(main, p)
