#!/usr/bin/env python3
"""governance-audit orchestrator.

Two modes:
  * with --ticker: a corporate-governance read on a public company from PUBLIC data —
    insider activity (Form 4), large/activist holders (SC 13D/13G), a sanctions /
    watchlist screen (OFAC SDN), and the latest proxy (DEF 14A) — synthesised into a
    governance narrative with red flags.
  * without --ticker: the immutable internal audit trail (decisions/overrides).

All data is deterministic + cached; the synthesis is the one judged step.
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "governance-audit.db"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit, ownership, sanctions, universe, edgar  # noqa: E402
from imrouter import orchestration as orch                          # noqa: E402

GOV_SCHEMA = {"type": "object", "properties": {
    "governance_summary": {"type": "string"},
    "red_flags": {"type": "array", "items": {"type": "string"}},
    "what_to_watch": {"type": "array", "items": {"type": "string"}},
}, "required": ["governance_summary"]}


def main(args):
    out = {"system": "governance-audit"}
    audit = skillkit.call_skill("audit-logger", ["--list", str(args.limit)])
    out["recent_audit"] = audit.get("entries", audit)

    if not args.ticker:
        out["summary"] = "Governance audit: pulled the recent internal audit trail."
        return out

    t = args.ticker.upper()
    info = dict(universe.resolve(t) or {})
    company = info.get("title") or t
    insider = ownership.insider_summary(t)
    beneficial = ownership.beneficial_ownership_filings(t)
    screen = sanctions.screen(company)
    proxy = edgar.latest_filing(t, "DEF 14A")
    proxy = dict(proxy) if proxy else {}
    gov = {
        "ticker": t, "company": company,
        "insider_activity": insider,
        "beneficial_ownership_filings": beneficial,
        "sanctions_screen": screen,
        "latest_proxy": ({"date": proxy.get("filing_date"), "accession": proxy.get("accession")}
                         if proxy else None),
    }
    out["governance"] = gov

    instr = (
        f"Write a corporate-governance read on {company} ({t}) from the public data "
        "below. Return keys 'governance_summary' (a substantive paragraph), 'red_flags' "
        "(array; e.g. heavy insider selling, an activist 13D, a sanctions hit, a stale "
        "or missing proxy — say 'none material' if clean), and 'what_to_watch' (array). "
        "Insider Form-4 signal: net buying is mildly positive, sustained open-market "
        "selling is a yellow flag (grants/tax-withholding are routine, not signals). A "
        "sanctions/watchlist HIT is a prominent red flag. Ground every claim in the data; "
        "do not invent.\n\n" + json.dumps(gov, default=str))
    res = orch.synthesize(instr, task="reasoning", schema=GOV_SCHEMA, max_tokens=2000,
                          system=orch.persona("governance-analyst",
                                              audience="the investment committee and compliance"))
    fields = None if res.get("_needs_model") else orch.recover(
        res, ("governance_summary", "red_flags", "what_to_watch"))
    out["narrative"] = fields
    out.update(orch.model_meta(res))

    # Deterministic red-flag overlay (never depends on the model).
    det_flags = []
    if not screen.get("clear"):
        det_flags.append(f"SANCTIONS/WATCHLIST HIT for '{company}' on {', '.join(screen.get('lists_checked', []))}.")
    if (insider.get("net_open_market_usd") or 0) < 0:
        det_flags.append(f"Net insider OPEN-MARKET SELLING (${abs(insider['net_open_market_usd']):,.0f}).")
    if not proxy:
        det_flags.append("No recent DEF 14A proxy located.")
    out["deterministic_flags"] = det_flags

    today = __import__("time").strftime("%Y-%m-%d", __import__("time").gmtime())
    summ = orch.text_field(fields or {}, "governance_summary") if fields else ""
    out["summary"] = summ or (f"Governance read for {company}: insider {insider.get('signal')}, "
                              f"{len(beneficial)} 13D/G filing(s), sanctions "
                              f"{'CLEAR' if screen.get('clear') else 'HIT'}.")
    out["report"] = orch.report(
        classification="Governance",
        as_of={"insider/ownership": today, "sanctions": "OFAC SDN (latest)"},
        provenance=[
            {"figure": "Insider transactions", "source": "SEC Form 4 (EDGAR, public)", "as_of": today},
            {"figure": "Beneficial ownership", "source": "SEC SC 13D/13G (EDGAR, public)", "as_of": today},
            {"figure": "Sanctions screen", "source": "OFAC SDN list (US Treasury, public)", "as_of": today},
            {"figure": "Proxy", "source": "SEC DEF 14A (EDGAR, public)", "as_of": (proxy or {}).get("filing_date", "n/a")},
        ],
        bluf=out["summary"],
        risks=det_flags + ["Insider/sanctions data is best-effort from free public feeds; confirm any hit against the primary record before acting."],
        falsifiers=["Re-run after the next Form 4 / proxy season or a new 13D/G."])
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Governance / audit orchestrator.")
    p.add_argument("--ticker", default=None, help="company to run a governance read on")
    p.add_argument("--limit", type=int, default=20)
    skillkit.run(main, p)
