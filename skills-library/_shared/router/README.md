# router (`imrouter`) — the routing mechanism

One engine, used by every system. **Policy is data** (`router-policy.yaml` per
system); the engine is identical everywhere. This is the guide's mechanism-vs-policy
split.

## What it does
`route(prompt, *, task, system, schema, max_tokens, policy)` takes a **task type**
(what kind of cognition is needed) and a **policy** (which route each task type
takes) and dispatches the model call to either:

- **local** → `qwen3.5:9b` via Ollama (`ollama_client`) — cheap, on-box, free.
- **claude** → the Claude API (`claude_client`) — heavy reasoning / synthesis /
  final drafting / judgment.

It returns a drop-in shape for the hybrid skills:
`{"_source": "ollama"|"api", "_route": ..., **fields}` on success, or
`{"_needs_model": true, ...}` if neither route is available.

## Default policy (firm-wide)
`classification · extraction · screening · summarization → local`;
`reasoning · synthesis · drafting · judgment → claude`.
Each system overrides via its `router-policy.yaml`.

## Graceful fallback (keyless-friendly)
- desired `claude` but no `ANTHROPIC_API_KEY` → fall back to qwen (so it runs free).
- desired `local` but Ollama down → fall back to Claude (if keyed).
- neither available → `_needs_model` envelope (caller still has the deterministic
  dossier).

## Auditability
Every routing decision (`task`, `desired`, `chosen`, `fell_back`, `model`, result)
is logged to `IM_ROUTER_LOG` (a system's `data/router_decisions.jsonl`) and stderr
— never stdout, which skills reserve for their JSON result.

## Policy resolution
`route(policy=None)` honors `IM_ROUTER_POLICY` (a path the orchestrator exports),
so every model call in a run — sub-skills included — obeys that system's policy
without threading it through every call.

## Files
- `engine.py` — `route()`, `DEFAULT_POLICY`, `load_policy()`, decision logging.
- `claude_client.py` — Anthropic Messages API (forced tool use for schemas).
- `ollama_client.py` — qwen3.5:9b via Ollama (JSON-schema constrained output).
- `orchestration.py` — helpers shared by orchestrators (`synthesize`, `write_output`,
  `audit`, defensive field readers).
