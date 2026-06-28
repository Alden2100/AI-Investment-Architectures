"""Per-stage output cache key + get-or-compute wrapper for the Evidence Store.

The cache key is ``(company, stage, skill, inputs_hash)`` where ``inputs_hash`` is a
deterministic digest of *exactly the inputs a stage consumed*. Unchanged inputs => a
cache hit, so a re-run skips the stage (and any model call) for that company. Because
``store.get_cached_evidence`` keys on ``inputs_hash`` (not ``run_id``), a NEW run reuses
a PRIOR run's evidence whenever inputs match — true incremental re-runs.

IMPORTANT (concurrency): all SQLite access here uses the parent process's shared
connection, so ``get_or_compute`` must be called on the MAIN thread, never inside a
worker thread (mirror the imdata/articles.py rule). Worker threads should call
``inputs_hash`` only (pure) and let the orchestrator do the cache read/write.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Optional

from imdata import store


def inputs_hash(stage: int, mandate_hash: str, payload: dict) -> str:
    """Deterministic sha256 over (stage, mandate_hash, the stage's exact inputs).

    `payload` must contain only the inputs that actually drive the stage's output —
    e.g. the latest filing accession + the mandate's semantic query for text-similarity —
    so that an unchanged input set yields a stable hash and a cache hit.
    """
    blob = json.dumps(
        {"stage": int(stage), "mandate": mandate_hash, "inputs": payload},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_or_compute(
    *, run_id: str, company: str, stage: int, skill: str, mandate_hash: str,
    inputs: dict, compute: Callable[[], dict], citations: Optional[list] = None,
) -> dict:
    """Return cached evidence for these exact inputs, else run `compute()`, persist it,
    and return it. MAIN-THREAD ONLY (touches the shared SQLite connection)."""
    ih = inputs_hash(stage, mandate_hash, inputs)
    hit = store.get_cached_evidence(company, stage, skill, ih)
    if hit is not None:
        return hit
    out = compute() or {}
    store.put_evidence(run_id, company, stage, skill, out, citations or [], ih)
    out.setdefault("_cached", False)
    return out
