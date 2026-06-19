"""Structure-aware RAG for SEC filings.

Fixed-length chunking mangles 10-Ks. This module instead:

  * splits a filing on its **Items / sections** (Item 1 Business, Item 1A Risk
    Factors, Item 7 MD&A, …), discarding the table-of-contents cluster;
  * keeps **tables intact** — a contiguous run of tabular/numeric lines is never
    split across chunks;
  * does **parent-document retrieval** — it indexes small child chunks for precise
    matching but returns the larger *parent section* they belong to, so the model
    sees coherent context, not a sentence fragment.

Retrieval ranking is keyless **BM25** over the filing's own chunks (a strong,
dependency-free baseline for the keyword/entity-heavy filing domain). A dense
route is pluggable: set ``OLLAMA_EMBED_MODEL`` to an embedding model served by
Ollama and retrieval upgrades to cosine similarity automatically. (True *late
chunking* — embedding the whole doc then pooling per chunk — needs a long-context
embedding model; the interface is here, the model is the only missing piece.)

Everything is cached in SQLite (rebuildable from the filing), so indexing a filing
once makes every later query fast.
"""
from __future__ import annotations

import math
import os
import re
from typing import Optional

from . import edgar, store

# --------------------------------------------------------------------------- #
# Schema (self-owned; CREATE IF NOT EXISTS so it co-exists with the core schema)
# --------------------------------------------------------------------------- #
_SCHEMA = """
CREATE TABLE IF NOT EXISTS filing_sections (
    accession TEXT, idx INTEGER, item TEXT, title TEXT, text TEXT,
    PRIMARY KEY (accession, idx)
);
CREATE TABLE IF NOT EXISTS filing_chunks (
    accession TEXT, idx INTEGER, parent_idx INTEGER, item TEXT, kind TEXT, text TEXT,
    PRIMARY KEY (accession, idx)
);
"""


def _ensure_schema():
    c = store.get_conn()
    c.executescript(_SCHEMA)
    c.commit()


# --------------------------------------------------------------------------- #
# Structure-aware splitting
# --------------------------------------------------------------------------- #
# Item header at the start of a line: "Item 1.", "Item 1A.", "Item 7A:", etc.
_ITEM_RE = re.compile(r"(?im)^\s*item\s+(\d{1,2}[A-Z]?)\s*[.:\-—]?\s*")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']+")
# A line is "tabular" if it is mostly numbers / separators / XBRL noise, not prose.
_XBRL_RE = re.compile(r"(us-gaap:|xbrli|dei:|iso4217|\b\d{10}\b)")


def _norm(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()


def _is_tabular(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _XBRL_RE.search(s):
        return True
    digits = sum(c.isdigit() for c in s)
    letters = sum(c.isalpha() for c in s)
    # number-dominant line, or a row with several wide gaps (column layout)
    if digits and digits >= letters:
        return True
    if len(re.findall(r"\s{2,}", s)) >= 3 and digits >= 2:
        return True
    return False


def split_sections(text: str) -> list:
    """Split filing text into Item/sections, dropping the table-of-contents cluster.

    Returns ``[{idx, item, title, text}]`` in document order. The leading
    front-matter (cover page, before Item 1's body) is kept as section idx 0.
    """
    matches = list(_ITEM_RE.finditer(text))
    if not matches:
        return [{"idx": 0, "item": "FULL", "title": "Document", "text": _norm(text)[:200000]}]

    # Build raw segments between consecutive item headers.
    segs = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end]
        # title = first short line after the header
        title = ""
        for ln in body.splitlines():
            ln = _norm(ln)
            if ln and not ln.isdigit():
                title = ln[:60]
                break
        segs.append({"item": "Item " + m.group(1).upper(), "title": title,
                     "start": start, "len": end - start, "text": body})

    # Real sections are long; TOC entries are tiny (header + page number). Keep the
    # longest segment per distinct item label — that's the body, not the TOC line.
    best = {}
    for s in segs:
        key = s["item"]
        if key not in best or s["len"] > best[key]["len"]:
            best[key] = s
    sections = sorted([s for s in best.values() if s["len"] >= 400],
                      key=lambda s: s["start"])

    out = []
    front = _norm(text[:sections[0]["start"]]) if sections else _norm(text)
    if len(front) > 200:
        out.append({"idx": 0, "item": "COVER", "title": "Cover / front matter",
                    "text": front[:40000]})
    for s in sections:
        out.append({"idx": len(out), "item": s["item"], "title": s["title"],
                    "text": _norm(s["text"])})
    return out


def chunk_section(section: dict, target_chars: int = 1100) -> list:
    """Split one section into small child chunks on paragraph/line boundaries,
    NEVER splitting inside a contiguous run of tabular lines (tables stay whole)."""
    lines = section["text"].splitlines()
    chunks, buf, buf_len, in_table = [], [], 0, False

    def flush(kind):
        nonlocal buf, buf_len
        if buf:
            t = _norm(" ".join(buf)) if kind == "prose" else "\n".join(buf).strip()
            if t:
                chunks.append({"kind": kind, "text": t})
        buf, buf_len = [], 0

    i = 0
    while i < len(lines):
        ln = lines[i]
        if _is_tabular(ln):
            # gather the whole contiguous table block as ONE atomic chunk
            if not in_table:
                flush("prose")
                in_table = True
            tbl = []
            while i < len(lines) and (_is_tabular(lines[i]) or not lines[i].strip()):
                tbl.append(lines[i]); i += 1
            t = "\n".join(l for l in tbl if l.strip())
            if len(t) > 25:
                chunks.append({"kind": "table", "text": t[:4000]})
            in_table = False
            continue
        s = _norm(ln)
        if s:
            buf.append(s); buf_len += len(s) + 1
        if buf_len >= target_chars and (not s or s.endswith((".", ";", ":"))):
            flush("prose")
        i += 1
    flush("prose")
    return [c for c in chunks if len(c["text"]) >= 40]


# --------------------------------------------------------------------------- #
# Index + persistence
# --------------------------------------------------------------------------- #
def index_filing(accession: str, force: bool = False) -> dict:
    """Split + chunk a filing and cache sections/chunks. Returns counts."""
    _ensure_schema()
    c = store.get_conn()
    have = c.execute("SELECT COUNT(*) n FROM filing_chunks WHERE accession=?",
                     (accession,)).fetchone()["n"]
    if have and not force:
        return {"accession": accession, "sections": c.execute(
            "SELECT COUNT(*) n FROM filing_sections WHERE accession=?",
            (accession,)).fetchone()["n"], "chunks": have, "cached": True}

    text = edgar.filing_text(accession)
    sections = split_sections(text)
    c.execute("DELETE FROM filing_sections WHERE accession=?", (accession,))
    c.execute("DELETE FROM filing_chunks WHERE accession=?", (accession,))
    chunk_idx = 0
    for sec in sections:
        c.execute("INSERT OR REPLACE INTO filing_sections VALUES (?,?,?,?,?)",
                  (accession, sec["idx"], sec["item"], sec["title"], sec["text"][:200000]))
        for ch in chunk_section(sec):
            c.execute("INSERT OR REPLACE INTO filing_chunks VALUES (?,?,?,?,?,?)",
                      (accession, chunk_idx, sec["idx"], sec["item"], ch["kind"], ch["text"]))
            chunk_idx += 1
    c.commit()
    return {"accession": accession, "sections": len(sections), "chunks": chunk_idx,
            "cached": False}


def get_sections(accession: str) -> list:
    _ensure_schema()
    rows = store.get_conn().execute(
        "SELECT idx, item, title, text FROM filing_sections WHERE accession=? ORDER BY idx",
        (accession,)).fetchall()
    return [dict(r) for r in rows]


def _chunks(accession: str) -> list:
    return [dict(r) for r in store.get_conn().execute(
        "SELECT idx, parent_idx, item, kind, text FROM filing_chunks WHERE accession=? ORDER BY idx",
        (accession,)).fetchall()]


# --------------------------------------------------------------------------- #
# Retrieval — BM25 over child chunks, return parent sections (parent-document)
# --------------------------------------------------------------------------- #
_STOP = set("the a an and or of to in for on at by is are was were be been with as "
            "that this it its our we their from than then which may will would could "
            "such other any all not no into over under per".split())


def _tok(s: str) -> list:
    return [w for w in (m.group(0).lower() for m in _WORD_RE.finditer(s))
            if w not in _STOP and len(w) > 1]


def _bm25_scores(query: str, docs: list, k1: float = 1.5, b: float = 0.75) -> list:
    """Return a BM25 score per doc (doc = token list)."""
    N = len(docs)
    avgdl = sum(len(d) for d in docs) / N if N else 0.0
    df = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    q = [t for t in _tok(query)]
    scores = [0.0] * N
    for i, d in enumerate(docs):
        if not d:
            continue
        tf = {}
        for t in d:
            tf[t] = tf.get(t, 0) + 1
        dl = len(d)
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        scores[i] = s
    return scores


def retrieve(accession: str, query: str, k: int = 4, return_parents: bool = True,
             child_pool: int = 12) -> dict:
    """Parent-document retrieval: match small chunks, return their parent sections.

    Returns ``{method, matches: [{item, title, score, text}], child_hits: [...]}``.
    """
    index_filing(accession)
    chunks = _chunks(accession)
    if not chunks:
        return {"method": "none", "matches": [], "child_hits": []}

    method = "bm25"
    dense = _dense_scores(query, [c["text"] for c in chunks])
    if dense is not None:
        scores, method = dense, "dense"
    else:
        scores = _bm25_scores(query, [_tok(c["text"]) for c in chunks])

    ranked = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
    top_children = [i for i in ranked if scores[i] > 0][:child_pool]
    child_hits = [{"item": chunks[i]["item"], "kind": chunks[i]["kind"],
                   "score": round(scores[i], 3), "text": chunks[i]["text"][:400]}
                  for i in top_children[:k]]

    if not return_parents:
        return {"method": method, "matches": child_hits, "child_hits": child_hits}

    # Map matched children -> parent sections, dedup, keep best-scoring order.
    sec_by_idx = {s["idx"]: s for s in get_sections(accession)}
    seen, parents = set(), []
    for i in top_children:
        pid = chunks[i]["parent_idx"]
        if pid in seen:
            continue
        seen.add(pid)
        sec = sec_by_idx.get(pid)
        if sec:
            parents.append({"item": sec["item"], "title": sec["title"],
                            "score": round(scores[i], 3), "text": sec["text"]})
        if len(parents) >= k:
            break
    return {"method": method, "matches": parents, "child_hits": child_hits}


# --------------------------------------------------------------------------- #
# Optional dense route (pluggable). Keyless default is BM25, so this returns None
# unless an Ollama embedding model is configured AND reachable.
# --------------------------------------------------------------------------- #
def _dense_scores(query: str, texts: list) -> Optional[list]:
    model = os.environ.get("OLLAMA_EMBED_MODEL")
    if not model:
        return None
    try:
        import requests
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        def emb(batch):
            r = requests.post(f"{host}/api/embed", json={"model": model, "input": batch},
                              timeout=120)
            r.raise_for_status()
            return r.json()["embeddings"]
        qv = emb([query])[0]
        # batch the chunk texts to keep requests reasonable
        vecs = []
        for i in range(0, len(texts), 64):
            vecs.extend(emb([t[:2000] for t in texts[i:i + 64]]))
    except Exception:
        return None

    def cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
    return [cos(qv, v) for v in vecs]
