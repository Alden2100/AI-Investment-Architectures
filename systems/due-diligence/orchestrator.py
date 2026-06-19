#!/usr/bin/env python3
"""due-diligence orchestrator — SCAFFOLD.

The deterministic data-gather is real and runnable (it composes working library
skills); the final multi-document synthesis step is stubbed. Promote it to a full
system by adding an `orch.synthesize(...)` step like the other orchestrators.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys
HERE = os.path.dirname(os.path.realpath(__file__))
_d, LIB = HERE, None
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "skills-library")):
        LIB = os.path.join(_d, "skills-library"); break
    _d = os.path.dirname(_d)
DATA_DIR = os.path.join(HERE, "data"); os.makedirs(DATA_DIR, exist_ok=True)
os.environ.setdefault("IM_LIB_ROOT", LIB)
os.environ.setdefault("IM_SKILLS_DIR", os.path.join(HERE, ".claude", "skills"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", DATA_DIR)
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "due-diligence.db"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit                         # noqa: E402


def main(args):
    t = args.ticker.upper()
    dossier = {
        "fundamentals": skillkit.call_skill("fundamentals-fetcher",
                                            ["--ticker", t, "--items", "revenue", "net_income"]),
        "moat": skillkit.call_skill("moat-analyzer", ["--ticker", t]).get("margins"),
        "dcf_upside": skillkit.call_skill("dcf-valuation", ["--ticker", t]).get("upside_vs_price"),
        "news": [i.get("title") for i in
                 skillkit.call_skill("news-fetcher", ["--ticker", t, "--lookback", "30"]
                                     ).get("items", [])[:5]],
    }
    return {
        "system": "due-diligence", "ticker": t, "dossier": dossier,
        "stub": True,
        "next_step": ("SCAFFOLD: deterministic gather done. Add a synthesize() step "
                      "(task='synthesis') to produce the full DD memo."),
        "summary": f"due-diligence (scaffold): gathered DD dossier for {t}.",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Due-diligence orchestrator (scaffold).")
    p.add_argument("--ticker", required=True)
    skillkit.run(main, p)
