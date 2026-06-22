# Copy-paste prompt: implement the Kurultai interactive installer

Paste the prompt below into Claude Code, Codex, or another local coding agent from the root of this repository. It is designed to make the agent implement, validate, and document an interactive installer/doctor for Kurultai.

Secret boundary: the implementation must never require or store real secrets in git. The installer may guide the user through authentication and write secrets only to the user's local Hermes secret store, environment file, OS credential store, or profile-local untracked config.

Compatibility target: macOS, Linux, and Windows-native PowerShell. Do not require WSL2 unless the user explicitly requests a Linux runtime.

```text
You are implementing the Kurultai interactive installer in this repository. Do the work, not just a plan. Inspect the existing repository first, then add code, docs, tests, and verification receipts.

Goal:
Create a guided, resumable, cross-platform installer/doctor that helps a new user install and authenticate everything needed for a fully functional Kurultai system across macOS, Linux, and Windows-native PowerShell, while preserving the repository's public/secret boundary. The installer must also let the operator choose the user-visible name attributed to the main chair/Kublai surface while keeping `kublai` as the default stable internal profile id unless explicitly renamed.

Repository contract to honor:
- This repo is a sanitized rebuild contract, not a private backup.
- Existing bootstrap script: scripts/bootstrap_kurultai_runtime.py.
- Existing install prompt: docs/operations/fresh-install-agent-prompt.md.
- Existing full checklist: docs/operations/full-installation-checklist.md.
- Install expert prompt: agents/hermes-install-expert.md.
- Install expert manifest: config/runtime-config/install-expert.yaml.
- Runtime manifests: config/runtime-config/.
- Public/private boundary: never commit secrets, tokens, OAuth files, cookies, session dumps, private chat IDs, private Brain indexes, API keys, or generated private runtime state.
- Kurultai coordination must remain native Hermes profiles + native Hermes Kanban + Brain receipts + cron. Do not add a replacement scheduler or parallel task source of truth.

Deliverables:
1. Add scripts/install_kurultai.py.
2. Add or update tests for the installer.
3. Update README.md and docs/operations/full-installation-checklist.md to reference the new installer.
4. Keep docs/operations/fresh-install-agent-prompt.md consistent with the new installer.
5. Add any small fixtures/templates needed for tests, but do not add secrets.
6. Run validation and fix failures before stopping.

Installer command surface:
Implement these modes:
- python3 scripts/install_kurultai.py --doctor
- python3 scripts/install_kurultai.py --dry-run
- python3 scripts/install_kurultai.py --interactive
- python3 scripts/install_kurultai.py --resume
- python3 scripts/install_kurultai.py --write-plan

Mode semantics:
- --doctor: read-only detection and readiness report; no mutations.
- --dry-run: show actions that would be taken; no mutations.
- --interactive: guided install with human prompts at auth/permission gates.
- --resume: continue from a local state file after interruption.
- --write-plan: write a local install plan/receipt without making changes.

Implementation requirements:
- Use Python standard library only unless the repository already declares a dependency.
- Be Windows-friendly: use pathlib, platform, shutil.which, subprocess with list args, and avoid Bash-only assumptions.
- Keep operations idempotent. Re-running should not duplicate profiles, cron jobs, files, or receipt entries.
- Preserve existing user data. Never blindly overwrite an existing Hermes home, Brain root, profile config, cron file, or gateway config.
- Before any potentially destructive operation, create a backup or stop and ask.
- Keep all generated install receipts outside git, defaulting to:
  - POSIX: ~/.kurultai-install/receipts/
  - Windows: %USERPROFILE%\.kurultai-install\receipts\
- Keep installer state outside git, defaulting to:
  - POSIX: ~/.kurultai-install/state.json
  - Windows: %USERPROFILE%\.kurultai-install\state.json
- Redact secrets in logs and receipts. Redact obvious token/password/API-key patterns and any values entered through secret prompts.

Installer phases:

Phase 0 — repository and platform discovery
- Verify current directory is the Kurultai repo root or locate it from the script path.
- Read required files and fail with a helpful message if missing:
  - agents/hermes-install-expert.md
  - config/runtime-config/install-expert.yaml
  - config/runtime-config/identity.yaml
  - config/runtime-config/hermes.template.yaml
  - config/runtime-config/profiles.yaml
  - config/runtime-config/kurultai.yaml
  - config/runtime-config/brain.yaml
  - config/runtime-config/gateways.yaml
  - config/runtime-config/cron.manifest.json
  - config/runtime-config/skills.manifest.json
  - config/runtime-config/kanban.schema.json
  - config/runtime-config/brain.manifest.json
  - docs/operations/full-installation-checklist.md
  - docs/operations/fresh-install-agent-prompt.md
- Detect OS, shell, CPU architecture, RAM if feasible, Python executable/version, Git, Node/npm, package manager, and whether Hermes is already installed.
- Write a redacted local receipt.

Phase 1 — identity and naming
- Read `config/runtime-config/identity.yaml`.
- Prompt for or accept CLI flags for operator name, system name, main chair display name, and main chair BotFather display name.
- Keep the internal chair profile id `kublai` unless the operator explicitly asks to rename the profile id and confirms config propagation.
- Write a local generated identity file outside git or in the local staging directory; do not write secrets.
- Use the chosen display name in generated next-step docs, profile description guidance, BotFather instructions, receipts, and final reports.

Phase 2 — prerequisite guidance
- Detect missing prerequisites:
  - git
  - Python 3.12+ or best available Python 3
  - node/npm
  - jq
  - ripgrep
  - sqlite/sqlite3
  - curl
  - uv or pipx when available
- For macOS, prefer Homebrew commands.
- For Linux, detect apt/dnf/pacman/zypper and print exact commands.
- For Windows, prefer winget and PowerShell commands.
- In --interactive mode, ask before running package-manager install commands.
- In --doctor/--dry-run, only report commands.

Phase 3 — Hermes Agent installation and verification
- Detect hermes with shutil.which("hermes").
- If absent, present the official install path from Hermes docs or the repository's existing install prompt.
- In --interactive mode, ask before running a network installer.
- Verify with equivalent commands when available:
  - hermes --version
  - hermes doctor
  - hermes config path
  - hermes config check
- Record pass/fail/non-blocking warnings.

Phase 4 — frontier provider authentication/configuration
- Guide OpenAI Codex OAuth / provider setup.
- Do not ask the user to paste secrets into tracked files.
- Prefer Hermes commands when available; otherwise print exact manual steps.
- Verify or instruct setting:
  - model.provider: openai-codex
  - model.default: gpt-5.5
  - model.context_length: 1000000
  - compression.enabled: true
  - compression.threshold: 0.25
- Run hermes config check after changes when Hermes is available.

Phase 5 — Brain setup
- Default Brain root:
  - POSIX: ~/brain
  - Windows: %USERPROFILE%\brain
- Create or verify the required public-safe directories only when not in --doctor/--dry-run:
  - queue
  - generated
  - receipts
  - docs/plans
  - operations
  - analyses
  - content
  - content/artifacts
- Copy public templates where appropriate without overwriting existing user pages.
- If qmd is installed, offer qmd update/embed; otherwise mark qmd as optional pending.
- Verify a harmless receipt write outside git or under the Brain receipts directory if appropriate.

Phase 6 — apply sanitized runtime manifests
- Prefer scripts/install_kurultai.py for doctor/dry-run/apply/interactive flows.
- Reuse or call scripts/bootstrap_kurultai_runtime.py only for lower-level staging compatibility checks.
- Stage sanitized config under ~/.kurultai-install/staging or Windows equivalent.
- Do not blindly apply staged config over live private config.
- Provide a merge checklist for local private config.

Phase 7 — profiles
- Ensure or guide creation of profiles:
  - kublai
  - batu
  - chagatai
  - jochi
  - temujin
  - coder
  - mongke
  - ogedei
  - subc
  - tolui
  - codex compatibility profile if supported
- Use Hermes profile commands when available.
- Preserve existing profile-local config and secrets.
- Verify profile list and profile config checks where available.

Phase 8 — local LLM lane
- Detect feasible local model runtime:
  - Ollama
  - llama.cpp / llama-server
  - other local OpenAI-compatible endpoint if already present
- Pick a safe default by hardware:
  - 32GB+ RAM: 9B Qwen/Gemma-class quantized model if feasible.
  - 16GB RAM: 7B/9B low quantization only if feasible; otherwise 3B/4B.
  - <16GB RAM: 3B/4B triage-only.
- Configure Tolui as local lightweight triage/summarization/classification only until tool-calling is verified.
- Run a one-sentence local smoke test if runtime is installed.

Phase 9 — skills
- Read config/runtime-config/skills.manifest.json.
- Reconcile installed skills with the manifest.
- Clearly list missing private skills as follow-up; do not pretend they installed.
- Do not copy private skills into git.

Phase 10 — native Kanban
- Initialize/verify native Hermes Kanban where supported.
- Run harmless create/complete/cancel smoke test if Hermes commands are available.
- Record only redacted/non-secret task evidence in the local receipt.

Phase 11 — cron
- Read config/runtime-config/cron.manifest.json.
- Recreate or print creation commands for jobs conservatively.
- Do not create jobs whose referenced script is missing; record those as private follow-up in cron reconciliation.
- Default delivery to local until Telegram is configured.
- Preserve script-only/no_agent jobs as script-only to avoid token waste.
- Do not create high-frequency LLM cron jobs unless the manifest explicitly requires it and the user approves.
- Verify with hermes cron list --all when available.

Phase 12 — Telegram dual gateway setup
- Use config/runtime-config/gateways.yaml as the non-secret contract.
- Guide the user through BotFather for two separate bots:
  - Main chair/Kublai primary operator gateway, using the chosen user-visible display and bot name.
  - Ogedei operations/intake gateway.
- Store bot tokens only in local secret stores / untracked env files / profile-local secret storage.
- Never print tokens back to the terminal or receipt.
- Prefer long polling for fresh installs.
- Start with foreground gateway smoke tests before installing services.
- Verify each gateway independently with /start, /sethome if supported, /help or /status, and identity-specific response.
- Ensure the root/default gateway does not also own the Ogedei token if a profile-local Ogedei gateway is installed.

Phase 13 — optional integrations
- Make integrations modular and explicitly gated:
  - GitHub
  - Google Workspace/Gmail
  - X/Grok/xurl
  - Readwise
  - Stripe
  - Airtable
  - Apify
  - Telegram groups/channels
  - local dashboards/cloudflared if present
- For each integration, implement detect -> explain credential -> authenticate/guidance -> smoke test -> receipt.
- Do not require optional integrations for the base install to pass.

Phase 14 — final report
- Print a concise final report with pass/fail/pending statuses:
  - OS/platform
  - Hermes install
  - provider/model
  - Brain
  - profiles
  - skills
  - Kanban
  - cron
  - local LLM/Tolui
  - Kublai Telegram gateway
  - Ogedei Telegram gateway
  - Buildroom/Dreamer/auto-research surfaces installed or pending
  - optional integrations
  - receipt path
- Save the same report to the local receipt.

Testing requirements:
- Add tests that run without network access and without Hermes installed.
- Mock subprocess calls and environment detection.
- Test at least:
  - command-line argument parsing
  - platform detection/report object shape
  - secret redaction
  - receipt path/state path resolution
  - dry-run makes no filesystem changes outside a temp dir
  - required repository files are checked
  - missing command detection works
  - Windows path handling where feasible from a non-Windows host
- Run:
  - python3 tests/validate_public_repo.py
  - python3 -m pytest -q
  - python3 -m py_compile scripts/install_kurultai.py
- If pytest is unavailable, document that and run the repository's available validation commands.

Documentation requirements:
- README.md must show the new preferred path:
  1. clone repo
  2. run installer doctor
  3. run interactive installer
  4. use fresh-install-agent-prompt.md only when a coding agent is completing/repairing the install
- docs/operations/full-installation-checklist.md must include the installer commands.
- docs/operations/fresh-install-agent-prompt.md must mention scripts/install_kurultai.py as the deterministic first step.

Safety requirements:
- No secrets in git.
- No private local runtime state in git.
- No destructive overwrite without backup and explicit approval.
- No production deploys, DNS changes, payment changes, or public webhook exposure by default.
- No WSL2 requirement for Windows-native installs.
- No replacement for Hermes-native Kanban/cron/profiles.

Implementation style:
- Prefer small functions with typed dataclasses for detection/reporting.
- Keep command execution wrapped so tests can mock it.
- Use JSON for local state and Markdown for human receipt.
- Make the installer useful even when it cannot perform an action: it should print exact next commands and mark the phase pending.

Before finishing:
1. Show git diff summary.
2. Run validation commands.
3. Commit the scoped changes with a conventional commit message, unless the user explicitly asked not to commit.
4. If authenticated and allowed to push, push to the GitHub repository.
5. Report the branch, commit SHA, validation results, and any remaining manual gates.
```
