# governance-audit — SCAFFOLD

Reads the immutable audit trail + saved theses/KPIs into a governance view (who did
what, which theses are live, which KPIs breached).

**Status:** the deterministic read is real; the governance-narrative synthesis is
**stubbed**. Promote it with an `orch.synthesize(task="reasoning", …)` step.

## Run (read only)
```bash
python ../../link.py governance-audit
python orchestrator.py --limit 20        # prints recent audit entries + a `stub: true` flag
```

Manifest: 3 skills (audit-logger, thesis-recorder, kpi-tracker). See `manifest.yaml`.
