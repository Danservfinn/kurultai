# Kurultai

[![License: MIT](https://img.shields.io/badge/License-MIT-22d3ee.svg)](LICENSE)
[![Open Source](https://img.shields.io/badge/open%20source-yes-34d399.svg)](CONTRIBUTING.md)
[![Runtime](https://img.shields.io/badge/runtime-Hermes%20Agent-a78bfa.svg)](https://hermes-agent.nousresearch.com/docs)

**Kurultai is an open-source operating layer for Hermes Agent and a Brain wiki.**

It packages the current Kublai/Kurultai way of running Hermes: a chair profile, specialist Hermes profiles, native Hermes Kanban, a durable Brain, cron-backed continuity, reusable skills, recovery receipts, and a safe rebuild contract that keeps private runtime state out of git.

## Copy-paste agent installation prompt

If you want a coding agent to install Kurultai for you, copy this whole block into Claude Code, Codex, Hermes, or another local coding agent:

```text
You are installing Kurultai from its public rebuild repository.

Goal: produce a fully functional local Kurultai/Hermes setup while preserving the repository's security boundary. Do not commit, print, or exfiltrate secrets. Do not overwrite an existing Hermes home, Brain root, profile, cron job set, Kanban database, or private config without asking first. Keep all credentials local.

Repository: https://github.com/Danservfinn/kurultai

Start by cloning or opening the repository, then read and follow these files in order:
1. docs/operations/fresh-install-agent-prompt.md
2. agents/hermes-install-expert.md
3. docs/operations/full-installation-checklist.md

If scripts/install_kurultai.py exists, prefer it and run its doctor/dry-run/interactive flow before falling back to scripts/bootstrap_kurultai_runtime.py. If the installer is missing or incomplete, use docs/operations/interactive-installer-implementation-prompt.md to implement or repair it first.

Required behavior:
- Detect macOS, Linux, or Windows and choose platform-appropriate commands.
- Install and verify Hermes Agent.
- Guide the human through provider auth, Telegram/BotFather setup, and any optional integration credentials.
- Create or verify the Brain root, Kurultai profiles, native Hermes Kanban, skills, cron jobs, receipts, and gateway setup.
- Keep private Brain contents, live Kanban data, sessions, tokens, chat IDs, OAuth credentials, cookies, and API keys out of git.
- Run the repository validation and available tests before reporting success.
- Finish with a concise install receipt: what was installed, what was verified, what remains gated on human auth, and exact next commands.
```

![Kurultai system overview](docs/assets/readme/01-kurultai-overview.png)

## What Kurultai provides

- **Hermes-native multi-agent coordination** — profiles, tools, skills, sessions, gateway, cron, and native Kanban remain the runtime substrate.
- **Kublai as chair** — Kublai routes work, keeps synthesis coherent, verifies receipts, and reports one concise operator-facing result.
- **Specialist profiles** — Batu, Chagatai, Jochi, Temujin, Coder, Mongke, Ogedei, Subc, and Tolui handle retrieval, research, analysis, implementation, review, operations, background signal detection, and local lightweight triage. `codex` is included as a non-routable compatibility profile for explicit Codex CLI flows.
- **Brain wiki** — durable plans, receipts, research, synthesis, operations notes, and public/private index contracts.
- **Rebuildable configuration** — sanitized templates and manifests describe how to recreate the system without publishing secrets or live private state.
- **Recovery loop** — canaries, drift checks, low-token monitors, and review gates keep the system moving without turning automation into recklessness.

## Systems included

Kurultai is not just a profile roster. The rebuild contract documents the larger operating system that has accumulated around Hermes:

- **Dreamer / Subconscious (`subc`)** — background pattern-noticing over Brain, Kanban, receipts, research, and session history. It creates candidate observations, learns suppression rules from reviewer decisions, promotes approved candidates through Kublai-reviewed gates, and exposes health through watchdog/review/triage jobs.
- **AGI caretaker harness** — a practical Observe → Propose layer for autonomous improvement. It uses script-first telemetry, canaries, scorecards, attention queues, replay evaluation, token baselines, proposal packets, and promotion ledgers before any real-world mutation authority is granted.
- **Buildroom / Auto-build** — a research-to-build operating room system. It turns high-signal ideas into room artifacts, plans, implementation receipts, verification reports, trust/retention reviews, Control Room readouts, and bounded low-risk Kanban drafts.
- **Auto research and signal intake** — scheduled signal capture, Batu research dispatch, bookmark/watchlist scouts, research proposal compilation, and research Control Room summaries. Retrieval stays read-only; implementation, public posting, payment, deploy, and security actions remain gated.
- **Native Hermes Kanban** — durable task graph with owners, parent dependencies, worker dispatch, review gates, blockers, completion receipts, and Kublai synthesis.
- **Brain memory layer** — durable wiki, receipts, proposals, research syntheses, operational pages, private/public index boundaries, retrieval evaluation harness, and Brain sync canaries.
- **Receipts and recovery loop** — append-only evidence, canaries, watchdogs, failure classifiers, drift monitors, quarantine paths, rollback-aware repair proposals, and assisted Coder handoffs.
- **Gateway and intake layer** — Telegram/operator gateway contracts, Ogedei operations/intake bot topology, webhook/local delivery boundaries, responsiveness canaries, and safe bot-to-bot/intake guardrails.
- **Local model lane (`tolui`)** — low-cost local summarization/classification/triage path for token-efficient reflexes, kept separate from tool-required frontier work until verified.
- **Agentic foundation** — Tailscale/SSH/tmux helper patterns, cross-device canaries, Brain sync checks, and ops-repo drift monitors for persistent multi-device agent work.
- **Dashboards and control rooms** — `the.kurult.ai`, Buildroom Control Room, research Control Room, Dreamer status surfaces, Kanban/health dashboards, and public-safe readouts.
- **Fresh install / rebuild tooling** — copy-paste installer prompts, install expert contract, sanitized runtime manifests, profile templates, cron manifests, and verification checklists.

The public repository contains the safe contracts, manifests, prompts, templates, diagrams, and runbooks for these systems. It intentionally excludes live secrets, private Brain contents, live Kanban databases, sessions, chat IDs, OAuth tokens, and private runtime state.

## Workflow diagram gallery

### Dreamer / Subconscious

![Dreamer / Subconscious workflow](docs/assets/workflows/01-dreamer-subconscious.png)

### AGI caretaker harness

![AGI caretaker harness workflow](docs/assets/workflows/02-agi-caretaker-harness.png)

### Buildroom / Auto-build

![Buildroom / Auto-build workflow](docs/assets/workflows/03-buildroom-auto-build.png)

### Auto research and signal intake

![Auto research and signal intake workflow](docs/assets/workflows/04-auto-research-signal-intake.png)

### Native Hermes Kanban

![Native Hermes Kanban workflow](docs/assets/workflows/05-native-hermes-kanban.png)

### Brain memory layer

![Brain memory layer workflow](docs/assets/workflows/06-brain-memory-layer.png)

### Receipts and recovery loop

![Receipts and recovery loop workflow](docs/assets/workflows/07-receipts-recovery-loop.png)

### Gateway and intake layer

![Gateway and intake layer workflow](docs/assets/workflows/08-gateway-intake-layer.png)

### Local model lane / Tolui

![Local model lane Tolui workflow](docs/assets/workflows/09-local-model-lane-tolui.png)

### Agentic foundation

![Agentic foundation workflow](docs/assets/workflows/10-agentic-foundation.png)

### Dashboards and Control Rooms

![Dashboards and Control Rooms workflow](docs/assets/workflows/11-dashboards-control-rooms.png)

### Fresh install / rebuild tooling

![Fresh install / rebuild tooling workflow](docs/assets/workflows/12-fresh-install-rebuild.png)

## Native Kanban lifecycle

Every meaningful piece of work gets a durable task record. The board is both the queue and the audit trail.

![Native Kanban work lifecycle](docs/assets/readme/02-native-kanban-flow.png)

A normal task flow is:

1. Intake a user request, proposal, bug, research question, or runtime signal.
2. Decompose it into an explicit graph with owners and parent dependencies.
3. Dispatch ready tasks to capable Hermes profiles.
4. Capture logs, comments, blockers, child tasks, reviews, and completion receipts.
5. Fan results back into Kublai for one concise operator-facing synthesis.

Blocked tasks are not terminal. Kublai or an assigned resolver clears safe blockers, reassigns, splits work, or escalates with evidence.

## Brain and rebuild contract

Kurultai separates durable public architecture from private runtime state.

![Brain memory and rebuild contract](docs/assets/readme/03-brain-memory-contract.png)

The Brain contains the long-term operating memory: plans, receipts, proposals, analyses, content artifacts, and status surfaces. This repository contains the **sanitized rebuild contract** for that system:

- `config/runtime-config/hermes.template.yaml` — non-secret Hermes runtime contract.
- `config/runtime-config/profiles.yaml` — Kurultai profile roster and model map.
- `config/runtime-config/kurultai.yaml` — native coordination contract.
- `config/runtime-config/brain.yaml` — Brain root, index, and gateway contract.
- `config/runtime-config/gateways.yaml` — Kublai primary gateway plus Ogedei operations/intake gateway contract.
- `config/runtime-config/cron.manifest.json` — sanitized cron manifest.
- `config/runtime-config/skills.manifest.json` — skill inventory without secret-bearing state.
- `config/runtime-config/kanban.schema.json` — Kanban schema only, not live tasks.
- `config/runtime-config/brain.manifest.json` — directory inventory, not private note contents.

## Fresh install path

A fresh user can clone this repository and paste a single prompt into Claude Code, Codex, or another local coding agent. That prompt performs the setup while preserving the secret boundary.

![Fresh install path](docs/assets/readme/04-fresh-install-path.png)

```bash
git clone https://github.com/Danservfinn/kurultai.git
cd kurultai
python3 scripts/bootstrap_kurultai_runtime.py --home "$HOME/.hermes-kurultai" --brain "$HOME/brain-kurultai" --dry-run
```

To implement or repair the full guided installer, paste this file into Claude Code or Codex:

```text
docs/operations/interactive-installer-implementation-prompt.md
```

For a fresh-machine install performed by a coding agent, paste this file instead:

```text
docs/operations/fresh-install-agent-prompt.md
```

For best results, also give the installing agent its expert operating prompt:

```text
agents/hermes-install-expert.md
```

The install prompts cover:

- macOS, Linux, and Windows-native PowerShell installation.
- Hermes Agent installation and verification.
- frontier model configuration for Kublai and tool-capable profiles.
- Brain directory creation and index setup.
- Kurultai profile creation.
- local LLM lane selection for Tolui.
- Telegram BotFather and Hermes gateway setup.
- second Hermes gateway setup for Ogedei operations/intake.
- sanitized cron, skills, Kanban, receipt, and verification setup.

For the installing agent's end-to-end completion definition, see:

```text
docs/operations/full-installation-checklist.md
```

The install expert contract is declared in `config/runtime-config/install-expert.yaml`.

The installer must never commit secrets.

## Open-source boundary

Kurultai is open source under the MIT License. The project is designed so the useful system can be inspected, forked, and rebuilt without exposing private operator state.

![Open-source boundary](docs/assets/readme/05-open-source-boundary.png)

Public repository contents include:

- source and scripts for the rebuild contract,
- docs and diagrams,
- runtime templates,
- sanitized manifests,
- runbooks,
- skill inventories.

Local/private contents must stay outside git:

- API keys and OAuth tokens,
- Telegram bot tokens and private chat IDs,
- live Hermes sessions,
- live Kanban databases,
- private Brain indexes,
- cookies, credentials, keys, and delivery targets,
- private operator memory.

See `.gitignore`, `docs/operations/kurultai-rebuild-runbook.md`, and `config/runtime-config/README.md` for the exact boundary.

## Profile roster

| Profile | Role | Default lane |
|---|---|---|
| `kublai` | caretaker / orchestrator / synthesis | frontier model |
| `batu` | retrieval / research intake / return path | frontier model |
| `chagatai` | research, writing, synthesis, content | frontier model |
| `jochi` | analysis, audit, scouting, alternatives | frontier model |
| `temujin` | implementation, tests, code repair | frontier model |
| `coder` | optional implementation worker lane | frontier model |
| `mongke` | review, risk, quality gates | frontier model |
| `ogedei` | operations, integration, runbooks | frontier model |
| `subc` | subconscious / Dreamer signal layer | frontier model or local/scheduled lane |
| `tolui` | local lightweight triage and summarization | local model, no tool-required work until verified |
| `codex` | Codex CLI compatibility / pseudo-profile | non-routable unless explicitly enabled |

## Repository map

```text
config/runtime-config/      sanitized runtime templates and manifests
agents/                    installer-agent prompts and operating contracts
brain/                      public Brain/wiki schema and page templates
profiles/                   public profile role templates
docs/operations/            rebuild runbooks and fresh-install prompt
docs/assets/readme/         README diagrams
scripts/                    manifest export and rebuild staging helpers
tests/                      public hygiene and retrieval-eval tests
```

## Development

Useful commands:

```bash
python3 tests/validate_public_repo.py
python3 scripts/bootstrap_kurultai_runtime.py --home /tmp/hermes-kurultai --brain /tmp/brain-kurultai --dry-run
python3 scripts/export_runtime_config_manifest.py
python3 scripts/export_rebuild_manifests.py
python3 -m pytest -q
```

Before changing runtime contracts, inspect live Hermes and Brain state, preserve the secret boundary, and update the README diagrams when architecture changes.

## Contributing

Contributions are welcome. Keep these rules:

1. Do not commit secrets or live private runtime files.
2. Keep Hermes native profiles and Kanban as the coordination substrate unless a future architecture decision explicitly changes it.
3. Prefer sanitized templates, manifests, tests, and runbooks over local machine snapshots.
4. Preserve reversibility and auditable receipts for runtime-changing work.
5. Update diagrams and README when architecture changes.

See `CONTRIBUTING.md` for the contributor guide.

## License

MIT. See [`LICENSE`](LICENSE).
