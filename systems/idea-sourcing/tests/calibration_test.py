"""Phase 3 verification (deterministic): confidence tracks data completeness.

The old logic was inverted — a name with no data and no flags scored "high". This asserts
stage7_rank.build now gives a fully-evaluated, evidence-backed name HIGH confidence and a
no-evidence/thin name LOW, and that no row is ever "fit 0 + high confidence". No model/network.
Exit 0 == pass.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # system dir (for stages)
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))

from stages import stage7_rank  # noqa: E402

fails = []
def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        fails.append(name)


def main():
    results = {
        "GOOD": {"company": "Good Co", "overall_fit": 0.9, "flags": [],
                 "criterion_results": [{"verdict": "meets"}, {"verdict": "meets"},
                                       {"verdict": "partial"}, {"verdict": "meets"}]},
        "FLAGGED": {"company": "Flagged Co", "overall_fit": 0.7, "flags": ["mcap reconciliation"],
                    "criterion_results": [{"verdict": "meets"}, {"verdict": "partial"},
                                          {"verdict": "meets"}, {"verdict": "does_not_meet"}]},
        "THIN": {"company": "Thin Co", "overall_fit": 0.0, "flags": [],
                 "criterion_results": []},
    }
    qual_by = {
        "GOOD": {"qual_lean": "confirming", "evidence": [{"tag": "confirming", "claim": "x"},
                                                          {"tag": "disconfirming", "claim": "y"}]},
        "FLAGGED": {"qual_lean": "balanced", "evidence": [{"tag": "confirming", "claim": "z"}]},
        "THIN": {},
    }
    rows = stage7_rank.build(results, {}, {}, {}, qual_by, {})
    by = {r["ticker"]: r for r in rows}
    print({t: (round(by[t]["mandate_fit"], 2), by[t]["confidence"]) for t in by})

    check("fully-evaluated + evidence -> high", by["GOOD"]["confidence"] == "high")
    check("data-quality flag caps at medium", by["FLAGGED"]["confidence"] == "medium")
    check("no evidence / no coverage -> low", by["THIN"]["confidence"] == "low")
    check("NO row is fit=0 AND high-confidence",
          not any(r["mandate_fit"] == 0 and r["confidence"] == "high" for r in rows))

    if fails:
        print(f"\nCALIBRATION TEST: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("\nCALIBRATION TEST: ALL PASS (confidence tracks data completeness)")


if __name__ == "__main__":
    main()
