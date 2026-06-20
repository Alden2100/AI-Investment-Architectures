#!/usr/bin/env python3
"""filing-intelligence orchestrator.

Deterministic lenses on ONE filing: retrieval (text + excerpt), change-detection
vs the prior comparable filing, and competitive read (margins + external news).
Then ONE bounded model step writes the Filing Intelligence Brief
(What changed -> Why it matters -> What to watch). Numbers are quoted, never made.
"""
# ---- system sandbox: set env BEFORE importing the shared library -----------
import argparse, json, os, sys, time
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
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(DATA_DIR, "filing-intelligence.db"))
os.environ.setdefault("IM_ROUTER_LOG", os.path.join(DATA_DIR, "router_decisions.jsonl"))
os.environ.setdefault("IM_ROUTER_POLICY", os.path.join(HERE, "router-policy.yaml"))
for _p in ("data-fetch", "router", "web-search"):
    sys.path.insert(0, os.path.join(LIB, "_shared", _p))
from imdata import skillkit                         # noqa: E402
from imrouter import orchestration as orch          # noqa: E402

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "what_changed": {"type": "string"},
        "why_it_matters": {"type": "string"},
        "what_to_watch": {"type": "string"},
        "summary": {"type": "string"},
    }, "required": ["what_changed", "why_it_matters", "what_to_watch", "summary"],
}


def retrieval(ticker, form):
    f = skillkit.call_skill("filing-fetcher",
                            ["--ticker", ticker, "--form", form, "--limit", "1", "--with-text"])
    filings = f.get("filings", [])
    if not filings:
        return None, None
    fil = filings[0]
    excerpt = skillkit.excerpt(fil.get("text", "") or "", max_chars=18000,
                               anchors=[r"risk factors", r"management.s discussion",
                                        r"results of operations"])
    meta = {"form": fil["form"], "date": fil["date"], "accession": fil["accession"],
            "url": fil["url"]}
    return meta, excerpt


def _similar(a, b):
    import difflib
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(a=a, b=b).ratio()


def _nontrivial(block):
    """Keep blocks that are real changes, not a one-word reword of an identical para."""
    old, new = block.get("old", "") or "", block.get("new", "") or ""
    if block.get("type") in ("added", "removed"):
        return len((new or old).strip()) >= 40
    return _similar(old, new) < 0.85 and len(new.strip()) >= 40


def change(ticker, form):
    c = skillkit.call_skill("filing-change-detector", ["--ticker", ticker, "--form", form])
    # The change-detector classifies each change by significance + section (high/medium/
    # low). Prefer those; fall back to the raw diffs with trivial rewordings filtered out.
    classified = c.get("changes") or []
    material = [ch for ch in classified
                if str(ch.get("significance", "")).lower().startswith(("high", "medium"))
                or "high" in str(ch.get("significance", "")).lower()
                or "medium" in str(ch.get("significance", "")).lower()]
    nontrivial = [b for b in c.get("diff_blocks", []) if _nontrivial(b)][:8]
    return {"raw_change_count": c.get("raw_change_count"),
            "change_summary": c.get("summary") if isinstance(c.get("summary"), str) else None,
            "classified": classified,
            "material_changes": material,
            "diff_blocks": nontrivial,
            "prior": c.get("old"), "current": c.get("new")}


def competitive(ticker):
    m = skillkit.call_skill("moat-analyzer", ["--ticker", ticker])
    n = skillkit.call_skill("news-fetcher", ["--ticker", ticker, "--lookback", "30"])
    return {"margins": m.get("margins", {}),
            "external_context": [{"title": i["title"], "date": i.get("date")}
                                 for i in n.get("items", [])[:5]]}


def main(args):
    meta, excerpt = retrieval(args.ticker, args.form)
    if meta is None:
        return {"system": "filing-intelligence",
                "summary": f"No {args.form} found for {args.ticker.upper()}."}
    chg = change(args.ticker, args.form)
    comp = competitive(args.ticker)
    # Structured read of the filing itself (business / drivers / risks / guidance),
    # via the structure-aware retriever under the hood.
    dig = skillkit.call_skill("filing-summarizer", ["--ticker", args.ticker, "--form", args.form])
    digest = None if dig.get("_needs_model") else orch.recover(
        dig, ("business", "drivers", "risks", "guidance"))

    # Feed the model the HIGH-SIGNAL classified changes (compact), not the raw filing —
    # a tighter, higher-signal prompt is what the local 9B model handles best.
    changes_for_model = chg["material_changes"] or chg["classified"] or [
        {"section": "diff", "new": (b.get("new") or b.get("old", ""))[:300],
         "significance": "unrated"} for b in chg["diff_blocks"][:6]]

    def _brief_prompt(detail):
        return (
            "Write a Filing Intelligence Brief from these classified changes. Return an "
            "object with keys 'what_changed', 'why_it_matters', 'what_to_watch' (each a "
            "short paragraph) and 'summary' (one sentence). Focus on the high/medium "
            "significance items; ignore boilerplate. Quote numbers exactly.\n\n"
            f"company: {args.ticker.upper()} {args.form} ({meta['date']})\n"
            f"classified_changes: {json.dumps(changes_for_model, default=str)[:detail]}\n"
            f"margins: {json.dumps(comp.get('margins', {}), default=str)}\n"
            f"recent_news: {json.dumps([c['title'] for c in comp.get('external_context', [])][:4])}"
        )

    KEYS = ("what_changed", "why_it_matters", "what_to_watch")
    brief = orch.synthesize(_brief_prompt(4500), task="synthesis", schema=BRIEF_SCHEMA,
                            max_tokens=1600,
                            system="You are an equity analyst. Precise, skeptical, concise.")
    brief_fields = None if brief.get("_needs_model") else orch.recover(brief, KEYS)
    # one retry with a smaller prompt if the local model came back empty
    if not brief.get("_needs_model") and not any((brief_fields or {}).values()):
        brief = orch.synthesize(_brief_prompt(2200), task="synthesis", schema=BRIEF_SCHEMA,
                                max_tokens=1400,
                                system="Equity analyst. Output only the JSON object, all four keys filled.")
        brief_fields = orch.recover(brief, KEYS)
    # Always emit a clean, deterministic one-line summary (never the model's raw blob).
    has_brief = bool(brief_fields and any(brief_fields.values()))
    n_material = len(chg.get("material_changes") or [])
    tail = (f"Brief written via {brief.get('_route')}." if has_brief
            else (chg.get("change_summary")
                  or "see the classified changes below (a Claude key yields a fuller Brief)."))
    summary = (f"{args.ticker.upper()} {args.form} ({meta['date']}): "
               f"{chg.get('raw_change_count')} raw diffs, {n_material} high/medium-significance "
               f"change(s). {tail}")
    out = {
        "system": "filing-intelligence",
        "ticker": args.ticker.upper(), "form": args.form,
        "filing": meta, "change": chg, "competitive": comp,
        "digest": digest,
        "brief": brief_fields,
        "model_route": brief.get("_route", "none"),
        "summary": summary,
    }
    orch.audit("filing-intelligence", "analyze-filing", f"{args.ticker.upper()} {args.form}",
               f"{chg.get('raw_change_count')} changes; brief via {brief.get('_route', 'none')}")
    out["output_path"] = orch.write_output("filing-intelligence", out)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Filing intelligence orchestrator.")
    p.add_argument("--ticker", required=True)
    p.add_argument("--form", default="10-K")
    skillkit.run(main, p)
