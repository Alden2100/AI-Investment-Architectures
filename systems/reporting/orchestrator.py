#!/usr/bin/env python3
"""reporting orchestrator.

Two deliverables, one entry point:
  --memo TICKER   : gather DCF + comps + moat + fundamentals deterministically, then
                    memo-writer drafts an IC memo from those exact numbers.
  --letter PERIOD : letter-drafter writes an investor/LP letter from supplied
                    performance + holdings.
The drafting skills route the writing step themselves (drafting -> Claude, qwen
fallback), so the final prose is auditable and the numbers are never invented.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys, tempfile, time
HERE = os.path.dirname(os.path.realpath(__file__))
_d, LIB = HERE, None
while _d != os.path.dirname(_d):
    if os.path.isdir(os.path.join(_d, "skills-library")):
        LIB = os.path.join(_d, "skills-library"); break
    _d = os.path.dirname(_d)
DATA_DIR = os.path.join(HERE, "data"); os.makedirs(DATA_DIR, exist_ok=True)
_envf = os.path.join(os.path.dirname(LIB), ".env")
if os.path.exists(_envf):
    for _ln in open(_envf):
        _ln = _ln.strip()
        if _ln and not _ln.startswith("#") and "=" in _ln:
            _k, _v = _ln.split("=", 1); os.environ.setdefault(_k.strip(), _v.strip().strip('"'))
os.environ.setdefault("IM_LIB_ROOT", LIB)
os.environ.setdefault("IM_SKILLS_DIR", os.path.join(HERE, ".claude", "skills"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", DATA_DIR)
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "reporting.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit                         # noqa: E402
from imrouter import orchestration as orch          # noqa: E402


def build_memo(ticker):
    t = ticker.upper()
    dcf = skillkit.call_skill("dcf-valuation", ["--ticker", t])
    comps = skillkit.call_skill("comps-builder", ["--tickers", t, "--target", t])
    moat = skillkit.call_skill("moat-analyzer", ["--ticker", t])
    fund = skillkit.call_skill("fundamentals-fetcher",
                               ["--ticker", t, "--items", "revenue", "net_income",
                                "operating_income"])
    # Distill to a compact, high-signal block — the model writes a sharper memo from
    # clean numbers than from four full raw skill dumps (and the 9B handles it keyless).
    inputs = {
        "price": dcf.get("current_price"),
        "dcf_intrinsic_per_share": dcf.get("intrinsic_value_per_share"),
        "dcf_upside": dcf.get("upside_vs_price"),
        "comps_median": comps.get("median"),
        "comps_implied_value": comps.get("target_value") or comps.get("implied_value"),
        "margins": moat.get("margins"),
        "moat_assessment": moat.get("assessment") if isinstance(moat.get("assessment"), str)
        else (moat.get("summary") if isinstance(moat.get("summary"), str) else None),
        "financials": fund.get("financials", {}),
    }
    fd, path = tempfile.mkstemp(suffix=".json", dir=DATA_DIR)
    with os.fdopen(fd, "w") as fh:
        json.dump(inputs, fh, default=str)
    memo = skillkit.call_skill("memo-writer", ["--ticker", t, "--input-file", path])
    os.unlink(path)
    inputs_used = ["dcf", "comps", "moat", "fundamentals"]  # the source skills distilled in
    route = "claude" if memo.get("_source") == "api" else (
        "local" if memo.get("_source") == "ollama" else "none")
    # Be robust to the local 9B model's schema looseness: memo-writer merges model
    # fields into its result, so sections may arrive under `memo_sections`, flattened
    # at top level, or as raw `text`. Recover the draft however it came back.
    SECT = ["thesis", "business_overview", "financials", "valuation", "risks", "recommendation"]
    sections = memo.get("memo_sections")
    if not (isinstance(sections, dict) and sections):
        flat = {k: memo[k] for k in SECT if isinstance(memo.get(k), str) and memo[k].strip()}
        sections = flat or None
    draft_text = memo.get("text") if not sections else None
    needs = bool(memo.get("_needs_model")) or (not sections and not draft_text)
    summary = (memo.get("summary") if isinstance(memo.get("summary"), str) and memo.get("summary").strip()
               else None) or (f"IC memo dossier for {t} ready — set a model route."
                              if needs else f"IC memo drafted for {t} via {route}.")
    return {
        "system": "reporting", "kind": "memo", "ticker": t,
        "inputs_used": inputs_used,
        "metrics": inputs,            # distilled numbers, for a key-metrics table in the PDF
        "memo_sections": sections,
        "draft_text": draft_text,
        "needs_model": needs,
        "model_route": route,
        "summary": summary,
    }


def build_letter(args):
    largs = ["--period", args.letter]
    if args.performance: largs += ["--performance", args.performance]
    if args.holdings:    largs += ["--holdings", *args.holdings]
    letter = skillkit.call_skill("letter-drafter", largs)
    route = "claude" if letter.get("_source") == "api" else (
        "local" if letter.get("_source") == "ollama" else "none")
    draft = letter.get("letter_draft") or letter.get("text")
    needs = bool(letter.get("_needs_model")) or not draft
    summary = (letter.get("summary") if isinstance(letter.get("summary"), str) and letter.get("summary").strip()
               else None) or (f"Letter dossier for {args.letter} ready — set a model route."
                              if needs else f"Investor letter drafted for {args.letter} via {route}.")
    return {
        "system": "reporting", "kind": "letter", "period": args.letter,
        "letter_draft": draft,
        "needs_model": needs,
        "model_route": route,
        "summary": summary,
    }


def main(args):
    if args.memo:
        out = build_memo(args.memo)
        orch.audit("reporting", "memo", out["ticker"], f"via {out['model_route']}")
    elif args.letter:
        out = build_letter(args)
        orch.audit("reporting", "letter", out["period"], f"via {out['model_route']}")
    else:
        raise ValueError("Provide --memo TICKER or --letter PERIOD.")
    out["output_path"] = orch.write_output("reporting", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Reporting orchestrator (IC memo / investor letter).")
    p.add_argument("--memo", default=None, metavar="TICKER", help="draft an IC memo for a ticker")
    p.add_argument("--letter", default=None, metavar="PERIOD", help='draft a letter, e.g. "Q2 2026"')
    p.add_argument("--performance", default=None, help="letter: e.g. 'fund=+4.2%,bench=+2.1%'")
    p.add_argument("--holdings", nargs="*", default=None, help="letter: TICKER=weight ...")
    skillkit.run(main, p)
