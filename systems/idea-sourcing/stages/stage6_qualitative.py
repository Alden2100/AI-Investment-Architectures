"""Stage 6 — qualitative-researcher driver with the confirming/disconfirming debate.

Pure (leaf-skill calls only -> worker-safe). For one company:
  1. confirming-evidence + disconfirming-evidence (round 1, cheap rung).
  2. one bounded rebuttal round — each side sees the other's evidence once.
  3. evidence-reconciler ONLY when the two sides materially conflict (overlap on a
     dimension), on the high rung.
Returns BOTH sides as tagged evidence + an optional reconciliation. Evidence only —
the leaf skills enforce the no-thesis rule.
"""
from __future__ import annotations

import json

from imdata import skillkit


def _evidence(out):
    return out.get("evidence", []) if isinstance(out, dict) else []


def run(mandate: dict, ticker: str) -> dict:
    conf1 = skillkit.call_skill("confirming-evidence", ["--ticker", ticker])
    disc1 = skillkit.call_skill("disconfirming-evidence", ["--ticker", ticker])
    conf_ev, disc_ev = _evidence(conf1), _evidence(disc1)

    # one bounded rebuttal round — each side rebuts the other's round-1 evidence
    if disc_ev:
        c2 = skillkit.call_skill("confirming-evidence",
                                 ["--ticker", ticker, "--round", 2, "--rebut", json.dumps(disc_ev)])
        conf_ev = _evidence(c2) or conf_ev
    if conf_ev:
        d2 = skillkit.call_skill("disconfirming-evidence",
                                 ["--ticker", ticker, "--round", 2, "--rebut", json.dumps(conf_ev)])
        disc_ev = _evidence(d2) or disc_ev

    # material conflict = the two sides argue the SAME dimension in opposite directions
    cdims = {e.get("dimension") for e in conf_ev if isinstance(e, dict)}
    ddims = {e.get("dimension") for e in disc_ev if isinstance(e, dict)}
    conflict = bool(cdims & ddims) and bool(conf_ev) and bool(disc_ev)

    reconciliation, lean = None, None
    if conflict:
        rec = skillkit.call_skill("evidence-reconciler",
                                  ["--ticker", ticker, "--confirming", json.dumps(conf_ev),
                                   "--disconfirming", json.dumps(disc_ev)])
        if not rec.get("error"):
            reconciliation = {k: rec.get(k) for k in
                              ("reconciled_view", "unresolved_conflicts", "weight_lean", "confidence")}
            lean = rec.get("weight_lean")
    if lean is None:
        lean = ("confirming" if len(conf_ev) > len(disc_ev)
                else "disconfirming" if len(disc_ev) > len(conf_ev) else "balanced")

    return {
        "ticker": ticker,
        "evidence": [e for e in conf_ev + disc_ev if isinstance(e, dict)],
        "reconciliation": reconciliation,
        "qual_lean": lean,
        "n_confirming": len(conf_ev),
        "n_disconfirming": len(disc_ev),
        "conflict": conflict,
    }
