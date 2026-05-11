# Runtime configuration home

This folder is the repository home for sanitized Hermes, Kurultai, and Brain runtime configuration.

It contains templates, rebuild manifests, and schema contracts, not live private runtime files.

Live sources:

- Hermes: `~/.hermes/config.yaml`, profile configs, cron jobs, sessions, Kanban DB.
- Kurultai: native Hermes profiles, native Kanban, receipts, recovery workflows.
- Brain: `/Users/kublai/brain`, QMD indexes, public gateway contract.

Committed files:

- `hermes.template.yaml`: sanitized Hermes runtime contract.
- `profiles.yaml`: Kurultai profile roster and model/provider map.
- `kurultai.yaml`: coordination contract.
- `brain.yaml`: Brain root, index, and gateway contract.
- `cron.manifest.json`: sanitized cron jobs.
- `skills.manifest.json`: skill inventory without skill bodies.
- `kanban.schema.json`: native Kanban schema without task data.
- `brain.manifest.json`: Brain directory inventory without note contents.

Refresh manifests from a live host with:

- `python3 scripts/export_runtime_config_manifest.py`
- `python3 scripts/export_rebuild_manifests.py`

See `docs/operations/kurultai-rebuild-runbook.md` for the full rebuild procedure.
