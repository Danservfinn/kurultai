# Memory Architecture Reference

**Version:** 1.0
**Date:** 2026-03-07
**Author:** Chagatai (Writer)
**Domain:** Infrastructure / Memory

---

## Overview

Each Kurultai agent maintains persistent memory across sessions through a layered file system. Memory serves three purposes: **behavioral rules** (self-correction), **context** (task continuity), and **daily logs** (reflection history). A separate audit system prevents bloat and contamination.

```
~/.openclaw/agents/<agent>/memory/
  YYYY-MM-DD.md    Daily reflection log (rotated, compacted)
  context.md       Short-term context (loaded into every task)
  rules.json       Structured rule lifecycle (CRUD via rule_registry.py)
  MEMORY.md        Rare; only temujin/tolui use this for persistent notes

~/.claude/projects/-Users-kublai--openclaw-agents-<agent>/memory/
  MEMORY.md        Claude auto-memory (loaded into every conversation)
```

---

## Store 1: Daily Logs (`YYYY-MM-DD.md`)

**Purpose:** Append-only record of hourly reflections, task outcomes, and rule evaluations.

**Written by:** `hourly_reflection.sh` (via Claude reflection output)
**Read by:** `prepare_reflection_context.py` (extracts rules, commitments, failure patterns)

**Lifecycle:**
1. Created at first reflection of the day
2. Grows with each hourly reflection cycle (~2-4KB per reflection)
3. Compacted by `memory_audit.py --fix` when intraday size exceeds 15KB (keeps last 4 sections)
4. Deleted by `memory_audit.py --fix` after 3 days (`DAILY_LOG_MAX_AGE_DAYS`)

**Thresholds:**
| Metric | Warn | Critical |
|--------|------|----------|
| Daily log size | 50KB | 500KB |
| Intraday size | 15KB | — |
| Sections before compact | 4 | — |

**Anti-bloat:** Each reflection appends a `---`-delimited section. When the file exceeds 15KB intraday, `memory_audit.py` keeps only the last 4 sections and prepends a compaction header.

---

## Store 2: Context Files (`context.md`)

**Purpose:** Short-term working memory loaded into every task execution. Contains current role, model, capabilities, and recent work items.

**Written by:** Agents during reflection or task completion
**Read by:** `agent-task-handler.py` (injected into Claude prompt)

**Size limit:** 4KB (`CONTEXT_WARN_KB` in `memory_audit.py`)
**Compaction:** `memory_audit.py --fix` trims "Latest Work" / "Recent Work" sections to last 3 items (`CONTEXT_MAX_RECENT_ITEMS`)

**Best practice:** Keep context.md under 2KB. Only include information needed for the *next* task, not historical records.

---

## Store 3: Rule Registry (`rules.json`)

**Purpose:** Persistent structured storage for WHEN/THEN behavioral rules with full lifecycle tracking.

**Managed by:** `rule_registry.py` (Python API)
**Read by:** `prepare_reflection_context.py` (injects active rules into reflection prompt)

### Rule Lifecycle

```
proposed ──> active ──> deprecated ──> pruned
                │            ▲
                │            │ (auto: max rules reached,
                │            │  never evaluated >24h,
                │            │  duplicate detected)
                └────────────┘
                  (reactivated)
```

### Lifecycle States

| State | Meaning | Transition |
|-------|---------|------------|
| `active` | Rule is enforced; injected into reflections | Created by `add_rule()` or `seed_from_memory()` |
| `deprecated` | No longer enforced; kept for history | Auto: max rules hit, dead rule (>24h, 0 evals), duplicate |
| `pruned` | Marked for eventual deletion | Manual via `deprecate_rule()` with reason |

### Limits

- **Max active rules per agent:** 7 (`MAX_ACTIVE_RULES`)
- **Auto-deprecation:** Rules active >24h with 0 evaluations are flagged as "dead" by `memory_audit.py`
- **Duplicate detection:** Rules with >60% word-level similarity (same agent) or >70% (cross-agent) are flagged

### API (`rule_registry.py`)

```python
from rule_registry import get_active_rules, add_rule, deprecate_rule, seed_from_memory

# Get active rules for reflection injection
rules = get_active_rules("mongke")  # Returns list[str], max 7

# Add a new rule
add_rule("mongke", "WHEN research task THEN validate sources", source="reflection")

# Deprecate a rule
deprecate_rule("mongke", "r003", reason="superseded by r007")

# One-time migration from memory files
count = seed_from_memory("mongke")
```

### Evaluation Tracking

Rules track `follow_count` and `violate_count` via `record_evaluation()`. This data feeds into duplicate resolution (higher-evaluated rules survive) and dead-rule detection.

---

## Store 4: Claude Auto-Memory (`MEMORY.md`)

**Location:** `~/.claude/projects/-Users-kublai--openclaw-agents-<project>/memory/MEMORY.md`

**Purpose:** Automatically loaded by Claude CLI into every conversation context. Contains high-level project knowledge, routing policies, and system architecture notes.

**Key constraint:** Lines after 200 are truncated. Keep concise.

**Ownership:** Each Claude project directory maps to one agent. Cross-agent contamination (agent X's data in agent Y's MEMORY.md) is detected by `memory_audit.py` via header inspection.

**Project-to-agent mapping:** Defined in `memory_audit.py:PROJECT_AGENT_MAP` dictionary.

---

## Memory Audit System (`memory_audit.py`)

Automated health checks and fixes for the entire memory layer.

### Checks Performed

| Check | Severity | What It Detects |
|-------|----------|----------------|
| `contamination` | critical | Wrong agent's data in a MEMORY.md file |
| `rules_json_corrupt` | critical | Unreadable rules.json |
| `size_bloat` | warn/crit | Daily logs >50KB (warn) or >500KB (crit) |
| `intraday_bloat` | warning | Today's log >15KB |
| `context_bloat` | warning | context.md >4KB |
| `rule_bloat` | warning | >7 WHEN/THEN rules in memory files |
| `rules_overflow` | warning | >7 active rules in rules.json |
| `dead_rule` | warning | Active rule >24h with 0 evaluations |
| `duplicate_rule` | warning | >60% similar rules (same agent) |
| `cross_agent_duplicate` | warning | >70% similar rules (different agents) |
| `stale_entries` | info | STALE/struck-through entries not pruned |

### Usage

```bash
# Audit only (read-only)
python3 memory_audit.py

# Machine-readable
python3 memory_audit.py --json

# Auto-fix all issues
python3 memory_audit.py --fix
```

### Fix Actions

| Fix | What It Does |
|-----|-------------|
| `fix_contamination` | Clears and resets contaminated MEMORY.md |
| `fix_dead_rules` | Deprecates never-evaluated rules |
| `fix_duplicate_rules` | Deprecates lower-scored duplicate |
| `fix_size_bloat` | Deletes daily logs older than 3 days |
| `fix_intraday_bloat` | Compacts today's log to last 4 sections |
| `fix_context_bloat` | Trims work history to last 3 items |
| `fix_stale_entries` | Removes STALE/struck lines |
| `fix_old_daily_logs` | Proactive cleanup of aged logs |

---

## Data Flow: Memory in the Reflection Pipeline

```
hourly_reflection.sh
  └─> prepare_reflection_context.py --agent <name>
        ├─ Reads: rules.json (via rule_registry.py)
        ├─ Reads: latest daily log (YYYY-MM-DD.md)
        ├─ Reads: tock/latest.json (system metrics)
        ├─ Queries: Neo4j (7-day failure patterns)
        └─ Outputs: compact markdown injected into reflection prompt
              │
              ▼
        Claude reflection session
              │
              ├─ Appends to: YYYY-MM-DD.md (new section)
              ├─ May update: rules.json (new/deprecated rules)
              └─ May update: context.md (changed priorities)
```

---

## Cross-Agent Visibility

Agents can **read** other agents' memory files but should **only write** to their own:

| File | Read | Write |
|------|------|-------|
| Own `memory/*.md` | Yes | Yes |
| Own `rules.json` | Yes | Yes (via rule_registry.py) |
| Other agent's `memory/` | Yes (for cross-agent awareness) | No |
| Other agent's `rules.json` | Yes (read-only, for audit) | No |
| Shared `main/memory/` | Yes | Kublai only |

**Exception:** `memory_audit.py --fix` writes to all agents' files for maintenance.

---

## Common Issues & Remedies

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Agent repeats same mistake | Rule not in `rules.json` or deprecated | `python3 rule_registry.py list --agent <name>` to check; re-add if missing |
| Reflection context is empty | No daily log or rules.json for today | Check `~/.openclaw/agents/<agent>/memory/` exists |
| Rule shows in reflection but agent ignores it | Rule in daily log but not in `rules.json` | Run `python3 rule_registry.py seed --agent <name>` |
| Context.md is stale | Last update was days ago | Agent should refresh during next reflection |
| Daily log is huge | Too many reflection sections | `python3 memory_audit.py --fix` to compact |
| MEMORY.md has wrong agent's data | Cross-agent contamination | `python3 memory_audit.py --fix` to clear |

---

## Key Constants (all in `memory_audit.py` unless noted)

| Constant | Value | Location |
|----------|-------|----------|
| `MAX_ACTIVE_RULES` | 7 | `rule_registry.py`, `prepare_reflection_context.py` |
| `DAILY_LOG_MAX_AGE_DAYS` | 3 | `memory_audit.py` |
| `SIZE_WARN_KB` | 50 | `memory_audit.py` |
| `SIZE_CRIT_KB` | 500 | `memory_audit.py` |
| `INTRADAY_WARN_KB` | 15 | `memory_audit.py` |
| `INTRADAY_MAX_SECTIONS` | 4 | `memory_audit.py` |
| `CONTEXT_WARN_KB` | 4 | `memory_audit.py` |
| `CONTEXT_MAX_RECENT_ITEMS` | 3 | `memory_audit.py` |
| `DEAD_RULE_AGE_HOURS` | 24 | `memory_audit.py` |
