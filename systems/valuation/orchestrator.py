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
from imdata import skillkit                         # noqa: E402
from imrouter import orchestration as orch          # noqa: E402

VAL_SCHEMA = {
    "type": "object",
    "properties": {
        "value_range": {"type": "object", "properties": {
            "low": {"type": "number"}, "base": {"type": "number"}, "high": {"type": "number"}},
            "required": ["low", "base", "high"]},
        "recommendation": {"type": "string", "enum": ["buy", "hold", "sell"]},
        "rationale": {"type": "string"},
        "summary": {"type": "string"},
    }, "required": ["value_range", "recommendation", "rationale", "summary"],
}


def main(args):
    t = args.ticker.upper()
    dcf_args = ["--ticker", t]
    if args.growth:         dcf_args += ["--growth", str(args.growth)]
    if args.discount_rate:  dcf_args += ["--discount-rate", str(args.discount_rate)]
    if args.terminal_growth: dcf_args += ["--terminal-growth", str(args.terminal_growth)]
    dcf = skillkit.call_skill("dcf-valuation", dcf_args)

    peers = [t] + [p.upper() for p in (args.peers or [])]
    comps = skillkit.call_skill("comps-builder", ["--tickers", *peers, "--target", t])
    scen = skillkit.call_skill("scenario-analyzer", ["--ticker", t])
    fund = skillkit.call_skill("fundamentals-fetcher",
                               ["--ticker", t, "--items", "revenue", "net_income"])

    price = dcf.get("current_price")
    scenarios = scen.get("scenarios", {})
    dossier = {
        "ticker": t, "current_price": price,
        "dcf_intrinsic": dcf.get("intrinsic_value_per_share"),
        "dcf_upside": dcf.get("upside_vs_price"),
        "comps_median": comps.get("median"),
        "comps_implied": comps.get("target_value") or comps.get("implied_value"),
        "scenarios": {k: scenarios.get(k, {}).get("intrinsic_value_per_share")
                      for k in ("bull", "base", "bear")},
        "fundamentals": fund.get("financials", {}),
    }
    prompt = (
        "Reconcile these three valuation methods into a defensible value range and a "
        "buy/hold/sell call. Return keys 'value_range' ({low, base, high} per-share), "
        "'recommendation' (buy/hold/sell), 'rationale', and 'summary'. low/high should "
        "bracket the DCF, comps-implied, and scenario spread; base is your central "
        "estimate. Compare to current_price. Use only these numbers.\n\n"
        f"{json.dumps(dossier, default=str)}"
    )
    val = orch.synthesize(prompt, task="reasoning", schema=VAL_SCHEMA, max_tokens=1800,
                          system="You are a valuation analyst. Triangulate; show your reasoning briefly.")
    if val.get("_needs_model"):
        summary = f"Built DCF/comps/scenario dossier for {t}; set a model route for the range."
    else:
        summary = orch.text_field(val, "summary") or f"Valuation for {t} via {val.get('_route')}."
    out = {
        "system": "valuation", "ticker": t, "current_price": price,
        "dossier": dossier,
        "valuation": {k: val.get(k) for k in ("value_range", "recommendation", "rationale")
                      } if not val.get("_needs_model") else None,
        "model_route": val.get("_route", "none"),
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
