#!/usr/bin/env python3
"""ask.py — a natural-language front door to the systems.

Prompt it like you'd prompt an LLM:

    python ask.py "what's Microsoft worth versus Apple and Google?"
    python ask.py "any catalysts in large-cap software?"
    python ask.py "is my book ok - NVDA 30%, MSFT 20%, AAPL 15%, cap 10%?"
    python ask.py "write an IC memo for Nvidia"
    python ask.py "what changed in Coca-Cola's latest 10-K?"

It interprets intent (which system + arguments) — the *judged* part — then dispatches
to the right orchestrator with exact CLI args — the *exact* part. Intent is resolved
with keyword heuristics + the shared router (local qwen by default; Claude if keyed),
and concrete entities (tickers, weights, form, sizes) are extracted deterministically
and validated against the company universe. It always prints the plan before running.

Also accepts the short form, passed straight through:
    python ask.py valuation --ticker MSFT --peers AAPL GOOGL
"""
import argparse
import os
import re
import subprocess
import sys

# ---- locate the shared library (set env BEFORE importing it) ----------------
HERE = os.path.dirname(os.path.realpath(__file__))
LIB = os.path.join(HERE, "skills-library")
CACHE = os.path.join(HERE, ".cache"); os.makedirs(CACHE, exist_ok=True)
_envf = os.path.join(HERE, ".env")
if os.path.exists(_envf):
    for _ln in open(_envf):
        _ln = _ln.strip()
        if _ln and not _ln.startswith("#") and "=" in _ln:
            _k, _v = _ln.split("=", 1); os.environ.setdefault(_k.strip(), _v.strip().strip('"'))
# ask.py's own universe lookups use a private cache DB; do NOT leak these into the
# child orchestrator (it must pick its own system DB) — see _child_env().
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(CACHE, "ask.db"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", CACHE)
for _p in ("data-fetch", "router", "web-search", "branding"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))

# A PDF is produced ONLY when the user explicitly asks for one in the prompt
# (or passes --pdf). Default output stays plain text in the terminal.
_PDF_RE = re.compile(r"\b(pdf|\.pdf|as a pdf|export (?:it |this )?(?:as |to )?pdf|"
                     r"pdf (?:report|version|format|export)|make (?:it |a )?pdf)\b", re.I)


def wants_pdf(text: str) -> bool:
    return bool(_PDF_RE.search(text or ""))


def strip_pdf_phrase(text: str) -> str:
    """Remove the PDF ask so it doesn't skew system/entity detection."""
    t = re.sub(r"\b(and )?(also )?(please )?(export|save|give me|make|render|output|"
               r"produce|create|generate)?\s*(it|this|that)?\s*(as|to|in|into)?\s*a?\s*"
               r"\.?pdf( report| version| format| file| export)?\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", t).strip(" .,-")
from imdata import universe, store          # noqa: E402
from imrouter import route                   # noqa: E402

SYSTEMS = ["idea-sourcing", "filing-intelligence", "portfolio-monitoring",
           "valuation", "reporting", "due-diligence", "governance-audit"]

# --- common company-name -> ticker aliases (extend freely) ------------------
ALIASES = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "nvidia": "NVDA", "amazon": "AMZN", "meta": "META", "facebook": "META",
    "tesla": "TSLA", "netflix": "NFLX", "coca-cola": "KO", "coke": "KO",
    "intel": "INTC", "amd": "AMD", "broadcom": "AVGO", "oracle": "ORCL",
    "salesforce": "CRM", "adobe": "ADBE", "disney": "DIS", "boeing": "BA",
    "walmart": "WMT", "exxon": "XOM", "pepsi": "PEP", "pepsico": "PEP",
}
# sector keyword -> SIC *description* substring (the screener matches on the SIC
# description text, e.g. "Services-Prepackaged Software", not the numeric code).
SECTORS = {
    "software": "software", "semiconductor": "semiconductor",
    "semiconductors": "semiconductor", "chip": "semiconductor", "chips": "semiconductor",
    "bank": "bank", "banks": "bank", "pharma": "pharmaceutical",
    "pharmaceutical": "pharmaceutical", "biotech": "biological", "retail": "retail",
    "oil": "petroleum", "energy": "petroleum", "auto": "motor vehicle",
    "automotive": "motor vehicle", "aerospace": "aircraft", "airline": "air transportation",
    "insurance": "insurance", "media": "television", "telecom": "telephone",
}
_STOP = {"A", "I", "THE", "IS", "IT", "MY", "ME", "AN", "OK", "OR", "TO", "VS",
         "AND", "FOR", "ANY", "ARE", "DCF", "IC", "LP", "WHAT", "HOW", "DO",
         "GIVE", "FIND", "WRITE", "WORTH", "BOOK", "CAP", "FY", "Q"}


def _load_universe():
    try:
        if store.companies_count() == 0:
            universe.refresh_universe()
    except Exception:
        pass


def valid_ticker(tok: str) -> bool:
    try:
        return store.company_by_ticker(tok) is not None
    except Exception:
        return False


def extract_tickers(text: str) -> list:
    """Validated tickers in TEXT order: known company names + explicit symbols.

    Ordering matters — the first ticker is treated as the subject (e.g. the company
    to value), the rest as peers — so we sort every hit by where it appears.
    """
    hits = []  # (position, ticker)
    low = text.lower()
    for name, tk in ALIASES.items():
        m = re.search(rf"\b{re.escape(name)}\b", low)
        if m:
            hits.append((m.start(), tk))
    for m in re.finditer(r"\b[A-Z]{1,5}\b", text):
        tok = m.group(0)
        if tok not in _STOP and valid_ticker(tok):
            hits.append((m.start(), tok))
    found, seen = [], set()
    for _pos, tk in sorted(hits, key=lambda h: h[0]):
        if tk not in seen:
            found.append(tk); seen.add(tk)
    return found


def extract_positions(text: str) -> list:
    """TICKER=weight pairs from forms like 'NVDA 30%', 'MSFT=0.20', 'AAPL: 15%'."""
    out = []
    for sym, num, pct in re.findall(r"\b([A-Za-z]{1,5})\b\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(%)?", text):
        sym = sym.upper()
        if sym in _STOP or not valid_ticker(sym):
            continue
        v = float(num)
        if pct or v > 1:        # 30% or 30 -> 0.30
            v = v / 100.0
        out.append(f"{sym}={v:g}")
    return out


def extract_mcap(text: str):
    low = text.lower()
    if "large-cap" in low or "large cap" in low or "megacap" in low or "mega-cap" in low:
        return "1e10", None
    if "mid-cap" in low or "mid cap" in low:
        return "2e9", "2e10"
    if "small-cap" in low or "small cap" in low:
        return None, "2e9"
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*(t|tn|trillion|b|bn|billion|m|mm|million)\b", low)
    if m:
        mult = {"t": 1e12, "tn": 1e12, "trillion": 1e12, "b": 1e9, "bn": 1e9,
                "billion": 1e9, "m": 1e6, "mm": 1e6, "million": 1e6}[m.group(2)]
        return f"{float(m.group(1)) * mult:.0f}", None
    return None, None


def heuristic_system(text: str):
    """Strong keyword signal -> (system, score). score 0 means 'no opinion'."""
    t = text.lower()
    score = {s: 0 for s in SYSTEMS}
    def add(s, n): score[s] += n
    if re.search(r"\b(memo|write-up|writeup|ic memo|pitch)\b", t): add("reporting", 3)
    if re.search(r"\b(letter|investor letter|lp letter|shareholder)\b", t): add("reporting", 3)
    if re.search(r"\b(worth|fair value|valuation|valu\w+|intrinsic|price target|undervalued|overvalued|cheap|expensive|upside|downside)\b", t): add("valuation", 3)
    if re.search(r"\b(10-?k|10-?q|8-?k|filing|annual report|quarterly report)\b", t): add("filing-intelligence", 3)
    if re.search(r"\b(catalyst|catalysts|screen|ideas|shortlist|names|sourcing|watchlist)\b", t): add("idea-sourcing", 3)
    if re.search(r"\b(portfolio|book|positions?|limits?|drift|rebalance|exposure|concentration|risk limit)\b", t): add("portfolio-monitoring", 3)
    if re.search(r"\bdue diligence|deep dive|full work-?up\b", t): add("due-diligence", 2)
    if re.search(r"\baudit|governance|compliance|paper trail\b", t): add("governance-audit", 2)
    if "%" in t and re.search(r"\b[A-Za-z]{1,5}\b\s*\d+\s*%", text): add("portfolio-monitoring", 2)
    best = max(score, key=score.get)
    return (best, score[best]) if score[best] > 0 else (None, 0)


_SYS_SCHEMA = {"type": "object", "properties": {
    "system": {"type": "string", "enum": SYSTEMS}}, "required": ["system"]}


def classify(text: str) -> tuple:
    sysname, score = heuristic_system(text)
    if score >= 3:
        return sysname, "keyword"
    # vague prompt -> ask the model (local qwen by default)
    res = route(f"Pick the single best system for this request: {text!r}",
                task="classification",
                system="You route investment requests. Choose exactly one system id.",
                schema=_SYS_SCHEMA, max_tokens=200)
    pick = res.get("system")
    if pick in SYSTEMS:
        return pick, ("model:" + res.get("_route", "?"))
    return sysname or "idea-sourcing", "fallback"


def build_argv(system: str, text: str) -> tuple:
    """Return (argv_list, missing_msg_or_None) for the chosen system."""
    tickers = extract_tickers(text)
    if system == "valuation":
        if not tickers:
            return None, "Which company? e.g. \"what's MSFT worth vs AAPL\""
        argv = ["--ticker", tickers[0]]
        if len(tickers) > 1:
            argv += ["--peers", *tickers[1:]]
        return argv, None
    if system == "filing-intelligence":
        if not tickers:
            return None, "Which company's filing? e.g. \"what changed in KO's 10-K\""
        form = "10-Q" if re.search(r"10-?q", text, re.I) else (
            "8-K" if re.search(r"8-?k", text, re.I) else "10-K")
        return ["--ticker", tickers[0], "--form", form], None
    if system == "portfolio-monitoring":
        positions = extract_positions(text)
        if not positions:
            return None, ("List positions with weights, e.g. "
                          "\"NVDA 30%, MSFT 20%, cap 10%\"")
        argv = ["--positions", *positions]
        m = re.search(r"cap\s*(\d+(?:\.\d+)?)\s*%", text, re.I) or \
            re.search(r"max[-\s]?weight\s*(\d+(?:\.\d+)?)\s*%?", text, re.I)
        if m:
            w = float(m.group(1)); argv += ["--max-weight", f"{w/100 if w > 1 else w:g}"]
        return argv, None
    if system == "reporting":
        if re.search(r"\bletter\b", text, re.I):
            per = re.search(r"\bQ[1-4]\s*\d{4}\b", text, re.I)
            return ["--letter", per.group(0) if per else "this quarter"], None
        if not tickers:
            return None, "Which company for the memo? e.g. \"IC memo for NVDA\""
        return ["--memo", tickers[0]], None
    if system == "due-diligence":
        if not tickers:
            return None, "Which company to dig into?"
        return ["--ticker", tickers[0]], None
    if system == "governance-audit":
        return ["--limit", "20"], None
    if system == "idea-sourcing":
        argv = []
        if tickers:
            argv += ["--ticker-in", *tickers]
        for kw, sic in SECTORS.items():
            if re.search(rf"\b{kw}\b", text, re.I):
                argv += ["--sic-contains", sic]; break
        lo, hi = extract_mcap(text)
        if lo: argv += ["--min-mcap", lo]
        if hi: argv += ["--max-mcap", hi]
        if not argv:
            return None, ("Give a mandate: a sector (\"software\"), size "
                          "(\"large-cap\"), or some tickers.")
        return argv, None
    return None, f"don't know how to build args for {system}"


def _child_env() -> dict:
    """Env for the orchestrator subprocess: strip ask.py's own sandbox keys so the
    orchestrator's os.environ.setdefault picks its OWN system DB / skills / policy."""
    env = dict(os.environ)
    for k in ("TOOLBOX_DB_PATH", "TOOLBOX_CACHE_DIR", "IM_SKILLS_DIR",
              "IM_ROUTER_LOG", "IM_ROUTER_POLICY", "IM_LIB_ROOT"):
        env.pop(k, None)
    return env


# --------------------------------------------------------------------------- #
# Human-readable rendering. The orchestrators emit machine JSON (dossier + model
# fields); we format a clean report from the RELIABLE structured fields rather than
# trusting the model's free-text `summary`, which a 9B model sometimes returns as a
# nested blob. Works the same with or without an API key.
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


def _line(v) -> str:
    """One readable line from a scalar / dict (pick its most descriptive fields)."""
    if isinstance(v, (str, int, float)):
        return str(v).strip()
    if isinstance(v, dict):
        for key in ("description", "detail", "text", "note", "thesis", "change", "reason"):
            if isinstance(v.get(key), str) and v[key].strip():
                quals = [str(v[k]) for k in ("status", "type", "ticker", "section", "metric")
                         if isinstance(v.get(k), (str, int, float)) and str(v[k]).strip()]
                return (" ".join(quals) + " — " if quals else "") + v[key].strip()
        return ", ".join(f"{k}: {x}" for k, x in v.items()
                         if isinstance(x, (str, int, float)) and str(x).strip())
    return str(v)


def _bullets(v, limit=12) -> list:
    """Readable bullet lines from a model field that may be str / list / dict."""
    if v is None:
        return []
    if isinstance(v, str):
        return ["  " + v.strip()] if v.strip() else []
    if isinstance(v, dict):
        return ["  • " + _line(v)] if _line(v) else []
    if isinstance(v, list):
        out = []
        for item in v[:limit]:
            s = _line(item)
            if s:
                out.append("  • " + s)
        if len(v) > limit:
            out.append(f"  … (+{len(v) - limit} more)")
        return out
    return ["  " + str(v)]


def _diff_lines(blocks, limit=6) -> list:
    """Readable lines from filing diff blocks, skipping XBRL/boilerplate noise."""
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        typ = b.get("type", "changed")
        old = re.sub(r"\s+", " ", (b.get("old") or "")).strip()
        new = re.sub(r"\s+", " ", (b.get("new") or b.get("text") or "")).strip()
        text = new or old
        low = text.lower()
        if not text or len(text) < 30:
            continue
        if "fasb.org" in low or "us-gaap" in low or "xbrl" in low or "http://" in low:
            continue
        if typ == "changed" and old and new:
            out.append(f"  • changed: …{old[:95]}…  →  …{new[:95]}…")
        else:
            out.append(f"  • {typ}: {text[:170]}")
        if len(out) >= limit:
            break
    return out


def _clean_summary(d) -> str:
    s = d.get("summary")
    if isinstance(s, str) and s.strip() and not s.lstrip().startswith(("{", "[")):
        return s.strip()
    return ""


def render(system: str, d: dict) -> str:
    L = []
    def add(s=""):
        L.append(s)

    if system == "valuation":
        dz = d.get("dossier", {})
        sc = dz.get("scenarios", {})
        add(f"VALUATION — {d.get('ticker')}   (price {_money(d.get('current_price'))})")
        add(f"  DCF intrinsic : {_money(dz.get('dcf_intrinsic'))}   (upside {_pct(dz.get('dcf_upside'))})")
        add(f"  Scenarios     : bear {_money(sc.get('bear'))} | base {_money(sc.get('base'))} | bull {_money(sc.get('bull'))}")
        if dz.get("comps_implied"):
            add(f"  Comps-implied : {_money(dz.get('comps_implied'))}")
        if dz.get("comps_median"):
            m = dz["comps_median"]
            add(f"  Comps median  : EV/EBITDA {m.get('ev_ebitda')}x · P/E {m.get('pe')}x · P/S {m.get('ps')}x")
        a = dz.get("dcf_assumptions") or {}
        if a:
            add(f"  DCF assumes   : {_pct(a.get('growth'))} growth · {_pct(a.get('discount_rate'))} WACC · "
                f"{_pct(a.get('terminal_growth'))} terminal")
        mg = dz.get("margins") or {}
        if mg:
            add(f"  Margins       : gross {_pct(mg.get('gross'))} · op {_pct(mg.get('operating'))} · net {_pct(mg.get('net'))}")
        v = d.get("valuation") or {}
        if v:
            vr = v.get("value_range", {}) or {}
            add(f"  Value range   : {_money(vr.get('low'))} – {_money(vr.get('high'))}  (base {_money(vr.get('base'))})")
            add(f"  Call          : {str(v.get('recommendation', 'n/a')).upper()}")
            if v.get("rationale"):
                add(f"  Rationale     : {_line(v['rationale'])}")

    elif system == "idea-sourcing":
        rows = d.get("shortlist") or d.get("candidates") or []
        add(f"IDEA SOURCING — {len(rows)} name(s)")
        for r in rows:
            tk = r.get("ticker", "?")
            verdict = (r.get("verdict") or "").upper()
            prefix = f"{r['rank']}." if r.get("rank") else "•"
            head = f"  {prefix} {tk}" + (f"  [{verdict}]" if verdict else "")
            if r.get("dcf_upside") is not None:
                head += f"  DCF {_pct(r.get('dcf_upside'))}"
            add(head)
            if r.get("thesis"):
                add(f"      {_line(r['thesis'])}")

    elif system == "portfolio-monitoring":
        breaches = d.get("breaches", [])
        add(f"PORTFOLIO MONITORING — {len(d.get('positions', {}))} positions, "
            f"{len(breaches)} breach(es)")
        ex = d.get("exposure", {})
        co = d.get("correlation", {})
        add(f"  Exposure  : gross {ex.get('gross')}  net {ex.get('net')}  "
            f"HHI {co.get('herfindahl_index')}  avg-corr {co.get('avg_pairwise_correlation')}")
        hold = d.get("holdings") or []
        if hold:
            add("  Holdings  :")
            add(f"    {'TICKER':7} {'WGT':>6} {'LAST':>9} {'1Y':>8} {'VOL':>6} {'MAXDD':>7}  STATUS")
            for p in hold:
                w = _pct(p.get('weight')); ret = _pct(p.get('return_1y'))
                vol = _pct(p.get('volatility')) if p.get('volatility') else 'n/a'
                dd = _pct(p.get('max_drawdown')) if p.get('max_drawdown') else 'n/a'
                add(f"    {p.get('ticker',''):7} {w:>6} {_money(p.get('last')):>9} {ret:>8} "
                    f"{vol:>6} {dd:>7}  {(p.get('status') or '').upper()}")
        if breaches:
            add("  Breaches  :")
            L.extend("  " + b for b in _bullets(breaches))
        triage = d.get("triage") or []
        if triage:
            add("  Triage    :")
            for t in triage:
                add(f"    [{str(t.get('status', '?')).upper():6}] {t.get('ticker', '?')} — {_line(t.get('note', ''))}")

    elif system == "filing-intelligence":
        f = d.get("filing", {})
        ch = d.get("change", {})
        material = ch.get("material_changes") or []
        add(f"FILING INTELLIGENCE — {d.get('ticker')} {d.get('form')}  ({f.get('date', 'n/a')})")
        add(f"  {ch.get('raw_change_count', 0)} raw diffs · {len(material)} high/medium-significance change(s)")
        dg = d.get("digest") or {}
        if dg.get("business"):
            add("\n  Business:"); add("  " + _line(dg["business"]))
        if dg.get("drivers"):
            add("\n  Growth drivers:"); L.extend("  • " + _line(x) for x in dg["drivers"][:6])
        if dg.get("risks"):
            add("\n  Key risks:"); L.extend("  • " + _line(x) for x in dg["risks"][:6])
        if dg.get("guidance"):
            add("\n  Guidance:"); add("  " + _line(dg["guidance"]))
        comp = d.get("competitive") or {}
        mar = comp.get("margins") or {}
        if mar or comp.get("quality"):
            add("\n  Competitive position:")
            if mar:
                add(f"    Quant — margins: gross {_pct(mar.get('gross'))} · op {_pct(mar.get('operating'))} · net {_pct(mar.get('net'))}")
            if comp.get("quality"):
                add(f"    Qual  — {comp['quality']}")
            if comp.get("moat_type"):
                add(f"    Moat  — {_line(comp.get('moat_type'))}" +
                    (f" ({_line(comp.get('moat_durability'))})" if comp.get("moat_durability") else ""))
        if material:
            add("\n  Material changes:")
            for m in material[:10]:
                sec = m.get("section", "?")
                sig = str(m.get("significance", "")).strip()
                txt = (m.get("new") or m.get("old") or "").strip()
                txt = re.sub(r"\s+", " ", txt)[:160]
                add(f"  • [{sec}] {txt}" + (f"  ({sig})" if sig and sig.lower() != "unrated" else ""))
        b = d.get("brief")
        # defend against older outputs where the model nested the brief in `summary`
        if (not b or not any((b or {}).values())) and isinstance(d.get("summary"), str) \
                and d["summary"].lstrip().startswith("{"):
            try:
                import json as _j
                b = _j.loads(d["summary"])
            except ValueError:
                pass
        if b and any(b.values()):
            for key, label in (("what_changed", "What changed"),
                               ("why_it_matters", "Why it matters"),
                               ("what_to_watch", "What to watch")):
                if b.get(key):
                    add(f"\n  {label}:")
                    L.extend("  " + x for x in _bullets(b[key]))
        elif not material:
            # no model Brief and no classified changes; show cleaned raw diffs
            diffs = _diff_lines(ch.get("diff_blocks", []))
            if diffs:
                add("\n  Notable changes (substantive prose diffs):")
                L.extend(diffs)
            else:
                add("  (no readable prose changes surfaced; see full result)")

    elif system == "reporting":
        if d.get("kind") == "letter":
            add(f"INVESTOR LETTER — {d.get('period')}")
            add("")
            add(d.get("letter_draft") or "(no draft — set a model route)")
        else:
            add(f"IC MEMO — {d.get('ticker')}   (inputs: {', '.join(d.get('inputs_used', []))})")
            sec = d.get("memo_sections")
            if isinstance(sec, dict) and sec:
                for k, v in sec.items():
                    add(f"\n  {k.replace('_', ' ').title()}")
                    add(f"    {_line(v)}")
            elif d.get("draft_text"):
                add(""); add(d["draft_text"])
            else:
                add("  (model route unavailable — inputs gathered; see full result)")

    elif system == "due-diligence":
        dz = d.get("dossier", {})
        add(f"DUE DILIGENCE — {d.get('ticker')}   (scaffold)")
        add(f"  DCF upside : {_pct(dz.get('dcf_upside'))}")
        if dz.get("moat"):
            add(f"  Margins    : {_line(dz.get('moat'))}")
        news = dz.get("news") or []
        if news:
            add("  Recent news:")
            for h in news[:5]:
                add(f"  • {h}")

    elif system == "governance-audit":
        entries = d.get("recent_audit") or []
        if isinstance(entries, dict):  # tolerate {entries:[...]} or similar
            entries = next((v for v in entries.values() if isinstance(v, list)), [])
        add(f"GOVERNANCE AUDIT — {len(entries)} recent entr(ies)   (scaffold)")
        for e in (entries if isinstance(entries, list) else [])[:12]:
            if isinstance(e, dict):
                add(f"  • {e.get('ts', '')}  {e.get('actor', '')} · {e.get('action', '')}"
                    f" · {e.get('target', '')} — {_line(e.get('detail', ''))}")
            else:
                add(f"  • {_line(e)}")

    else:  # generic fallback
        add(f"{system.upper()}")
        for k, v in d.items():
            if k in ("system", "summary", "output_path", "stub", "next_step"):
                continue
            if isinstance(v, (str, int, float)):
                add(f"  {k}: {v}")
            elif isinstance(v, (list, dict)) and v:
                add(f"  {k}:")
                L.extend("  " + x for x in _bullets(v, limit=8))

    if d.get("coherence_warning"):
        add("")
        add("⚠ " + str(d["coherence_warning"]))

    cs = _clean_summary(d)
    if cs:
        add("")
        add("➤ " + cs)

    # Name the model that wrote the narrative, so a qwen run is never mistaken for
    # Claude. Loudly flag a needs-model (no narrative) or degraded (qwen stand-in) run.
    route = d.get("model_route")
    if d.get("degraded"):
        add("")
        add(f"⚠ DEGRADED — narrative written by the local fallback ({d.get('model_id') or 'qwen'}), "
            "NOT Claude. Quality is capped. Run `claude login` (Max plan) for analyst-grade output.")
    elif route == "none" or d.get("needs_model"):
        add("")
        add("⚠ No model narrative — the Claude session is unavailable, so only the "
            "deterministic numbers above were produced. Run `claude login` (Max plan), "
            "or set IM_ALLOW_DEGRADED=1 to allow the local qwen stand-in.")
    elif route and route != "n/a":
        add("")
        add(f"· narrative model: {route}" + (f" ({d.get('model_id')})" if d.get("model_id") else ""))
    return "\n".join(L)


def _make_pdf(system: str, d: dict) -> str:
    from imbrand import build_report  # lazy: only imports reportlab when a PDF is asked
    out_dir = os.path.join(HERE, "systems", system, "data", "output")
    os.makedirs(out_dir, exist_ok=True)
    # overwrite one stable PDF per system (copy it out when you want to keep a version)
    return build_report(system, d, os.path.join(out_dir, f"{system}.pdf"))


def run_system(system: str, argv: list, show_json: bool, want_pdf: bool = False) -> int:
    import json
    orch = os.path.join(HERE, "systems", system, "orchestrator.py")
    # make sure symlinks exist
    subprocess.run([sys.executable, os.path.join(HERE, "link.py"), system],
                   capture_output=True, text=True, env=_child_env())
    proc = subprocess.run([sys.executable, orch, *argv], text=True,
                          stdout=subprocess.PIPE, env=_child_env())  # stderr -> terminal (progress)
    if proc.returncode != 0:
        print(f"\n(system exited {proc.returncode})", file=sys.stderr)
        return proc.returncode
    try:
        d = json.loads(proc.stdout)
    except ValueError:
        print(proc.stdout.strip()[:2000] if not show_json else proc.stdout)
        return 0
    if show_json:
        print(json.dumps(d, indent=2, default=str))
    else:
        print("\n" + "=" * 70)
        print(render(system, d))
    if want_pdf:
        try:
            pdf_path = _make_pdf(system, d)
            print(f"\n  📄 PDF: {pdf_path}")
        except Exception as e:  # never let PDF failure kill the run
            print(f"\n  (PDF generation failed: {e})", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Natural-language front door to the investment systems.",
        usage="ask.py \"<plain-English request>\"  |  ask.py <system> [--flags]")
    ap.add_argument("request", nargs=argparse.REMAINDER,
                    help="plain-English request, or '<system> --flags'")
    ap.add_argument("-n", "--dry-run", action="store_true", help="show the plan, don't run")
    ap.add_argument("--json", action="store_true", help="print full JSON, not just the summary")
    ap.add_argument("--pdf", action="store_true", help="also render a branded PDF")
    ap.add_argument("--system", default=None, help="force a system (skip intent detection)")
    args = ap.parse_args()

    parts = args.request
    if not parts:
        print("Ask me something, e.g.:  ask.py \"what's MSFT worth vs AAPL and GOOGL?\"")
        return 1

    # short form: first token is a system name -> pass the rest straight through
    if parts[0] in SYSTEMS and not args.system:
        return run_system(parts[0], parts[1:], args.json, want_pdf=args.pdf)

    text = " ".join(parts)
    # PDF is produced ONLY if explicitly requested in the prompt (or via --pdf).
    want_pdf = args.pdf or wants_pdf(text)
    if want_pdf:
        text = strip_pdf_phrase(text)  # don't let "as a pdf" skew intent detection
    _load_universe()
    if args.system:
        system, why = args.system, "forced"
    else:
        system, why = classify(text)
    argv, missing = build_argv(system, text)
    print(f"→ system: {system}  ({why}){'   [+PDF]' if want_pdf else ''}")
    if missing:
        print(f"  need more: {missing}")
        return 2
    print(f"  running: {system} {' '.join(argv)}")
    if args.dry_run:
        return 0
    return run_system(system, argv, args.json, want_pdf=want_pdf)


if __name__ == "__main__":
    sys.exit(main())
