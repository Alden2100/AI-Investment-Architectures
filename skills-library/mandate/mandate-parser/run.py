"""mandate-parser: turn a raw investment mandate into a structured MandateSpec. Hybrid model skill.

Stage 0 of idea-sourcing v2. PRIMARY job: CLASSIFICATION of every criterion as
hard_constraint | soft_preference | qualitative. The model classifies; Python assigns the
mandate_id / mandate_hash, normalizes criterion ids, and validates seed tickers.
"""
import argparse
import hashlib
import json
import os
import sys

# --- locate the shared library (_shared/) whether run from its canonical path,
# --- a system's symlinked .claude/skills, or a standalone bundle -------------
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

from imdata import skillkit, universe
from imrouter import route as _route

SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Stable id like c1, c2 (optional; will be normalized)"},
                    "text": {"type": "string", "description": "Verbatim mandate phrase this criterion came from"},
                    "type": {"type": "string", "enum": ["hard_constraint", "soft_preference", "qualitative"]},
                    "field": {"type": ["string", "null"],
                              "description": "Machine field for hard_constraint (e.g. country, market_cap, sector); null otherwise"},
                    "operator": {"type": ["string", "null"], "enum": ["in", "not_in", "gte", "lte", "between", None]},
                    "value": {"description": "Scalar / list / [low,high] for hard_constraint; null otherwise"},
                    "weight": {"type": ["number", "null"], "description": "0..1 importance for soft/qualitative; null for hard"},
                    "rationale": {"type": "string", "description": "Why this type was chosen"},
                },
                "required": ["text", "type"],
            },
        },
        "seed_tickers": {"type": "array", "items": {"type": "string"},
                         "description": "Tickers of any example companies the mandate names"},
        "semantic_query": {"type": "string",
                           "description": "Concatenated qualitative + soft-preference language for semantic search"},
        "exclusions": {"type": "array", "items": {"type": "string"},
                       "description": "Explicit exclusions (countries, sectors, themes) as short phrases"},
    },
    "required": ["criteria", "seed_tickers", "semantic_query", "exclusions"],
}

SYSTEM = (
    "You are a portfolio-mandate parser. Read an investment mandate and decompose it into a list "
    "of criteria, CLASSIFYING each one precisely. This classification is the most important part "
    "of your job; downstream code treats hard constraints as binary filters and the rest as "
    "ranking signals, so a mis-tag changes the entire candidate set.\n\n"
    "Classify every criterion as exactly one of:\n"
    "  - hard_constraint: a BINARY, mandate-EXPLICIT requirement. Examples: a country/region the "
    "    universe must be IN, an explicit market-cap floor or ceiling ('over $10B', 'small-cap "
    "    only'), an explicit sector inclusion or exclusion ('software companies', 'no financials').\n"
    "  - soft_preference: a numeric or directional PREFERENCE, not a hard cutoff "
    "    (e.g. 'prefer higher gross margins', 'reasonable valuation', 'lower leverage').\n"
    "  - qualitative: a judgment about moat, management quality, business-model fit, durability, "
    "    or other non-numeric character.\n\n"
    "CRITICAL RULE: directional / hedging language is NEVER a hard_constraint. If the phrase "
    "contains 'preferably', 'ideally', 'strong', 'high-quality', 'lean toward', 'where possible', "
    "'attractive', or similar, it is a soft_preference or qualitative — never hard_constraint, "
    "even when it mentions a metric like margins or ROIC.\n\n"
    "For hard_constraint criteria fill structured fields: field (e.g. country, market_cap, sector, "
    "industry), operator (one of in | not_in | gte | lte | between), and value (a scalar, a list "
    "for in/not_in, or [low, high] for between). For soft_preference and qualitative criteria, set "
    "field, operator, and value to null and give a weight in [0,1] reflecting emphasis.\n\n"
    "Extract seed_tickers from any example companies named (use the ticker if you know it, else the "
    "company name). Build semantic_query by concatenating the qualitative and soft-preference "
    "language into a search string. Put explicit exclusions (e.g. 'exclude China') in exclusions "
    "AND as a hard_constraint with operator not_in. Do not invent criteria the mandate does not state."
)


def _read_mandate(args):
    """read-file-else-text-else-stdin."""
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    if getattr(args, "text", None):
        return args.text.strip()
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    raise ValueError("No mandate provided. Pass --file, --text, or pipe text on stdin.")


def _slug(text, n=40):
    keep = []
    for ch in text.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_/," and (keep and keep[-1] != "-"):
            keep.append("-")
    s = "".join(keep).strip("-")
    return s[:n].strip("-")


def _mandate_id(text):
    base = _slug(text)
    if base:
        return base
    return "m-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _normalize_criteria(criteria):
    """Ensure every criterion has c1,c2,... ids and the full key set."""
    out = []
    for i, c in enumerate(criteria, start=1):
        c = dict(c or {})
        cid = c.get("id")
        if not cid or not isinstance(cid, str):
            cid = f"c{i}"
        out.append({
            "id": cid,
            "text": c.get("text", ""),
            "type": c.get("type", "qualitative"),
            "field": c.get("field"),
            "operator": c.get("operator"),
            "value": c.get("value"),
            "weight": c.get("weight"),
            "rationale": c.get("rationale", ""),
        })
    return out


def _mandate_hash(criteria, exclusions):
    """Stable sha256 over sorted criteria (by id) + sorted exclusions."""
    payload = {
        "criteria": sorted(criteria, key=lambda c: c.get("id", "")),
        "exclusions": sorted(exclusions or []),
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_tickers(raw_tickers):
    """Resolve each candidate against the SEC universe. Returns (resolved, note)."""
    resolved, dropped = [], []
    for t in (raw_tickers or []):
        sym = str(t).strip().upper()
        if not sym:
            continue
        try:
            info = universe.resolve(sym)
            if info["ticker"] not in resolved:
                resolved.append(info["ticker"])
        except Exception:
            dropped.append(sym)
    note = None
    if dropped:
        note = "Dropped unresolvable seed tickers: " + ", ".join(dropped)
    return resolved, note


def main(args):
    mandate_text = _read_mandate(args)
    mandate_id = _mandate_id(mandate_text)

    prompt = (
        "Parse the following investment mandate into a structured MandateSpec. Classify EVERY "
        "criterion (hard_constraint | soft_preference | qualitative) per the rules. Remember: "
        "directional/hedging language ('preferably', 'strong', 'ideally', 'high-quality') is never "
        "a hard_constraint. Fill field/operator/value only for hard_constraint criteria.\n\n"
        "MANDATE:\n"
        f"{skillkit.excerpt(mandate_text, max_chars=20000)}\n"
    )

    analysis = _route(prompt, task="reasoning", system=SYSTEM, schema=SCHEMA, max_tokens=2500)

    # --- assemble the deterministic half ------------------------------------
    meta = {"mandate_id": mandate_id}

    if analysis.get("_needs_model"):
        # Model rung deferred: we cannot compute a content hash over criteria that
        # do not exist yet. Hash the raw mandate text so the id/hash are still stable,
        # and flag it as a placeholder for the orchestrating agent.
        meta["mandate_hash"] = "raw:" + hashlib.sha256(mandate_text.encode("utf-8")).hexdigest()
        meta["mandate_hash_basis"] = "raw_text_placeholder"
        meta["seed_tickers"] = []
        meta["criteria"] = []
        meta["semantic_query"] = ""
        meta["exclusions"] = []
        return skillkit.model_output(analysis, meta)

    # Model filled the fields — normalize and finalize.
    criteria = _normalize_criteria(analysis.get("criteria", []))
    exclusions = list(analysis.get("exclusions", []) or [])
    seed_tickers, ticker_note = _validate_tickers(analysis.get("seed_tickers", []))

    final = {
        "mandate_id": mandate_id,
        "mandate_hash": _mandate_hash(criteria, exclusions),
        "seed_tickers": seed_tickers,
        "criteria": criteria,
        "semantic_query": analysis.get("semantic_query", "") or "",
        "exclusions": exclusions,
        "summary": analysis.get("summary", ""),
    }
    if ticker_note:
        final["seed_ticker_note"] = ticker_note
    if not final["summary"]:
        n_hard = sum(1 for c in criteria if c["type"] == "hard_constraint")
        n_soft = sum(1 for c in criteria if c["type"] == "soft_preference")
        n_qual = sum(1 for c in criteria if c["type"] == "qualitative")
        final["summary"] = (
            f"Parsed {len(criteria)} criteria ({n_hard} hard, {n_soft} soft, {n_qual} qualitative); "
            f"{len(seed_tickers)} seed ticker(s); {len(exclusions)} exclusion(s)."
        )
    return final


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Parse a raw investment mandate into a structured MandateSpec.")
    p.add_argument("--file", help="Path to a file containing the mandate text.")
    p.add_argument("--text", help="Mandate text passed inline.")
    skillkit.run(main, p)
