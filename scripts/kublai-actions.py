#!/usr/bin/env python3
"""
Kublai Actions — Rule-based action engine for the 3 checkpoints.

Called after each checkpoint to translate observations into agent tasks.
Creates task files in agent task queues for the task-consumer to dispatch.

Usage:
    python3 kublai-actions.py --trigger tick
    python3 kublai-actions.py --trigger tock
    python3 kublai-actions.py --trigger kurultai
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

BASE = "/Users/kublai/.openclaw/agents/main"
AGENT_DIR = f"{BASE}/agent"
TICKS_FILE = f"{BASE}/logs/ticks.jsonl"
TOCK_LATEST = f"{BASE}/logs/tock/latest.json"
ACTIONS_LOG = f"{BASE}/logs/kublai-actions.log"
COOLDOWN_FILE = f"{BASE}/logs/action-cooldowns.json"

# Cooldown periods (seconds) to prevent duplicate task creation
COOLDOWNS = {
    "error_spike": 1800,       # 30 min
    "service_down": 600,       # 10 min
    "high_cpu": 1800,          # 30 min
    "high_memory": 1800,       # 30 min
    "cron_fix": 3600,          # 1 hour
    "queue_backlog": 1800,     # 30 min
    "agent_stalled": 3600,     # 1 hour
    "feedback_review": 7200,   # 2 hours
}

AGENT_ROUTING = {
    "infrastructure": "ogedei",
    "code_fix": "temujin",
    "investigation": "jochi",
    "documentation": "chagatai",
    "research": "mongke",
    "coordination": "kublai",
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
    with open(ACTIONS_LOG, "a") as f:
        f.write(line + "\n")


def load_cooldowns():
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cooldowns(cooldowns):
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(cooldowns, f, indent=2)


def is_cooled_down(action_key):
    """Check if an action is still in cooldown period."""
    cooldowns = load_cooldowns()
    last_fired = cooldowns.get(action_key, 0)
    cooldown_secs = COOLDOWNS.get(action_key.split(":")[0], 1800)
    return (time.time() - last_fired) < cooldown_secs


def mark_fired(action_key):
    """Mark an action as fired, resetting its cooldown."""
    cooldowns = load_cooldowns()
    cooldowns[action_key] = time.time()
    save_cooldowns(cooldowns)


def create_task(agent, priority, title, body, source="kublai-actions"):
    """Create a task file in an agent's task queue."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    os.makedirs(task_dir, exist_ok=True)

    epoch = int(time.time())
    filename = f"{priority}-{epoch}.md"
    filepath = f"{task_dir}/{filename}"

    content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: {source}
---

# Task: {title}

{body}
"""
    with open(filepath, "w") as f:
        f.write(content)

    log(f"ACTION: Created {priority} task for {agent}: {title}")
    return filepath


# ============================================================
# TICK ACTIONS (every 5 minutes)
# ============================================================
def tick_actions():
    """Rule-based actions from tick (infrastructure) data."""
    # Read latest tick
    if not os.path.exists(TICKS_FILE):
        log("TICK: No ticks.jsonl found, skipping")
        return 0

    with open(TICKS_FILE) as f:
        lines = f.readlines()

    if not lines:
        log("TICK: ticks.jsonl empty, skipping")
        return 0

    try:
        tick = json.loads(lines[-1].strip())
    except json.JSONDecodeError:
        log("TICK: Failed to parse latest tick")
        return 0

    actions_created = 0
    decision = tick.get("decision", "healthy")
    errors_5m = tick.get("errors", {}).get("last_5m", 0)
    errors_1h = tick.get("errors", {}).get("last_1h", 0)
    fatal_5m = tick.get("errors", {}).get("fatal_5m", 0)
    services = tick.get("services", {})
    process = tick.get("process", {})
    gateway = tick.get("gateway", {})
    tasks = tick.get("tasks", {})

    # Rule 1: Fatal errors — immediate high-priority investigation
    if fatal_5m > 0 and not is_cooled_down("error_spike:fatal"):
        create_task(
            "jochi", "high",
            "Investigate FATAL/CRASH errors in gateway log",
            f"""## Context
The tick detected {fatal_5m} FATAL/CRASH errors in the last 5 minutes.
Total errors last 5m: {errors_5m}, last 1h: {errors_1h}.

## Action Required
1. Read the last 200 lines of `~/.openclaw/logs/openclaw.log`
2. Identify the FATAL/CRASH entries
3. Determine root cause
4. Propose fix or escalate to temujin for code changes
"""
        )
        mark_fired("error_spike:fatal")
        actions_created += 1

    # Rule 2: High error rate (non-fatal) — investigate
    elif errors_5m > 50 and not is_cooled_down("error_spike:high"):
        create_task(
            "jochi", "normal",
            f"Investigate error spike: {errors_5m} errors in 5m",
            f"""## Context
The tick detected {errors_5m} errors in the last 5 minutes (1h total: {errors_1h}).
No FATAL errors, but error rate is elevated.

## Action Required
1. Check `~/.openclaw/logs/openclaw.log` for error patterns
2. Determine if this is a transient spike or ongoing issue
3. Report findings and recommend action
"""
        )
        mark_fired("error_spike:high")
        actions_created += 1

    # Rule 3: Service down — create restart task
    for svc in ["neo4j", "redis"]:
        if services.get(svc) == "down" and not is_cooled_down(f"service_down:{svc}"):
            create_task(
                "ogedei", "high",
                f"Restart {svc} — service is DOWN",
                f"""## Context
The tick health check shows {svc} is DOWN.
Gateway status: {gateway.get('status', '?')}, HTTP: {gateway.get('http', '?')}

## Action Required
1. Check if {svc} process is running: `pgrep -f {svc}`
2. If not running, restart it:
   - Neo4j: `brew services restart neo4j` or `neo4j start`
   - Redis: `brew services restart redis` or `redis-server`
3. Verify it's back up
4. Check logs for why it went down
"""
            )
            mark_fired(f"service_down:{svc}")
            actions_created += 1

    # Rule 4: High CPU
    cpu = process.get("cpu_pct", 0)
    if cpu > 80 and not is_cooled_down("high_cpu"):
        create_task(
            "ogedei", "normal",
            f"Investigate high CPU usage: {cpu}%",
            f"""## Context
OpenClaw gateway CPU is at {cpu}%.
Memory: {process.get('mem_pct', 0)}%, RSS: {process.get('rss_kb', 0)}KB

## Action Required
1. Check what's consuming CPU: `top -l 1 -o cpu`
2. Check if there are runaway sessions or loops
3. Report findings
"""
        )
        mark_fired("high_cpu")
        actions_created += 1

    # Rule 5: High memory
    rss_mb = process.get("rss_kb", 0) / 1024
    if rss_mb > 900 and not is_cooled_down("high_memory"):
        create_task(
            "ogedei", "normal",
            f"Investigate high memory usage: {rss_mb:.0f}MB RSS",
            f"""## Context
OpenClaw gateway RSS is {rss_mb:.0f}MB (threshold: 900MB).

## Action Required
1. Check session count and context usage
2. Run `openclaw doctor` for cleanup recommendations
3. Consider restarting gateway if memory is climbing
"""
        )
        mark_fired("high_memory")
        actions_created += 1

    if actions_created == 0:
        log(f"TICK: {decision} — no actions needed")
    else:
        log(f"TICK: {decision} — created {actions_created} action(s)")

    return actions_created


# ============================================================
# TOCK ACTIONS (every 30 minutes)
# ============================================================
def tock_actions():
    """Rule-based actions from tock (agent effectiveness) data."""
    if not os.path.exists(TOCK_LATEST):
        log("TOCK: No latest.json found, skipping")
        return 0

    try:
        with open(TOCK_LATEST) as f:
            tock = json.load(f)
    except Exception as e:
        log(f"TOCK: Failed to parse latest.json: {e}")
        return 0

    actions_created = 0
    agents = tock.get("agents", {})
    cron = tock.get("cron", {})
    queues = tock.get("queues", {})
    assessment = tock.get("llm_assessment", {})

    # Rule 1: Cron jobs erroring repeatedly
    for job in cron.get("jobs", []):
        consec = job.get("consecutive_errors", 0)
        name = job.get("name", "?")
        if consec >= 3 and not is_cooled_down(f"cron_fix:{name}"):
            create_task(
                "temujin", "high",
                f"Fix cron job: {name} ({consec} consecutive errors)",
                f"""## Context
Cron job "{name}" has failed {consec} consecutive times.
Last status: {job.get('status', '?')}
Last duration: {job.get('last_duration_ms', 0)}ms

## Action Required
1. Check the cron job configuration: `openclaw cron list`
2. Try running it manually: `openclaw cron run <job-id>`
3. Check logs for the error
4. Fix the underlying issue (timeout, script error, etc.)
"""
            )
            mark_fired(f"cron_fix:{name}")
            actions_created += 1

    # Rule 2: Queue backlog — tasks piling up
    total_pending = queues.get("total_pending", 0)
    if total_pending > 10 and not is_cooled_down("queue_backlog"):
        by_agent = queues.get("by_agent", {})
        backlog_detail = ", ".join(
            f"{a}={c}" for a, c in by_agent.items() if c > 0
        )
        create_task(
            "kublai", "high",
            f"Rebalance workload: {total_pending} tasks queued",
            f"""## Context
Task queue backlog: {total_pending} total pending.
By agent: {backlog_detail}

## Action Required
1. Review pending tasks for each overloaded agent
2. Determine if tasks can be redistributed to idle agents
3. Check if task-consumer is running properly
4. Consider temporarily increasing task-consumer frequency
"""
        )
        mark_fired("queue_backlog")
        actions_created += 1

    # Rule 3: Agent stalled — has pending tasks but 0 completions in 30m
    for name, data in agents.items():
        t = data.get("tasks", {})
        queue_depth = t.get("queue_depth", 0)
        completed = t.get("completed", 0)
        running = t.get("running", 0)
        if queue_depth > 0 and completed == 0 and running == 0:
            if not is_cooled_down(f"agent_stalled:{name}"):
                create_task(
                    name, "normal",
                    f"Check in: you have {queue_depth} queued tasks with 0 completions",
                    f"""## Context
You ({name}) have {queue_depth} tasks in your file queue but 0 completions
in the last 30 minutes and nothing currently running.

## Action Required
1. List your pending tasks: `ls ~/.openclaw/agents/main/agent/{name}/tasks/*.md`
2. Pick the highest priority task and execute it
3. If you're blocked on something, report the blocker
"""
                )
                mark_fired(f"agent_stalled:{name}")
                actions_created += 1

    # Rule 4: LLM assessment says HIGH or CRITICAL
    severity = assessment.get("severity", "LOW")
    if severity in ["HIGH", "CRITICAL"] and not is_cooled_down("tock_severity"):
        action = assessment.get("recommended_action", "unknown")
        bottleneck = assessment.get("bottleneck", "unknown")
        create_task(
            "kublai", "high",
            f"Tock assessment: {severity} — {bottleneck}",
            f"""## Context
The 30-minute tock assessment flagged severity: {severity}
Bottleneck: {bottleneck}
Workload: {assessment.get('workload_balance', '?')}
Coordination: {assessment.get('coordination_gap', '?')}
Recommended action: {action}

## Action Required
Review the tock data at `~/.openclaw/agents/main/logs/tock/latest.json`
and take the recommended action or delegate to the appropriate agent.
"""
        )
        mark_fired("tock_severity")
        actions_created += 1

    if actions_created == 0:
        log(f"TOCK: severity={severity} — no actions needed")
    else:
        log(f"TOCK: created {actions_created} action(s)")

    return actions_created


# ============================================================
# KURULTAI ACTIONS (every hour)
# ============================================================
def kurultai_actions():
    """Process agent feedback from Neo4j and create implementation tasks."""
    actions_created = 0

    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "myStrongPassword123")
        )

        with driver.session() as session:
            # Get pending feedback sorted by priority
            result = session.run("""
                MATCH (f:AgentFeedback {status: 'pending_review'})
                RETURN f.id AS id, f.agent AS agent, f.feedback AS feedback,
                       f.priority AS priority, f.proposals AS proposals
                ORDER BY
                    CASE f.priority
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'HIGH' THEN 2
                        WHEN 'MEDIUM' THEN 3
                        ELSE 4
                    END
                LIMIT 10
            """)
            feedbacks = [dict(r) for r in result]

            if not feedbacks:
                log("KURULTAI: No pending feedback to review")
                driver.close()
                return 0

            log(f"KURULTAI: Found {len(feedbacks)} pending feedback items")

            for fb in feedbacks:
                fb_id = fb.get("id", "?")
                agent = fb.get("agent", "?")
                priority = fb.get("priority", "MEDIUM")
                feedback_text = fb.get("feedback", "")[:500]

                # Parse proposals if present
                proposals = []
                try:
                    proposals = json.loads(fb.get("proposals", "[]"))
                except Exception:
                    pass

                # Only auto-create tasks for HIGH and CRITICAL
                if priority in ["CRITICAL", "HIGH"]:
                    # Determine target agent based on feedback content
                    target = _route_feedback(feedback_text)
                    task_priority = "high" if priority == "CRITICAL" else "normal"

                    if not is_cooled_down(f"feedback_review:{fb_id}"):
                        create_task(
                            target, task_priority,
                            f"Implement feedback from {agent}: {feedback_text[:60]}",
                            f"""## Agent Feedback (from {agent}, priority: {priority})

{feedback_text}

## Proposals
{json.dumps(proposals, indent=2) if proposals else "No specific proposals"}

## Action Required
1. Review the feedback above
2. Implement the proposed changes if feasible
3. Report results back
"""
                        )
                        mark_fired(f"feedback_review:{fb_id}")
                        actions_created += 1

                        # Mark feedback as actioned in Neo4j
                        session.run("""
                            MATCH (f:AgentFeedback {id: $id})
                            SET f.status = 'actioned',
                                f.actioned_at = datetime(),
                                f.actioned_by = 'kublai-actions'
                        """, id=fb_id)

                else:
                    # MEDIUM/LOW — just mark as reviewed, don't create tasks
                    session.run("""
                        MATCH (f:AgentFeedback {id: $id})
                        SET f.status = 'reviewed',
                            f.reviewed_at = datetime()
                    """, id=fb_id)

        driver.close()

    except ImportError:
        log("KURULTAI: neo4j driver not available")
    except Exception as e:
        log(f"KURULTAI: Error processing feedback: {e}")

    if actions_created == 0:
        log("KURULTAI: no actionable feedback")
    else:
        log(f"KURULTAI: created {actions_created} action(s) from feedback")

    return actions_created


def _route_feedback(text):
    """Route feedback to the appropriate agent based on content."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["infrastructure", "deploy", "restart", "monitor", "cron"]):
        return "ogedei"
    if any(w in text_lower for w in ["code", "implement", "build", "fix", "script", "bug"]):
        return "temujin"
    if any(w in text_lower for w in ["test", "security", "audit", "analyze", "pattern"]):
        return "jochi"
    if any(w in text_lower for w in ["document", "write", "readme", "describe"]):
        return "chagatai"
    if any(w in text_lower for w in ["research", "discover", "api", "explore"]):
        return "mongke"
    return "kublai"


def main():
    parser = argparse.ArgumentParser(description="Kublai Actions — checkpoint action engine")
    parser.add_argument("--trigger", required=True, choices=["tick", "tock", "kurultai"],
                        help="Which checkpoint triggered this")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without creating tasks")
    args = parser.parse_args()

    if args.trigger == "tick":
        count = tick_actions()
    elif args.trigger == "tock":
        count = tock_actions()
    elif args.trigger == "kurultai":
        count = kurultai_actions()
    else:
        count = 0

    print(f"ACTIONS: {count} task(s) created")
    return count


if __name__ == "__main__":
    main()
