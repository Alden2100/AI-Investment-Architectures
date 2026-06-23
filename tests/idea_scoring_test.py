#!/usr/bin/env python3
"""Offline tests for the idea-sourcing composite score + software SIC synonym.

    .venv/bin/python tests/idea_scoring_test.py
"""
import importlib.util
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
os.environ["TOOLBOX_CACHE_DIR"] = tempfile.mkdtemp()
os.environ["TOOLBOX_DB_PATH"] = os.path.join(os.environ["TOOLBOX_CACHE_DIR"], "s.db")
os.environ["IM_LIB_ROOT"] = os.path.join(REPO, "skills-library")
sys.path.insert(0, os.path.join(REPO, "systems", "idea-sourcing"))

import orchestrator as O   # noqa: E402


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


scr = _load("skills-library/research/universe-screener/run.py", "screener_run")

_results = []


def check(name, cond, detail=None):
    _results.append(bool(cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  -> {detail!r}"))


def _cand(t, **kw):
    base = dict(ticker=t, peg=None, ev_ebitda=None, target_upside=None, revenue_growth=None,
                earnings_growth=None, gross_margin=None, operating_margin=None, rule_of_40=None,
                net_margin=None, catalyst_signals={}, catalysts=[], insider_signal=None)
    base.update(kw)
    return base


def test_composite():
    print("\nComposite score:")
    cands = [
        _cand("CHEAP", peg=0.8, ev_ebitda=10, target_upside=0.3, revenue_growth=0.10,
              earnings_growth=0.08, gross_margin=0.6, operating_margin=0.15, rule_of_40=25,
              net_margin=0.12, catalyst_signals={"filings": 3}, catalysts=[1, 2], insider_signal="net buying"),
        _cand("GROWTH", peg=2.5, ev_ebitda=40, target_upside=0.05, revenue_growth=0.45,
              earnings_growth=0.40, gross_margin=0.78, operating_margin=0.20, rule_of_40=65,
              net_margin=0.18, catalyst_signals={"filings": 1}, catalysts=[1], insider_signal="net selling"),
        _cand("MEH", peg=1.6, ev_ebitda=25, target_upside=-0.1, revenue_growth=0.05,
              earnings_growth=0.0, gross_margin=0.4, operating_margin=0.05, rule_of_40=10,
              net_margin=0.03, catalyst_signals={}, catalysts=[], insider_signal="no open-market activity"),
    ]
    O.score_candidates(cands)
    comp = {c["ticker"]: c["composite_score"] for c in cands}
    check("all composites in 0-100", all(0 <= v <= 100 for v in comp.values()), comp)
    check("weak name (MEH) ranks last", comp["MEH"] < comp["CHEAP"] and comp["MEH"] < comp["GROWTH"], comp)
    check("each candidate has 5 sub-scores",
          all(set(c["scores"]) == {"value", "growth", "quality", "catalyst", "momentum"} for c in cands))
    check("cheap name tops the value sub-score",
          max(cands, key=lambda c: c["scores"]["value"])["ticker"] == "CHEAP")
    check("growth name tops growth + quality",
          max(cands, key=lambda c: c["scores"]["growth"])["ticker"] == "GROWTH"
          and max(cands, key=lambda c: c["scores"]["quality"])["ticker"] == "GROWTH")

    # None-robustness: a candidate with almost no data must not crash and stays mid.
    sparse = [_cand("A", revenue_growth=0.2), _cand("B")]
    O.score_candidates(sparse)
    check("sparse candidates score without crashing",
          all(isinstance(c["composite_score"], int) for c in sparse))


def test_software_synonym():
    print("\nSoftware multi-SIC synonym:")
    check("software matches 7372 (prepackaged)", scr._sic_match("software", 7372, "prepackaged software"))
    check("software matches 7370 (computer services)", scr._sic_match("software", 7370, "services-computer programming"))
    check("software matches 7389 (services nec)", scr._sic_match("software", 7389, "services-computer programming, data"))
    check("software does NOT match pharma", not scr._sic_match("software", 2834, "pharmaceutical preparations"))


if __name__ == "__main__":
    test_composite()
    test_software_synonym()
    n = sum(_results)
    print(f"\n{n}/{len(_results)} idea-scoring checks passed")
    sys.exit(0 if all(_results) else 1)
