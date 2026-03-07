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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update
from kurultai_paths import AGENTS_DIR, MAIN_DIR, LOGS_DIR

BASE = str(MAIN_DIR)
AGENT_DIR = str(AGENTS_DIR)
TICKS_FILE = str(LOGS_DIR / "ticks.jsonl")
TOCK_LATEST = str(LOGS_DIR / "tock/latest.json")
ACTIONS_LOG = str(LOGS_DIR / "kublai-actions.log")
COOLDOWN_FILE = str(LOGS_DIR / "action-cooldowns.json")

# Staleness thresholds — skip actions if data is too old
MAX_TICK_AGE_SECS = 600   # 10 minutes (2 missed ticks)
MAX_TOCK_AGE_SECS = 3600  # 60 minutes (2 missed tocks)

# Cooldown periods (seconds) to prevent duplicate task creation
COOLDOWNS = {
    "error_spike": 7200,       # 2 hours
    "service_down": 600,       # 10 min
    "high_cpu": 1800,          # 30 min
    "high_memory": 1800,       # 30 min
    "cron_fix": 3600,          # 1 hour
    "queue_backlog": 1800,     # 30 min
    "agent_stalled": 3600,     # 1 hour
    "task_stall": 3600,        # 1 hour (time-to-first-action)
    "feedback_review": 7200,   # 2 hours
    "queue_audit": 1800,       # 30 min
}

MAX_ACTIONS_PER_CYCLE = 3

# Minimal routing for programmatic actions -- source of truth is kurultai-router SKILL.md
CATEGORY_ROUTING = {
    "infrastructure": "ogedei",
    "code_fix": "temujin",
    "code": "temujin",
    "investigation": "jochi",
    "documentation": "chagatai",
    "research": "mongke",
    "coordination": "kublai",
    "monitoring": "ogedei",
    "security": "jochi",
    "writing": "chagatai",
    "ops": "ogedei",
}

def route_by_category(category):
    """Route by pre-classified category string. Returns agent name."""
    return CATEGORY_ROUTING.get(category.lower(), "kublai")

def route_by_text(text):
    """Lightweight keyword routing for programmatic task creation."""
    from task_intake import route_by_text as _route
    return _route(text)


def has_pending_task(agent, title_prefix):
    """Check if an agent already has an uncompleted task with this title prefix."""
    task_dir = f"{AGENT_DIR}/{agent}/tasks"
    if not os.path.exists(task_dir):
        return False
    for fname in os.listdir(task_dir):
        if fname.endswith('.done') or fname.endswith('.done.md'):
            continue
        fpath = os.path.join(task_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read(500)
            if f"# Task: {title_prefix}" in content:
                return True
        except Exception:
            continue
    return False


def _file_age_secs(path):
    """Return age of file in seconds, or infinity if missing."""
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return float('inf')


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(ACTIONS_LOG), exist_ok=True)
        with open(ACTIONS_LOG, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass  # Disk full — stdout still works for cron capture


def load_cooldowns():
    return locked_json_read(COOLDOWN_FILE, default={})


def save_cooldowns(cooldowns):
    with locked_json_update(COOLDOWN_FILE) as data:
        data.clear()
        data.update(cooldowns)


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


def create_task(agent, priority, title, body, source="kublai-actions", depth=0,
                skill_hint=None, force_claude_code=True):
    """Create a task via canonical task_intake pipeline.

    Delegates to task_intake.create_task() for Neo4j + filesystem creation,
    duplicate checking, and depth limiting.
    """
    from task_intake import create_task as _intake_create
    result = _intake_create(
        title=title,
        body=body,
        priority=priority,
        source=source,
        depth=depth,
        agent=agent,
        skip_duplicate_check=True,  # callers already check has_pending_task
        skill_hint=skill_hint,
        force_claude_code=force_claude_code,
    )
    if result:
        log(f"ACTION: Created {priority} task for {agent}: {title} (depth={depth})")
    return result


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

    # Staleness check — warn if tick data is too old
    tick_age = _file_age_secs(TICKS_FILE)
    if tick_age > MAX_TICK_AGE_SECS:
        log(f"TICK: WARNING — ticks.jsonl is {tick_age:.0f}s old (tick may be failing)")
    tick_epoch = tick.get("epoch", 0)
    if tick_epoch and (time.time() - tick_epoch) > MAX_TICK_AGE_SECS:
        log(f"TICK: WARNING — last tick record is {time.time()-tick_epoch:.0f}s old")

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
    if fatal_5m > 0 and not is_cooled_down("error_spike:fatal") and not has_pending_task("jochi", "Investigate FATAL"):
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
    elif errors_5m > 50 and not is_cooled_down("error_spike:high") and not has_pending_task("jochi", "Investigate error spike"):
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
        if services.get(svc) == "down" and not is_cooled_down(f"service_down:{svc}") and not has_pending_task("ogedei", f"Restart {svc}"):
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
    if cpu > 80 and not is_cooled_down("high_cpu") and not has_pending_task("ogedei", "Investigate high CPU"):
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
    if rss_mb > 900 and not is_cooled_down("high_memory") and not has_pending_task("ogedei", "Investigate high memory"):
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

    # Rule 6: Time-to-first-action stall detection
    if actions_created < MAX_ACTIONS_PER_CYCLE:
        try:
            from stall_detector import detect_stalls
            stall_warnings = detect_stalls()
            for warning in stall_warnings:
                # Parse agent name from "STALL_WARNING: <agent> idle ..."
                parts = warning.split()
                if len(parts) >= 2:
                    stalled_agent = parts[1]
                else:
                    continue
                cooldown_key = f"task_stall:{stalled_agent}"
                # Route investigation away from the stalled agent
                target = "kublai" if stalled_agent == "jochi" else "jochi"
                if not is_cooled_down(cooldown_key) and not has_pending_task(target, f"Investigate stalled task:") and actions_created < MAX_ACTIONS_PER_CYCLE:
                    create_task(
                        target, "normal",
                        f"Investigate stalled task: {stalled_agent} has idle task with no workspace output",
                        f"""## Context
{warning}

An active task has been sitting for over 60 minutes with no workspace artifact produced.
This likely indicates a stuck execution, a task that was never picked up, or a silent failure.

## Action Required
1. Check {stalled_agent}'s task directory for the stalled task file
2. Check task-watcher logs for dispatch/execution errors: `~/.openclaw/agents/main/logs/task-watcher.log`
3. Check if the agent's Claude Code process is running: `pgrep -f "claude.*{stalled_agent}"`
4. Either re-queue the task, cancel it, or escalate
5. Report findings
""",
                        source="stall-detector",
                    )
                    mark_fired(cooldown_key)
                    actions_created += 1
        except ImportError:
            pass  # stall_detector not available
        except Exception as e:
            log(f"TICK: stall detection error: {e}")

    if actions_created >= MAX_ACTIONS_PER_CYCLE:
        log(f"TICK: hit MAX_ACTIONS_PER_CYCLE={MAX_ACTIONS_PER_CYCLE}, stopping early")

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

    # Staleness check — skip entirely if tock data is too old
    tock_age = _file_age_secs(TOCK_LATEST)
    if tock_age > MAX_TOCK_AGE_SECS:
        log(f"TOCK: WARNING — latest.json is {tock_age:.0f}s old, skipping stale data")
        return 0

    actions_created = 0
    agents = tock.get("agents", {})
    cron = tock.get("cron", {})
    queues = tock.get("queues", {})
    assessment = tock.get("llm_assessment", {})

    # Log when running on heuristic fallback (LLM unavailable)
    if assessment.get("model") == "heuristic-fallback":
        log("TOCK: WARNING — LLM assessment unavailable, using heuristic fallback")

    # Rule 1: Cron jobs erroring repeatedly
    for job in cron.get("jobs", []):
        consec = job.get("consecutive_errors", 0)
        name = job.get("name", "?")
        if consec >= 3 and not is_cooled_down(f"cron_fix:{name}") and not has_pending_task("temujin", f"Fix cron job: {name}") and actions_created < MAX_ACTIONS_PER_CYCLE:
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

    # Rule 2: Queue backlog — log only (creating tasks worsens backlog)
    total_pending = queues.get("total_pending", 0)
    if total_pending > 10 and not is_cooled_down("queue_backlog"):
        by_agent = queues.get("by_agent", {})
        backlog_detail = ", ".join(
            f"{a}={c}" for a, c in by_agent.items() if c > 0
        )
        log(f"TOCK: queue_backlog detected: {total_pending} pending ({backlog_detail}) — logging only, not creating task")
        mark_fired("queue_backlog")

    # Rule 2b: Queue audit — fake completions detected
    queue_audit = tock.get("queue_audit", {})
    audit_requeued = queue_audit.get("requeued", 0)
    audit_fake = queue_audit.get("fake_found", 0)
    if audit_requeued > 0:
        log(f"TOCK: queue_audit auto-fixed {audit_requeued} fake completion(s)")
    if audit_fake > 3 and not is_cooled_down("queue_audit") and not has_pending_task("ogedei", "Investigate task queue") and actions_created < MAX_ACTIONS_PER_CYCLE:
        create_task(
            "ogedei", "high",
            f"Investigate task queue: {audit_fake} fake completions detected",
            f"""## Context
The queue audit detected {audit_fake} tasks marked as "done" that were never
actually executed by Claude Code. {audit_requeued} were automatically re-queued.

## Action Required
1. Check task-watcher logs for execution errors
2. Verify Claude Code (claude-agent) is functioning
3. Review workspace result files for agents with fake completions
4. Ensure the execution chain is working: task-watcher -> agent-task-handler -> claude-agent
5. Report findings to Kublai
"""
        )
        mark_fired("queue_audit")
        actions_created += 1

    # Rule 3: Agent stalled — route to jochi (analyst) for investigation
    # NEVER route to the stalled agent itself (causes deadlock — see circular triage bug 2026-03-05)
    # Cross-validate tock queue_depth against filesystem to avoid false alarms from stale Neo4j data
    for name, data in agents.items():
        t = data.get("tasks", {})
        queue_depth = t.get("queue_depth", 0)
        completed = t.get("completed", 0)
        running = t.get("running", 0)
        if queue_depth > 0 and completed == 0 and running == 0:
            # Filesystem cross-validation: tock queue_depth can be stale (from Neo4j).
            # Count actual pending .md files (not .done, not .executing) before alerting.
            fs_pending = 0
            agent_task_dir = f"{AGENT_DIR}/{name}/tasks"
            if os.path.exists(agent_task_dir):
                for fname in os.listdir(agent_task_dir):
                    if '.done' in fname or fname.startswith('.') or '.executing' in fname:
                        continue
                    if fname.endswith('.md'):
                        fs_pending += 1
            if fs_pending == 0:
                log(f"TICK: stall alert suppressed for {name} — tock reports queue_depth={queue_depth} but filesystem has 0 pending tasks (stale Neo4j data)")
                continue
            # Guard: if jochi is stalled, route to kublai instead (prevent self-routing deadlock)
            target = "kublai" if name == "jochi" else "jochi"
            if not is_cooled_down(f"agent_stalled:{name}") and not has_pending_task(target, f"Triage stalled agent: {name}") and actions_created < MAX_ACTIONS_PER_CYCLE:
                create_task(
                    target, "normal",
                    f"Triage stalled agent: {name} has {queue_depth} queued tasks with 0 completions",
                    f"""## Context
Agent {name} has {queue_depth} tasks in file queue but 0 completions
in the last 30 minutes and nothing currently running.

## Action Required
1. Review {name}'s pending tasks
2. Determine if tasks should be redistributed or if there's a blocker
3. Take corrective action (reassign, cancel stale tasks, or investigate)
4. Report findings to kublai for coordination
"""
                )
                mark_fired(f"agent_stalled:{name}")
                actions_created += 1

    # Rule 4: LLM assessment says HIGH or CRITICAL
    # Route to jochi (analyst), NOT kublai — kublai is often idle when this fires,
    # creating a circular deadlock (see circular triage bug 2026-03-05)
    severity = assessment.get("severity", "LOW")
    if severity in ["HIGH", "CRITICAL"] and not is_cooled_down("tock_severity") and not has_pending_task("jochi", "Tock assessment:") and actions_created < MAX_ACTIONS_PER_CYCLE:
        action = assessment.get("recommended_action", "unknown")
        bottleneck = assessment.get("bottleneck", "unknown")
        create_task(
            "jochi", "high",
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

    if actions_created >= MAX_ACTIONS_PER_CYCLE:
        log(f"TOCK: hit MAX_ACTIONS_PER_CYCLE={MAX_ACTIONS_PER_CYCLE}, stopping early")

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
        from neo4j_task_tracker import get_driver
        driver = get_driver()

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
                if priority in ["CRITICAL", "HIGH"] and actions_created < MAX_ACTIONS_PER_CYCLE:
                    # Determine target agent based on feedback content
                    target = _route_feedback(feedback_text)
                    task_priority = "high" if priority == "CRITICAL" else "normal"

                    if not is_cooled_down(f"feedback_review:{fb_id}") and not has_pending_task(target, "Implement feedback from"):
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
    """Route feedback to the appropriate agent based on content.
    Delegates to canonical task_router.
    """
    agent = route_by_text(text)
    return agent if agent != "subagent" else "kublai"


def main():
    parser = argparse.ArgumentParser(description="Kublai Actions — checkpoint action engine")
    parser.add_argument("--trigger", required=True, choices=["tick", "tock", "kurultai"],
                        help="Which checkpoint triggered this")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without creating tasks")
    args = parser.parse_args()

    try:
        if args.trigger == "tick":
            count = tick_actions()
        elif args.trigger == "tock":
            count = tock_actions()
        elif args.trigger == "kurultai":
            count = kurultai_actions()
        else:
            count = 0
    except Exception as e:
        log(f"FATAL: Unhandled exception in {args.trigger}_actions: {e}")
        count = 0

    print(f"ACTIONS: {count} task(s) created")
    return count


if __name__ == "__main__":
    main()
