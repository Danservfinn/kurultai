# Gateway Plugin & Notification Architecture

**Last Updated**: 2026-03-29

---

## Overview

The notification pipeline was rebuilt to replace a broken 3-stage subprocess chain with direct Signal delivery. The system now reliably notifies humans when tasks complete or fail.

---

## Notification Pipeline (Current)

### Completion Path
```
Task COMPLETED in Neo4j
  → ogedei_dispatch._queue_notification(task, agent, duration, content=result)
  → NotificationQueue.enqueue() (SQLite WAL)
  → _notification_loop() every 15s
  → _send_notification_sync():
      1. Query Neo4j for origin_message_id + origin_initiator
      2. signal_send.send(target, message, quote_timestamp, quote_author)
  → Signal DM to human (threaded reply to original request)
```

### Failure Path
```
Task FAILED in Neo4j
  → ogedei_dispatch._handle_failure()
  → _queue_notification(task, agent, 0, content=error, status="failed")
  → Same delivery chain → "[FAILED] agent: title\nReason: ..."
```

### Dual Dispatcher
Both `ogedei_dispatch.py` and `task_executor.py` send notifications:
- `ogedei_dispatch`: via notification_queue with retry + backoff
- `task_executor`: direct send with nqueue fallback on failure

### Spam Prevention
- `origin_type` guard: only notify when `origin_type == "human"` or None (with warning)
- Phone number validation: must start with `+`
- Dead-letter alerting: operator notified after 5 failed attempts

---

## Signal Reply Threading

### How It Works
1. Signal envelope timestamp captured as `raw_msg["message_id"]` in `signal_jsonrpc_server.py`
2. Passed to `_escalate_to_task()` as `message_id` parameter
3. Stored in Neo4j as `origin_message_id` on the Task node
4. On completion, `_send_notification_sync()` queries Neo4j for `origin_message_id`
5. Passes to `signal_send.send()` as `quote_timestamp` + `quote_author`
6. Signal shows the reply threaded under the original request

### signal_send.py API
```python
send(recipient, message, quote_timestamp=None, quote_author=None) -> (int, dict)
# Returns: 0=success, 1=delivery_failure, 2=daemon_unreachable
```

---

## Context Assembler Phase 10: Active Tasks

Added to `context_assembler.py` — queries Task nodes for the human (48h window, LIMIT 5).

```cypher
MATCH (t:Task)
WHERE t.origin_initiator = $phone
  AND t.status IN ['PENDING', 'WORKING', 'COMPLETED', 'FAILED']
  AND t.created > datetime() - duration({hours: 48})
RETURN t.task_id, t.title, t.status, t.assigned_to,
       substring(coalesce(t.solution, ''), 0, 500) AS solution_preview
ORDER BY t.created DESC LIMIT 5
```

Formatted by `context_formatter._format_active_tasks()`.

---

## Notification Queue (SQLite)

**Path**: `~/.openclaw/notifications/queue.db`
**Schema**: `queue` table with columns: id, task_id, agent, notify_target, message, attempts, last_error, created_at, sent_at, status, backoff_until

### Retry Logic
- Max attempts: 5
- Backoff: exponential (2^n minutes: 2, 4, 8, 16, 32)
- `peek()` respects `backoff_until` column
- Dead-letter: alerts operator at `+19194133445` on permanent failure

---

## Gateway Verification (2026-03-29)

### Confirmed Capabilities
- **Plugin SDK**: `api.registerTool()` and `api.on('message_received')` confirmed via TypeScript types
- **Message injection**: `openclaw agent --to <phone> --channel signal --deliver`
- **Signal receive**: Gateway actively receiving via signal-cli at 127.0.0.1:8080
- **Current binding**: Only `tolui` → one Signal group

### For Future Gateway Migration
- Programmatic message injection: use CLI `openclaw agent --deliver`, not HTTP POST
- Plugin tools: use `definePluginEntry()` from `openclaw/plugin-sdk`
- Message hooks: `api.on('message_received', handler)` with typed event context
- 23 lifecycle hooks available for full agent lifecycle interception
