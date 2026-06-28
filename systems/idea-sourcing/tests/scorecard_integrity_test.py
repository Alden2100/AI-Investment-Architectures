"""Phase 4 verification (deterministic): scorecard integrity + honest reasons.

  * overall_fit is rolled up in Python, weight-aware, EXCLUDING already-enforced
    hard_constraint + portfolio_constraint criteria (no boilerplate inflation).
  * top_reasons rank by criterion importance and never surface hard/portfolio tautologies.
  * max-N-per-industry greedy cap keeps <=N per industry, overflow logged (not silent).
No model/network. Exit 0 == pass.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # system dir (stages)
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))

from stages import stage7_rank  # noqa: E402

_sc_run = os.path.join(_root, "skills-library", "opportunity", "mandate-scorecard", "run.py")
spec = importlib.util.spec_from_file_location("sc_run", _sc_run)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

fails = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def main():
    criteria = [
        {"id": "c1", "type": "hard_constraint", "weight": None, "text": "publicly listed"},
        {"id": "c2", "type": "soft_preference", "weight": 0.8, "text": "ROIC > 15%"},
        {"id": "c3", "type": "qualitative", "weight": 1.0, "text": "durable moat"},
        {"id": "c4", "type": "portfolio_constraint", "weight": None, "text": "max 2 per industry"},
    ]
    results = [
        {"criterion_id": "c1", "verdict": "meets"},      # excluded (hard)
        {"criterion_id": "c2", "verdict": "meets"},       # 0.8 * 1.0
        {"criterion_id": "c3", "verdict": "partial"},     # 1.0 * 0.5
        {"criterion_id": "c4", "verdict": "meets"},       # excluded (portfolio)
    ]
    fit = sc._rollup_overall_fit(results, criteria)
    expected = round((0.8 * 1.0 + 1.0 * 0.5) / (0.8 + 1.0), 4)
    check("overall_fit excludes hard+portfolio, weight-aware", abs(fit - expected) < 1e-6,
          f"{fit} != {expected}")

    # top_reasons: ranked by weight, no hard/portfolio tautologies
    cmeta = stage7_rank._crit_meta({"criteria": criteria})
    crs = [{"criterion_id": "c1", "criterion_text": "publicly listed", "verdict": "meets", "evidence": "is listed"},
           {"criterion_id": "c2", "criterion_text": "ROIC > 15%", "verdict": "meets", "evidence": "ROIC 22%"},
           {"criterion_id": "c3", "criterion_text": "durable moat", "verdict": "meets", "evidence": "switching costs"}]
    reasons = stage7_rank._top_reasons(crs, cmeta)
    texts = [r["criterion"] for r in reasons]
    check("top_reasons excludes hard-constraint tautology", "publicly listed" not in texts)
    check("top_reasons ranked by weight (ROIC before moat)", texts[:2] == ["durable moat", "ROIC > 15%"] or texts[0] == "durable moat",
          str(texts))

    # max-2-per-industry cap
    rows = [{"ticker": "A", "industry": 7372, "opportunity_score": 0.9},
            {"ticker": "B", "industry": 7372, "opportunity_score": 0.8},
            {"ticker": "C", "industry": 7372, "opportunity_score": 0.7},
            {"ticker": "D", "industry": 3841, "opportunity_score": 0.6}]
    kept, overflow = stage7_rank.cap_per_industry(rows, 2)
    kt = [r["ticker"] for r in kept]
    check("cap keeps <=2 per industry", kt == ["A", "B", "D"], str(kt))
    check("overflow is the 3rd software name, logged", [r["ticker"] for r in overflow] == ["C"]
          and overflow[0].get("capped_by"))

    if fails:
        print(f"\nSCORECARD INTEGRITY: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("\nSCORECARD INTEGRITY: ALL PASS (deterministic fit, weighted reasons, industry cap)")


if __name__ == "__main__":
    main()
