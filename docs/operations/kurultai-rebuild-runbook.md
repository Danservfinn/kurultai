# Kurultai rebuild runbook

Purpose: make this repository the non-secret rebuild contract for the current Hermes + Brain based Kurultai operating system.

This is not a secret backup. Live tokens, private chat targets, session logs, private indexes, credentials, and private operator memory stay outside Git.

## Rebuild target

A rebuilt host should provide these capabilities:

- Hermes runtime for the main chair/Kublai surface, with user-visible display name chosen at install time.
- Kurultai Hermes profile roster, including optional/internal agent lanes such as Batu, Coder, Subc, and non-routable Codex compatibility.
- Native Hermes Kanban with the expected schema.
- Brain wiki at the configured path, with QMD indexing.
- Cron jobs recreated from sanitized manifests after review.
- Skill inventory restored from source or backups.
- Local LLM lane configured for Tolui/lightweight triage with host-fit model selection.
- Telegram bot/gateway configured from local secrets after BotFather token handoff.
- Second Hermes gateway for Ogedei operations/intake configured from a separate local BotFather credential when available.
- macOS, Linux, and Windows-native installs supported by the fresh-install prompt.
- Receipts and recovery directories available.

## Repository surfaces

- `config/runtime-config/identity.yaml`: customizable public naming contract for the main chair/Kublai surface and gateway display names.
- `config/runtime-config/hermes.template.yaml`: sanitized Hermes runtime contract.
- `config/runtime-config/profiles.yaml`: Kurultai profiles and roles.
- `config/runtime-config/kurultai.yaml`: native coordination contract.
- `config/runtime-config/brain.yaml`: Brain wiki and index contract.
- `config/runtime-config/gateways.yaml`: Kublai and Ogedei gateway contract.
- `config/runtime-config/install-expert.yaml`: installing-agent expertise contract and required-reading manifest.
- `config/runtime-config/cron.manifest.json`: sanitized cron manifest.
- `config/runtime-config/skills.manifest.json`: skill names, relative paths, descriptions.
- `config/runtime-config/kanban.schema.json`: Kanban schema only.
- `config/runtime-config/brain.manifest.json`: Brain directory inventory only.
- `scripts/export_runtime_config_manifest.py`: refreshes cron manifest.
- `scripts/export_rebuild_manifests.py`: refreshes skills, Kanban schema, Brain inventory.
- `scripts/install_kurultai.py`: guided doctor/dry-run/apply/interactive installer that stages config, creates Brain scaffold, writes local identity/receipt files, and reconciles cron/skills without secrets.
- `scripts/bootstrap_kurultai_runtime.py`: lower-level compatibility helper for a review staging area.
- `docs/operations/fresh-install-agent-prompt.md`: pasteable Claude Code/Codex prompt for macOS, Linux, and Windows installs.
- `docs/operations/full-installation-checklist.md`: concrete completion definition and gateway install checklist for the installing agent.
- `agents/hermes-install-expert.md`: public operating prompt that makes the local coding agent an expert in installing and configuring Hermes/Kurultai from this repo.

## Secret boundary

Do not commit live Hermes config, Kanban databases, session JSON, private Brain indexes, telemetry DBs, API keys, OAuth data, cookies, private keys, account identifiers, raw transcript dumps, or private delivery targets.

Use placeholders and environment-variable names in repo files.

## Rebuild sequence

1. Install host prerequisites: Python, Git, Node/npm where needed, Hermes Agent CLI, QMD, and provider/tool CLIs.
2. Clone this repository.
3. Run `python3 scripts/install_kurultai.py --doctor`, then a personalized dry-run/apply or `--interactive` flow. Choose the main chair's user-visible display name during this step; the default internal profile id can remain `kublai`.
4. Review staged config under `~/.kurultai-install/staging/` and merge sanitized Hermes settings with local private values.
5. Recreate Hermes profiles from `profiles.yaml` and apply the generated main-chair display-name guidance from `identity.generated.yaml`.
6. Initialize native Hermes Kanban and compare its schema to `kanban.schema.json`.
7. Mount or clone the Brain wiki at the configured path and refresh QMD indexes.
8. Recreate only cron jobs from `cron.manifest.json` whose scripts exist locally; keep missing-script jobs as private follow-up and restore redacted delivery targets only from local private config.
9. Restore skills from source repositories or private skill backups using `skills.manifest.json` as the checklist; keep missing paths as explicit follow-up.
10. Configure the main chair gateway and, if the Ogedei bot credential is available, the separate Ogedei gateway from `gateways.yaml`.
11. Verify canaries: Hermes config check, profile startup, Kanban create/complete, Brain search/indexing, one safe cron run, main chair gateway reply, Ogedei gateway reply when configured, receipt write/index, and repo secret scan.

## Drift rule

When the live system gains a new non-secret architecture surface, update these manifests and this runbook. The live system may contain private state; the repo should contain the rebuildable contract.
