#!/usr/bin/env python3
"""governance-audit orchestrator — SCAFFOLD.

Reads the immutable audit trail and saved theses for a name and lists them. The
deterministic read is real; the governance-narrative synthesis is stubbed.
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "governance-audit.db"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit                         # noqa: E402


def main(args):
    log = skillkit.call_skill("audit-logger", ["--list", str(args.limit)])
    return {
        "system": "governance-audit",
        "recent_audit": log.get("entries", log),
        "stub": True,
        "next_step": ("SCAFFOLD: add a synthesize() step (task='reasoning') to turn "
                      "the trail into a governance/compliance narrative and exceptions."),
        "summary": "governance-audit (scaffold): pulled the recent audit trail.",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Governance/audit orchestrator (scaffold).")
    p.add_argument("--limit", type=int, default=20)
    skillkit.run(main, p)
