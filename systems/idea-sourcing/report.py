"""Explainable PDF report for an idea-sourcing run (institutional-research style).

Renders a run's JSON output (plus per-company evidence read back from the Evidence Store)
into a PDF: a rich ranking table, a standardized page per company (score breakdown,
top reasons, structured catalysts, risks, supporting evidence), score DEFINITIONS, and an
audit/provenance section. Every text cell is a wrapped Paragraph and every table row grows
to fit its content, so nothing is ever truncated (P7).

Usage:
    python report.py --json data/output/run.json          # render a saved run
    python report.py --run-id <run_id>                    # pull the run row from the store
Output: data/output/idea-sourcing-report-<run_id>.pdf
"""
import _bootstrap  # noqa: F401  (env + sys.path before imdata)

import argparse
import json
import os
import time

from imdata import store
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, HRFlowable)

NAVY = colors.HexColor("#1a3c5e")
_ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_ss["Title"], fontSize=18, spaceAfter=4)
H2 = ParagraphStyle("H2", parent=_ss["Heading2"], fontSize=12.5, textColor=NAVY, spaceBefore=12, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=_ss["Heading3"], fontSize=11, textColor=colors.HexColor("#223"), spaceBefore=8, spaceAfter=2)
BODY = ParagraphStyle("BODY", parent=_ss["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("SMALL", parent=_ss["BodyText"], fontSize=8, leading=10.5, textColor=colors.HexColor("#444"))
CELL = ParagraphStyle("CELL", parent=_ss["BodyText"], fontSize=8, leading=10)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
CELLW = ParagraphStyle("CELLW", parent=CELL, textColor=colors.white, fontName="Helvetica-Bold")
FRAME_W = letter[0] - 1.2 * inch  # usable width inside 0.6" margins

DEFINITIONS = [
    ("Opportunity Score", "Overall mandate-weighted attractiveness for diligence triage (0-100). A "
     "reproducible weighted blend of the components below, minus a risk adjustment, scaled by a "
     "business-quality gate. NOT a buy/sell call."),
    ("Mandate Fit / Business Quality", "How well the company matches the mandate's CORE principles "
     "and preferences (deterministic weight-aware roll-up of per-criterion verdicts; core principles "
     "carry the most weight). Passing a hard constraint earns nothing; violating a negative "
     "constraint penalizes."),
    ("Confidence", "Quality of the ANALYSIS, not attractiveness of the investment: data completeness "
     "(criteria evaluated / total), evidence present, and data-quality flags. No evidence => low; "
     "flags cap it at medium."),
    ("Semantic / Text Fit", "Alignment of the company's business description to the mandate language "
     "(TF-IDF over 10-K business text vs the mandate's semantic query + seed companies)."),
    ("Catalyst Strength", "Recent hard, dated events (8-K filings, guidance, insider buying) — opinion "
     "/ chatter is excluded."),
    ("Risk Rating", "Penalty from data-quality flags and a disconfirming evidence lean."),
]


def _P(t, s=BODY):
    return Paragraph("" if t is None else str(t), s)


def _load_run(args):
    if args.json:
        return json.load(open(args.json))
    if args.run_id:
        row = store.get_run(args.run_id)
        if not row:
            raise SystemExit(f"run {args.run_id} not found")
        # The full envelope isn't stored; rebuild a minimal view from the store.
        raise SystemExit("--run-id rebuild not supported; pass --json of the run output")
    raise SystemExit("provide --json <run output> (or --run-id)")


def _evidence(run_id, company, stage):
    for e in store.evidence_for_run(run_id, company):
        if e["stage"] == stage:
            try:
                return json.loads(e["json"])
            except (ValueError, TypeError):
                return None
    return None


def _table(data, widths, header=True, font=8):
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    sty = [("FONTSIZE", (0, 0), (-1, -1), font), ("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ccc")),
           ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f3f6fa")]),
           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        sty += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(sty))
    return t


def render(run: dict, out_dir: str) -> str:
    run_id = run.get("run_id", "run")
    rows = run.get("ranked", [])
    E = []
    E.append(_P("Idea-Sourcing — Investment Research Report", H1))
    E.append(_P("Mandate-matched shortlist · evidence-backed · reproducible scoring · not investment advice", SMALL))

    w = run.get("warming") or {}
    cov = run.get("coverage") or {}
    meta = [
        [_P("Run ID", CELLB), _P(run_id, CELL)],
        [_P("Generated", CELLB), _P(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), CELL)],
        [_P("Universe", CELLB), _P(f"{w.get('classified_total','?')} classified → {w.get('candidates','?')} "
                                   f"candidates → {w.get('warmed','?')} warmed; snapshot {cov.get('snapshot_names','?')}/"
                                   f"{cov.get('universe','?')}", CELL)],
        [_P("Funnel", CELLB), _P(f"{run.get('n_survivors','?')} survivors → {len(rows)} ranked; "
                                 f"{len(run.get('needs_data') or [])} quarantined (needs data); "
                                 f"{run.get('n_challenged','?')} challenged", CELL)],
    ]
    E.append(_table(meta, [1.4 * inch, FRAME_W - 1.4 * inch], header=False))

    # ---- Ranking table (rich columns, all wrapped) ----
    E.append(_P("Ranked shortlist", H2))
    hdr = [_P(h, CELLW) for h in ("#", "Company", "Opp", "Quality", "Conf", "Catalyst", "Risk", "Primary characteristics")]
    tdata = [hdr]
    for r in rows:
        chars = "; ".join(x.get("criterion", "") for x in (r.get("top_reasons") or [])[:3]) or "—"
        tdata.append([
            _P(r.get("rank"), CELL), _P(f"<b>{r.get('ticker')}</b><br/>{(r.get('company') or '')[:28]}", CELL),
            _P(round(r.get("opportunity_score_100", (r.get("opportunity_score") or 0) * 100), 1), CELL),
            _P(r.get("business_quality", round((r.get('mandate_fit') or 0) * 100, 1)), CELL),
            _P(r.get("confidence", ""), CELL), _P(r.get("catalyst_strength", ""), CELL),
            _P(r.get("risk_rating", ""), CELL), _P(chars, CELL)])
    E.append(_table(tdata, [0.3 * inch, 1.45 * inch, 0.5 * inch, 0.6 * inch, 0.55 * inch, 0.65 * inch,
                            0.5 * inch, FRAME_W - 5.05 * inch]))
    E.append(_P("Opportunity Score = weighted blend (see Methodology); business quality dominates and a "
                "quality gate prevents catalysts from rescuing a weak business.", SMALL))

    # ---- Per-company pages ----
    for r in rows:
        E.append(PageBreak())
        E.append(_P(f"#{r.get('rank')} &nbsp; {r.get('ticker')} — {r.get('company','')}", H2))
        E.append(_P(f"Opportunity {round(r.get('opportunity_score_100', 0),1)}/100 · Business quality "
                    f"{r.get('business_quality','?')} · Confidence {r.get('confidence','')} · "
                    f"Risk {r.get('risk_rating','')} · Industry SIC {r.get('industry','')}", SMALL))

        E.append(_P("Score breakdown (reproducible)", H3))
        bd = [[_P(h, CELLW) for h in ("Component", "Weight", "Score /100", "Contribution")]]
        for b in (r.get("score_breakdown") or []):
            bd.append([_P(b.get("component"), CELL), _P(b.get("weight_pct"), CELL),
                       _P(b.get("score_0_100"), CELL), _P(b.get("contribution"), CELL)])
        bd.append([_P("<b>Final Opportunity Score</b>", CELL), _P(""), _P(""),
                   _P(f"<b>{round(r.get('opportunity_score_100',0),1)}</b>", CELL)])
        E.append(_table(bd, [FRAME_W - 3.1 * inch, 0.9 * inch, 1.1 * inch, 1.1 * inch]))

        if r.get("top_reasons"):
            E.append(_P("Why it fits the mandate", H3))
            for x in r["top_reasons"]:
                E.append(_P(f"• <b>{x.get('criterion','')}</b> — {x.get('evidence','')}", SMALL))

        catev = (_evidence(run_id, r["ticker"], 5) or {}).get("events") or []
        if catev:
            E.append(_P("Recent catalysts", H3))
            ch = [[_P(h, CELLW) for h in ("Date", "Type", "Importance", "Source", "Conf")]]
            for e in catev[:8]:
                imp = "high" if e.get("hard_event") else "low"
                ch.append([_P(e.get("date") or "—", CELL), _P(e.get("type"), CELL), _P(imp, CELL),
                           _P(e.get("source") or "", CELL), _P(e.get("confidence"), CELL)])
            E.append(_table(ch, [0.9 * inch, FRAME_W - 3.4 * inch, 0.7 * inch, 1.3 * inch, 0.5 * inch]))

        if r.get("primary_risks"):
            E.append(_P("Primary risks", H3))
            for x in r["primary_risks"][:4]:
                E.append(_P(f"• {x}", SMALL))

        s6 = _evidence(run_id, r["ticker"], 6) or {}
        conf_ev = [e.get("claim") for e in (s6.get("evidence") or []) if e.get("tag") == "confirming"][:4]
        if conf_ev:
            E.append(_P("Supporting evidence", H3))
            for x in conf_ev:
                E.append(_P(f"• {x}", SMALL))
        rec = s6.get("reconciliation") or {}
        if rec.get("reconciled_view"):
            E.append(_P(f"<b>Reconciled view ({rec.get('weight_lean','')}):</b> {rec.get('reconciled_view')}", SMALL))
        if r.get("data_flags"):
            E.append(_P("Data-quality flags: " + ", ".join(str(f) for f in r["data_flags"]), SMALL))

    # ---- Definitions ----
    E.append(PageBreak())
    E.append(_P("Score definitions", H2))
    for term, defn in DEFINITIONS:
        E.append(_P(f"<b>{term}.</b> {defn}", SMALL))

    # ---- Audit & provenance ----
    aud = run.get("audit") or {}
    E.append(_P("Audit &amp; provenance", H2))
    E.append(_P("Stages run: " + ", ".join(aud.get("stages_run", [])), SMALL))
    if aud.get("rejections_by_reason"):
        E.append(_P("Rejections by reason (every removed name is queryable in reject_log): "
                    + ", ".join(f"{k}={v}" for k, v in aud["rejections_by_reason"].items()), SMALL))
    mr = run.get("model_routing", [])
    if mr:
        E.append(_P("Models: " + ", ".join(sorted({x.get('model', '') for x in mr})) + ".", SMALL))
    E.append(_P(aud.get("note", ""), SMALL))
    E.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#bbb"), spaceBefore=6, spaceAfter=4))
    E.append(_P("Evidence + ranking explanation only — contains no buy/sell recommendation. Prototype "
                "screen for diligence triage; validate every figure against primary sources before acting.", SMALL))

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"idea-sourcing-report-{run_id[:12]}.pdf")
    SimpleDocTemplate(out, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                      title="Idea-Sourcing Investment Research Report").build(E)
    return out


def main():
    p = argparse.ArgumentParser(description="Render an idea-sourcing run as an explainable PDF.")
    p.add_argument("--json", help="path to a saved run-output JSON")
    p.add_argument("--run-id", help="run id (requires the run JSON for the full envelope)")
    args = p.parse_args()
    run = _load_run(args)
    out = render(run, os.path.join(_bootstrap.DATA_DIR, "output"))
    print("WROTE", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
