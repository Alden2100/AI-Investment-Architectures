#!/usr/bin/env python3
"""Smoke test: the branded PDF theme renders a valid PDF for every system. Keyless.

    .venv/bin/python tests/pdf_test.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(REPO, "skills-library", "_shared", "branding"))

from imbrand import build_report

SAMPLES = {
    "valuation": {"system": "valuation", "ticker": "MSFT", "current_price": 379.4,
                  "dossier": {"dcf_intrinsic": 190.96, "dcf_upside": -0.497,
                              "scenarios": {"bear": 145.32, "base": 190.96, "bull": 257.31},
                              "comps_implied": 379.4},
                  "valuation": {"value_range": {"low": 145.32, "base": 190.96, "high": 257.31},
                                "recommendation": "sell", "rationale": "Price far above fair value."},
                  "model_route": "local", "summary": "MSFT looks overvalued."},
    "idea-sourcing": {"system": "idea-sourcing",
                      "shortlist": [{"rank": 1, "ticker": "MSFT", "verdict": "pursue",
                                     "dcf_upside": -0.005, "thesis": "Cheapest multiple, strong catalysts."}],
                      "model_route": "local", "summary": "MSFT top pick."},
    "portfolio-monitoring": {"system": "portfolio-monitoring", "positions": {"NVDA": "0.3"},
                             "exposure": {"gross": 0.65, "net": 0.65},
                             "correlation": {"herfindahl_index": 0.36, "avg_pairwise_correlation": 0.23},
                             "breaches": [{"type": "max_weight", "detail": "NVDA 0.30 > 0.10"}],
                             "triage": [{"ticker": "NVDA", "status": "red", "note": "Over cap."}],
                             "model_route": "local", "summary": "1 breach."},
    "filing-intelligence": {"system": "filing-intelligence", "ticker": "KO", "form": "10-K",
                            "filing": {"date": "2026-02-20"},
                            "change": {"raw_change_count": 173, "material_changes": []},
                            "brief": {"what_changed": "Workforce cut.", "why_it_matters": "Efficiency.",
                                      "what_to_watch": "Operating leverage."},
                            "model_route": "local", "summary": "KO brief."},
    "reporting": {"system": "reporting", "kind": "memo", "ticker": "MSFT",
                  "inputs_used": ["dcf", "comps"],
                  "memo_sections": {"thesis": "Strong moat.", "recommendation": "Hold."},
                  "model_route": "local", "summary": "MSFT memo."},
}


def run():
    d = tempfile.mkdtemp()
    ok = 0
    for sysname, data in SAMPLES.items():
        path = os.path.join(d, f"{sysname}.pdf")
        build_report(sysname, data, path)
        head = open(path, "rb").read(5)
        assert head == b"%PDF-", f"{sysname}: not a PDF"
        assert os.path.getsize(path) > 1500, f"{sysname}: PDF too small"
        ok += 1
    print(f"PASS pdf: {ok}/{len(SAMPLES)} systems rendered valid branded PDFs")


if __name__ == "__main__":
    run()
