"""Stage 2 — quantitative pre-rank driver (deterministic). SCORES, NEVER CUTS.

Scores survivors on soft_preference numeric criteria from cheap snapshot metrics
(size / liquidity / industry-fit). Richer fundamentals-based factors are evaluated
per-name in Stage 4 (mandate-scorecard).
"""
from __future__ import annotations

import json
import os
import tempfile

from imdata import skillkit


def _tmp_json(obj) -> str:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="stage2_")
    with os.fdopen(fd, "w") as fh:
        json.dump(obj, fh, default=str)
    return path


def run(mandate: dict, survivors: list) -> dict:
    mpath = _tmp_json(mandate)
    spath = _tmp_json(survivors)
    try:
        out = skillkit.call_skill(
            "factor-ranker", ["--mandate-file", mpath, "--survivors-file", spath])
    finally:
        os.unlink(mpath)
        os.unlink(spath)
    if out.get("error"):
        raise RuntimeError(f"factor-ranker failed: {out['error']}")
    out.setdefault("ranked", [])
    return out
