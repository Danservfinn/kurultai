# Contributing to Kurultai

Kurultai is open source under the MIT License. Contributions are welcome when they preserve the project's safety boundary and rebuildability.

## Core rules

1. **Do not commit secrets.** Keep API keys, OAuth tokens, cookies, Telegram bot tokens, private chat IDs, live session dumps, live Kanban DBs, private Brain indexes, and local credentials out of git.
2. **Use sanitized templates and manifests.** Runtime configuration belongs in `config/runtime-config/` as placeholders and schema contracts, not as private machine snapshots.
3. **Respect the current substrate.** Kurultai currently coordinates through native Hermes profiles, native Hermes Kanban, Brain receipts, skills, cron, and gateway surfaces. Do not introduce a replacement scheduler or second task source of truth without an explicit architecture decision.
4. **Keep changes reversible.** Runtime-changing work should include backup/rollback notes, tests, and receipts where appropriate.
5. **Update docs and diagrams.** If architecture changes, update `README.md`, `docs/assets/readme/`, and the relevant runbooks.

## Development checks

Run targeted tests for the area you touch. When in doubt:

```bash
python3 -m pytest tests/ -q
```

For rebuild-contract changes, also run:

```bash
python3 scripts/bootstrap_kurultai_runtime.py --dry-run
python3 scripts/export_rebuild_manifests.py
```

## Security reports

Please do not open public issues containing secrets or exploit details. File a minimal report that describes the affected surface and coordinate privately for sensitive reproduction details.
