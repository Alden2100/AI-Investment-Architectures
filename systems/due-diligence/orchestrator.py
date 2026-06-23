#!/usr/bin/env python3
"""due-diligence orchestrator.

A full work-up on one public company: financials + moat + valuation (existing
skills), plus the broadened public data — segment mix, insider activity, a
sanctions screen, Street consensus, and the macro backdrop — synthesised into a
due-diligence brief with a verdict, key risks, and diligence to-dos.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys
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
os.environ.setdefault("IM_LIB_ROOT", LIB)
os.environ.setdefault("IM_SKILLS_DIR", os.path.join(HERE, ".claude", "skills"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", DATA_DIR)
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "due-diligence.db"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit, estimates, ownership, sanctions, segments, macro, universe  # noqa: E402
from imrouter import orchestration as orch                                               # noqa: E402

DD_SCHEMA = {"type": "object", "properties": {
    "verdict": {"type": "string"},
    "thesis": {"type": "string"},
    "key_risks": {"type": "array", "items": {"type": "string"}},
    "diligence_todos": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"},
}, "required": ["verdict", "thesis", "summary"]}


def main(args):
    t = args.ticker.upper()
    info = dict(universe.resolve(t) or {})
    company = info.get("title") or t
    moat = skillkit.call_skill("moat-analyzer", ["--ticker", t])
    dcf = skillkit.call_skill("dcf-valuation", ["--ticker", t])
    fund = skillkit.call_skill("fundamentals-fetcher",
                               ["--ticker", t, "--items", "revenue", "net_income",
                                "operating_income", "free_cash_flow"])
    seg = segments.segments(t)
    insider = ownership.insider_summary(t)
    screen = sanctions.screen(company)
    cons = estimates.get_consensus(t)
    own = estimates.get_ownership(t)
    dossier = {
        "company": company,
        "financials": fund.get("financials", {}),
        "margins": moat.get("margins"),
        "margin_trend": moat.get("margin_trend"),
        "roic": moat.get("roic"),
        "moat": {"type": moat.get("moat_type"), "durability": moat.get("durability"),
                 "summary": moat.get("summary")},
        "dcf": {"intrinsic": dcf.get("intrinsic_value_per_share"),
                "upside": dcf.get("upside_vs_price"),
                "wacc": (dcf.get("assumptions") or {}).get("discount_rate")},
        "segments": {k: v for k, v in seg.items() if k in ("business", "geographic") and v},
        "insider_activity": insider,
        "sanctions_screen": screen,
        "consensus": cons,
        "ownership": own,
        "macro": macro.snapshot(),
    }

    instr = (
        f"Write a due-diligence brief on {company} ({t}) from the dossier below. Return "
        "keys 'verdict' (a clear stance for the IC), 'thesis' (the connected argument), "
        "'key_risks' (array — the real ways this is wrong, incl. any sanctions hit or heavy "
        "insider selling), 'diligence_todos' (array — what to verify before committing), and "
        "'summary' (one paragraph). Use the segment mix for sum-of-parts context, the "
        "multi-year margins/ROIC for moat durability, insider activity as a smart-money tell, "
        "and the consensus to position vs the Street. Ground every claim in the data; do not "
        "invent.\n\n" + json.dumps(dossier, default=str)[:14000])
    res = orch.synthesize(instr, task="synthesis", schema=DD_SCHEMA, max_tokens=3500,
                          system=orch.persona("filing-analyst",
                                              audience="the investment committee, for a full work-up"))
    fields = None if res.get("_needs_model") else orch.recover(
        res, ("verdict", "thesis", "key_risks", "diligence_todos", "summary"))

    import time as _t
    today = _t.strftime("%Y-%m-%d", _t.gmtime())
    summary = orch.text_field(fields or {}, "summary", "thesis") if fields else \
        f"Due-diligence dossier for {company} gathered — set a model route for the brief."
    risks = list((fields or {}).get("key_risks") or [])
    if not screen.get("clear"):
        risks.insert(0, f"⚠ Sanctions/watchlist hit for {company}.")
    if (insider.get("net_open_market_usd") or 0) < 0:
        risks.append(f"Net insider open-market selling (${abs(insider['net_open_market_usd']):,.0f}).")
    out = {
        "system": "due-diligence", "ticker": t, "company": company,
        "dossier": dossier, "brief": fields, "summary": summary,
        **orch.model_meta(res),
        "report": orch.report(
            classification="IC — Due Diligence",
            as_of={"financials": "latest annual", "prices/insider": today},
            bluf=orch.text_field(fields or {}, "thesis", "summary") if fields else summary,
            risks=risks + ["Free-data limitations: single-vendor prices, best-effort insider/segment parsing."],
            falsifiers=list((fields or {}).get("diligence_todos") or
                            ["Verify segment economics, insider context, and the WACC inputs before committing."]),
            provenance=[
                {"figure": "Financials / margins / ROIC / segments", "source": "SEC EDGAR XBRL (public)", "as_of": "latest 10-K"},
                {"figure": "Insider activity", "source": "SEC Form 4 (public)", "as_of": today},
                {"figure": "Sanctions screen", "source": "OFAC SDN (US Treasury, public)", "as_of": today},
                {"figure": "Consensus / ownership", "source": "yfinance (Yahoo)", "as_of": today},
                {"figure": "WACC inputs", "source": "US Treasury + Damodaran (public)", "as_of": today},
            ]),
    }
    orch.audit("due-diligence", "workup", t, f"DD brief via {out.get('model_route', 'none')}")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Due-diligence orchestrator.")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
