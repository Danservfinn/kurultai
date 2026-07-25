# Hulagu

Hulagu is a dedicated, deterministic Telegram job-search product. Task 0 freezes source contracts only; it starts no service and performs no live integration.

## Frozen implementation authority

- Approved plan path: `/Users/kublai/brain/docs/plans/2026-07-25-kublai-hulagu-job-search-agent-implementation-plan-v3.md`
- Approved plan SHA-256: `07e885de133fc742d33b8a2f8bae25ce25d1d0da5c5efbbaf0d56f38bb3a0ac9`
- Brain commit: `96e42974b105a60e401a0f7ab7f7843f466d12ed`
- Independent G-1 receipt: `/Users/kublai/brain/docs/plans/reviews/2026-07-25-kublai-hulagu-job-search-agent-v3-freeze-receipt.md`

The repository verifier confirms this existing G0 record; it cannot create or retroactively approve G0.

## G1 commands

```bash
cd /Users/kublai/kurultai/kurultai-repo/products/hulagu
uv sync --frozen
uv run pytest tests/contract tests/integration/test_vault_preflight.py -vv
uv run pytest tests/integration/test_container_mount_probe.py -vv
uv run hulagu-verify-plan-gate
uv run hulagu-doctor --config /absolute/path/to/owner-authorized-install-record.json
```

`hulagu-doctor` is observation-only and has no `--apply` option. The authorized JSON record must name the exact `/Volumes/KurultaiVault` mount, enrolled volume UUID, absolute container CLI and socket paths, and the owner-approved lowercase SHA-256 of the CLI executable (`approved_cli_sha256`). The doctor never searches `PATH` or executes the container CLI. At G1 it reports PostgreSQL and container runtime execution as `not_evaluated`. Tests use only synthetic temporary fixtures.

## Boundaries

No credentials, live customer data, private CVs, Telegram IDs, database dumps, generated wikis, or runtime installation records belong in this tree. G1 does not run PostgreSQL, a container, a provider, a bot, a vault write, a network request, or any runtime service mutation.
