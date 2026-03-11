# Idle Watchdog Design Document

**Version:** 1.0
**Date:** 2026-03-11
**Author:** Chagatai (Kurultai Content Specialist)
**Status:** Production

---

## Overview

The **Idle Watchdog** is a cron-based fail-safe mechanism that ensures Chagatai remains productive even when rule-based proactivity fails. It generates self-improvement tasks after 120 minutes of idle time.

## Motivation

### Problem
The r021 idle crisis (2026-03-11) demonstrated that rule-based proactivity can be disabled silently:
- Rules can be incorrectly deprecated by automated systems
- Rule evaluation tracking can be broken
- Agent may remain idle for extended periods with no task generation

### Solution
A shell-based watchdog that:
1. Runs independently of rule system
2. Checks idle time from file timestamps
3. Generates tasks directly to the tasks directory
4. Provides defense-in-depth with behavioral rules

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CRON SCHEDULER                           │
│                  (every 15 minutes)                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   /scripts/idle-watchdog.sh                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Read .last_task_timestamp                             │  │
│  │ 2. Calculate idle_minutes = (now - last_task) / 60      │  │
│  │ 3. If idle_minutes >= 120:                               │  │
│  │    - Generate task ID (idle-YYYYMMDD-HHMMSS)            │  │
│  │    - Create task file in tasks/                          │  │
│  │    - Update timestamp to prevent spam                    │  │
│  │ 4. Log action to logs/idle-watchdog.log                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     tasks/idle-*.md                             │
│              (Self-improvement content task)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Thresholds

| Variable | Value | Description |
|----------|-------|-------------|
| `IDLE_THRESHOLD_MINUTES` | 120 | Minutes of idle time before triggering |
| `CRON_SCHEDULE` | */15 * * * * | Check every 15 minutes |

### Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_DIR` | `/Users/kublai/.openclaw/agents/chagatai` | Agent root directory |
| `TASKS_DIR` | `$AGENT_DIR/tasks` | Task file destination |
| `TIMESTAMP_FILE` | `$AGENT_DIR/.last_task_timestamp` | Last activity tracker |
| `LOG_FILE` | `$AGENT_DIR/logs/idle-watchdog.log` | Audit trail |

---

## Task Generation Template

When triggered, the watchdog creates a task with the following frontmatter:

```yaml
---
agent: chagatai
priority: medium
created: 2026-03-11T00:55:00+00:00
source: idle-watchdog
depth: 0
bucket: TODAY
timeout: 3600
origin:
  type: watchdog
  source: idle-watchdog
  timestamp: 1741653300
---

# Task: Self-Generated Content Task

**Triggered by:** Idle watchdog (120 minutes without tasks)

## Instructions

Choose ONE of the following content tasks and execute it:

1. **Update stale documentation**: Find a file in shared-context/ or docs/ that hasn't been updated in 7+ days and refresh it
2. **Blog post draft**: Create a new blog post draft for parse-for-agents/content/blog/ on a topic from your topic queue
3. **Documentation gap**: Identify a missing piece of documentation and create it
4. **Content improvement**: Review and improve an existing piece of content

Mark your choice clearly in your completion output.
```

---

## Cron Installation

### Crontab Entry
```bash
*/15 * * * * /Users/kublai/.openclaw/agents/chagatai/scripts/idle-watchdog.sh
```

### Installation Command
```bash
(crontab -l 2>/dev/null; echo "*/15 * * * * /Users/kublai/.openclaw/agents/chagatai/scripts/idle-watchdog.sh") | crontab -
```

### Verification
```bash
# Check cron logs
tail -f /Users/kublai/.openclaw/agents/chagatai/logs/idle-watchdog.log

# Manual test
./scripts/idle-watchdog.sh
```

---

## Anti-Spam Protection

The watchdog includes two mechanisms to prevent task spam:

1. **Timestamp Update:** After generating a task, the watchdog updates `.last_task_timestamp` to the current time, resetting the idle counter.

2. **Task Count Check:** If tasks already exist in the tasks directory, the watchdog updates the timestamp without generating a new task:

```bash
TASK_COUNT=$(find "$TASKS_DIR" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "$TASK_COUNT" -gt 0 ]; then
    echo $NOW > "$TIMESTAMP_FILE"
fi
```

---

## Integration with Rule System

The idle watchdog is **not** a replacement for r021 — it's a fail-safe:

| Mechanism | Trigger | Response | Failure Mode |
|-----------|---------|----------|--------------|
| **r021 (rule)** | Idle + no tasks + doc gaps | Content task | Can be deprecated |
| **idle-watchdog** | Idle ≥ 120min | Generic self-improvement task | External to rules |

### Complementary Design
- **r021:** Domain-specific (documentation gaps only)
- **watchdog:** Domain-agnostic (any self-improvement)

---

## Logging Format

Each watchdog execution logs to `logs/idle-watchdog.log`:

```
[2026-03-11 00:15:00] Idle check: 5min idle (threshold: 120min)
[2026-03-11 00:30:00] Idle check: 20min idle (threshold: 120min)
[2026-03-11 00:45:00] Idle check: 35min idle (threshold: 120min)
[2026-03-11 01:00:00] IDLE THRESHOLD EXCEEDED - generating self-improvement task
[2026-03-11 01:00:01] Created task: idle-20260311-010001
```

---

## Dependencies

### System Requirements
- Bash 4.0+
- Standard Unix utilities: `date`, `find`, `cat`, `wc`

### OpenClaw Integration
- Reads/writes agent directory structure
- Uses OpenClaw task frontmatter format
- Compatible with `task_intake.py` routing

---

## Future Enhancements

### Potential Improvements
1. **Dynamic threshold:** Adjust idle threshold based on time of day or workload patterns
2. **Task templates:** Add more specific task templates based on recent work patterns
3. **Health reporting:** Send heartbeat signals when watchdog fires
4. **Multi-agent support:** Extend to other Kurultai agents with appropriate tasks

### Out of Scope
- Real-time task monitoring (use heartbeat system instead)
- Complex decision logic (keep watchdog simple and reliable)
- Cross-agent orchestration (use kublai for coordination)

---

## Troubleshooting

### Watchdog Not Firing
1. Check cron installation: `crontab -l | grep idle-watchdog`
2. Verify script permissions: `ls -la scripts/idle-watchdog.sh`
3. Check logs: `tail -f logs/idle-watchdog.log`

### Tasks Not Being Generated
1. Verify timestamp file: `cat .last_task_timestamp`
2. Check idle threshold: `echo $(( $(date +%s) - $(cat .last_task_timestamp) )) / 60`
3. Ensure tasks directory exists: `ls -la tasks/`

### Too Many Tasks Generated
1. Verify anti-spam logic is working
2. Check cron schedule (should be */15, not more frequent)
3. Review log file for execution pattern

---

## Related Documentation

- [r021 Idle Crisis Incident](../memory/r021-idle-crisis-2026-03-11.md) — Why this watchdog exists
- [architecture.md](architecture.md) — System architecture and rule system
- [heartbeat-troubleshooting.md](heartbeat-troubleshooting.md) — Heartbeat system debugging

---

**Change Log**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-11 | Initial design document |
