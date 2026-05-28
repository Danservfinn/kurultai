# Fresh Kurultai install prompt for Claude Code / Codex

Paste the prompt below into Claude Code, Codex, or another local coding agent in a fresh checkout of this repository. It is designed to make the agent do the installation work, not merely describe it.

Secret boundary: this prompt intentionally uses placeholders and interactive setup for secrets. Do not paste API keys into the repository. Store secrets only in the user's local Hermes `.env` / credential store.

Compatibility target: macOS, Linux, and Windows. On Windows, prefer Windows Terminal + PowerShell 7; use WSL2 only when the user explicitly wants the Linux runtime.

```text
You are installing the Kurultai runtime from this repository onto a fresh machine. Act as the installer. Do not stop at advice: inspect the system, create files, run commands, verify results, and leave a short receipt with exact commands run and what remains manual.

Non-negotiable constraints:
- Do not configure or depend on alternative hosted fallback model providers beyond the stated Hermes frontier lane.
- Do not write secrets, tokens, OAuth files, cookies, session dumps, private chat IDs, private Brain indexes, or API keys into git.
- Use placeholders in tracked files and real values only in local untracked secret stores.
- Kurultai coordination is native Hermes profiles + native Hermes Kanban + Brain receipts.
- Configure the frontier runtime as Hermes `openai-codex` / `gpt-5.5`, `model.context_length: 1000000`, and `compression.threshold: 0.25`.
- Configure a local LLM lane for lightweight triage/Tolui. The system should choose the best local model it can run. Prefer Jackrong/Qwen3.5-9B-DeepSeek-V4-Flash-GGUF through a local OpenAI-compatible server or Ollama/HF GGUF import. If hardware cannot run it, choose the strongest local Qwen/Gemma-class model that fits memory, record the chosen model, and mark it as no-tool-call/lightweight-only until verified.
- Telegram bot setup must be included and, when the user supplies the BotFather token, performed by you through Hermes gateway setup/configuration.
- Windows installation must work. Use PowerShell equivalents and avoid Bash-only assumptions unless running under WSL2.

Repository contract to honor:
- Runtime manifests live in `config/runtime-config/`.
- Main rebuild guide: `docs/operations/kurultai-rebuild-runbook.md`.
- This repo is a non-secret rebuild contract, not a private backup.
- Brain wiki default root: `~/brain` on POSIX, `%USERPROFILE%\brain` on Windows.
- Hermes home default: `~/.hermes` on POSIX, `%USERPROFILE%\.hermes` on Windows unless Hermes itself reports another path.

Phase 0 — detect platform and make a log
1. Detect OS, shell, CPU arch, RAM, GPU, Python version, Git, Node/npm, and whether the current directory is a git checkout.
2. Create a local receipt directory outside git:
   - POSIX: `~/.kurultai-install/receipts/`
   - Windows: `$env:USERPROFILE\.kurultai-install\receipts\`
3. Save all commands/results that do not contain secrets into an install receipt file named `install-YYYYMMDD-HHMMSS.md`.
4. If existing Hermes/Brain/Kurultai data is present, back up before changing it:
   - POSIX: `~/.hermes` → `~/.hermes.backup.<timestamp>` metadata-only if full copy is too large.
   - Windows: `%USERPROFILE%\.hermes` → `%USERPROFILE%\.hermes.backup.<timestamp>` metadata-only if full copy is too large.

Phase 1 — install prerequisites
Choose commands for the detected OS.

macOS:
- Ensure Homebrew exists or install it after asking the user.
- Install/verify: `git`, `python@3.12` or newer stable Python, `node`, `npm`, `jq`, `ripgrep`, `sqlite`, `uv` or `pipx`.
- Optional local model tools: install Ollama or llama.cpp if absent.

Linux:
- Use the detected package manager (`apt`, `dnf`, `pacman`, `zypper`) to install/verify: `git`, `python3`, `python3-venv`, `pipx` or `uv`, `nodejs`, `npm`, `jq`, `ripgrep`, `sqlite3`, `curl`.
- Optional local model tools: install Ollama or llama.cpp if absent.

Windows native:
- Use PowerShell 7 if available. If not available, use Windows PowerShell carefully.
- Use `winget` when present; otherwise instruct the user for the missing installer.
- Install/verify: Git for Windows, Python 3.12+ with launcher `py`, Node.js LTS, jq, ripgrep, SQLite tools, PowerShell 7.
- Optional local model tools: Ollama for Windows is preferred for the local lane. If using llama.cpp, use a Windows build and run an OpenAI-compatible server.
- Do not require WSL2 unless the user explicitly asks for Linux parity.

Phase 2 — install Hermes Agent
1. Install Hermes Agent using the official installer or the local repository workflow preferred by Hermes docs:
   - POSIX default: `curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash`
   - Windows: use the Hermes documented Windows path if available; otherwise install from the Hermes Agent repository in a Python virtual environment and expose a `hermes` command or PowerShell function.
2. Run:
   - `hermes doctor`
   - `hermes config path`
   - `hermes config env-path`
3. If Hermes is not installed successfully, fix that before continuing.

Phase 3 — authenticate/configure the frontier provider
1. Configure Hermes for OpenAI Codex OAuth / provider mode without storing secrets in git:
   - Run `hermes login --provider openai-codex` if available.
   - Otherwise run `hermes model` and select provider `openai-codex`, model `gpt-5.5`.
2. Set or verify these config values:
   - `model.provider: openai-codex`
   - `model.default: gpt-5.5`
   - `model.context_length: 1000000`
   - `compression.enabled: true`
   - `compression.threshold: 0.25`
   - memory enabled
   - session search enabled
   - cron, terminal, file, skills, memory, session_search, delegation, messaging/gateway toolsets enabled where Hermes supports per-platform configuration
3. Run `hermes config check` and `hermes doctor` again.

Phase 4 — create Brain directories and indexes
1. Create the Brain root:
   - POSIX: `~/brain`
   - Windows: `$env:USERPROFILE\brain`
2. Create at least these directories: `queue`, `generated`, `receipts`, `docs/plans`, `operations`, `analyses`, `content`, `content/artifacts`.
3. Create public/private index directories:
   - POSIX public: `~/.brain-index/`
   - POSIX private: `~/.kublai/brain-index-private/`
   - Windows public: `$env:USERPROFILE\.brain-index\`
   - Windows private: `$env:USERPROFILE\.kublai\brain-index-private\`
4. If `qmd` is installed, run or prepare:
   - `qmd update -c brain`
   - `qmd embed -c brain`
5. If `qmd` is absent, record it as pending and keep Brain directories usable.
6. Brain canonical storage is Brain service, SQLite-compatible receipts, and QMD-style indexes.

Phase 5 — apply sanitized runtime manifests
1. Run the bootstrap script from this repository:
   - POSIX/macOS/Linux: `python3 scripts/bootstrap_kurultai_runtime.py --dry-run`
   - Windows PowerShell: `py -3 scripts\bootstrap_kurultai_runtime.py --dry-run` or `python scripts\bootstrap_kurultai_runtime.py --dry-run`
2. If it looks correct, run the non-dry-run form:
   - POSIX/macOS/Linux: `python3 scripts/bootstrap_kurultai_runtime.py`
   - Windows PowerShell: `py -3 scripts\bootstrap_kurultai_runtime.py` or `python scripts\bootstrap_kurultai_runtime.py`
3. Review staged files under `~/.kurultai-rebuild-staging/` or Windows equivalent if the script uses the current user's home.
4. Use `config/runtime-config/hermes.template.yaml`, `profiles.yaml`, `kurultai.yaml`, `brain.yaml`, `cron.manifest.json`, `skills.manifest.json`, `kanban.schema.json`, and `brain.manifest.json` as the contract.
5. Do not blindly overwrite a user's existing private config. Merge non-secret settings and preserve local credentials.

Phase 6 — create Kurultai Hermes profiles
Create these Hermes profiles if missing, preserving existing profiles if present:
- `kublai`: caretaker/orchestrator, provider `openai-codex`, model `gpt-5.5`.
- `batu`: retrieval/research intake and return-path compilation, provider `openai-codex`, model `gpt-5.5`.
- `chagatai`: research/writing/content synthesis, provider `openai-codex`, model `gpt-5.5`.
- `jochi`: analysis/audit, provider `openai-codex`, model `gpt-5.5`.
- `temujin`: development/implementation/testing, provider `openai-codex`, model `gpt-5.5`.
- `coder`: optional implementation worker lane, provider `openai-codex`, model `gpt-5.5`.
- `mongke`: review/research synthesis, provider `openai-codex`, model `gpt-5.5`.
- `ogedei`: operations/infrastructure, provider `openai-codex`, model `gpt-5.5`.
- `subc`: Subconscious/Dreamer signal lane, provider `openai-codex`, model `gpt-5.5` unless host policy assigns local/scheduled-only duties.
- `tolui`: local lightweight triage lane, local provider/model selected in Phase 7.
- `codex`: non-routable compatibility/pseudo-profile for explicit Codex CLI workflows only; do not put it in the ordinary Kanban worker pool unless intentionally enabled.

Use Hermes profile commands when available:
- `hermes profile list`
- `hermes profile create <name>`
- `hermes --profile <name> config set ...` or the equivalent documented config path for profile-local config.

If a command is unsupported by the installed Hermes version, create profile config directories only after verifying Hermes's profile path convention with `hermes profile show` or docs. Record any manual follow-up.

Phase 7 — configure local LLM lane with automatic model selection
1. Inspect hardware:
   - RAM total and free.
   - GPU vendor and VRAM if available.
   - OS constraints.
2. Prefer this model target when feasible:
   - `Jackrong/Qwen3.5-9B-DeepSeek-V4-Flash-GGUF`
3. Choose runtime:
   - If Ollama is installed or easiest on this OS, use Ollama and try an HF GGUF import/pull for the Jackrong model. If Ollama cannot pull that HF model directly, create a Modelfile using the downloaded GGUF.
   - If llama.cpp is installed or easier, download the appropriate quantized GGUF and run `llama-server` / OpenAI-compatible endpoint on localhost.
   - If neither is installed, install the least invasive local runtime for the OS: Ollama on Windows/macOS, package/native install on Linux.
4. Fit model to hardware:
   - 32GB+ RAM or adequate VRAM: prefer 9B Q4_K_M/Q5_K_M.
   - 16GB RAM: prefer 9B Q4_K_M only if it runs; otherwise use a 7B/4B Qwen/Gemma-class model.
   - <16GB RAM: use a 3B/4B local model and mark it as triage-only.
5. Configure Tolui to use the selected local endpoint/model.
6. Run a one-sentence local test prompt and record latency/model name.
7. Do not assign local Tolui to tasks requiring Hermes tool calls until tool-call behavior has been explicitly tested. Mark local lane as `lightweight_triage`, `summarization`, `classification`, and `receipt prefilter` by default.

Phase 8 — install skills and integrations
1. Use `config/runtime-config/skills.manifest.json` as the checklist.
2. Ensure these Kurultai-critical skills are available if this install has access to the same skill library:
   - `hermes-agent`
   - `kurultai-operations`
   - `brain-wiki-operations`
   - `kurultai-retro-learn`
   - `kanban-orchestrator`
   - `kanban-worker`
   - `kanban-task-lifecycle`
   - `research-to-brain-compiler`
   - `content-os-workflows`
   - `reddit`
   - `stripe`
   - `apify`
   - `readwise`
   - `granola-fathom`
3. Install skills with `hermes skills install`, copying private skill backups, or source checkout as appropriate. Do not invent secrets for integrations; use env placeholders.
4. Run `hermes skills list` and save the result to the receipt.

Phase 9 — initialize native Kanban and process directories
1. Initialize/verify native Hermes Kanban.
2. Compare schema to `config/runtime-config/kanban.schema.json` where practical.
3. Create receipt/recovery directories under Brain and Hermes home.
4. Use only native Hermes routing and gateway surfaces.
5. Create a small harmless test task and complete/cancel it to prove Kanban works; record the task ID in the local receipt only.

Phase 10 — recreate cron jobs from sanitized manifest
1. Read `config/runtime-config/cron.manifest.json`.
2. Recreate jobs with sanitized prompts/schedules and redacted delivery targets.
3. For delivery:
   - Use `local` by default until Telegram is configured.
   - Switch selected operator-facing jobs to Telegram only after `/sethome` or explicit target verification.
4. Preserve script-only jobs as script-only where possible to reduce token usage.
5. Include these operating patterns:
   - Frequent telemetry/canaries should be script-first and silent unless action is needed.
   - Token reduction is a primary goal: avoid high-frequency LLM cron unless there is a strong reason.
   - Compression-threshold drift monitor should verify `compression.threshold == 0.25` when main context is 1M and aux compression context is smaller.
6. Run `hermes cron list` and save a redacted summary to the receipt.

Phase 11 — Telegram bot setup and gateway configuration
Do the setup if the user supplies the token. If they do not yet have a bot, guide them through BotFather exactly and then continue.

BotFather directions for the user:
1. Open Telegram and message `@BotFather`.
2. Send `/newbot`.
3. Choose display name, e.g. `Kurultai Kublai`.
4. Choose username ending in `bot`, e.g. `your_kurultai_bot`.
5. Copy the bot token. Treat it as a secret.
6. Optional but recommended:
   - `/setdescription` with a short description.
   - `/setabouttext`.
   - `/setuserpic`.
   - `/setcommands` with at least: `help`, `status`, `restart`, `sethome`, `approve`, `deny`, `platforms` if Hermes supports them.

Installer actions after token is available:
1. Put the token only into Hermes's local secret store (`hermes config env-path` / `.env`) or `hermes gateway setup`; never into git.
2. Run `hermes gateway setup` and enable Telegram, or directly set the documented Telegram config keys for this Hermes version.
3. Prefer long polling for a private fresh install. Use webhook only if the machine has a stable public HTTPS endpoint.
4. Start gateway:
   - POSIX systemd user if available: `hermes gateway install`, then `hermes gateway start`.
   - macOS LaunchAgent if Hermes installer provides it; otherwise foreground test with `hermes gateway run` first.
   - Windows: use a PowerShell-friendly foreground test first; then create a scheduled task or NSSM/WinSW service only after the gateway works.
5. Send `/start` to the bot from the operator's Telegram account.
6. Send `/sethome` in the intended DM or group if Hermes supports it.
7. Send `/platforms` or `/status` and verify the bot responds.
8. If using a group, ensure privacy/mode/message permissions are correct in BotFather and Telegram group settings.
9. Save only redacted Telegram status to the receipt.

Phase 12 — verification canaries
Run and record all feasible checks:
- `hermes doctor`
- `hermes config check`
- `hermes profile list`
- `hermes skills list`
- `hermes cron list`
- One `hermes chat -q` smoke test on Kublai/frontier model.
- One local LLM smoke test on Tolui/local model.
- Brain directory exists with receipt write.
- QMD update/embed if available.
- Kanban create/complete/cancel smoke test if Hermes Kanban commands are available.
- Telegram bot replies to `/status` or `/help` after gateway starts.
- Repo secret scan: verify no API keys/tokens were written into tracked files.

Phase 13 — final receipt
At the end, produce a concise report with:
- OS and install mode used.
- Hermes version/path.
- Frontier provider/model and context/compression values.
- Local LLM runtime/model selected and why.
- Brain root and index paths.
- Profiles created/verified.
- Cron jobs created/verified.
- Telegram status: not configured / token needed / configured and responding.
- Any manual steps remaining.
- Location of the local receipt file.

If something fails, diagnose and retry with a safe alternative. Do not silently skip phases. If an operation is destructive or would expose secrets, stop and ask for that specific approval/input only.
```
