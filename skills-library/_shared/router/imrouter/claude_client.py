"""Client for the high-judgment model step, run through the Claude Code CLI.

This is the firm's reasoning/synthesis/drafting/judgment route. It does NOT call
the metered Anthropic API — instead it shells out to the `claude` CLI in
non-interactive *print* mode (`claude -p`), authenticated by the user's Max-plan
OAuth subscription. That keeps the heavy model on the flat-rate subscription
rather than pay-per-token API billing.

Key design points (see the handoff brief, fix #1):
  * Transport is a subprocess, not an HTTP POST. The prompt (filing text, full
    dossiers) is piped on **stdin**, never passed as an argv string, so it can't
    blow past arg-length limits.
  * Auth must stay on the subscription. If ``ANTHROPIC_API_KEY`` (or an auth
    token) is set in the environment, Claude Code would silently use the *API*
    (billed). We strip those from the child env so the call uses the Max login.
  * Structured output is requested in-prompt (emit one JSON object matching the
    schema) and parsed robustly with the shared ``_extract_json`` — print mode
    has no reliable forced-tool-use, so we never trust free text blindly.
  * ``available()`` detects a usable CLI (binary resolves on PATH or a known
    install location), NOT the presence of an env var. Auth itself is enforced
    at call time: a logged-out CLI makes ``complete()`` raise, and the engine
    fails loud for high-judgment routes rather than silently dropping to qwen.

One-time user setup:
    npm install -g @anthropic-ai/claude-code      # or the native installer
    claude login                                   # choose the Max subscription
    claude   then  /status                         # confirm "subscription" auth
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Reuse the exact same best-effort JSON extractor the local route uses, so the
# two transports parse model output identically.
from .ollama_client import _extract_json

# Pinned default. The brief pins claude-opus-4-8 as the firm's judgment model.
# `--model` accepts full ids (claude-opus-4-8) and aliases (opus/sonnet/haiku).
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

# Env vars that, if present, make Claude Code bill the API instead of the Max
# subscription. We strip these from the child env on every call.
_BILLING_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

# Common install locations to check when `claude` is not on a (GUI-thin) PATH.
_KNOWN_PATHS = (
    "~/.claude/local/claude",
    "~/.local/bin/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js",
)


def _resolve_cli() -> Optional[str]:
    """Locate the `claude` binary. Honors CLAUDE_CLI override, then PATH, then
    known install locations (GUI-launched parents often have a thin PATH)."""
    override = os.environ.get("CLAUDE_CLI")
    if override:
        return override if (Path(override).expanduser().exists()
                            or shutil.which(override)) else None
    found = shutil.which("claude")
    if found:
        return found
    for p in _KNOWN_PATHS:
        ep = Path(p).expanduser()
        if ep.exists():
            return str(ep)
    return None


def cli_path() -> Optional[str]:
    """Public accessor for diagnostics (e.g. a setup/doctor check)."""
    return _resolve_cli()


def available() -> bool:
    """True if a usable Claude Code CLI is resolvable.

    Detects the CLI, not an env var. Auth is *not* probed here (a live probe
    costs latency/tokens on every routing decision); instead a logged-out CLI
    surfaces as a loud error from ``complete()``, which the engine turns into a
    fail-loud ``_needs_model`` for high-judgment routes. Set IM_DISABLE_CLAUDE=1
    to force this off (useful for local qwen-only testing)."""
    if os.environ.get("IM_DISABLE_CLAUDE") == "1":
        return False
    return _resolve_cli() is not None


def _child_env() -> dict:
    """Env for the CLI subprocess with API-billing vars stripped so the call is
    served by the Max-plan subscription, not metered API access."""
    env = dict(os.environ)
    for k in _BILLING_ENV:
        env.pop(k, None)
    return env


def _schema_instruction(schema: dict) -> str:
    """Instruction appended to the prompt so print mode returns parseable JSON."""
    return (
        "\n\n---\nReturn ONLY a single JSON object that conforms to this JSON "
        "schema. Fill every required field with substantive content. Do not wrap "
        "it in markdown fences or add any prose before or after the object.\n"
        f"Schema:\n{json.dumps(schema)}"
    )


def complete(prompt: str, *, system: str = "", schema: Optional[dict] = None,
             max_tokens: int = 3000, model: Optional[str] = None,
             timeout: int = 240) -> dict:
    """Run one high-judgment completion through `claude -p`.

    With a schema, instructs the model to emit a single matching JSON object and
    parses it with the shared extractor. Returns the structured dict on success,
    or ``{"text": ...}`` when no schema / parsing fails (mirrors the local route).
    Raises ``RuntimeError`` on any transport/auth failure so the engine can fail
    loud — high-judgment routes must never silently degrade.

    ``max_tokens`` is accepted for interface parity with the local route; print
    mode has no stable max-tokens flag, so length is governed by the persona and
    prompt instead.
    """
    cli = _resolve_cli()
    if not cli:
        raise RuntimeError(
            "Claude Code CLI not found. Install it (npm i -g "
            "@anthropic-ai/claude-code) and run `claude login` with your Max plan."
        )

    user_text = prompt + (_schema_instruction(schema) if schema else "")

    cmd = [cli, "-p", "--output-format", "json",
           "--model", model or DEFAULT_MODEL,
           # Single-shot completion, not an agentic loop. Keep it a pure text turn.
           "--max-turns", "1"]
    if system:
        cmd += ["--append-system-prompt", system]
    # .js entrypoints (npm global) must be run via node.
    if cli.endswith(".js"):
        cmd = ["node", *cmd]

    try:
        proc = subprocess.run(
            cmd, input=user_text, env=_child_env(),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Claude CLI timed out after {timeout}s") from e
    except OSError as e:
        raise RuntimeError(f"Claude CLI failed to launch: {e}") from e

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:600]
        raise RuntimeError(
            f"Claude CLI exited {proc.returncode}: {err or 'no output'}. "
            "If this says you are not logged in, run `claude login` (Max plan); "
            "if it mentions an API key, unset ANTHROPIC_API_KEY."
        )

    # Print-mode JSON envelope: the assistant text is in `.result`.
    raw = proc.stdout.strip()
    try:
        envelope = json.loads(raw)
        result_text = envelope.get("result", "")
        if isinstance(envelope, dict) and envelope.get("is_error"):
            raise RuntimeError(f"Claude CLI reported an error: {result_text[:400]}")
    except json.JSONDecodeError:
        # Tolerate a CLI that printed bare text instead of the JSON envelope.
        result_text = raw

    if schema:
        parsed = _extract_json(result_text)
        return parsed if parsed is not None else {"text": result_text}
    parsed = _extract_json(result_text)
    return parsed if parsed is not None else {"text": result_text}
