# router (`imrouter`) — the routing mechanism

One engine, used by every system. **Policy is data** (`router-policy.yaml` per
system); the engine is identical everywhere. This is the guide's mechanism-vs-policy
split.

## What it does
`route(prompt, *, task, system, schema, max_tokens, policy)` takes a **task type**
(what kind of cognition is needed) and a **policy** (which route each task type
takes) and dispatches the model call to either:

- **local** → `qwen3.5:9b` via Ollama (`ollama_client`) — cheap, on-box, free.
- **claude** → Claude via the **Claude Code CLI** (`claude_client`) on the user's
  **Max-plan subscription** — heavy reasoning / synthesis / final drafting /
  judgment. Not the metered API: it shells out to `claude -p` with the prompt on
  stdin and `ANTHROPIC_API_KEY` stripped from the child env so billing stays on
  the subscription. One-time setup: `npm i -g @anthropic-ai/claude-code` then
  `claude login` (pick Max; confirm with `/status`).

It returns a drop-in shape for the hybrid skills:
`{"_source": "ollama"|"cli", "_route": ..., "_model": ..., "_degraded": ..., **fields}`
on success, or `{"_needs_model": true, ...}` if the route is unavailable.

## Default policy (firm-wide)
`classification · extraction · screening · summarization → local`;
`reasoning · synthesis · drafting · judgment → claude`.
Each system overrides via its `router-policy.yaml`.

## Fail-loud for the judgment layer (the important bit)
The four high-judgment tasks (`reasoning · synthesis · drafting · judgment`) must
run on Claude. If no Claude session is available they **fail loud** — the engine
returns `_needs_model` (deterministic dossier only, no narrative) and writes a
`WARNING` to stderr — rather than silently dropping to the 9B model and logging
`result:"ok"`. That silent degrade was the root cause of the "childish imitation"
output: a 9B model was writing every memo while the logs claimed success.

To let qwen stand in for the judgment layer (local testing only — quality is
capped, **not** analyst-grade), opt in explicitly:
`IM_ALLOW_DEGRADED=1` (env) or `allow_degraded: true` in a `router-policy.yaml`.
Such runs are flagged `_degraded: true` and surfaced in the report footer / CLI.

Low-tier tasks keep graceful fallback:
- desired `local` but Ollama down → fall back to Claude (if a session exists).
- neither available → `_needs_model` envelope (caller still has the dossier).

`IM_DISABLE_CLAUDE=1` forces the Claude route off (qwen-only).

## Auditability
Every routing decision (`task`, `desired`, `chosen`, `fell_back`, `degraded`,
`model`, result, and `level:"WARNING"` on a fail-loud/degrade) is logged to
`IM_ROUTER_LOG` (a system's `data/router_decisions.jsonl`) and stderr — never
stdout, which skills reserve for their JSON result.

## Policy resolution
`route(policy=None)` honors `IM_ROUTER_POLICY` (a path the orchestrator exports),
so every model call in a run — sub-skills included — obeys that system's policy
without threading it through every call.

## Files
- `engine.py` — `route()`, `DEFAULT_POLICY`, `HIGH_JUDGMENT`, fail-loud gating, logging.
- `claude_client.py` — Claude Code CLI subprocess (`claude -p`, subscription auth).
- `ollama_client.py` — qwen3.5:9b via Ollama (JSON-schema constrained output).
- `orchestration.py` — helpers shared by orchestrators (`synthesize`, `write_output`,
  `audit`, defensive field readers).
