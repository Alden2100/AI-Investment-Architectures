"""Stage 1 — universe-validator/opportunity-engine driver (deterministic).

Applies ONLY hard_constraint criteria against the company_metrics snapshot and returns
survivors + a reject log. NO SILENT DROPS: soft/qualitative criteria never cut here.
"""
from __future__ import annotations

import json
import os
import tempfile

from imdata import skillkit


def run(mandate: dict) -> dict:
    # The leaf skill reads a MandateSpec file; write it to a temp path.
    fd, path = tempfile.mkstemp(suffix=".json", prefix="mandate_")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(mandate, fh, default=str)
        out = skillkit.call_skill("universe-filter", ["--mandate-file", path])
    finally:
        os.unlink(path)
    if out.get("error"):
        raise RuntimeError(f"universe-filter failed: {out['error']}")
    out.setdefault("survivors", [])
    out.setdefault("rejects", [])
    return out
