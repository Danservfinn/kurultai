# Knowledge Base Index

Operational reference documentation for the Kurultai multi-agent system.
All files are derived from source code and configuration, not generated from assumptions.

---

## Reference Documents

### [api-endpoints.md](api-endpoints.md)
Complete reference of all HTTP API endpoints served by the Kurultai dashboard server (`server.js`). Covers 60+ endpoints organized by domain: task management, agent status, reflections, sessions, settings, providers, calendar, dispatch contexts, and more. Includes method, path, auth requirements, request/response format.

### [neo4j-schema.md](neo4j-schema.md)
Documents the Neo4j graph database schema used for task storage. Covers the Task node type with all 25+ properties, status mapping (PENDING/WORKING/COMPLETED/FAILED to kanban columns), and common Cypher query patterns used throughout the codebase (load board, redistribute tasks, retry, pause/resume, reorder, etc.). Also documents the legacy filesystem fallback.

### [provider-fallback.md](provider-fallback.md)
Explains the LLM provider fallback chain: how the `claude-agent` wrapper script works, the three dispatch modes (auto/backup/primary), primary vs backup settings files, retryable error detection, the credential vault structure, session logging, and how the UI controls routing. Covers the full flow from mode.json through provider selection.

### [agent-roster.md](agent-roster.md)
Documents all 7 agents (kublai, temujin, mongke, chagatai, jochi, ogedei, tolui) with their roles, executor type, workdir, domains, specialist skills, overflow routing, hard rules, completion templates, and key projects. Includes shared infrastructure: horde skills, R008 mandatory skill invocation, completion gates, task file format, and per-agent directory structure.

### [dashboard-views.md](dashboard-views.md)
Documents each tab/view in the Kurultai dashboard (Kanban, Calendar, Reflections, Wrappers, Sessions, Dispatch, Settings) with what data they show, which API endpoints they call, and what user actions are available. Includes CORS configuration and security headers.

---

## By Topic

| Topic | File |
|-------|------|
| API reference | [api-endpoints.md](api-endpoints.md) |
| Database schema | [neo4j-schema.md](neo4j-schema.md) |
| LLM providers and fallback | [provider-fallback.md](provider-fallback.md) |
| Agent roles and configuration | [agent-roster.md](agent-roster.md) |
| Dashboard UI | [dashboard-views.md](dashboard-views.md) |
| Task lifecycle | [neo4j-schema.md](neo4j-schema.md), [api-endpoints.md](api-endpoints.md) |
| Authentication | [api-endpoints.md](api-endpoints.md), [provider-fallback.md](provider-fallback.md) |
| Reflections system | [api-endpoints.md](api-endpoints.md), [dashboard-views.md](dashboard-views.md) |

## Last Updated

2026-03-19 -- Updated provider-fallback, api-endpoints, dashboard-views for OpenRouter provider and auth fix.

---

## How to Use

- Check this index for available topics before researching
- Read specific knowledge files for operational details
- Files are derived from: `server.js`, `neo4j.js`, `kurultai.json`, `claude-agent`, `provider.env`, `mode.json`, `settings.json`, and agent `CLAUDE.md` files
- To update: re-read source files and revise the corresponding knowledge file
