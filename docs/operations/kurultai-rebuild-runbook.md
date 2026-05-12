# Kurultai rebuild runbook

Purpose: make this repository the non-secret rebuild contract for the current Hermes + Brain based Kurultai operating system.

This is not a secret backup. Live tokens, private chat targets, session logs, private indexes, credentials, and private operator memory stay outside Git.

## Rebuild target

A rebuilt host should provide these capabilities:

- Hermes runtime for Kublai.
- Kurultai Hermes profile roster.
- Native Hermes Kanban with the expected schema.
- Brain wiki at the configured path, with QMD indexing.
- Cron jobs recreated from sanitized manifests after review.
- Skill inventory restored from source or backups.
- Local LLM lane configured for Tolui/lightweight triage with host-fit model selection.
- Telegram bot/gateway configured from local secrets after BotFather token handoff.
- macOS, Linux, and Windows-native installs supported by the fresh-install prompt.
- Receipts and recovery directories available.

## Repository surfaces

- `config/runtime-config/hermes.template.yaml`: sanitized Hermes runtime contract.
- `config/runtime-config/profiles.yaml`: Kurultai profiles and roles.
- `config/runtime-config/kurultai.yaml`: native coordination contract.
- `config/runtime-config/brain.yaml`: Brain wiki and index contract.
- `config/runtime-config/cron.manifest.json`: sanitized cron manifest.
- `config/runtime-config/skills.manifest.json`: skill names, relative paths, descriptions.
- `config/runtime-config/kanban.schema.json`: Kanban schema only.
- `config/runtime-config/brain.manifest.json`: Brain directory inventory only.
- `scripts/export_runtime_config_manifest.py`: refreshes cron manifest.
- `scripts/export_rebuild_manifests.py`: refreshes skills, Kanban schema, Brain inventory.
- `scripts/bootstrap_kurultai_runtime.py`: creates a review staging area for a rebuilt host.
- `docs/operations/fresh-install-agent-prompt.md`: pasteable Claude Code/Codex prompt for macOS, Linux, and Windows installs.

## Secret boundary

Do not commit live Hermes config, Kanban databases, session JSON, private Brain indexes, telemetry DBs, API keys, OAuth data, cookies, private keys, account identifiers, raw transcript dumps, or private delivery targets.

Use placeholders and environment-variable names in repo files.

## Rebuild sequence

1. Install host prerequisites: Python, Git, Node/npm where needed, Hermes Agent CLI, QMD, and provider/tool CLIs.
2. Clone this repository.
3. Run the bootstrap script in dry-run mode, then normal mode, to create `~/.kurultai-rebuild-staging/`.
4. Restore Hermes configuration from the sanitized template and local private values.
5. Recreate Hermes profiles from `profiles.yaml`.
6. Initialize native Hermes Kanban and compare its schema to `kanban.schema.json`.
7. Mount or clone the Brain wiki at the configured path and refresh QMD indexes.
8. Recreate cron jobs from `cron.manifest.json`; manually restore redacted delivery targets.
9. Restore skills from source repositories or private skill backups using `skills.manifest.json` as the checklist.
10. Verify canaries: Hermes config check, profile startup, Kanban create/complete, Brain search/indexing, one safe cron run, receipt write/index, and repo secret scan.

## Drift rule

When the live system gains a new non-secret architecture surface, update these manifests and this runbook. The live system may contain private state; the repo should contain the rebuildable contract.
