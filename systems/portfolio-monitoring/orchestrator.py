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
from imdata import skillkit                         # noqa: E402
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

    # --- breaches are computed deterministically; the model never decides these ---
    breaches = [{"type": b.get("type"), "detail": b.get("detail")}
                for b in risk.get("breaches", [])]
    for t, info in thesis.items():
        for name in info.get("breaches", []):
            breaches.append({"type": "thesis_kpi", "detail": f"{t}: {name}"})

    prompt = (
        "Triage each position green/yellow/red and write a one-sentence summary. "
        "Return keys 'triage' (array of {ticker, status, note}) and 'summary'. "
        "RULES (do not override): red = the position appears in `breaches` (hard "
        "limit or thesis-KPI breach); yellow = drift past tolerance or weakening "
        "KPI; green = within tolerance. Note is one short clause.\n\n"
        f"positions: {json.dumps(positions)}\n"
        f"per_position: {json.dumps(per, default=str)}\n"
        f"drift: {json.dumps(drift, default=str)}\n"
        f"breaches: {json.dumps(breaches)}\n"
        f"correlation: HHI={corr.get('herfindahl_index')} avg_corr={corr.get('avg_pairwise_correlation')}"
    )
    tri = orch.synthesize(prompt, task="judgment", schema=TRIAGE_SCHEMA, max_tokens=1500,
                          system="You are a risk officer. Conservative, rules-first.")
    triage = tri.get("triage") or orch.first_list(tri)
    summary = (orch.text_field(tri, "summary") if not tri.get("_needs_model")
               else f"Checked {len(positions)} positions; {len(breaches)} breach(es).")

    out = {
        "system": "portfolio-monitoring",
        "positions": positions, "per_position": per, "drift": drift, "trades": trades,
        "exposure": {"gross": risk.get("gross_exposure"), "net": risk.get("net_exposure"),
                     "max_drawdown": risk.get("max_drawdown")},
        "correlation": {"herfindahl_index": corr.get("herfindahl_index"),
                        "avg_pairwise_correlation": corr.get("avg_pairwise_correlation")},
        "thesis": thesis,
        "breaches": breaches,           # deterministic source of truth
        "triage": triage,               # model narration only
        "model_route": tri.get("_route", "none"),
        "summary": summary or f"{len(breaches)} breach(es) across {len(positions)} positions.",
    }
    for b in breaches:
        orch.audit("portfolio-monitoring", "breach", b.get("type", "?"), b.get("detail", ""))
    out["output_path"] = orch.write_output("portfolio-monitoring", out)
    return out


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
