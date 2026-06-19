# agents

Reusable **role definitions**. Each agent is a single `.md` file with: a mandate,
instructions, the skills it may use, and an input/output **contract only**.

Agents never hard-code handoffs — which agent runs before/after, and how data flows
between them, is **wiring the orchestrator owns**. That's what makes an agent
reusable across systems: `valuation-analyst` is the same role whether it's invoked
by the `valuation` system or as a step inside `due-diligence`.

| Agent | Role | Used by (systems) |
|---|---|---|
| screening-analyst | Source + rank ideas from a mandate | idea-sourcing |
| filing-analyst | Read one filing → Filing Intelligence Brief | filing-intelligence, due-diligence |
| valuation-analyst | Triangulate DCF / comps / scenarios | valuation, due-diligence |
| portfolio-risk-monitor | Triage a book vs limits + thesis KPIs | portfolio-monitoring |
| report-writer | Draft IC memos / investor letters | reporting |

A system pins the agents it uses in its `manifest.yaml`; `link.py` materializes them
as `.claude/agents/<name>.md` symlinks.
