"""Thin client for the Claude API (Anthropic Messages endpoint).

Route for heavy reasoning, multi-document synthesis, final memo/letter drafting,
and judgment calls. Requires ANTHROPIC_API_KEY (loaded from .env). Schema-bound
calls use forced tool use so the model returns validated structured output.
"""
from __future__ import annotations

import json
import os
from typing import Optional

import requests

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(prompt: str, *, system: str = "", schema: Optional[dict] = None,
             max_tokens: int = 3000, model: Optional[str] = None,
             timeout: int = 180) -> dict:
    """Call Claude. With a schema, force tool use and return the tool input dict.

    Returns the structured dict on success (schema path) or {"text": ...}.
    Raises requests.HTTPError on transport failure so the engine can fall back.
    """
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body: dict = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if schema:
        body["tools"] = [{
            "name": "emit",
            "description": "Return the structured analysis result.",
            "input_schema": schema,
        }]
        body["tool_choice"] = {"type": "tool", "name": "emit"}

    resp = requests.post(API_URL, headers=headers, json=body, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    if schema:
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return dict(block["input"])
        return {"text": ""}
    text = "".join(b.get("text", "") for b in data.get("content", [])
                   if b.get("type") == "text")
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"text": text}
