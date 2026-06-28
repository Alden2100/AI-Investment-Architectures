"""research-archive-search: retrieve relevant historical research/memos/notes. Hybrid model skill."""
import argparse
import glob
import json as _json
import os
import re
import sys

_here = os.path.realpath(__file__)
_root = os.environ.get("IM_LIB_ROOT", "")
if not _root:
    _d = os.path.dirname(_here)
    while _d != os.path.dirname(_d):
        if os.path.isdir(os.path.join(_d, "_shared", "data-fetch")):
            _root = _d
            break
        _d = os.path.dirname(_d)
for _p in ("data-fetch", "router", "web-search"):
    _cand = os.path.join(_root, "_shared", _p)
    if os.path.isdir(_cand) and _cand not in sys.path:
        sys.path.insert(0, _cand)

from imdata import skillkit
from imrouter import route as _route

SYSTEMS_ROOT = "/Users/amehta2/AI-Investment-Architectures/systems"

SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "File path or table the hit came from"},
                    "snippet": {"type": "string", "description": "Relevant excerpt"},
                    "ref": {"type": "string", "description": "How to locate it (path/line/id)"},
                },
                "required": ["source", "snippet"],
            },
        },
        "scope_note": {"type": "string", "description": "What was and was not searched"},
        "summary": {"type": "string", "description": "One-line summary of what was found"},
    },
    "required": ["query", "results", "summary"],
}

SYSTEM = (
    "You are a research librarian. You are given candidate hits already retrieved from a local "
    "research archive by keyword matching. Rank them by relevance to the query, explain briefly "
    "why each is relevant, and produce tidy snippets. Use only the provided candidates; do not "
    "invent sources or content."
)


def _tokens(query):
    return [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]


def _score(text, toks):
    low = text.lower()
    return sum(low.count(t) for t in toks)


def _gather_candidates(query, limit=25):
    toks = _tokens(query)
    patterns = [
        os.path.join(SYSTEMS_ROOT, "*", "data", "output", "*.json"),
        os.path.join(SYSTEMS_ROOT, "*", "data", "output", "*.md"),
        os.path.join(SYSTEMS_ROOT, "*", "*.md"),
    ]
    scored = []
    for pat in patterns:
        for path in glob.glob(pat):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue
            s = _score(content, toks)
            if s <= 0:
                continue
            # build a snippet around the first matching token
            snippet = content[:600]
            for t in toks:
                idx = content.lower().find(t)
                if idx >= 0:
                    start = max(0, idx - 200)
                    snippet = content[start:start + 600]
                    break
            scored.append({"source": path, "score": s,
                           "snippet": snippet.strip(), "ref": path})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:limit]


def _gather_store(query):
    """Best-effort: scan any 'thesis' table in the imdata store. Never fail if absent."""
    try:
        from imdata import store
    except Exception:
        return []
    toks = _tokens(query)
    out = []
    try:
        conn = store.get_conn() if hasattr(store, "get_conn") else None
    except Exception:
        conn = None
    if conn is None:
        return out
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        for tbl in tables:
            if "thesis" not in tbl.lower():
                continue
            try:
                rows = conn.execute(f"SELECT * FROM {tbl} LIMIT 200").fetchall()
            except Exception:
                continue
            for row in rows:
                blob = " ".join(str(v) for v in (dict(row).values() if hasattr(row, "keys") else row))
                if _score(blob, toks) > 0:
                    out.append({"source": f"store:{tbl}", "score": _score(blob, toks),
                                "snippet": blob[:600], "ref": f"store table {tbl}"})
    except Exception:
        pass
    return out


def main(args):
    query = args.query
    if not query or not query.strip():
        raise ValueError("Provide --query.")

    candidates = _gather_candidates(query)
    candidates += _gather_store(query)
    candidates.sort(key=lambda r: r.get("score", 0), reverse=True)
    candidates = candidates[:25]

    meta = {"query": query,
            "candidate_count": len(candidates),
            "searched_paths": [os.path.join(SYSTEMS_ROOT, "*", "data", "output", "*.json|*.md"),
                               os.path.join(SYSTEMS_ROOT, "*", "*.md")]}

    if not candidates:
        return skillkit.model_output(
            {"query": query, "results": [],
             "scope_note": "No local research artifacts matched the query (archive may be empty).",
             "summary": f"No matches for '{query}' in the local research archive."},
            meta,
        )

    prompt = (
        f"Query: {query}\n\n"
        "Candidate hits retrieved by keyword matching from the local research archive "
        "(source path, keyword score, snippet):\n"
        + _json.dumps(candidates, default=str)[:30000]
        + "\n\nRank the most relevant, explain relevance in the snippet, and report scope."
    )
    analysis = _route(prompt, task="extraction", system=SYSTEM, schema=SCHEMA, max_tokens=2200)
    return skillkit.model_output(analysis, meta)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Retrieve relevant historical research/memos/notes from the local archive.")
    p.add_argument("--query", required=True)
    skillkit.run(main, p)
