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

## Systems in detail

Kurultai is not just a profile roster. It is a set of cooperating systems around Hermes Agent: some run continuously, some are invoked by Kublai, and some are rebuild/install contracts. The public repository contains the safe contracts, manifests, prompts, templates, diagrams, and runbooks for these systems. It intentionally excludes live secrets, private Brain contents, live Kanban databases, sessions, chat IDs, OAuth tokens, and private runtime state.

### Dreamer / Subconscious (`subc`)

![Dreamer / Subconscious workflow](docs/assets/workflows/01-dreamer-subconscious.png)

The Dreamer is Kurultai's background pattern-noticing layer. It watches durable context sources such as the Brain, Kanban, receipts, research outputs, and recent session history, then turns weak signals into reviewable candidate observations.

How it works:

1. Deterministic collectors gather bounded, sanitized packets from approved sources.
2. A local or scheduled synthesis lane proposes candidate observations, links, contradictions, no-ops, or follow-up actions.
3. Low-signal and duplicate candidates are suppressed before they consume frontier-model review.
4. Reviewer decisions feed a decision corpus and learned suppression rules.
5. Approved candidates move through Kublai-reviewed promotion gates before they become Brain notes, Kanban tasks, skills, or operator reports.
6. Watchdogs, heartbeats, queue metrics, and review-readiness metrics make idle/healthy/failing states visible.

Why it matters: Dreamer lets Kurultai notice repeated patterns without turning every observation into an expensive or risky action.

Public rebuild artifacts:

- `profiles/README.md` — public profile roster contract.
- `config/runtime-config/profiles.yaml` — sanitized `subc` role and model lane mapping.
- `config/runtime-config/cron.manifest.json` — sanitized scheduled jobs.
- `config/runtime-config/brain.manifest.json` — safe Brain directory contract.
- `docs/assets/workflows/01-dreamer-subconscious.png` — workflow diagram.

### AGI caretaker harness

![AGI caretaker harness workflow](docs/assets/workflows/02-agi-caretaker-harness.png)

The AGI caretaker harness is Kurultai's practical Observe → Propose layer. It is designed to improve the system without jumping straight to unbounded mutation authority.

How it works:

1. Script-first telemetry reads canaries, cron health, dashboard health, Kanban flow, Brain status, token baselines, and receipt summaries.
2. Scorecards and attention queues rank what needs human or Kublai attention.
3. Replay evaluation checks whether prior classifications, escalations, suppressions, and proposals would have made good decisions.
4. Proposal packets describe candidate improvements, expected benefit, blast radius, rollback path, and verification plan.
5. Promotion ledgers record decisions and outcomes so the harness can learn from what actually helped.
6. Mutation authority stays separate from observation: production deploys, security changes, payments, secrets, and hard deletes remain gated.

Why it matters: the harness creates a measured path from "the system can observe itself" to "the system can safely improve itself."

Public rebuild artifacts:

- `config/runtime-config/kurultai.yaml` — coordination contract.
- `config/runtime-config/cron.manifest.json` — scheduled observe/propose surfaces.
- `brain/templates/` — public-safe Brain page templates.
- `docs/assets/workflows/02-agi-caretaker-harness.png` — workflow diagram.

### Buildroom / Auto-build

![Buildroom / Auto-build workflow](docs/assets/workflows/03-buildroom-auto-build.png)

Buildroom is Kurultai's research-to-build operating room. It keeps promising ideas from disappearing into chat history by turning them into rooms, plans, receipts, and reviewable implementation work.

How it works:

1. A high-signal idea, research finding, user request, or proposal opens a room.
2. The room accumulates context, source links, goals, constraints, risks, and acceptance criteria.
3. Planning agents convert the room into an implementation sequence with explicit verification.
4. Implementation workers produce commits, artifacts, or runbooks.
5. Review workers check quality, safety, trust, retention value, and deployment readiness.
6. Kublai closes the loop with a concise result, receipts, and any follow-up tasks.

Why it matters: Buildroom makes autonomous building auditable. It preserves the path from idea → plan → build → verification → retained knowledge.

Public rebuild artifacts:

- `docs/operations/` — operating runbooks and install/checklist flows.
- `config/runtime-config/kanban.schema.json` — task graph schema.
- `docs/assets/workflows/03-buildroom-auto-build.png` — workflow diagram.

### Auto research and signal intake

![Auto research and signal intake workflow](docs/assets/workflows/04-auto-research-signal-intake.png)

Auto research and signal intake collect external and internal signals without granting those signals direct authority to act.

How it works:

1. Read-only scouts monitor approved sources such as watchlists, bookmarks, feeds, research queues, and operator-provided links.
2. Retrieval agents normalize raw items into cited receipts with source, freshness, and dedupe metadata.
3. Batu-style research lanes investigate selected candidates and reject low-signal items with reasons.
4. Research compilers turn high-signal findings into Brain notes, proposal packets, or Buildroom rooms.
5. Kublai decides whether the result needs an operator report, Kanban task, or no-op receipt.
6. Implementation, public posting, payment, deploy, refund, cancellation, and security actions remain gated.

Why it matters: Kurultai can keep learning from the outside world while preserving a clean boundary between observation and action.

Public rebuild artifacts:

- `profiles/batu.md` — retrieval/research intake role.
- `brain/templates/` — research and proposal page shapes.
- `docs/assets/workflows/04-auto-research-signal-intake.png` — workflow diagram.

### Opportunity and revenue scouts

Kurultai can also run read-only opportunity scouts for public paid-task, grant, bounty, audit, marketplace, and resale-arbitrage surfaces. These jobs convert broad public signals into ranked candidates, receipts, follow-up tasks, and low-risk public PR monitoring while preserving hard gates around accounts, KYC, wallets, payments, customer contact, security testing, submissions, publishing, and material deploys.

Public rebuild artifacts:

- `config/runtime-config/cron.manifest.json` — sanitized scout, first-dollar operator, and PR-monitor schedules.
- `config/runtime-config/skills.manifest.json` — public-safe triage and opportunity-research skill inventory.

### Native Hermes Kanban

![Native Hermes Kanban workflow](docs/assets/workflows/05-native-hermes-kanban.png)

Kanban is Kurultai's durable task graph. It is the queue, dependency map, work ledger, and cross-profile coordination surface.

How it works:

1. Kublai or an intake surface creates a task from a user request, system signal, proposal, or Buildroom plan.
2. The task receives owner, priority, status, parent/child dependencies, acceptance criteria, and review expectations.
3. Ready tasks route to specialist Hermes profiles using native Hermes worker behavior rather than a custom dispatcher.
4. Workers attach notes, blockers, artifacts, test output, and completion receipts.
5. Reviewers or Kublai verify the result before it is closed or promoted.
6. Blocked tasks are split, reassigned, retried, or escalated with evidence.

Why it matters: Kanban lets Kurultai carry work across sessions and agents without relying on one chat window's memory.

Public rebuild artifacts:

- `config/runtime-config/kanban.schema.json` — schema only, not live tasks.
- `config/runtime-config/profiles.yaml` — routable profile roster.
- `docs/assets/workflows/05-native-hermes-kanban.png` — workflow diagram.

### Brain memory layer

![Brain memory layer workflow](docs/assets/workflows/06-brain-memory-layer.png)

The Brain is Kurultai's durable wiki and memory substrate. It stores long-lived synthesis, not transient chat noise.

How it works:

1. Agents write public/private-safe notes, receipts, research syntheses, proposals, runbooks, and status surfaces.
2. Index contracts separate public pages, private pages, hard-private encrypted areas, and generated indexes.
3. Retrieval paths let Kublai and specialist profiles ground new work in prior decisions and receipts.
4. Brain service surfaces expose bounded search, status, and health checks.
5. Sync and canary checks verify that the Brain remains readable and recoverable.
6. Private operator contents remain local and are not exported into this public repository.

Why it matters: Brain gives Kurultai institutional memory that survives sessions, restarts, and agent handoffs.

Public rebuild artifacts:

- `brain/` — public schemas and templates only.
- `config/runtime-config/brain.yaml` — Brain root/index/gateway contract.
- `config/runtime-config/brain.manifest.json` — directory inventory without private contents.
- `docs/assets/workflows/06-brain-memory-layer.png` — workflow diagram.

### Receipts and recovery loop

![Receipts and recovery loop workflow](docs/assets/workflows/07-receipts-recovery-loop.png)

Receipts and recovery are Kurultai's nervous system for evidence, failure classification, and reversible repair.

How it works:

1. Canaries, watchdogs, dashboard checks, cron checks, and task receipts collect evidence.
2. Failures are classified by blast radius, recurrence, affected subsystem, and repair authority.
3. Low-risk fixes can become bounded repair proposals or assisted implementation tasks.
4. Suspicious or high-risk failures can be quarantined rather than repeatedly retried.
5. Rollback notes, verification commands, and before/after receipts accompany changes.
6. Kublai reports the final state in terms of evidence, action taken, and remaining gates.

Why it matters: Kurultai should not merely notice failures; it should preserve enough evidence to repair them safely.

Public rebuild artifacts:

- `config/runtime-config/cron.manifest.json` — sanitized monitors and canaries.
- `docs/operations/` — recovery and rebuild runbooks.
- `docs/assets/workflows/07-receipts-recovery-loop.png` — workflow diagram.

### Gateway and intake layer

![Gateway and intake layer workflow](docs/assets/workflows/08-gateway-intake-layer.png)

The gateway and intake layer connects Kurultai to humans, webhooks, Telegram, local delivery, and optional operations bots while preserving authorization boundaries.

How it works:

1. Incoming messages arrive through Hermes gateway channels such as Telegram, webhook, SMS, or local delivery.
2. Kublai handles the primary operator conversation and synthesis path.
3. Ogedei can serve a separate operations/intake topology when configured with its own credentials.
4. Intake guardrails distinguish explicit requests from passive capture, unauthorized messages, bot-to-bot traffic, and background receipts.
5. Delivery targets remain local or configured channels; chat IDs and tokens are private runtime state.
6. Responsiveness canaries and gateway logs help distinguish real gateway wedges from long healthy work.

Why it matters: Kurultai needs multiple intake paths, but no intake path should silently bypass authorization or safety gates.

Public rebuild artifacts:

- `config/runtime-config/gateways.yaml` — sanitized gateway topology.
- `agents/hermes-install-expert.md` — guided setup expectations.
- `docs/assets/workflows/08-gateway-intake-layer.png` — workflow diagram.

### Local model lane / Tolui

![Local model lane Tolui workflow](docs/assets/workflows/09-local-model-lane-tolui.png)

Tolui is the local lightweight lane. It handles cheap summarization, classification, and triage where local inference is sufficient and safe.

How it works:

1. Deterministic scripts prepare compact, sanitized inputs.
2. A local OpenAI-compatible model lane can classify, summarize, or pre-filter items.
3. Tool-required work, external side effects, ambiguous judgment, and high-risk decisions escalate to Kublai or a frontier-model profile.
4. Local-model canaries verify server health and prevent silent fallback assumptions.
5. Memory-sensitive model loading is bounded so background daemons do not destabilize the host.
6. Results feed queues, attention caches, or suppression decisions instead of acting directly.

Why it matters: Tolui reduces token burn while keeping important judgment and tool use on verified, capable lanes.

Public rebuild artifacts:

- `profiles/README.md` — public profile roster contract.
- `config/runtime-config/profiles.yaml` — sanitized `tolui` role and model lane mapping.
- `docs/assets/workflows/09-local-model-lane-tolui.png` — workflow diagram.

### Agentic foundation

![Agentic foundation workflow](docs/assets/workflows/10-agentic-foundation.png)

The agentic foundation is the operational substrate for persistent multi-device work: shell access, tmux continuity, private repos, helper scripts, and health canaries.

How it works:

1. Tailscale and SSH provide private network reachability where the operator enables them.
2. tmux sessions give long-running agents and humans stable places to resume work.
3. Helper scripts standardize status checks, attach flows, and cross-node probes.
4. A private operations repo can hold executable substrate and scripts while Brain holds durable wiki memory.
5. Cross-device canaries verify connectivity without spending LLM tokens.
6. Secrets, private keys, ACLs, and remote authorization remain explicit human gates.

Why it matters: a persistent agent needs reliable places to work, reconnect, recover, and prove liveness.

Public rebuild artifacts:

- `docs/operations/` — bootstrap and fresh-install guidance.
- `scripts/` — public-safe helper/exporter scripts.
- `docs/assets/workflows/10-agentic-foundation.png` — workflow diagram.

### Dashboards and Control Rooms

![Dashboards and Control Rooms workflow](docs/assets/workflows/11-dashboards-control-rooms.png)

Dashboards and Control Rooms turn raw system state into operator-readable control surfaces.

How it works:

1. Deterministic exporters collect public-safe status JSON, metrics, and readouts.
2. Dashboard pages summarize Kanban flow, Dreamer state, Buildroom progress, research queues, health checks, and installation state.
3. Control Rooms group related artifacts so a project can be reviewed without scanning raw logs.
4. Public dashboards redact private content and show only safe aggregate or explicitly public material.
5. Kublai uses dashboard health as one input, then verifies important claims from source receipts before acting.
6. Broken dashboard data is treated as an observability bug, not as proof the underlying system is healthy or dead.

Why it matters: dashboards keep the operator from having to ask "what is happening?" every time the system works in the background.

Public rebuild artifacts:

- `docs/assets/readme/` and `docs/assets/workflows/` — public visual architecture.
- `config/runtime-config/*.json` — sanitized manifest inputs.
- `docs/assets/workflows/11-dashboards-control-rooms.png` — workflow diagram.

### Fresh install / rebuild tooling

![Fresh install / rebuild tooling workflow](docs/assets/workflows/12-fresh-install-rebuild.png)

Fresh install and rebuild tooling make Kurultai reproducible from public instructions without exposing the live private system.

How it works:

1. A human or coding agent clones the repository and reads the install prompt, expert contract, and checklist.
2. The installer detects platform details and installs/verifies Hermes Agent.
3. The human supplies provider credentials, Telegram BotFather tokens, and optional integration secrets locally.
4. Scripts create or verify Brain roots, profiles, Kanban schema, skills, cron manifests, gateway templates, and receipt directories.
5. Dry-run and doctor modes explain changes before touching existing runtime state.
6. Validation tests confirm the public repository remains secret-safe and internally consistent.

Why it matters: Kurultai should be reconstructable without copying Danny's private machine state.

Public rebuild artifacts:

- `docs/operations/fresh-install-agent-prompt.md` — full coding-agent install prompt.
- `agents/hermes-install-expert.md` — installer expert operating contract.
- `docs/operations/full-installation-checklist.md` — completion checklist.
- `scripts/bootstrap_kurultai_runtime.py` — bootstrap helper.
- `docs/operations/interactive-installer-implementation-prompt.md` — prompt to implement or repair the guided installer when needed.
- `docs/assets/workflows/12-fresh-install-rebuild.png` — workflow diagram.

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
