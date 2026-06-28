"""Stage 4 — mandate-scorecard driver (model, per company).

Pure: calls the `mandate-scorecard` leaf skill (a subprocess) for one ticker, so it is
safe to run inside a worker thread in the Phase-3 fan-out. Returns the scorecard dict.
"""
from __future__ import annotations

import json
import os
import tempfile

from imdata import skillkit


def run(mandate: dict, ticker: str, *, factor_score=None, text_score=None) -> dict:
    fd, path = tempfile.mkstemp(suffix=".json", prefix="stage4_")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(mandate, fh, default=str)
        args = ["--ticker", ticker, "--mandate-file", path]
        if factor_score is not None:
            args += ["--factor-score", factor_score]
        if text_score is not None:
            args += ["--text-score", text_score]
        out = skillkit.call_skill("mandate-scorecard", args)
    finally:
        os.unlink(path)
    if out.get("error"):
        raise RuntimeError(f"mandate-scorecard failed for {ticker}: {out['error']}")
    return out
