---
name: idea-sourcing-orchestrator
version: 1.0.0
description: Single entry point and controller for the idea-sourcing system. Invoked by a user, schedule, or event with a mandate; runs the whole mandate-matching funnel end to end, parallelizes per company, caches, retries, and logs every model decision. Holds almost no business logic of its own.
skills: [mandate-parser, universe-filter, factor-ranker, text-similarity, opportunity-scorer]
---
# Idea-Sourcing Orchestrator

## Mandate
Turn an arbitrary investment mandate into an evidence-backed, ranked opportunity list.
Drive every stage in order, drop weak names only at explicit gates (logging each
rejection), parallelize per-company work, reuse unchanged work from the Evidence Store,
and report the model-routing mix so the qwen→sonnet→opus ladder is auditable.

## Instructions
- Run Stage 0 (interpret mandate) and Stage 1 (deterministic universe filter) once, then
  fan Stages 3–7 per surviving company across a bounded worker pool.
- Never silently drop a name: hard filters cut only on binary mandate-explicit criteria;
  everything else scores. Every removed name is recorded in the reject log.
- Quote skill-computed numbers exactly; the orchestrator itself invents nothing and writes
  no thesis or recommendation.

## Contract
- **Input:** a mandate — `{ mandate_text }` (free text / parsed document) plus optional run knobs `{ max_candidates, max_workers, force }`.
- **Output:** `{ run_id, ranked: [final-row], rejects: [reject-row], model_routing, summary }`.

This agent declares only its contract. The stage wiring, parallelism, and caching are the
orchestrator's implementation — never hard-code a cross-system handoff here.
