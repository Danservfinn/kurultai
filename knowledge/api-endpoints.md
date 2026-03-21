# Kurultai API Endpoints Reference

**Server**: `the-kurultai/server.js`
**Port**: 18790 (bound to 127.0.0.1)
**Base URL**: `http://127.0.0.1:18790` / `https://the.kurult.ai`

## Authentication

- Protected paths: `/api/providers`, `/api/settings` (except `/api/settings/mode` and `/api/settings/model` GET requests, which are public; POST requests to these paths require auth)
- Auth method: API key via `Authorization: Bearer <key>` header only (query param auth removed to avoid log/Referer leakage)
- Same-origin detection: checks both `Origin` and `Referer` headers against ALLOWED_ORIGINS
- Key file: `~/.openclaw/credentials/kurultai-api.key` (auto-generated if missing)
- Rate limiting: LRU-cache based per-IP rate limiter (general + review-specific)

---

## Provider Configuration

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/providers` | Yes | Read provider.env configuration (tokens masked) |
| POST | `/api/providers` | Yes | Update a single provider field |

**POST /api/providers** body:
```json
{ "provider": "zai|alibaba|anthropic|openrouter|default", "field": "authToken|apiKey|baseUrl|model|defaultModel", "value": "..." }
```

---

## Task Management (Kanban)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tasks` | No | Load kanban board columns (pending, executing, failed, done). With query params (`status`, `agent`, `priority`, `limit`, `offset`), returns paginated list from Neo4j. |
| GET | `/api/tasks/:agent/:filename` | No | Get single task details by task_id |
| PUT | `/api/tasks/:agent/:filename` | No | Update task prompt/body |
| GET | `/api/tasks/:agent/:filename/report` | No | Get completion report for a task |
| POST | `/api/tasks/:agent/wake` | No | Create a self-wake task for an idle agent |
| POST | `/api/tasks/:agent/:filename/retry` | No | Retry a single failed task (resets to PENDING) |
| POST | `/api/tasks/:agent/retry-all` | No | Retry all failed tasks for an agent |
| POST | `/api/tasks/:agent/:filename/pause` | No | Pause a pending task |
| POST | `/api/tasks/:agent/:filename/resume` | No | Resume a paused task |
| POST | `/api/tasks/:agent/:filename/review` | No | Create a `/horde-review` task for an existing task (rate limited: 10/min/IP) |
| PUT | `/api/tasks/reorder` | No | Reorder pending tasks by setting sort_order |
| POST | `/api/tasks/:agent/:filename/move-to-top` | No | Move a single task to top of pending queue |

**PUT /api/tasks/reorder** body:
```json
{ "tasks": [{ "filename": "task_id_1" }, { "filename": "task_id_2" }] }
```

---

## Agent Status

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/agents/status` | No | Get all agents' executing/pending counts, live process detection, availability |
| POST | `/api/queue/clear` | No | Redistribute tasks from overloaded agents (3+ pending) to available agents (<2 pending) |
| GET | `/api/avatars/:agent` | No | Serve agent avatar PNG image (cached 24h) |

---

## Continuous Tasks

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/continuous-tasks` | No | List all continuous tasks (launchd daemons, cron jobs) with status, last run, log health |
| GET | `/api/continuous-tasks/logs` | No | Read tail of a log file. Query: `?file=<absolute_path>` (must start with HOME) |

---

## Reflections

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/reflections` | No | List reflections with summaries. Query: `?date=`, `?agent=`, `?limit=`, `?offset=` |
| GET | `/api/reflections/:id` | No | Get full parsed reflection (executive summary, agent blocks, grades, rules, fleet status, etc.) |
| GET | `/api/reflections/:id/audit` | No | Get audit trail: matches reflection proposals to actual task files |
| GET | `/api/agents/:name/reflections` | No | Get all reflections for a specific agent (consolidated + per-agent) |
| GET | `/api/per-agent-reflections/:id` | No | Get a single per-agent standalone reflection |
| GET | `/api/agents/:name/grade-history` | No | Get grade history across all reflections for an agent |
| POST | `/api/rollback/:reflectionId` | No | Create a rollback investigation task for a reflection |

**POST /api/rollback/:reflectionId** body:
```json
{ "agent": "ogedei", "reason": "Rollback reason text" }
```

---

## Proposals and Rules

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/proposals` | No | Aggregated proposals from reflections and hourly reports. Query: `?agent=`, `?status=`, `?limit=`, `?offset=` |
| GET | `/api/rules` | No | All WHEN/THEN rules from reflections. Query: `?agent=` |

---

## Tock (System Snapshots)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tock/latest` | No | Latest tock system snapshot |
| GET | `/api/tock/history/:date` | No | Historical tock snapshots for a date (YYYY-MM-DD) |

---

## Verifications

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/verifications` | No | Verification log (JSONL). Query: `?limit=`, `?offset=`, `?agent=` |

> **NOT IMPLEMENTED**: `GET /api/completions` — referenced in earlier docs but no corresponding route in server.js.

---

## Hourly Reports

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/hourly-reports` | No | List hourly report files. Query: `?limit=`, `?offset=` |
| GET | `/api/hourly-reports/:filename` | No | Get a specific hourly report content |

---

## Calendar

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/calendar/people` | No | List agents as calendar people |
| GET | `/api/calendar/events` | No | Calendar events from Signal integration. Query: `?person=` |

---

## Claude Agent Configuration

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/agents/claude-config` | No | Read per-agent profile/model/effort settings |
| PUT | `/api/agents/claude-config/all` | No | Apply same profile/model/effort to all agents |
| PUT | `/api/agents/:name/claude-config` | No | Update single agent profile/model/effort |

> **NOT IMPLEMENTED**: `GET /api/agents/wrapper-status` and `GET /api/claude-agent/config` — referenced in earlier docs but no corresponding routes in server.js.

---

## Model Configuration (Settings)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/settings/models` | Yes | Get all model configurations (per-agent + global) |
| PUT | `/api/settings/models/agent/:agent` | Yes | Update single agent model config |
| PUT | `/api/settings/models/all` | Yes | Apply same model to all agents |
| POST | `/api/settings/models/backup` | Yes | Create timestamped backups of all config files |
| GET | `/api/settings/models/files` | Yes | Read a config file content. Query: `?path=` (restricted to `~/.openclaw/agents/` and `~/.openclaw/openclaw.json`) |
| PUT | `/api/settings/models/files` | Yes | Update a config file (JSON validated). Query: `?path=` |
| GET | `/api/settings/models/status` | Yes | Get agent model health status (has token, has model, has URL) |

---

## Settings Mode and Model

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/settings/mode` | No | Read current dispatch mode (`auto`, `backup`, `primary`) |
| POST | `/api/settings/mode` | Yes | Update dispatch mode |
| GET | `/api/settings/model` | No | Read current Claude model from primary settings.json |
| POST | `/api/settings/model` | Yes | Update Claude model (restricted to allowed list: `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`) |

---

## Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/sessions` | No | List session JSONL files across agents. Query: `?agent=`, `?status=` (active/drifted/stale/reset/backup), `?limit=`, `?offset=` |
| GET | `/api/sessions/:agent/:filename` | No | Get session details with parsed JSONL events. Query: `?tail=N` for last N events |
| GET | `/api/sessions/:agent/:filename/stream` | Yes | SSE stream for live session events (500ms poll) |
| GET | `/api/sessions/active` | No | Currently running claude-agent processes with model, task, duration |
| POST | `/api/sessions/trigger` | No | Manually trigger a Kurultai reflection session |

---

## Dispatch Contexts

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/acp-contexts` (alias: `/api/dispatch-contexts`) | No | List task execution contexts from task-ledger.jsonl. Query: `?status=`, `?limit=`, `?offset=` |
| GET | `/api/acp-contexts/:taskId` | No | Get specific task context with all ledger events |
