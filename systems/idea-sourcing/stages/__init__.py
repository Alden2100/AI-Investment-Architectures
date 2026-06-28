"""Thin per-stage drivers the idea-sourcing orchestrator composes.

Each stage driver owns its per-stage cache logic (see ``_cache``) and calls leaf
skills via ``imdata.skillkit.call_skill``. Drivers run in-process (the orchestrator
imports them); the skills they call are subprocesses.
"""
