"""Branded PDF report builder (Avenoth Advisory theme).

Turns a system's structured result into a clean, concise, slide-deck-ready PDF:
a navy header band with the wordmark, a serif title, organized sections and
branded tables, muted semantic colors for financial data, and a slate footer.

Used only when the user explicitly asks for a PDF (the front door decides). One
entry point: ``build_report(system, data, out_path, subject=None)``.
"""
from __future__ import annotations

import time

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, KeepTogether,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import colors as C

# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
TITLE = ParagraphStyle("title", fontName=C.FONT_SERIF_BOLD, fontSize=22, leading=26,
                       textColor=C.NAVY, spaceAfter=2)
SUBTITLE = ParagraphStyle("subtitle", fontName=C.FONT_SANS, fontSize=10.5, leading=14,
                          textColor=C.STEEL, spaceAfter=10)
H2 = ParagraphStyle("h2", fontName=C.FONT_SANS_BOLD, fontSize=11, leading=14,
                    textColor=C.STEEL, spaceBefore=12, spaceAfter=5,
                    letterSpacing=0.6)
BODY = ParagraphStyle("body", fontName=C.FONT_SANS, fontSize=9.7, leading=14,
                      textColor=C.INK, spaceAfter=6)
SMALL = ParagraphStyle("small", fontName=C.FONT_SANS, fontSize=8.6, leading=11.5,
                       textColor=C.INK)
CAPTION = ParagraphStyle("caption", fontName=C.FONT_SANS, fontSize=8, leading=10,
                         textColor=C.SLATE)
LEAD = ParagraphStyle("lead", fontName=C.FONT_SERIF, fontSize=11.5, leading=16,
                      textColor=C.NAVY, spaceAfter=8)


def _hex(c):
    return "#%02X%02X%02X" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def cell(text, *, color=C.INK, bold=False, size=8.8, align=TA_LEFT):
    st = ParagraphStyle("c", fontName=C.FONT_SANS_BOLD if bold else C.FONT_SANS,
                        fontSize=size, leading=size + 3, textColor=color, alignment=align)
    return Paragraph("" if text is None else str(text), st)


# --------------------------------------------------------------------------- #
# Header band + footer (drawn on every page)
# --------------------------------------------------------------------------- #
def _decorate(canvas, doc):
    w, h = LETTER
    canvas.saveState()
    # top navy band
    band_h = 0.62 * inch
    canvas.setFillColor(C.NAVY)
    canvas.rect(0, h - band_h, w, band_h, fill=1, stroke=0)
    # thin azure accent rule under the band (~10% accent, never a background)
    canvas.setFillColor(C.AZURE)
    canvas.rect(0, h - band_h - 2.2, w, 2.2, fill=1, stroke=0)
    # wordmark
    canvas.setFillColor(C.WHITE)
    canvas.setFont(C.FONT_SERIF_BOLD, 14)
    canvas.drawString(0.8 * inch, h - 0.4 * inch, "AVENOTH ADVISORY")
    canvas.setFillColor(C.SKY)
    canvas.setFont(C.FONT_SANS, 8)
    canvas.drawRightString(w - 0.8 * inch, h - 0.39 * inch,
                           doc._brand_tag.upper())
    # footer
    canvas.setStrokeColor(C.MIST)
    canvas.setLineWidth(0.6)
    canvas.line(0.8 * inch, 0.62 * inch, w - 0.8 * inch, 0.62 * inch)
    canvas.setFillColor(C.SLATE)
    canvas.setFont(C.FONT_SANS, 7.5)
    canvas.drawString(0.8 * inch, 0.45 * inch,
                      f"{C.BRAND_NAME}  ·  Confidential  ·  Generated {doc._gen_date}")
    canvas.drawRightString(w - 0.8 * inch, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------- #
# Reusable flowables
# --------------------------------------------------------------------------- #
def hr():
    return HRFlowable(width="100%", thickness=0.6, color=C.MIST,
                      spaceBefore=4, spaceAfter=8)


def badge(label, color):
    """A filled status pill (one-cell table)."""
    t = Table([[cell(label.upper(), color=C.WHITE, bold=True, size=8.5, align=TA_LEFT)]],
              colWidths=[1.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def kv(rows, label_w=1.7, val_w=4.8):
    """Two-column label/value block."""
    data = [[cell(k, color=C.SLATE, bold=True), v if hasattr(v, "wrap")
             else cell(v, color=C.INK)] for k, v in rows]
    t = Table(data, colWidths=[label_w * inch, val_w * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def data_table(header, rows, col_widths, aligns=None):
    """Branded table: navy header row, alternating cloud/white, mist rules.
    `rows` cells may be Paragraphs (use cell()) or plain strings."""
    aligns = aligns or [TA_LEFT] * len(header)
    head = [cell(h, color=C.WHITE, bold=True, size=8.6, align=aligns[i])
            for i, h in enumerate(header)]
    body = []
    for r in rows:
        body.append([c if hasattr(c, "wrap") else cell(c, align=aligns[i])
                     for i, c in enumerate(r)])
    t = Table([head] + body, colWidths=[c * inch for c in col_widths], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C.NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, C.MIST),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C.WHITE, C.CLOUD]),
    ]
    t.setStyle(TableStyle(style))
    return t


# --------------------------------------------------------------------------- #
# Numeric helpers
# --------------------------------------------------------------------------- #
def _money(v):
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _pct(v):
    try:
        return f"{float(v) * 100:+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _pct_color(v):
    try:
        return C.POSITIVE if float(v) >= 0 else C.NEGATIVE
    except (TypeError, ValueError):
        return C.INK


def _flat(v):
    """Readable string from a scalar / list / dict model field."""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        for k in ("description", "detail", "text", "note", "thesis", "change"):
            if isinstance(v.get(k), str) and v[k].strip():
                q = [str(v[x]) for x in ("status", "type", "section") if v.get(x)]
                return (" ".join(q) + " — " if q else "") + v[k].strip()
        return ", ".join(f"{k}: {x}" for k, x in v.items() if isinstance(x, (str, int, float)))
    if isinstance(v, list):
        return " ".join(_flat(x) for x in v)
    return str(v)


# --------------------------------------------------------------------------- #
# Per-system content
# --------------------------------------------------------------------------- #
def _valuation(d):
    f, dz = [], d.get("dossier", {})
    sc = dz.get("scenarios", {})
    v = d.get("valuation") or {}
    vr = (v.get("value_range") or {})
    f.append(Paragraph("Valuation Snapshot", H2))
    f.append(kv([
        ("Current price", cell(_money(d.get("current_price")), color=C.NAVY, bold=True)),
        ("DCF intrinsic", cell(f"{_money(dz.get('dcf_intrinsic'))}   ({_pct(dz.get('dcf_upside'))})",
                               color=_pct_color(dz.get("dcf_upside")))),
        ("Scenario range", cell(f"bear {_money(sc.get('bear'))}   ·   base {_money(sc.get('base'))}"
                                f"   ·   bull {_money(sc.get('bull'))}")),
        ("Value range", cell(f"{_money(vr.get('low'))} – {_money(vr.get('high'))}  "
                             f"(base {_money(vr.get('base'))})", color=C.NAVY, bold=True)),
    ]))
    if v.get("recommendation"):
        f.append(Spacer(1, 6))
        f.append(badge(str(v["recommendation"]), C.status_color(v["recommendation"])))
    if v.get("rationale"):
        f.append(Paragraph("Rationale", H2))
        f.append(Paragraph(_flat(v["rationale"]), BODY))
    return f


def _idea(d):
    f = [Paragraph("Ranked Shortlist", H2)]
    rows = d.get("shortlist") or d.get("candidates") or []
    table_rows = []
    for r in rows:
        verdict = (r.get("verdict") or "").upper()
        table_rows.append([
            cell(r.get("rank", "•"), bold=True),
            cell(r.get("ticker", "?"), color=C.NAVY, bold=True),
            cell(verdict or "—", color=C.status_color(r.get("verdict", "")), bold=True),
            cell(_pct(r.get("dcf_upside")), color=_pct_color(r.get("dcf_upside")), align=TA_RIGHT),
            cell(_flat(r.get("thesis", "")), size=8.4),
        ])
    f.append(data_table(["#", "Ticker", "Verdict", "DCF", "Thesis"], table_rows,
                        [0.4, 0.8, 0.95, 0.8, 3.95],
                        aligns=[TA_LEFT, TA_LEFT, TA_LEFT, TA_RIGHT, TA_LEFT]))
    return f


def _portfolio(d):
    f = [Paragraph("Exposure", H2)]
    ex, co = d.get("exposure", {}), d.get("correlation", {})
    f.append(kv([
        ("Gross / Net", cell(f"{ex.get('gross')}  /  {ex.get('net')}")),
        ("Concentration", cell(f"HHI {co.get('herfindahl_index')}   ·   "
                               f"avg corr {co.get('avg_pairwise_correlation')}")),
    ]))
    breaches = d.get("breaches", [])
    f.append(Paragraph(f"Breaches ({len(breaches)})", H2))
    if breaches:
        f.append(data_table(["Type", "Detail"],
                            [[cell(b.get("type", ""), color=C.NEGATIVE, bold=True),
                              cell(b.get("detail", ""))] for b in breaches],
                            [1.5, 5.0]))
    else:
        f.append(Paragraph("None — within all limits.", BODY))
    triage = d.get("triage") or []
    if triage:
        f.append(Paragraph("Triage", H2))
        f.append(data_table(["Status", "Ticker", "Note"],
                            [[cell((t.get("status") or "").upper(),
                                   color=C.status_color(t.get("status", "")), bold=True),
                              cell(t.get("ticker", ""), color=C.NAVY, bold=True),
                              cell(_flat(t.get("note", "")))] for t in triage],
                            [0.9, 0.9, 4.7]))
    return f


def _filing(d):
    f, ch = [], d.get("change", {})
    f.append(kv([
        ("Filing", cell(f"{d.get('ticker')} {d.get('form')}  ·  {d.get('filing', {}).get('date', '')}",
                        color=C.NAVY, bold=True)),
        ("Changes", cell(f"{ch.get('raw_change_count', 0)} raw diffs  ·  "
                         f"{len(ch.get('material_changes') or [])} high/medium-significance")),
    ]))
    b = d.get("brief") or {}
    for key, label in (("what_changed", "What changed"), ("why_it_matters", "Why it matters"),
                       ("what_to_watch", "What to watch")):
        if b.get(key):
            f.append(Paragraph(label, H2))
            f.append(Paragraph(_flat(b[key]), BODY))
    mats = ch.get("material_changes") or []
    if not any(b.values()) and mats:
        f.append(Paragraph("Material changes", H2))
        f.append(data_table(["Section", "Change"],
                            [[cell(m.get("section", ""), color=C.STEEL, bold=True),
                              cell(_flat(m.get("new") or m.get("old") or ""), size=8.4)]
                             for m in mats[:10]], [1.3, 5.2]))
    return f


def _reporting(d):
    f = []
    if d.get("kind") == "letter":
        f.append(Paragraph(_flat(d.get("letter_draft") or "(no draft)"), LEAD))
        return f
    sec = d.get("memo_sections")
    if isinstance(sec, dict) and sec:
        for k, v in sec.items():
            f.append(Paragraph(k.replace("_", " ").title(), H2))
            f.append(Paragraph(_flat(v), BODY))
    elif d.get("draft_text"):
        f.append(Paragraph(_flat(d["draft_text"]), BODY))
    else:
        f.append(Paragraph("Inputs gathered; memo draft unavailable.", BODY))
    return f


def _generic(d):
    f = []
    for k, v in d.items():
        if k in ("system", "summary", "output_path", "stub", "next_step", "model_route"):
            continue
        if isinstance(v, (str, int, float)):
            f.append(kv([(k.replace("_", " ").title(), cell(v))]))
        elif isinstance(v, dict) and v:
            f.append(Paragraph(k.replace("_", " ").title(), H2))
            f.append(Paragraph(_flat(v), BODY))
        elif isinstance(v, list) and v:
            f.append(Paragraph(k.replace("_", " ").title(), H2))
            for item in v[:8]:
                f.append(Paragraph("• " + _flat(item), SMALL))
    return f


_BUILDERS = {
    "valuation": _valuation, "idea-sourcing": _idea, "portfolio-monitoring": _portfolio,
    "filing-intelligence": _filing, "reporting": _reporting,
}
_TITLES = {
    "valuation": lambda d: f"Valuation — {d.get('ticker', '')}",
    "idea-sourcing": lambda d: "Idea Sourcing — Ranked Shortlist",
    "portfolio-monitoring": lambda d: "Portfolio Status Report",
    "filing-intelligence": lambda d: f"Filing Intelligence Brief — {d.get('ticker', '')} {d.get('form', '')}",
    "reporting": lambda d: (f"Investor Letter — {d.get('period', '')}" if d.get("kind") == "letter"
                            else f"Investment Committee Memo — {d.get('ticker', '')}"),
    "due-diligence": lambda d: f"Due Diligence — {d.get('ticker', '')}",
    "governance-audit": lambda d: "Governance & Audit",
}
_TAGS = {
    "valuation": "Valuation", "idea-sourcing": "Idea Sourcing",
    "portfolio-monitoring": "Portfolio Monitoring", "filing-intelligence": "Filing Intelligence",
    "reporting": "Reporting", "due-diligence": "Due Diligence",
    "governance-audit": "Governance",
}


def build_report(system: str, data: dict, out_path: str, subject: str = None) -> str:
    """Render a system's result to a branded PDF. Returns out_path."""
    gen_date = time.strftime("%d %b %Y", time.localtime())
    doc = BaseDocTemplate(out_path, pagesize=LETTER,
                          topMargin=0.95 * inch, bottomMargin=0.85 * inch,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          title=f"{C.BRAND_NAME} — {_TAGS.get(system, system)}",
                          author=C.BRAND_NAME)
    doc._brand_tag = _TAGS.get(system, system)
    doc._gen_date = gen_date
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_decorate)])

    story = [Spacer(1, 0.12 * inch)]
    title = _TITLES.get(system, lambda d: system.replace("-", " ").title())(data)
    story.append(Paragraph(title, TITLE))
    sub = subject or data.get("summary") or ""
    if isinstance(sub, str) and sub and not sub.lstrip().startswith(("{", "[")):
        story.append(Paragraph(sub[:240], SUBTITLE))
    else:
        story.append(Spacer(1, 6))
    story.append(hr())
    story += _BUILDERS.get(system, _generic)(data)
    # source / method footnote
    route = data.get("model_route") or "n/a"
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Numbers computed deterministically from SEC EDGAR &amp; market data; narrative "
        f"via model route “{route}”. For internal investment use.", CAPTION))
    doc.build(story)
    return out_path
