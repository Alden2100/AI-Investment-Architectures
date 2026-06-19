"""imrouter — the model-routing mechanism (engine) shared by every system.

Policy is data (per-system router-policy.yaml); the engine is identical everywhere.
"""
from .engine import route, load_policy, DEFAULT_POLICY  # noqa: F401
from . import claude_client, ollama_client  # noqa: F401

__all__ = ["route", "load_policy", "DEFAULT_POLICY", "claude_client", "ollama_client"]
