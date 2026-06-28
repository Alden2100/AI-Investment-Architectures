"""v3-C verification (deterministic): explainable score + business-quality dominance.

  * Every row carries a score_breakdown whose contributions reproduce the score.
  * Business quality dominates and a quality gate stops catalysts from rescuing a poor
    business (P10).
No model/network. Exit 0 == pass.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))
from stages import stage7_rank  # noqa: E402

fails = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def main():
    crs = [{"criterion_id": "c1", "verdict": "meets"}, {"criterion_id": "c2", "verdict": "meets"}]
    results = {
        "GOOD": {"company": "Good Co", "overall_fit": 0.90, "flags": [], "criterion_results": crs},
        "POOR": {"company": "Poor Co", "overall_fit": 0.20, "flags": [], "criterion_results": crs},
    }
    fs_by = {"GOOD": 0.5, "POOR": 0.5}
    ts_by = {"GOOD": 0.6, "POOR": 0.6}
    events = [{"type": "earnings", "hard_event": True}, {"type": "guidance", "hard_event": True}]
    events_by = {"GOOD": events, "POOR": events}      # identical strong catalysts
    qual_by = {"GOOD": {"qual_lean": "confirming", "evidence": [{"tag": "confirming"}]},
               "POOR": {"qual_lean": "confirming", "evidence": [{"tag": "confirming"}]}}
    rows = {r["ticker"]: r for r in stage7_rank.build(results, fs_by, ts_by, events_by, qual_by, {})}

    g = rows["GOOD"]
    # weights sum to 100 across the 5 positive components
    wsum = sum(b["weight_pct"] for b in g["score_breakdown"] if isinstance(b["weight_pct"], (int, float)))
    check("component weights sum to 100%", abs(wsum - 100.0) < 0.5, str(wsum))
    # contributions reproduce the score (no risk, gate=1 for GOOD)
    contrib = sum(b["contribution"] for b in g["score_breakdown"]
                  if isinstance(b.get("contribution"), (int, float)))
    check("contributions reproduce opportunity_score_100",
          abs(contrib - g["opportunity_score_100"]) < 0.2, f"{contrib} vs {g['opportunity_score_100']}")
    check("business_quality surfaced (90)", g["business_quality"] == 90.0)

    # business quality dominates: identical catalysts, but POOR is gated down
    check("good business ranks well above poor one with same catalysts",
          g["opportunity_score"] > rows["POOR"]["opportunity_score"] + 0.2,
          f"good={g['opportunity_score']} poor={rows['POOR']['opportunity_score']}")
    poor_gate = [b for b in rows["POOR"]["score_breakdown"] if b["component"].startswith("Quality-gate")]
    check("quality gate applied to the poor business (catalysts can't rescue)", bool(poor_gate))

    if fails:
        print(f"\nSCORE BREAKDOWN: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("\nSCORE BREAKDOWN: ALL PASS (reproducible breakdown; business quality dominates)")


if __name__ == "__main__":
    main()
