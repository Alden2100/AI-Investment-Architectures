"""text-similarity: TF-IDF cosine of survivors vs mandate + seed companies. Deterministic.

Stage 3 of idea-sourcing v2. Hand-rolled TF-IDF + cosine over numpy ONLY (no sklearn/scipy,
no model calls, no network). Descriptions are supplied by upstream stages; nothing is fetched
here. Scores are comparable WITHIN a run (IDF is fit on the in-run company set) but not across
runs with different survivor sets — see SKILL.md "documented decision".
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np

# --- locate the shared library (_shared/) so `imdata.skillkit` imports whether run from
# --- the canonical path, a system's symlinked .claude/skills, or a standalone bundle ----
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

from imdata import skillkit  # noqa: E402

VERSION = "1.0.0"

# Small inline English stoplist (no external corpus). Tokens are length>=3, so 1-2 char
# words (a, an, of, to, in, is, it, on...) are already dropped by the length filter; this
# list catches the remaining high-frequency function words that survive it.
STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "are", "was", "its", "from",
    "has", "have", "had", "will", "our", "their", "they", "them", "his", "her",
    "she", "him", "you", "your", "but", "not", "all", "any", "can", "may",
    "such", "than", "then", "into", "over", "under", "out", "off", "per",
    "via", "also", "been", "were", "which", "who", "whom", "whose", "what",
    "when", "where", "how", "why", "about", "above", "below", "between",
    "both", "each", "more", "most", "other", "some", "only", "own", "same",
    "very", "these", "those", "there", "here", "while", "during", "including",
    "include", "includes", "provides", "provide", "company", "companies",
    "inc", "corp", "corporation", "ltd", "llc", "plc", "group", "holdings",
})

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def tokenize(text):
    """lowercase -> split on non-alphanumeric -> keep len>=3 alphanumeric tokens not in stoplist.

    Deterministic; returns a list (order preserved) so counts and presence are stable.
    """
    if not text:
        return []
    toks = _TOKEN_SPLIT.split(text.lower())
    return [t for t in toks if len(t) >= 3 and t not in STOPWORDS]


def _fit_vocab_idf(company_docs_tokens, min_df=2, max_features=20000):
    """Fit vocabulary + IDF on the COMPANY corpus only (survivors u seed_companies).

    - min_df: drop tokens appearing in fewer than `min_df` company docs.
    - max_features: cap vocab to the most-frequent-by-document-frequency tokens.
    - idf(t) = log(N / (1 + df(t))) + 1, N = number of company docs.

    Returns (vocab_index: {token: col}, idf: np.ndarray aligned to columns).
    """
    n_docs = len(company_docs_tokens)
    df = {}
    for toks in company_docs_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1

    # Keep tokens with df >= min_df. Rank by (df desc, token asc) for a fully
    # deterministic vocab when caps bite; then take the top `max_features`.
    kept = [(tok, d) for tok, d in df.items() if d >= min_df]
    kept.sort(key=lambda kv: (-kv[1], kv[0]))
    kept = kept[:max_features]

    # Assign columns in sorted-token order so the vector space is reproducible.
    kept_tokens = sorted(t for t, _ in kept)
    vocab = {tok: i for i, tok in enumerate(kept_tokens)}

    idf = np.zeros(len(vocab), dtype=np.float64)
    for tok, col in vocab.items():
        idf[col] = math.log(n_docs / (1.0 + df[tok])) + 1.0
    return vocab, idf


def _vectorize(tokens, vocab, idf):
    """tf(t)=1+log(count) for present in-vocab terms; component = tf*idf; L2-normalize.

    All-zero vector (no in-vocab terms, or empty doc) stays zero. Asserts non-negativity.
    """
    vec = np.zeros(len(vocab), dtype=np.float64)
    if not vocab.__len__() or not tokens:
        return vec
    counts = {}
    for t in tokens:
        col = vocab.get(t)
        if col is not None:
            counts[col] = counts.get(col, 0) + 1
    for col, c in counts.items():
        vec[col] = (1.0 + math.log(c)) * idf[col]
    assert np.all(vec >= 0.0), "TF-IDF components must be non-negative"
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec = vec / norm
    return vec


def _cosine(a, b):
    """Dot of two already-L2-normalized, non-negative vectors -> cosine in [0,1].

    Returns 0.0 if either vector is all-zero. Clipped to [0,1] to absorb fp drift.
    """
    if a.size == 0 or b.size == 0:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    sim = float(np.dot(a, b))
    sim = max(0.0, min(1.0, sim))  # non-negative tf-idf => cosine already in [0,1]
    assert 0.0 <= sim <= 1.0, "cosine of non-negative L2-normed vectors must be in [0,1]"
    return sim


def score_text_similarity(mandate_text, seed_companies, survivors,
                          w_seed=0.6, w_mandate=0.4):
    """Score each survivor's business-text similarity to the mandate and to the seed set.

    Pure function: no I/O, no fetching, no randomness, deterministic ordering.

    Args:
        mandate_text: str. The mandate / thesis text. Required and non-empty.
        seed_companies: list of {ticker, description}. May be empty.
        survivors: list of {ticker, description}. description is business text
            already fetched upstream (NOT fetched here).
        w_seed, w_mandate: blend weights when seeds exist.

    Returns:
        list of {ticker, text_score, sim_mandate, sim_seeds (None if no seeds),
        missing_description}, one row per survivor, in input order (stable).
    """
    if not mandate_text or not str(mandate_text).strip():
        raise ValueError("mandate_text is empty — Stage 3 requires a non-empty mandate to score against.")

    seed_companies = list(seed_companies or [])
    survivors = list(survivors or [])
    has_seeds = len(seed_companies) > 0

    # --- FIT vocab + IDF on the COMPANY corpus ONLY (survivors u seed_companies) ---
    # (the mandate is a QUERY, not a fitting document — never folded into IDF.)
    company_docs_tokens = []
    for c in survivors:
        company_docs_tokens.append(tokenize((c or {}).get("description") or ""))
    for s in seed_companies:
        company_docs_tokens.append(tokenize((s or {}).get("description") or ""))
    vocab, idf = _fit_vocab_idf(company_docs_tokens)

    # --- VECTORIZE the mandate and each seed in that fitted space ---
    mandate_vec = _vectorize(tokenize(mandate_text), vocab, idf)
    seed_vecs = [_vectorize(tokenize((s or {}).get("description") or ""), vocab, idf)
                 for s in seed_companies]

    results = []
    for c in survivors:
        c = c or {}
        ticker = c.get("ticker")
        desc = c.get("description")
        if not desc or not str(desc).strip():
            # Missing description -> never silently 0; flag it explicitly.
            results.append({
                "ticker": ticker,
                "text_score": 0.0,
                "sim_mandate": 0.0,
                "sim_seeds": None if not has_seeds else 0.0,
                "missing_description": True,
            })
            continue

        cvec = _vectorize(tokenize(desc), vocab, idf)
        sim_mandate = _cosine(cvec, mandate_vec)

        if has_seeds:
            sims = [_cosine(cvec, sv) for sv in seed_vecs]
            sim_seeds = float(np.mean(sims)) if sims else 0.0
            text_score = w_seed * sim_seeds + w_mandate * sim_mandate
        else:
            sim_seeds = None
            text_score = sim_mandate

        text_score = max(0.0, min(1.0, float(text_score)))
        assert 0.0 <= text_score <= 1.0, "text_score must be in [0,1]"

        results.append({
            "ticker": ticker,
            "text_score": text_score,
            "sim_mandate": sim_mandate,
            "sim_seeds": sim_seeds,
            "missing_description": False,
        })

    # Stable: preserve input order (already the case); explicit no-op to document intent.
    return results


def _load_payload(args):
    """Resolve {mandate_text, seed_companies, survivors} from --file or the split flags."""
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return (
            payload.get("mandate_text"),
            payload.get("seed_companies") or [],
            payload.get("survivors") or [],
        )
    survivors = []
    if args.survivors_file:
        with open(args.survivors_file, "r", encoding="utf-8") as f:
            doc = json.load(f)
        # Accept either a bare list or {survivors:[...], seed_companies:[...], mandate_text}
        if isinstance(doc, list):
            survivors = doc
        else:
            survivors = doc.get("survivors") or []
            if args.mandate_text is None:
                args.mandate_text = doc.get("mandate_text")
    seed_companies = []
    if args.seeds_file:
        with open(args.seeds_file, "r", encoding="utf-8") as f:
            sdoc = json.load(f)
        seed_companies = sdoc if isinstance(sdoc, list) else (sdoc.get("seed_companies") or [])
    return args.mandate_text, seed_companies, survivors


def main(args):
    mandate_text, seed_companies, survivors = _load_payload(args)
    if mandate_text is None:
        raise ValueError(
            "No mandate_text provided. Pass --file <stage2.json> or --mandate-text "
            "(optionally with --survivors-file / --seeds-file).")

    results = score_text_similarity(
        mandate_text, seed_companies, survivors,
        w_seed=args.w_seed, w_mandate=args.w_mandate,
    )

    scored = [r for r in results if not r["missing_description"]]
    missing = [r for r in results if r["missing_description"]]
    ranked = sorted(scored, key=lambda r: (-r["text_score"], str(r["ticker"])))
    top = ranked[0] if ranked else None
    summary = (
        f"Scored {len(scored)} survivor(s) against the mandate"
        + (f" and {len(seed_companies)} seed(s)" if seed_companies else " (no seeds)")
        + (f"; {len(missing)} missing description" if missing else "")
        + (f". Top: {top['ticker']} ({top['text_score']:.3f})." if top else ".")
    )
    return {
        "version": VERSION,
        "results": results,
        "summary": summary,
        "params": {
            "w_seed": args.w_seed,
            "w_mandate": args.w_mandate,
            "n_survivors": len(survivors),
            "n_seeds": len(seed_companies),
            "n_missing_description": len(missing),
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Stage 3: TF-IDF cosine similarity of survivors vs mandate + seed companies.")
    p.add_argument("--file", default=None,
                   help="Stage-2 artifact JSON: {mandate_text, seed_companies, survivors}")
    p.add_argument("--mandate-text", dest="mandate_text", default=None,
                   help="mandate/thesis text (alternative to --file)")
    p.add_argument("--survivors-file", dest="survivors_file", default=None,
                   help="JSON list of {ticker, description} or {survivors:[...]}")
    p.add_argument("--seeds-file", dest="seeds_file", default=None,
                   help="JSON list of {ticker, description} seed companies (optional)")
    p.add_argument("--w-seed", dest="w_seed", type=float, default=0.6)
    p.add_argument("--w-mandate", dest="w_mandate", type=float, default=0.4)
    skillkit.run(main, p)
