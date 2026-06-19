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


def change(ticker, form):
    c = skillkit.call_skill("filing-change-detector", ["--ticker", ticker, "--form", form])
    return {"raw_change_count": c.get("raw_change_count"),
            "diff_blocks": c.get("diff_blocks", [])[:10],
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

    prompt = (
        "Write a Filing Intelligence Brief. Return an object with keys "
        "'what_changed', 'why_it_matters', 'what_to_watch', and 'summary'. Use the "
        "diff blocks for what changed (flag new/removed risk factors and changed "
        "guidance; ignore boilerplate), the margins and news for competitive read, "
        "and the excerpt for business context. Quote numbers exactly.\n\n"
        f"filing: {json.dumps(meta)}\n"
        f"change: {json.dumps(chg, default=str)[:6000]}\n"
        f"competitive: {json.dumps(comp, default=str)[:3000]}\n"
        f"excerpt: {excerpt[:9000]}"
    )
    brief = orch.synthesize(prompt, task="synthesis", schema=BRIEF_SCHEMA, max_tokens=2200,
                            system="You are an equity analyst. Precise, skeptical, concise.")
    KEYS = ("what_changed", "why_it_matters", "what_to_watch")
    brief_fields = None if brief.get("_needs_model") else orch.recover(brief, KEYS)
    # Always emit a clean, deterministic one-line summary (never the model's raw blob).
    has_brief = bool(brief_fields and any(brief_fields.values()))
    summary = (f"{args.ticker.upper()} {args.form} ({meta['date']}): "
               f"{chg.get('raw_change_count')} material change(s) vs the prior {args.form}; "
               + (f"Brief written via {brief.get('_route')}."
                  if has_brief else
                  "model Brief was thin this run — substantive diffs available "
                  "(a Claude key yields a fuller Brief)."))
    out = {
        "system": "filing-intelligence",
        "ticker": args.ticker.upper(), "form": args.form,
        "filing": meta, "change": chg, "competitive": comp,
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
