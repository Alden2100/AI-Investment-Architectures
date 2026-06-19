# due-diligence — SCAFFOLD

Deep single-name research dossier (fundamentals · moat · valuation · news · filing
read) feeding a full DD write-up.

**Status:** the deterministic data-gather is real and runnable; the final
multi-document synthesis is **stubbed**. Promote it by adding an
`orch.synthesize(task="synthesis", …)` step like the full systems do.

## Run (gather only)
```bash
python ../../link.py due-diligence
python orchestrator.py --ticker AAPL      # prints the DD dossier + a `stub: true` flag
```

Manifest: 8 skills + agents `filing-analyst`, `valuation-analyst`. See `manifest.yaml`.
