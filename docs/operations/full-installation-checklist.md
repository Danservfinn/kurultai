# Full Kurultai installation checklist

This checklist is for the local coding agent performing a fresh install from this repository. It complements `fresh-install-agent-prompt.md` with a concrete end-to-end completion definition.

The agent must do the work, verify it, and leave receipts. Do not stop at advice unless a human-only secret or permission is missing.

## Completion definition

A host is fully installed when all of these are true:

1. Hermes Agent is installed and `hermes doctor` / `hermes config check` pass or have documented non-blocking warnings.
2. Frontier runtime is configured for `openai-codex` / `gpt-5.5`, 1M context, and compression threshold `0.25`.
3. The Brain directory exists, contains the public schema/template files, and can accept a receipt write.
4. Kurultai profiles exist: `kublai`, `batu`, `chagatai`, `jochi`, `temujin`, `coder`, `mongke`, `ogedei`, `subc`, `tolui`, and non-routable `codex` compatibility if supported by the installed Hermes version.
5. Native Hermes Kanban is initialized and a harmless create/complete/cancel smoke test has run.
6. Skills are installed or reconciled against `config/runtime-config/skills.manifest.json`; missing private skills are listed as private follow-up rather than silently skipped.
7. Cron jobs are recreated from `config/runtime-config/cron.manifest.json` with redacted delivery targets restored only from local private configuration.
8. The local LLM lane for Tolui is installed or explicitly deferred with hardware reason and a selected fallback plan.
9. Two Hermes Telegram gateways are configured when bot credentials are supplied:
   - Kublai primary operator gateway.
   - Ogedei dedicated operations/intake gateway.
10. Verification receipts are written outside git and contain no secrets.

## Gateway installation contract

Use `config/runtime-config/gateways.yaml` as the non-secret contract.

### Kublai gateway

- Profile: `kublai`.
- Telegram bot: separate BotFather bot for the chair/operator interface.
- Secret environment variable name: `KURULTAI_KUBLAI_TELEGRAM_BOT_TOKEN`.
- Service name suggestion: `hermes-gateway-kublai`.
- Foreground smoke command shape: `hermes --profile kublai gateway run`.

### Ogedei gateway

- Profile: `ogedei`.
- Telegram bot: separate BotFather bot for operations/intake.
- Secret environment variable name: `KURULTAI_OGEDEI_TELEGRAM_BOT_TOKEN`.
- Service name suggestion: `hermes-gateway-ogedei`.
- Foreground smoke command shape: `hermes --profile ogedei gateway run`.

Do not reuse one Telegram bot token for both gateways. Do not configure the Ogedei bot in the root/default gateway and the profile gateway at the same time. If both are present, preserve a backup, remove the duplicate from the wrong scope, and verify both gateways independently.

## OS service guidance

### macOS

Prefer the Hermes-provided gateway service command if available. If not available, create LaunchAgents only after foreground smoke tests pass.

For a profile-specific LaunchAgent, record the exact plist path and include:

- profile name,
- Hermes executable path,
- working directory,
- environment file location,
- stdout/stderr log paths under the local Hermes home.

Never include bot credentials directly in plist files.

### Linux

Prefer systemd user services after foreground smoke tests pass. Put secrets in the user's local Hermes secret store or an environment file outside git. Record:

- unit name,
- `ExecStart`,
- environment file path,
- `systemctl --user status` result,
- log command for follow-up.

### Windows

Start with a foreground PowerShell smoke test. Only after it works, create a Scheduled Task, NSSM service, or WinSW service. Store secrets outside the repository, preferably in the user environment or a local secret store. Record the service name and command.

## Agent execution order

1. Read `config/runtime-config/*.yaml`, `*.json`, this checklist, and `fresh-install-agent-prompt.md`.
2. Detect host OS and write a receipt path outside git.
3. Install prerequisites and Hermes.
4. Configure frontier model and compression.
5. Create Brain directories and indexes.
6. Create profiles and role templates.
7. Install/reconcile skills.
8. Initialize Kanban and receipts.
9. Configure local LLM lane.
10. Recreate cron jobs conservatively; keep delivery local until Telegram targets are verified.
11. Configure Kublai gateway if the Kublai bot credential is available.
12. Configure Ogedei gateway if the Ogedei bot credential is available.
13. Run all canaries and write the final receipt.

## Required verification commands

Use the installed Hermes version's exact command spelling where it differs. At minimum run equivalent checks for:

```bash
hermes --version
hermes doctor
hermes config check
hermes profile list
hermes skills list
hermes cron list --all
hermes --profile kublai config check
hermes --profile ogedei config check
```

Then verify both gateways separately when configured:

```bash
hermes --profile kublai gateway status
hermes --profile ogedei gateway status
```

If status commands are unavailable, use foreground gateway runs plus Telegram `/status` or `/help` replies as the proof.

## Human-only gates

Stop and ask only for:

- BotFather tokens or authorization to create bots.
- OAuth/browser logins.
- Payment, production deployment, DNS, public webhook, or security-policy changes.
- Deleting or overwriting existing private Hermes/Brain data.

Everything else should be performed and verified by the installing agent.
