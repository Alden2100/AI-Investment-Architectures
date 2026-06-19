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
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
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
# sector keyword -> SIC prefix
SECTORS = {
    "software": "7372", "semiconductor": "3674", "semiconductors": "3674",
    "chip": "3674", "chips": "3674", "bank": "6022", "banks": "6022",
    "pharma": "2834", "pharmaceutical": "2834", "biotech": "2836",
    "retail": "5200", "oil": "1311", "energy": "1311", "auto": "3711",
    "automotive": "3711", "aerospace": "3728", "airline": "4512",
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


def run_system(system: str, argv: list, show_json: bool) -> int:
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
        # a system emitted non-JSON (rare model-output edge); still surface a summary
        if show_json:
            print(proc.stdout); return 0
        m = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', proc.stdout)
        print("\n" + "=" * 70)
        print(m.group(1) if m else proc.stdout.strip()[:1500])
        return 0
    if show_json:
        print(json.dumps(d, indent=2, default=str)); return 0
    print("\n" + "=" * 70)
    print(d.get("summary", "(no summary)"))
    if d.get("output_path"):
        print(f"\nfull result: {d['output_path']}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Natural-language front door to the investment systems.",
        usage="ask.py \"<plain-English request>\"  |  ask.py <system> [--flags]")
    ap.add_argument("request", nargs=argparse.REMAINDER,
                    help="plain-English request, or '<system> --flags'")
    ap.add_argument("-n", "--dry-run", action="store_true", help="show the plan, don't run")
    ap.add_argument("--json", action="store_true", help="print full JSON, not just the summary")
    ap.add_argument("--system", default=None, help="force a system (skip intent detection)")
    args = ap.parse_args()

    parts = args.request
    if not parts:
        print("Ask me something, e.g.:  ask.py \"what's MSFT worth vs AAPL and GOOGL?\"")
        return 1

    # short form: first token is a system name -> pass the rest straight through
    if parts[0] in SYSTEMS and not args.system:
        return run_system(parts[0], parts[1:], args.json)

    text = " ".join(parts)
    _load_universe()
    if args.system:
        system, why = args.system, "forced"
    else:
        system, why = classify(text)
    argv, missing = build_argv(system, text)
    print(f"→ system: {system}  ({why})")
    if missing:
        print(f"  need more: {missing}")
        return 2
    print(f"  running: {system} {' '.join(argv)}")
    if args.dry_run:
        return 0
    return run_system(system, argv, args.json)


if __name__ == "__main__":
    sys.exit(main())
