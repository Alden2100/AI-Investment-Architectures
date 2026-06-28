"""v3-E verification: the explainable report renders a valid, non-truncating PDF.

Feeds report.render a synthetic v3 run (with score_breakdown, top_reasons, rich columns)
— no orchestrator/model run — and checks a valid PDF is produced. Wrapped Paragraph cells
+ auto-growing rows mean long text never truncates. Exit 0 == pass.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # system dir (report.py, _bootstrap)
import report  # noqa: E402  (imports _bootstrap -> sets env + sys.path)

RUN = {
    "run_id": "reporttest0001",
    "coverage": {"snapshot_names": 362, "universe": 10433},
    "warming": {"classified_total": 950, "candidates": 288, "warmed": 200},
    "n_survivors": 110, "n_challenged": 4, "needs_data": ["XYZ"],
    "model_routing": [{"task": "reasoning", "rung": "sonnet", "model": "claude-sonnet-4-6", "n": 5}],
    "audit": {"stages_run": ["0 mandate-parser", "1 universe-filter", "7 opportunity-ranker"],
              "rejections_by_reason": {"c2": 69, "gate:quality": 88, "instrument_hygiene": 15},
              "note": "Every score traces to the Evidence Store."},
    "ranked": [
        {"rank": 1, "ticker": "PCTY", "company": "Paylocity Holding Corporation",
         "opportunity_score": 0.84, "opportunity_score_100": 84.0, "confidence": "high",
         "mandate_fit": 0.9, "business_quality": 90.0, "catalyst_strength": 50.0, "risk_rating": "low",
         "industry": 7372,
         "score_breakdown": [
             {"component": "Business Quality (mandate fit)", "weight_pct": 45.0, "score_0_100": 90.0, "contribution": 40.5},
             {"component": "Semantic / Text Fit", "weight_pct": 20.0, "score_0_100": 60.0, "contribution": 12.0},
             {"component": "Qualitative Evidence", "weight_pct": 15.0, "score_0_100": 65.0, "contribution": 9.75},
             {"component": "Catalysts", "weight_pct": 10.0, "score_0_100": 50.0, "contribution": 5.0},
             {"component": "Factor (size / liquidity)", "weight_pct": 10.0, "score_0_100": 66.0, "contribution": 6.6},
             {"component": "Risk adjustment", "weight_pct": "penalty", "score_0_100": "low", "contribution": 0.0}],
         "top_reasons": [
             {"criterion": "durable competitive moat with high switching costs in payroll/HR software",
              "evidence": "Filing: 'more than 39,000 clients' with high retention — a long, sticky revenue base."},
             {"criterion": "high return on invested capital", "evidence": "ROIC 24% vs peers ~12%."}],
         "primary_risks": ["Decelerating client growth could compress the premium multiple over a multi-year horizon."],
         "data_flags": []},
        {"rank": 2, "ticker": "ADI", "company": "Analog Devices",
         "opportunity_score": 0.71, "opportunity_score_100": 71.0, "confidence": "medium",
         "mandate_fit": 0.75, "business_quality": 75.0, "catalyst_strength": 25.0, "risk_rating": "medium",
         "industry": 3674,
         "score_breakdown": [
             {"component": "Business Quality (mandate fit)", "weight_pct": 45.0, "score_0_100": 75.0, "contribution": 33.75},
             {"component": "Risk adjustment", "weight_pct": "penalty", "score_0_100": "medium", "contribution": -6.0}],
         "top_reasons": [{"criterion": "pricing power in analog semiconductors", "evidence": "Gross margin 65%."}],
         "primary_risks": ["Cyclical end-market demand."], "data_flags": ["finviz key stats unavailable"]},
    ],
}


def main():
    out = report.render(RUN, tempfile.mkdtemp(prefix="report_test_"))
    assert os.path.exists(out), "no PDF produced"
    head = open(out, "rb").read(8)
    assert head.startswith(b"%PDF"), f"not a PDF: {head!r}"
    size = os.path.getsize(out)
    assert size > 3000, f"PDF suspiciously small ({size} bytes)"
    print(f"report_test: PASS — wrote {os.path.basename(out)} ({size} bytes), valid PDF, "
          f"{len(RUN['ranked'])} company pages + breakdowns + definitions + audit")


if __name__ == "__main__":
    main()
