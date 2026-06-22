# Full Kurultai installation checklist

This checklist is for the local coding agent performing a fresh install from this repository. It complements `fresh-install-agent-prompt.md` with a concrete end-to-end completion definition.

The agent must do the work, verify it, and leave receipts. Do not stop at advice unless a human-only secret or permission is missing.

Before acting, the agent must read and adopt `agents/hermes-install-expert.md`. That prompt is the public expertise pack for Hermes/Kurultai self-installation.

Preferred installer implementation prompt:

```text
docs/operations/interactive-installer-implementation-prompt.md
```

Preferred guided installer command surface:

```bash
python3 scripts/install_kurultai.py --doctor
python3 scripts/install_kurultai.py --dry-run --chair-display-name "Sophia's chosen name"
python3 scripts/install_kurultai.py --interactive
python3 scripts/install_kurultai.py --resume
python3 scripts/install_kurultai.py --write-plan
```

Use `scripts/bootstrap_kurultai_runtime.py` only as a lower-level staging helper or compatibility fallback.

## Completion definition

A host is fully installed when all of these are true:

1. Hermes Agent is installed and `hermes doctor` / `hermes config check` pass or have documented non-blocking warnings.
2. Frontier runtime is configured for `openai-codex` / `gpt-5.5`, 1M context, and compression threshold `0.25`.
3. The Brain directory exists, contains the public schema/template files, and can accept a receipt write.
4. The main chair profile exists with the operator's chosen user-visible name applied from `config/runtime-config/identity.yaml` / local `identity.generated.yaml`; the default stable internal profile id is `kublai` unless explicitly renamed.
5. Kurultai profiles exist: `kublai`, `batu`, `chagatai`, `jochi`, `temujin`, `coder`, `mongke`, `ogedei`, `subc`, `tolui`, and non-routable `codex` compatibility if supported by the installed Hermes version.
6. Native Hermes Kanban is initialized and a harmless create/complete/cancel smoke test has run.
7. Skills are installed or reconciled against `config/runtime-config/skills.manifest.json`; missing private skills are listed as private follow-up rather than silently skipped.
8. Cron jobs are recreated from `config/runtime-config/cron.manifest.json` only when any referenced scripts exist locally; missing-script jobs are listed as private follow-up rather than created broken.
9. The local LLM lane for Tolui is installed or explicitly deferred with hardware reason and a selected fallback plan.
10. Two Hermes Telegram gateways are configured when bot credentials are supplied:
    - Main chair/Kublai primary operator gateway, using the operator's chosen display/bot name.
    - Ogedei dedicated operations/intake gateway.
11. Verification receipts are written outside git and contain no secrets.

## Gateway installation contract

Use `config/runtime-config/gateways.yaml` and `config/runtime-config/identity.yaml` as the non-secret contract. The default internal chair profile id is `kublai`, but the user-visible chair name and BotFather display name are installer inputs.

### Main chair/Kublai gateway

- Profile: `kublai` by default, or the explicitly selected chair profile id if the operator intentionally renames it.
- User-visible attribution: chosen through `scripts/install_kurultai.py --chair-display-name ...` or `--interactive`.
- Telegram bot: separate BotFather bot for the chair/operator interface.
- Secret environment variable name: generated from the selected profile id, default `KURULTAI_KUBLAI_TELEGRAM_BOT_TOKEN`.
- Service name suggestion: `hermes-gateway-kublai` unless the profile id is renamed.
- Foreground smoke command shape: `hermes --profile kublai gateway run` or the selected profile id equivalent.

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

1. Read `agents/hermes-install-expert.md`, `config/runtime-config/install-expert.yaml`, `config/runtime-config/identity.yaml`, `config/runtime-config/*.yaml`, `*.json`, this checklist, and `fresh-install-agent-prompt.md`.
2. Detect host OS and write a receipt path outside git.
3. Ask or accept CLI args for the main chair's user-visible display name, BotFather display name, operator name, and system name; write only non-secret generated identity files outside git.
4. Install prerequisites and Hermes.
5. Configure frontier model and compression.
6. Create Brain directories and indexes.
7. Create profiles and role templates.
8. Install/reconcile skills.
9. Initialize Kanban and receipts.
10. Configure local LLM lane.
11. Recreate cron jobs conservatively; keep delivery local until Telegram targets are verified, and do not create jobs whose scripts are missing.
12. Configure the main chair gateway if the chair bot credential is available.
13. Configure Ogedei gateway if the Ogedei bot credential is available.
14. Run all canaries and write the final receipt.

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
