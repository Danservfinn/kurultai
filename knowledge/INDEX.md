# Knowledge Base Index

Operational reference documentation for the Kurultai multi-agent system.
All files are derived from source code and configuration, not generated from assumptions.

---

## Reference Documents

### [api-endpoints.md](api-endpoints.md)
Complete reference of all HTTP API endpoints served by the Kurultai dashboard server (`server.js`). Covers 60+ endpoints organized by domain: task management, agent status, reflections, sessions, settings, providers, calendar, dispatch contexts, and more. Includes method, path, auth requirements, request/response format.

### [neo4j-schema.md](neo4j-schema.md)
Documents the Neo4j graph database schema used for task storage, proposal voting, and ASMR memory extraction. Covers Task (25+ properties), Event (task lifecycle), AgentMetrics, Inference (multi-label: PersonalFact, Preference, CalendarEvent, TemporalSeq), Proposal (tiered approval: T0/T1/T2/T3), and Vote node types. Includes the [:SUPERSEDES] audit chain, status mapping, common Cypher patterns, indexes/constraints, WAL buffering, and the legacy filesystem fallback.

### [provider-fallback.md](provider-fallback.md)
Explains the LLM provider fallback chain: how the `claude-agent` wrapper script works, the three dispatch modes (auto/backup/primary), primary vs backup settings files, retryable error detection, the credential vault structure, session logging, and how the UI controls routing. Covers the full flow from mode.json through provider selection.

### [task-executor.md](task-executor.md)
Documents the unified task executor (`task_executor.py`) that replaced `task-watcher.py` and `agent-task-handler.py`. Covers the 6-component architecture (data types, SessionManager, TaskRunner, verify_result gate, build_agent_env, Executor loop), module constants, dependencies, observability (file-based + graph-based), key design decisions, and the **post-completion hook** (`post_completion_hook.py`) that auto-queues follow-up tasks declared by completing agents.

### [agent-roster.md](agent-roster.md)
Documents all 7 agents (kublai, temujin, mongke, chagatai, jochi, ogedei, tolui) with their roles, executor type, workdir, domains, specialist skills, overflow routing, hard rules, completion templates, and key projects. Includes shared infrastructure: horde skills, R008 mandatory skill invocation, task execution (unified executor), completion gates, ASMR memory extraction, context profile builder, task file format, and per-agent directory structure.

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
| Task execution and lifecycle | [task-executor.md](task-executor.md), [neo4j-schema.md](neo4j-schema.md), [api-endpoints.md](api-endpoints.md) |
| Task observability (Events, Metrics) | [neo4j-schema.md](neo4j-schema.md), [task-executor.md](task-executor.md) |
| Follow-up task auto-queuing (post-completion hook) | [task-executor.md](task-executor.md) |
| ASMR memory extraction | [neo4j-schema.md](neo4j-schema.md), [agent-roster.md](agent-roster.md) |
| Context profiles | [agent-roster.md](agent-roster.md) |
| Inference nodes and supersede chains | [neo4j-schema.md](neo4j-schema.md) |
| Authentication | [api-endpoints.md](api-endpoints.md), [provider-fallback.md](provider-fallback.md) |
| Reflections system | [api-endpoints.md](api-endpoints.md), [dashboard-views.md](dashboard-views.md) |
| Proposal voting pipeline | [neo4j-schema.md](neo4j-schema.md) |
| Tiered approval (T0-T3) | [neo4j-schema.md](neo4j-schema.md) |
| WAL and outage resilience | [task-executor.md](task-executor.md), [neo4j-schema.md](neo4j-schema.md) |

## Last Updated

2026-03-23 -- Added post-completion hook section to task-executor.md; updated INDEX with follow-up hook entry.
2026-03-23 -- Created task-executor.md. Updated neo4j-schema.md with Event, AgentMetrics, Inference multi-label nodes, [:SUPERSEDES] chain, and new indexes/constraints. Updated agent-roster.md with unified executor, ASMR extraction, and context profile builder. Updated provider-fallback.md vault reference.
2026-03-23 -- Added Proposal/Vote node types and tiered approval pipeline (T0-T3) to neo4j-schema.md.
2026-03-19 -- Updated provider-fallback, api-endpoints, dashboard-views for OpenRouter provider and auth fix.

---

## How to Use

- Check this index for available topics before researching
- Read specific knowledge files for operational details
- Files are derived from: `server.js`, `neo4j.js`, `kurultai.json`, `claude-agent`, `provider.env`, `mode.json`, `settings.json`, `task_executor.py`, `neo4j_v2_events.py`, `asmr_extractor.py`, `context_profile.py`, `supersede_detector.py`, `asmr_schema_validator.py`, `parallel_memory_search.py`, and agent `CLAUDE.md` files
- To update: re-read source files and revise the corresponding knowledge file
