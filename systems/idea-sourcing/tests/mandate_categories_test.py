"""v3-A verification (deterministic): mandate categories drive scoring correctly.

  * negative_constraint: a VIOLATION (does_not_meet) penalizes; staying CLEAN (meets) earns
    nothing — passing a disqualifier never becomes positive evidence.
  * core_principle outweighs positive_preference (business quality dominates).
  * top_reasons surface only positive categories — never 'avoid X' or hard tautologies.
No model/network. Exit 0 == pass.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))
from stages import stage7_rank  # noqa: E402

_sc = os.path.join(_root, "skills-library", "opportunity", "mandate-scorecard", "run.py")
spec = importlib.util.spec_from_file_location("sc_run", _sc)
sc = importlib.util.module_from_spec(spec); spec.loader.exec_module(sc)

fails = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def main():
    crit = [
        {"id": "c1", "type": "core_principle", "weight": 1.0, "text": "durable moat / high ROIC"},
        {"id": "c2", "type": "positive_preference", "weight": 0.4, "text": "founder-led"},
        {"id": "c3", "type": "negative_constraint", "weight": 1.0, "text": "avoid aggressive accounting"},
        {"id": "c4", "type": "hard_constraint", "weight": None, "text": "publicly listed"},
    ]
    base_results = [{"criterion_id": "c1", "verdict": "meets"},
                    {"criterion_id": "c2", "verdict": "meets"},
                    {"criterion_id": "c4", "verdict": "meets"}]

    # clean on the negative constraint -> no penalty, no bonus
    clean = sc._rollup_overall_fit(base_results + [{"criterion_id": "c3", "verdict": "meets"}], crit)
    # violates the negative constraint -> penalty
    dirty = sc._rollup_overall_fit(base_results + [{"criterion_id": "c3", "verdict": "does_not_meet"}], crit)
    print(f"clean fit={clean}  dirty(violation) fit={dirty}")
    check("clean negative-constraint earns no bonus (base 1.0)", abs(clean - 1.0) < 1e-6, str(clean))
    check("violating a negative-constraint penalizes (0.5 off)", abs(dirty - 0.5) < 1e-6, str(dirty))

    # core_principle dominates positive_preference
    core_only = sc._rollup_overall_fit(
        [{"criterion_id": "c1", "verdict": "meets"}, {"criterion_id": "c2", "verdict": "does_not_meet"}], crit)
    pref_only = sc._rollup_overall_fit(
        [{"criterion_id": "c1", "verdict": "does_not_meet"}, {"criterion_id": "c2", "verdict": "meets"}], crit)
    check("core_principle outweighs positive_preference", core_only > pref_only,
          f"core_only={core_only} pref_only={pref_only}")

    # top_reasons: positives only, core first, no 'avoid' / hard tautology
    cmeta = stage7_rank._crit_meta({"criteria": crit})
    crs = [{"criterion_id": "c1", "criterion_text": "durable moat / high ROIC", "verdict": "meets", "evidence": "ROIC 26%"},
           {"criterion_id": "c2", "criterion_text": "founder-led", "verdict": "meets", "evidence": "founder is CEO"},
           {"criterion_id": "c3", "criterion_text": "avoid aggressive accounting", "verdict": "meets", "evidence": "clean"},
           {"criterion_id": "c4", "criterion_text": "publicly listed", "verdict": "meets", "evidence": "NYSE"}]
    reasons = [r["criterion"] for r in stage7_rank._top_reasons(crs, cmeta)]
    print("top_reasons:", reasons)
    check("negative-constraint 'avoid ...' not a reason", "avoid aggressive accounting" not in reasons)
    check("hard-constraint tautology not a reason", "publicly listed" not in reasons)
    check("core_principle leads the reasons", reasons and reasons[0] == "durable moat / high ROIC")

    if fails:
        print(f"\nMANDATE CATEGORIES: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("\nMANDATE CATEGORIES: ALL PASS")


if __name__ == "__main__":
    main()
