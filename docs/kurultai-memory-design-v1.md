# Kurultai Memory Design v1

Date: 2026-04-29
Status: Draft
Origin: Group-chat design discussion about Mercury/Karpathy-style memory and Kurultai agent-scale memory needs

## Purpose

Kurultai needs a memory architecture that preserves human readability while giving agents fast, reliable, token-aware operational memory.

The design principle:

> Markdown is the human control plane. Structured memory is the agent execution plane.

The goal is not to remember more. The goal is to remember correctly, cheaply, selectively, and when useful.

---

## 1. Split Memory Into Three Layers

### A. Human-Owned Files

Examples:

- `SOUL.md`
- `AGENTS.md`
- `USER.md`
- journals
- reports
- design docs

Purpose:

- readable
- editable
- inspectable
- versionable
- human-owned control plane

These files define identity, policy, narrative context, and high-level intent.

### B. Structured Agent Memory

Queryable records for:

- facts
- preferences
- decisions
- task state
- agent state
- entities
- relationships
- blockers
- supersessions

Purpose:

- operational truth for agents
- deterministic retrieval
- low-token context assembly
- reliable updates
- conflict detection

Agents should not rely on rereading prose and inferring state when structured answers are possible.

### C. Generated Summaries

Markdown views generated from structured memory:

- daily summary
- agent status
- project state
- open decisions
- stale memories
- contradiction reports

Purpose:

- human-readable mirrors
- audit trails
- review surfaces

Generated summaries are not the source of truth. They are interfaces over structured state.

---

## 2. Memory Record Metadata

Every structured memory record should carry enough metadata to support scoring, conflict resolution, retrieval, and decay.

Minimum schema:

```json
{
  "id": "...",
  "type": "preference | decision | fact | task_state | relationship | note",
  "subject": "...",
  "value": "...",
  "source": "user | agent | tool | file | system",
  "source_ref": "...",
  "created_at": "...",
  "updated_at": "...",
  "confidence": 0.0,
  "importance": 0.0,
  "freshness": 0.0,
  "reinforcement_count": 0,
  "expires_at": null,
  "supersedes": [],
  "superseded_by": null,
  "visibility": "human | agent | private | system",
  "owner": "kublai | hermes | temujin | mongke | chagatai | jochi | ogedei | tolui",
  "tags": []
}
```

Recommended additions for later versions:

- `scope`: global, user, project, agent, task
- `valid_from`
- `valid_until`
- `last_accessed_at`
- `access_count`
- `embedding_id`
- `graph_node_id`
- `audit_log_refs`

---

## 3. Retrieval Should Answer Questions, Not Dump Notes

Agents should query memory for precise answers, for example:

- latest valid user preference about notifications
- active blocked tasks for a specific agent
- decisions related to memory architecture
- facts superseded in the last 7 days
- context that should be injected for a given task
- changes since an agent's last heartbeat

The memory layer should return ranked records with citations/source references, not raw folders.

Retrieval should support both:

1. deterministic structured queries for known memory types
2. semantic search for fuzzy related context

Semantic retrieval should assist discovery, but canonical answers should come from structured state when possible.

---

## 4. Conflict Resolution Rules

Default hierarchy:

1. Explicit user instruction wins.
2. Newer user instruction beats older user instruction.
3. Higher-confidence structured record beats lower-confidence inferred record.
4. Architecture docs beat casual agent guesses.
5. Runtime/tool state beats stale written status.
6. If conflict remains and impact is high, ask Danny.

No silent contradiction.

Conflicts should produce explicit records, not be left as hidden ambiguity.

Suggested conflict record fields:

```json
{
  "id": "...",
  "type": "conflict",
  "records": ["memory_a", "memory_b"],
  "detected_at": "...",
  "severity": "low | medium | high",
  "resolution": "newer_wins | higher_confidence_wins | user_resolved | unresolved",
  "resolved_by": "agent | user | system",
  "resolved_at": null
}
```

---

## 5. Decay Model

Not all memory should live equally forever.

Suggested policies:

| Memory Type | Decay Policy |
| --- | --- |
| Preferences | Decay slowly; supersede explicitly |
| Task state | Expires or updates aggressively |
| Operational status | Very short TTL |
| Decisions | Durable, but can be superseded |
| Reports/journals | Archived and searchable, not injected by default |
| Agent observations | Medium TTL unless reinforced |

Decay should affect retrieval ranking and injection eligibility before deletion.

Possible states:

- active
- weakened
- archived
- superseded
- expired
- deleted, only when safe and explicitly allowed

---

## 6. Injection Policy

Context injection should be role-aware and task-aware.

For each run, inject only the smallest useful memory set:

- identity/mandate essentials
- current task state
- latest relevant user preferences
- active decisions related to the task
- recent conflicts/blockers
- top relevant memories by score

Everything else remains retrievable but out of context.

Injection should optimize for:

- relevance
- freshness
- confidence
- importance
- token budget
- task intent
- agent role

Agents should receive context because it is useful, not because it exists.

---

## 7. Kurultai-Specific Architecture

Recommended direction:

- Keep Markdown as the human interface.
- Use Neo4j for relationships and task/agent graph.
- Add a structured memory table/store for canonical memory records.
- Add embeddings for semantic retrieval, but never rely on embeddings alone.
- Add deterministic queries for preferences, task state, decisions, and conflicts.
- Generate Markdown reports from structured memory nightly or after major events.

Likely storage split:

| Layer | Candidate Store | Purpose |
| --- | --- | --- |
| Human docs | Markdown/git | Identity, policy, reports, review |
| Graph | Neo4j | Agents, tasks, entities, relationships, dependencies |
| Structured records | SQLite/Postgres/JSONL-backed service | Canonical facts, preferences, decisions, state |
| Semantic index | vector index | fuzzy retrieval and discovery |
| Audit log | append-only JSONL | traceability and replay |

---

## 8. Proposed Agent-Facing Queries

Examples:

```text
memory.latest_preference(subject, scope?)
memory.active_tasks(agent?, project?)
memory.blockers(agent?, older_than?)
memory.related_decisions(topic, include_superseded=false)
memory.context_for_task(task_id, agent, token_budget)
memory.changed_since(agent_id, timestamp)
memory.detect_conflicts(scope?)
memory.supersede(old_record_id, new_record_id, reason)
memory.reinforce(record_id, source_ref)
memory.archive(record_id, reason)
```

These queries should return concise records with source references and confidence metadata.

---

## 9. Failure Modes to Guard Against

- Memory dumps masquerading as retrieval
- stale preferences overriding newer ones
- agent-inferred facts competing with user-authored facts
- embeddings returning semantically similar but operationally wrong memories
- Markdown summaries drifting from structured truth
- duplicate records without supersession links
- unbounded writes from autonomous agents
- no audit trail for memory changes
- hidden contradictions
- injecting private/system-only memory into the wrong context

---

## 10. Implementation Path

### Phase 1: Define Canonical Schema

- memory record schema
- conflict record schema
- scoring fields
- source/visibility model
- TTL/decay policy by type

### Phase 2: Build Minimal Structured Store

- create append-only memory log
- create active canonical record view
- support deterministic queries for preferences, decisions, task state, and blockers

### Phase 3: Add Retrieval API

- latest preference
- related decisions
- task context
- changed-since
- conflict detection

### Phase 4: Add Context Injection

- per-agent role filters
- per-task retrieval
- token budget enforcement
- citations/source refs in injected context

### Phase 5: Generate Human Markdown Views

- daily memory summary
- open conflicts
- stale records
- active decisions
- agent status

### Phase 6: Add Scoring and Decay Automation

- freshness scoring
- reinforcement updates
- expiry/archive transitions
- stale-memory review queue

---

## 11. Open Collaboration Questions

For Hermes/runtime review:

1. What belongs in OpenClaw core versus Kurultai-specific infrastructure?
2. What should the retrieval API look like?
3. How should memory injection happen before each agent run?
4. What additional failure modes should be handled?
5. What storage layer best fits local-first, inspectable, agent-scale operation?

---

## Current Position

Kurultai should not become a pure wiki, nor abandon Markdown.

The target architecture is hybrid:

- Markdown for humans.
- Structured memory for agents.
- Graph relationships for coordination.
- Semantic search for discovery.
- Scored, selective injection for runtime context.
- Explicit conflict resolution and decay.

This makes Kurultai less dependent on note-reading and more capable of compounding operational context reliably over time.
