"""Shared helpers for skill run.py scripts: argument parsing and JSON output.

Skills import only the `data` package, so this infrastructure lives here rather
than in a separate skills library. Every skill emits a single JSON object on
stdout containing named fields plus a `summary` prose string.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import traceback
from typing import Any, Callable, Optional

from . import config


def call_skill(name: str, args: list, timeout: int = 300) -> dict:
    """Run a leaf skill's run.py as a subprocess and return its parsed JSON.

    Used by a system's orchestrator to compose leaf skills (the deterministic
    equivalent of an agent delegating to a subagent). The skills directory is
    resolved from ``IM_SKILLS_DIR`` (an orchestrator sets this to its own
    ``.claude/skills`` so only the manifest-pinned, symlinked skills are visible);
    if unset, falls back to searching the canonical ``skills-library`` drawers.
    """
    skills_dir = os.environ.get("IM_SKILLS_DIR")
    run_py = None
    if skills_dir and os.path.exists(os.path.join(skills_dir, name, "run.py")):
        run_py = os.path.join(skills_dir, name, "run.py")
    else:
        lib = config.PROJECT_ROOT.parent.parent  # data-fetch -> _shared -> skills-library
        if lib.exists():
            for drawer in lib.iterdir():
                cand = drawer / name / "run.py"
                if cand.exists():
                    run_py = str(cand)
                    break
    if not run_py or not os.path.exists(run_py):
        return {"error": f"skill '{name}' not found (IM_SKILLS_DIR={skills_dir})",
                "skill": name}
    try:
        proc = subprocess.run(
            [sys.executable, str(run_py), *[str(a) for a in args]],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"skill '{name}' timed out", "skill": name}
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return {"error": (proc.stderr or proc.stdout or "no output")[:800], "skill": name}


def as_dict(row) -> dict:
    """Convert a sqlite3.Row (or None) to a plain dict."""
    return dict(row) if row is not None else None


def as_dicts(rows) -> list:
    """Convert an iterable of sqlite3.Row to a list of dicts."""
    return [dict(r) for r in rows]


def excerpt(text: str, max_chars: int = 60000, anchors: Optional[list] = None) -> str:
    """Trim long text for an LLM prompt. With `anchors` (regexes/strings), keep a
    window around each anchor; otherwise return the head."""
    if not text or len(text) <= max_chars:
        return text
    if not anchors:
        return text[:max_chars]
    per = max(2000, max_chars // len(anchors))
    windows = []
    for a in anchors:
        m = re.search(a, text, re.IGNORECASE)
        if m:
            windows.append(text[m.start(): m.start() + per])
    joined = "\n\n[...]\n\n".join(windows) if windows else text[:max_chars]
    return joined[:max_chars]


def model_output(analysis: dict, meta: dict) -> dict:
    """Standard shape for a hybrid 'model' skill's result.

    `analysis` is the return of data.llm.analyze(). If a key was present it holds
    the model's structured fields; otherwise it carries a `_needs_model` envelope
    (system/prompt/schema) for the orchestrating agent to fulfil. `meta` holds the
    deterministic fields the skill always knows (ticker, form, accession, ...).
    """
    out = dict(meta)
    if analysis.get("_needs_model"):
        out["_needs_model"] = True
        out["system"] = analysis.get("system", "")
        out["prompt"] = analysis.get("prompt", "")
        out["schema"] = analysis.get("schema")
        out.setdefault(
            "summary",
            "Model analysis pending: set ANTHROPIC_API_KEY to auto-fill, or have the "
            "calling agent read `prompt` and return JSON matching `schema`.",
        )
    else:
        for k, v in analysis.items():
            out[k] = v
    return out


def emit(result: dict) -> None:
    """Print a result object as JSON. Guarantees a `summary` field exists."""
    if "summary" not in result:
        result["summary"] = ""
    sys.stdout.write(json.dumps(result, indent=2, default=str))
    sys.stdout.write("\n")


def run(main: Callable[[Any], dict], parser) -> None:
    """Parse args, call `main(args)`, emit its dict. Any exception becomes a
    JSON error object so callers always get parseable output."""
    args = parser.parse_args()
    try:
        result = main(args)
    except Exception as e:  # noqa: BLE001 - we want every failure as JSON
        emit(
            {
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
                "summary": f"Skill failed: {e}",
            }
        )
        sys.exit(1)
    emit(result)
