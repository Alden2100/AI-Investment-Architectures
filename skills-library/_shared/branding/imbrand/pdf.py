"""Branded PDF report builder (Tensh Consulting Group theme).

Turns a system's structured result into a clean, full-page, slide-deck-ready PDF:
a navy header band with the wordmark, a serif title, a hero callout, organized
sections and branded tables with muted semantic colors, and a navy footer band —
framing the page top and bottom so it reads as a full portrait page.

Used only when the user explicitly asks for a PDF (the front door decides). One
entry point: ``build_report(system, data, out_path, subject=None)``.
"""
from __future__ import annotations

import time

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, HRFlowable,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import colors as C

# --------------------------------------------------------------------------- #
# Styles — presentation scale (sized so a typical report fills a portrait page)
# --------------------------------------------------------------------------- #
TITLE = ParagraphStyle("title", fontName=C.FONT_SERIF_BOLD, fontSize=27, leading=31,
                       textColor=C.NAVY, spaceAfter=3)
SUBTITLE = ParagraphStyle("subtitle", fontName=C.FONT_SANS, fontSize=12.5, leading=17,
                          textColor=C.STEEL, spaceAfter=12)
H2 = ParagraphStyle("h2", fontName=C.FONT_SANS_BOLD, fontSize=13, leading=16,
                    textColor=C.STEEL, spaceBefore=18, spaceAfter=7)
BODY = ParagraphStyle("body", fontName=C.FONT_SANS, fontSize=11, leading=16.5,
                      textColor=C.INK, spaceAfter=9)
SMALL = ParagraphStyle("small", fontName=C.FONT_SANS, fontSize=9.8, leading=14,
                       textColor=C.INK, spaceAfter=4)
CAPTION = ParagraphStyle("caption", fontName=C.FONT_SANS, fontSize=8.6, leading=11,
                         textColor=C.SLATE, alignment=TA_CENTER)
LEAD = ParagraphStyle("lead", fontName=C.FONT_SERIF, fontSize=13, leading=19,
                      textColor=C.NAVY, spaceAfter=10)


def cell(text, *, color=C.INK, bold=False, size=10, align=TA_LEFT):
    st = ParagraphStyle("c", fontName=C.FONT_SANS_BOLD if bold else C.FONT_SANS,
                        fontSize=size, leading=size + 3.5, textColor=color, alignment=align)
    return Paragraph("" if text is None else str(text), st)


# --------------------------------------------------------------------------- #
# Page furniture: navy band top + bottom (frames the page), azure accent rules
# --------------------------------------------------------------------------- #
def _decorate(canvas, doc):
    w, h = LETTER
    canvas.saveState()
    # ---- top band ----
    top_h = 0.72 * inch
    canvas.setFillColor(C.NAVY)
    canvas.rect(0, h - top_h, w, top_h, fill=1, stroke=0)
    canvas.setFillColor(C.AZURE)                       # azure accent rule (~10%)
    canvas.rect(0, h - top_h - 2.4, w, 2.4, fill=1, stroke=0)
    canvas.setFillColor(C.WHITE)
    canvas.setFont(C.FONT_SERIF_BOLD, 15)
    canvas.drawString(0.8 * inch, h - 0.46 * inch, C.BRAND_NAME.upper())
    canvas.setFillColor(C.SKY)
    canvas.setFont(C.FONT_SANS, 8.5)
    canvas.drawRightString(w - 0.8 * inch, h - 0.45 * inch, doc._brand_tag.upper())
    # ---- bottom band ----
    bot_h = 0.55 * inch
    canvas.setFillColor(C.NAVY)
    canvas.rect(0, 0, w, bot_h, fill=1, stroke=0)
    canvas.setFillColor(C.AZURE)
    canvas.rect(0, bot_h, w, 2.0, fill=1, stroke=0)
    canvas.setFillColor(C.WHITE)
    canvas.setFont(C.FONT_SANS_BOLD, 8)
    canvas.drawString(0.8 * inch, bot_h / 2 - 3, C.BRAND_NAME)
    canvas.setFillColor(C.SKY)
    canvas.setFont(C.FONT_SANS, 7.5)
    canvas.drawCentredString(w / 2, bot_h / 2 - 3, "CONFIDENTIAL — FOR INTERNAL INVESTMENT USE")
    canvas.drawRightString(w - 0.8 * inch, bot_h / 2 - 3,
                           f"{doc._gen_date}  ·  Page {doc.page}")
    canvas.restoreState()


class Filler(Flowable):
    """Expands to consume the remaining frame height, anchoring what follows to the
    bottom — so short reports still fill the page top-to-bottom."""
    def wrap(self, aw, ah):
        self.width, self.height = aw, max(0, ah - 0.02)
        return self.width, self.height

    def draw(self):
        pass


# --------------------------------------------------------------------------- #
# Reusable flowables
# --------------------------------------------------------------------------- #
def hr():
    return HRFlowable(width="100%", thickness=0.7, color=C.MIST, spaceBefore=4, spaceAfter=10)


def hero(label, value, value_color=C.NAVY, note=None):
    """A full-width callout card: steel label + large value (the page's anchor)."""
    inner = [[cell(label.upper(), color=C.STEEL, bold=True, size=9.5)],
             [Paragraph(str(value), ParagraphStyle(
                 "hv", fontName=C.FONT_SERIF_BOLD, fontSize=21, leading=25, textColor=value_color))]]
    if note:
        inner.append([cell(note, color=C.SLATE, size=9.5)])
    t = Table(inner, colWidths=[6.9 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C.CLOUD),
        ("LINEBEFORE", (0, 0), (0, -1), 3, C.AZURE),   # azure spine on the left
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 11), ("BOTTOMPADDING", (0, -1), (-1, -1), 11),
        ("TOPPADDING", (0, 1), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
    ]))
    return t


def badge(label, color):
    t = Table([[cell(label.upper(), color=C.WHITE, bold=True, size=10.5)]],
              colWidths=[1.15 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def kv(rows, label_w=1.9, val_w=5.0):
    data = [[cell(k, color=C.SLATE, bold=True), v if hasattr(v, "wrap") else cell(v)]
            for k, v in rows]
    t = Table(data, colWidths=[label_w * inch, val_w * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, C.MIST),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def data_table(header, rows, col_widths, aligns=None):
    aligns = aligns or [TA_LEFT] * len(header)
    head = [cell(h, color=C.WHITE, bold=True, size=10, align=aligns[i])
            for i, h in enumerate(header)]
    body = [[c if hasattr(c, "wrap") else cell(c, align=aligns[i]) for i, c in enumerate(r)]
            for r in rows]
    t = Table([head] + body, colWidths=[c * inch for c in col_widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C.NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, C.MIST),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C.WHITE, C.CLOUD]),
    ]))
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
# Per-system content  ->  (hero_flowable_or_None, [body flowables])
# --------------------------------------------------------------------------- #
def _valuation(d):
    dz, sc = d.get("dossier", {}), d.get("dossier", {}).get("scenarios", {})
    v = d.get("valuation") or {}
    vr = v.get("value_range") or {}
    rec = str(v.get("recommendation", "n/a")).upper()
    h = hero("Recommendation",
             f"{rec} · {d.get('ticker', '')}",
             C.status_color(v.get("recommendation", "")),
             note=f"Value range {_money(vr.get('low'))} – {_money(vr.get('high'))}  "
                  f"vs price {_money(d.get('current_price'))}")
    f = [Paragraph("Valuation Snapshot", H2), kv([
        ("Current price", cell(_money(d.get("current_price")), color=C.NAVY, bold=True)),
        ("DCF intrinsic", cell(f"{_money(dz.get('dcf_intrinsic'))}   ({_pct(dz.get('dcf_upside'))})",
                               color=_pct_color(dz.get("dcf_upside")))),
        ("Scenario range", cell(f"bear {_money(sc.get('bear'))}   ·   base {_money(sc.get('base'))}"
                                f"   ·   bull {_money(sc.get('bull'))}")),
        ("Comps-implied", cell(_money(dz.get("comps_implied")))),
        ("Value range", cell(f"{_money(vr.get('low'))} – {_money(vr.get('high'))}  "
                             f"(base {_money(vr.get('base'))})", color=C.NAVY, bold=True)),
    ])]
    if v.get("rationale"):
        f += [Paragraph("Rationale", H2), Paragraph(_flat(v["rationale"]), BODY)]
    return h, f


def _idea(d):
    rows = d.get("shortlist") or d.get("candidates") or []
    top = rows[0] if rows else {}
    h = hero("Top Idea", f"{top.get('ticker', '—')} · {(top.get('verdict') or '').upper()}",
             C.status_color(top.get("verdict", "")),
             note=_flat(top.get("thesis", "")) if top.get("thesis") else None)
    tr = []
    for r in rows:
        tr.append([
            cell(r.get("rank", "•"), bold=True),
            cell(r.get("ticker", "?"), color=C.NAVY, bold=True),
            cell((r.get("verdict") or "—").upper(), color=C.status_color(r.get("verdict", "")), bold=True),
            cell(_pct(r.get("dcf_upside")), color=_pct_color(r.get("dcf_upside")), align=TA_RIGHT),
            cell(_flat(r.get("thesis", "")), size=9.5),
        ])
    f = [Paragraph("Ranked Shortlist", H2),
         data_table(["#", "Ticker", "Verdict", "DCF", "Thesis"], tr,
                    [0.4, 0.85, 1.05, 0.85, 3.75],
                    [TA_LEFT, TA_LEFT, TA_LEFT, TA_RIGHT, TA_LEFT])]
    return h, f


def _portfolio(d):
    ex, co = d.get("exposure", {}), d.get("correlation", {})
    breaches = d.get("breaches", [])
    h = hero("Breaches", f"{len(breaches)} flagged",
             C.NEGATIVE if breaches else C.POSITIVE,
             note=f"Gross {ex.get('gross')} · Net {ex.get('net')} · "
                  f"HHI {co.get('herfindahl_index')} · avg corr {co.get('avg_pairwise_correlation')}")
    f = [Paragraph(f"Breaches ({len(breaches)})", H2)]
    if breaches:
        f.append(data_table(["Type", "Detail"],
                            [[cell(b.get("type", ""), color=C.NEGATIVE, bold=True),
                              cell(b.get("detail", ""))] for b in breaches], [1.7, 5.2]))
    else:
        f.append(Paragraph("None — within all limits.", BODY))
    triage = d.get("triage") or []
    if triage:
        f.append(Paragraph("Position Triage", H2))
        f.append(data_table(["Status", "Ticker", "Note"],
                            [[cell((t.get("status") or "").upper(),
                                   color=C.status_color(t.get("status", "")), bold=True),
                              cell(t.get("ticker", ""), color=C.NAVY, bold=True),
                              cell(_flat(t.get("note", "")))] for t in triage],
                            [1.0, 1.0, 4.9]))
    return h, f


def _filing(d):
    ch = d.get("change", {})
    h = hero(f"{d.get('ticker', '')} {d.get('form', '')}",
             f"{ch.get('raw_change_count', 0)} changes",
             C.NAVY,
             note=f"Filed {d.get('filing', {}).get('date', '')} · "
                  f"{len(ch.get('material_changes') or [])} high/medium-significance")
    f, b = [], d.get("brief") or {}
    for key, label in (("what_changed", "What Changed"), ("why_it_matters", "Why It Matters"),
                       ("what_to_watch", "What to Watch")):
        if b.get(key):
            f += [Paragraph(label, H2), Paragraph(_flat(b[key]), BODY)]
    mats = ch.get("material_changes") or []
    if not any(b.values()) and mats:
        f += [Paragraph("Material Changes", H2),
              data_table(["Section", "Change"],
                         [[cell(m.get("section", ""), color=C.STEEL, bold=True),
                           cell(_flat(m.get("new") or m.get("old") or ""), size=9.5)]
                          for m in mats[:10]], [1.5, 5.4])]
    return h, f


def _reporting(d):
    if d.get("kind") == "letter":
        h = hero("Investor Letter", d.get("period", ""), C.NAVY)
        return h, [Paragraph(_flat(d.get("letter_draft") or "(no draft)"), LEAD)]
    sec = d.get("memo_sections")
    rec = ""
    if isinstance(sec, dict):
        rec = _flat(sec.get("recommendation", ""))
    h = hero(f"IC Memo · {d.get('ticker', '')}", rec or "Investment Committee Memo",
             C.NAVY, note="Inputs: " + ", ".join(d.get("inputs_used", [])))
    f = []
    if isinstance(sec, dict) and sec:
        for k, v in sec.items():
            f += [Paragraph(k.replace("_", " ").title(), H2), Paragraph(_flat(v), BODY)]
    elif d.get("draft_text"):
        f.append(Paragraph(_flat(d["draft_text"]), BODY))
    else:
        f.append(Paragraph("Inputs gathered; memo draft unavailable.", BODY))
    return h, f


def _generic(d):
    f = []
    for k, v in d.items():
        if k in ("system", "summary", "output_path", "stub", "next_step", "model_route"):
            continue
        if isinstance(v, (str, int, float)):
            f.append(kv([(k.replace("_", " ").title(), cell(v))]))
        elif isinstance(v, dict) and v:
            f += [Paragraph(k.replace("_", " ").title(), H2), Paragraph(_flat(v), BODY)]
        elif isinstance(v, list) and v:
            f.append(Paragraph(k.replace("_", " ").title(), H2))
            for item in v[:8]:
                f.append(Paragraph("• " + _flat(item), SMALL))
    return None, f


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
    "reporting": "Reporting", "due-diligence": "Due Diligence", "governance-audit": "Governance",
}


def build_report(system: str, data: dict, out_path: str, subject: str = None) -> str:
    """Render a system's result to a branded, full-page PDF. Returns out_path."""
    doc = BaseDocTemplate(out_path, pagesize=LETTER,
                          topMargin=1.05 * inch, bottomMargin=0.95 * inch,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          title=f"{C.BRAND_NAME} — {_TAGS.get(system, system)}",
                          author=C.BRAND_NAME)
    doc._brand_tag = _TAGS.get(system, system)
    doc._gen_date = time.strftime("%d %b %Y", time.localtime())
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_decorate)])

    story = [Spacer(1, 0.1 * inch)]
    story.append(Paragraph(_TITLES.get(system, lambda d: system.replace("-", " ").title())(data), TITLE))
    sub = subject or data.get("summary") or ""
    if isinstance(sub, str) and sub and not sub.lstrip().startswith(("{", "[")):
        story.append(Paragraph(sub[:260], SUBTITLE))
    else:
        story.append(Spacer(1, 8))
    story.append(hr())

    hero_flow, body = _BUILDERS.get(system, _generic)(data)
    if hero_flow is not None:
        story += [hero_flow, Spacer(1, 6)]
    story += body

    # push the method footnote to the bottom so the page reads full top-to-bottom
    route = data.get("model_route") or "n/a"
    story += [Filler(), Spacer(1, 6),
              Paragraph(f"Numbers computed deterministically from SEC EDGAR &amp; market "
                        f"data; narrative via model route “{route}”.", CAPTION)]
    doc.build(story)
    return out_path
