"""Thin client for the local qwen3.5:9b model served by Ollama.

Route for cheap, high-volume work (classification, extraction, screening,
summarization). Free and local — no API key, nothing leaves the machine.
The model id is pinned to qwen3.5:9b; override only via OLLAMA_MODEL.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import requests

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")


def available(timeout: float = 2.0) -> bool:
    """True if Ollama is reachable and the pinned model is present."""
    try:
        r = requests.get(f"{HOST}/api/tags", timeout=timeout)
        r.raise_for_status()
        names = {m.get("name") for m in r.json().get("models", [])}
        return MODEL in names or any(n.split(":")[0] == MODEL.split(":")[0] for n in names)
    except Exception:
        return False


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort: pull the first JSON object out of a model response."""
    if not text:
        return None
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (ValueError, TypeError):
            return None
    return None


def complete(prompt: str, *, system: str = "", schema: Optional[dict] = None,
             max_tokens: int = 3000, temperature: float = 0.2,
             timeout: int = 300) -> dict:
    """Call qwen3.5:9b. With a schema, constrain output to JSON and parse it.

    Returns the structured dict on success, or {"text": ...} when no schema /
    parsing fails. Raises on transport errors so the engine can fall back.
    """
    messages = []
    sys_text = system
    if schema:
        # Nudge the 9B model to emit only the JSON object the schema describes;
        # `format` constrains the grammar, this keeps it from adding prose/fields.
        nudge = ("Respond with a SINGLE JSON object that matches the requested "
                 "schema. Fill every required field. Output JSON only — no prose.")
        sys_text = (system + "\n\n" + nudge) if system else nudge
    if sys_text:
        messages.append({"role": "system", "content": sys_text})
    messages.append({"role": "user", "content": prompt})
    body = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    if schema:
        body["format"] = schema  # Ollama structured outputs (JSON schema)
    # qwen3.5 is a thinking model; disable for low-latency structured work.
    body["think"] = False
    try:
        resp = requests.post(f"{HOST}/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError:
        body.pop("think", None)  # older Ollama may reject unknown field
        resp = requests.post(f"{HOST}/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
    content = resp.json().get("message", {}).get("content", "")
    if schema:
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
        return {"text": content}
    parsed = _extract_json(content)
    return parsed if parsed is not None else {"text": content}
