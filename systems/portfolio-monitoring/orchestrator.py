#!/usr/bin/env python3
"""portfolio-monitoring orchestrator.

Deterministic checks (auditable, NEVER model-decided): drift vs targets, gross/net
exposure, drawdown, concentration (HHI), correlation, and thesis-KPI status. The
model only TRIAGES (green/yellow/red) and narrates. Every breach is logged.
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "portfolio-monitoring.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit, estimates, macro, volatility   # noqa: E402
from imrouter import orchestration as orch          # noqa: E402

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "triage": {"type": "array", "items": {"type": "object", "properties": {
            "ticker": {"type": "string"},
            "status": {"type": "string", "enum": ["green", "yellow", "red"]},
            "note": {"type": "string"},
        }, "required": ["ticker", "status", "note"]}},
        "summary": {"type": "string"},
    }, "required": ["triage", "summary"],
}


def _pairs(items):
    out = {}
    for it in items or []:
        if "=" in it:
            k, v = it.split("=", 1); out[k.upper()] = v
    return out


def positions_stage(positions, targets):
    per = {}
    for t in positions:
        px = skillkit.call_skill("price-fetcher", ["--ticker", t, "--lookback", "365", "--no-series"])
        per[t] = {"last": px.get("last"), "return_1y": px.get("return_1y"),
                  "volatility": px.get("annualized_volatility"), "max_drawdown": px.get("max_drawdown")}
    drift, trades = {}, []
    if targets:
        rb = skillkit.call_skill("rebalance-checker",
                                 ["--current", *[f"{t}={w}" for t, w in positions.items()],
                                  "--target", *[f"{t}={w}" for t, w in targets.items()]])
        drift = {d["ticker"]: d for d in rb.get("drift", [])}
        trades = rb.get("trades", [])
    return per, drift, trades


def exposure_stage(positions, args):
    pos = []
    for t, w in positions.items():
        pos += ["--positions", f"{t}={w}"]
    risk = skillkit.call_skill("risk-limit-checker",
                               [*pos, "--max-weight", args.max_weight, "--max-gross",
                                args.max_gross, "--max-drawdown", args.max_drawdown])
    tickers = list(positions.keys())
    corr = skillkit.call_skill("correlation-analyzer",
                               ["--tickers", *tickers, "--weights", *[positions[t] for t in tickers]])
    return risk, corr


def thesis_stage(kpis_by_ticker):
    out = {}
    for t, kpis in kpis_by_ticker.items():
        kargs = ["--ticker", t]
        for k in kpis:
            kargs += ["--kpi", k]
        res = skillkit.call_skill("kpi-tracker", kargs)
        out[t] = {"kpis": res.get("kpis", []), "breaches": res.get("breaches", [])}
    return out


def main(args):
    positions = _pairs(args.positions)
    if not positions:
        raise ValueError("Provide --positions TICKER=weight [TICKER=weight ...].")
    targets = _pairs(args.targets)
    kpis_by_ticker = {}
    for spec in args.kpi or []:
        parts = spec.split(":", 1)
        if len(parts) == 2:
            kpis_by_ticker.setdefault(parts[0].upper(), []).append(parts[1])

    per, drift, trades = positions_stage(positions, targets)
    risk, corr = exposure_stage(positions, args)
    thesis = thesis_stage(kpis_by_ticker)

    # Crowding / ownership risk context (free, yfinance): high short-interest or very
    # high institutional ownership is a real risk lens the model should weigh in triage.
    ownership = {}
    for t in positions:
        o = estimates.get_ownership(t)
        sh = (o or {}).get("short") or {}
        ctx = {"short_pct_float": sh.get("pct_of_float"),
               "short_ratio": sh.get("short_ratio"),
               "pct_institutions": o.get("pct_held_institutions") if o else None}
        ctx = {k: v for k, v in ctx.items() if v is not None}
        if ctx:
            ownership[t] = ctx

    # Macro / volatility risk overlay (public: US Treasury + CBOE VIX). The regime
    # frames how much the book's concentration/correlation actually matters now.
    macro_ctx = {"rates": macro.snapshot(), "vix": volatility.vix()}
    macro_ctx = {k: v for k, v in macro_ctx.items() if v}

    # --- breaches are computed deterministically; the model never decides these ---
    breaches = [{"type": b.get("type"), "detail": b.get("detail")}
                for b in risk.get("breaches", [])]
    for t, info in thesis.items():
        for name in info.get("breaches", []):
            breaches.append({"type": "thesis_kpi", "detail": f"{t}: {name}"})

    prompt = (
        "Triage each position green/yellow/red and write a summary. Return keys "
        "'triage' (array of {ticker, status, note}) and 'summary'. RULES (do not "
        "override): red = the position appears in `breaches` (hard limit or thesis-KPI "
        "breach); yellow = drift past tolerance or weakening KPI; green = within "
        "tolerance. Each 'note' must say WHAT is driving the status (cite the breach, "
        "drift, correlation, or KPI by its number) and the action it implies — not a "
        "generic label. The 'summary' states the book's overall risk posture and the "
        "most urgent action. Ground every note in the data below.\n\n"
        f"positions: {json.dumps(positions)}\n"
        f"per_position: {json.dumps(per, default=str)}\n"
        f"drift: {json.dumps(drift, default=str)}\n"
        f"breaches: {json.dumps(breaches)}\n"
        f"correlation: HHI={corr.get('herfindahl_index')} avg_corr={corr.get('avg_pairwise_correlation')}\n"
        f"ownership_short (crowding context): {json.dumps(ownership, default=str)}\n"
        f"macro_regime (rates + volatility): {json.dumps(macro_ctx, default=str)}"
    )
    tri_system = orch.persona("portfolio-risk-monitor",
                              audience="the portfolio manager and the risk committee")
    tri = orch.synthesize(prompt, task="judgment", schema=TRIAGE_SCHEMA, max_tokens=2500,
                          system=tri_system)
    triage = tri.get("triage") or orch.first_list(tri)
    if not tri.get("_needs_model") and not triage:
        # tighter retry: just the tickers + which ones are in breach
        breached = sorted({b["detail"].split(":")[0].split()[0] for b in breaches if b.get("detail")})
        tri = orch.synthesize(
            "Return key 'triage': an array of {ticker, status, note}. status is red if the "
            "ticker is in `breached`, else green. Each note says what drives the status. "
            "Also a 'summary'.\n"
            f"tickers: {json.dumps(list(positions))}\nbreached: {json.dumps(breached)}",
            task="judgment", schema=TRIAGE_SCHEMA, max_tokens=1500,
            system=orch.persona("portfolio-risk-monitor",
                                audience="the portfolio manager and the risk committee",
                                json_only=True))
        triage = tri.get("triage") or orch.first_list(tri)
    summary = (orch.text_field(tri, "summary") if not tri.get("_needs_model")
               else f"Checked {len(positions)} positions; {len(breaches)} breach(es).")

    # Per-position holdings table: weight + price stats + drift + triage status, merged.
    triage_by = {str(x.get("ticker", "")).upper(): x for x in (triage or []) if isinstance(x, dict)}
    holdings = []
    for tk, w in positions.items():
        p = per.get(tk, {})
        dr = drift.get(tk, {})
        holdings.append({
            "ticker": tk, "weight": float(w) if str(w).replace(".", "", 1).replace("-", "").isdigit() else w,
            "last": p.get("last"), "return_1y": p.get("return_1y"),
            "volatility": p.get("volatility"), "max_drawdown": p.get("max_drawdown"),
            "target": dr.get("target"), "drift": dr.get("drift"),
            "status": (triage_by.get(tk, {}).get("status")),
        })

    # ---------- Report Contract envelope ----------------------------------- #
    today = time.strftime("%Y-%m-%d", time.gmtime())
    by_status = {"red": 0, "yellow": 0, "green": 0}
    for h in holdings:
        s = (h.get("status") or "").lower()
        if s in by_status:
            by_status[s] += 1
    action = ("Action required: " + "; ".join(b.get("detail", "") for b in breaches[:3])
              if breaches else "No limit breaches — book is within all tolerances today.")
    bluf = (f"{len(positions)} positions. Traffic light: {by_status['red']} red, "
            f"{by_status['yellow']} yellow, {by_status['green']} green. "
            f"{len(breaches)} limit breach(es); gross {ex_gross(risk)}, HHI {corr.get('herfindahl_index')}. {action}")
    lim = risk.get("limits", {}) or {}
    assumptions = [
        {"param": "Max position weight", "value": str(args.max_weight), "why": "Single-name concentration cap."},
        {"param": "Max gross exposure", "value": str(args.max_gross), "why": "Leverage / gross-book limit."},
        {"param": "Max drawdown", "value": str(args.max_drawdown), "why": "Trailing peak-to-trough stop."},
        {"param": "Drift tolerance", "value": "vs target weights", "why": "Rebalance trigger when a name drifts past target."},
    ]
    provenance = [
        {"figure": "Prices / returns / vol / drawdown", "source": "yfinance → Yahoo → Stooq (fallback)", "as_of": today},
        {"figure": "Exposure & limit checks", "source": "risk-limit-checker (deterministic)", "as_of": today},
        {"figure": "Concentration (HHI) & correlation", "source": "correlation-analyzer (252-day window)", "as_of": today},
        {"figure": "Thesis KPIs", "source": "kpi-tracker vs recorded baseline", "as_of": today},
    ]
    commentary = [
        {"skill": "price-fetcher", "note": f"Pulled price/return/vol/drawdown for {len(positions)} name(s)."},
        {"skill": "risk-limit-checker", "note": f"Checked weight/gross/net/drawdown vs limits → {len(breaches)} breach(es)."},
        {"skill": "correlation-analyzer", "note": f"HHI {corr.get('herfindahl_index')}, avg pairwise corr {corr.get('avg_pairwise_correlation')}; {len(corr.get('concentration_flags', []))} concentration flag(s)."},
        {"skill": "rebalance-checker", "note": (f"{len(trades)} rebalance trade(s) vs target weights." if trades else "No targets supplied — drift not assessed.")},
        {"skill": "kpi-tracker / audit-logger", "note": f"Thesis KPIs checked; {len(breaches)} breach(es) logged to the audit trail."},
    ]
    risks = []
    if (corr.get("herfindahl_index") or 0) > 0.25:
        risks.append(f"Concentration: HHI {corr.get('herfindahl_index')} exceeds an equal-weight book — single-name risk is elevated.")
    if (corr.get("avg_pairwise_correlation") or 0) > 0.5:
        risks.append(f"Holdings are highly correlated (avg {corr.get('avg_pairwise_correlation')}) — diversification benefit is limited.")
    risks.append("Free-data limitations: weights are as-supplied (not market-value-derived); vol/drawdown on a best-effort price feed.")
    falsifiers = []
    for b in breaches[:3]:
        falsifiers.append(f"Resolve breach: {b.get('detail', '')} — trim to the limit or document an override.")
    falsifiers.append("Re-run after any trade; a new thesis-KPI break flips a holding to red.")
    report = orch.report(classification="Internal", as_of={"prices": today},
                         assumptions=assumptions, provenance=provenance, commentary=commentary,
                         bluf=bluf, risks=risks, falsifiers=falsifiers)

    out = {
        "system": "portfolio-monitoring",
        "positions": positions,
        "holdings": holdings,
        "per_position": per, "drift": drift, "trades": trades,
        "exposure": {"gross": risk.get("gross_exposure"), "net": risk.get("net_exposure"),
                     "max_drawdown": risk.get("max_drawdown"), "limits": risk.get("limits", {})},
        "correlation": {"herfindahl_index": corr.get("herfindahl_index"),
                        "avg_pairwise_correlation": corr.get("avg_pairwise_correlation"),
                        "concentration_flags": corr.get("concentration_flags", []),
                        "kept_tickers": corr.get("kept_tickers", []),
                        "correlation_matrix": corr.get("correlation_matrix")},
        "thesis": thesis,
        "ownership": ownership,         # per-name short interest / institutional ownership
        "macro": macro_ctx,             # rates + VIX regime overlay (public)
        "breaches": breaches,           # deterministic source of truth
        "triage": triage,               # model narration only
        **orch.model_meta(tri),
        "report": report,
        "summary": summary or f"{len(breaches)} breach(es) across {len(positions)} positions.",
    }
    for b in breaches:
        orch.audit("portfolio-monitoring", "breach", b.get("type", "?"), b.get("detail", ""))
    return out


def ex_gross(risk):
    return risk.get("gross_exposure")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Portfolio monitoring orchestrator.")
    p.add_argument("--positions", nargs="*", default=None, help="TICKER=weight ...")
    p.add_argument("--targets", nargs="*", default=None, help="TICKER=weight ...")
    p.add_argument("--kpi", action="append", default=None,
                   help="TICKER:name:metric:comparator:target (repeatable)")
    p.add_argument("--max-weight", default="0.10")
    p.add_argument("--max-gross", default="1.5")
    p.add_argument("--max-drawdown", default="0.25")
    skillkit.run(main, p)
