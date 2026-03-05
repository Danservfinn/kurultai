#!/usr/bin/env python3
"""
Kurultai Self-Improvement Brainstorming Engine (Claude Code Edition)

Spawns Claude Code (opus) sessions for each agent that run the
/horde-brainstorming skill to generate structured improvement proposals
for the OpenClaw system architecture.

Each agent session receives rich context:
- Last 2 hours of chat history (session transcripts)
- Last 2 hours of system logs (ticks, actions, watchdog)
- Task assignment and execution patterns
- Available skills and their usage
- Previous brainstorm proposals and outcomes (meta-reflection)
- Rotating architectural domain focus

The Claude Code instance is configured per claude-code-setup-v2 so it
gets all horde skills, plugins, and agents.

Usage:
    python3 kurultai_brainstorm.py --agent temujin
    python3 kurultai_brainstorm.py --all
    python3 kurultai_brainstorm.py --agent jochi --dry-run
    python3 kurultai_brainstorm.py --all --domain routing_pipeline
"""

import argparse
import glob as glob_mod
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS, AGENT_ROLES
from json_state import locked_json_read, locked_json_update

BASE = Path.home() / ".openclaw/agents"
MAIN = BASE / "main"
LOG_FILE = MAIN / "logs/kurultai-brainstorm.log"
COOLDOWN_FILE = MAIN / "logs/brainstorm-cooldown.json"
DOMAIN_FILE = MAIN / "logs/brainstorm-domain-rotation.json"

# Claude Code — opus for brainstorming (via claude-agent wrapper)
CLAUDE_AGENT_BIN = os.getenv("CLAUDE_AGENT_BIN", "/Users/kublai/.local/bin/claude-agent")
CLAUDE_MODEL = os.getenv("CLAUDE_BRAINSTORM_MODEL", "opus")
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_BRAINSTORM_TIMEOUT", "300"))
CLAUDE_MAX_BUDGET = os.getenv("CLAUDE_BRAINSTORM_BUDGET", "1.00")

# Cooldown: 55 minutes per agent
BRAINSTORM_COOLDOWN_SECS = 3300

# Context window for history/logs
HISTORY_HOURS = 2

# 6 architectural domains — one per hourly cycle, rotating
DOMAINS = [
    "routing_pipeline",
    "task_dispatch",
    "state_management",
    "heartbeat_system",
    "reflection_pipeline",
    "memory_architecture",
]

DOMAIN_DESCRIPTIONS = {
    "routing_pipeline": (
        "Task routing accuracy, keyword tables in task-router.py, LLM routing "
        "fallback, misclassification patterns, routing table drift across scripts"
    ),
    "task_dispatch": (
        "Task lifecycle: creation via task_intake.py, filesystem queues under "
        "agents/{agent}/tasks/, task-watcher.py dispatch, state machine transitions, "
        "depth limits, duplicate execution prevention"
    ),
    "state_management": (
        "Neo4j + filesystem dual state, json_state.py locking, Task/AgentFeedback/"
        "Hypothesis nodes, data consistency between Neo4j and filesystem"
    ),
    "heartbeat_system": (
        "tick (5min watchdog-gather.sh), tock (30min tock-gather.sh), kurultai "
        "(60min hourly_reflection.sh), timing dependencies between phases, "
        "cron job reliability, data freshness"
    ),
    "reflection_pipeline": (
        "Protocol reflections via meta_reflection.py, brainstorming via this script, "
        "WHEN/THEN rule extraction, commitment tracking, proposal lifecycle, "
        "prepare_reflection_context.py data quality"
    ),
    "memory_architecture": (
        "Agent memory files at ~/.openclaw/agents/{agent}/memory/, WHEN/THEN rule "
        "lifecycle (proposed->active->deprecated->pruned), cross-agent visibility, "
        "knowledge retention vs. file bloat, ACTIVE RULES section management"
    ),
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        os.makedirs(LOG_FILE.parent, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def is_cooled_down(agent):
    """Check if this agent is still in cooldown from last brainstorm."""
    data = locked_json_read(str(COOLDOWN_FILE), default={})
    last = data.get(agent, 0)
    return (time.time() - last) < BRAINSTORM_COOLDOWN_SECS


def mark_fired(agent):
    with locked_json_update(str(COOLDOWN_FILE)) as data:
        data[agent] = time.time()


def get_current_domain():
    """Get the current rotating domain focus. Rotates each hour."""
    data = locked_json_read(str(DOMAIN_FILE), default={"index": 0, "last_rotated": 0})
    now = time.time()
    if now - data.get("last_rotated", 0) > 3500:  # ~58 minutes
        new_index = (data.get("index", 0) + 1) % len(DOMAINS)
        with locked_json_update(str(DOMAIN_FILE)) as d:
            d["index"] = new_index
            d["last_rotated"] = now
        return DOMAINS[new_index]
    return DOMAINS[data["index"] % len(DOMAINS)]


# ── Context Gathering ────────────────────────────────────────────────


def _recent_sessions(agent, max_chars=1500):
    """Extract summary of last 2h of agent chat/session history."""
    sessions_dir = BASE / agent / "sessions"
    if not sessions_dir.exists():
        return "(no sessions directory)"

    cutoff = time.time() - (HISTORY_HOURS * 3600)
    recent_files = []
    for f in sessions_dir.iterdir():
        if f.suffix == ".jsonl" and f.stat().st_mtime > cutoff:
            recent_files.append(f)
    recent_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    if not recent_files:
        return "(no sessions in last 2h)"

    lines = []
    chars = 0
    for sf in recent_files[:3]:  # max 3 recent sessions
        try:
            with open(sf, encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entry = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    etype = entry.get("type", "")
                    # Extract user messages and assistant summaries
                    if etype == "human":
                        text = ""
                        for block in entry.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block["text"][:200]
                                break
                            elif isinstance(block, str):
                                text = block[:200]
                                break
                        if text:
                            lines.append(f"  [user] {text}")
                            chars += len(lines[-1])
                    elif etype == "assistant" and entry.get("message", {}).get("stop_reason") == "end_turn":
                        # Get first text block of final assistant turn
                        for block in entry.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "text":
                                snippet = block["text"][:150]
                                lines.append(f"  [assistant] {snippet}")
                                chars += len(lines[-1])
                                break
                    if chars > max_chars:
                        break
            if chars > max_chars:
                break
        except Exception:
            continue

    return "\n".join(lines[-20:]) if lines else "(sessions exist but no extractable messages)"


def _recent_logs(max_chars=1200):
    """Extract key events from system logs in the last 2 hours."""
    cutoff = time.time() - (HISTORY_HOURS * 3600)
    summaries = []

    # 1. Ticks (system health snapshots)
    ticks_file = MAIN / "logs/ticks.jsonl"
    if ticks_file.exists():
        try:
            recent_ticks = []
            with open(ticks_file, encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        t = json.loads(raw)
                        if t.get("epoch", 0) > cutoff:
                            recent_ticks.append(t)
                    except json.JSONDecodeError:
                        continue
            if recent_ticks:
                last = recent_ticks[-1]
                errors = last.get("errors", {})
                summaries.append(
                    f"  Ticks ({len(recent_ticks)} in 2h): "
                    f"last errors={json.dumps(errors)[:150]}"
                )
        except Exception:
            pass

    # 2. Kublai actions log (tail)
    actions_log = MAIN / "logs/kublai-actions.log"
    if actions_log.exists():
        try:
            lines = actions_log.read_text(encoding="utf-8", errors="replace").split("\n")
            recent = [l for l in lines[-50:] if l.strip()][-10:]
            if recent:
                summaries.append("  Actions (recent):\n" + "\n".join(f"    {l[:120]}" for l in recent))
        except Exception:
            pass

    # 3. Watchdog log (tail)
    watchdog_log = MAIN / "logs/watchdog.log"
    if watchdog_log.exists():
        try:
            lines = watchdog_log.read_text(encoding="utf-8", errors="replace").split("\n")
            recent = [l for l in lines[-30:] if l.strip()][-5:]
            if recent:
                summaries.append("  Watchdog (recent):\n" + "\n".join(f"    {l[:120]}" for l in recent))
        except Exception:
            pass

    # 4. Routing decisions
    routing_log = MAIN / "logs/routing-decisions.jsonl"
    if routing_log.exists():
        try:
            decisions = []
            with open(routing_log, encoding="utf-8", errors="replace") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                        if d.get("timestamp", 0) > cutoff:
                            decisions.append(d)
                    except (json.JSONDecodeError, TypeError):
                        continue
            if decisions:
                summaries.append(
                    f"  Routing decisions ({len(decisions)} in 2h): "
                    + ", ".join(
                        f"{d.get('task','?')[:30]}->{d.get('agent','?')}"
                        for d in decisions[-5:]
                    )
                )
        except Exception:
            pass

    return "\n".join(summaries) if summaries else "  (no recent log activity)"


def _task_patterns():
    """Summarize task assignment and execution across all agents."""
    summaries = []
    for agent in AGENTS:
        task_dir = BASE / agent / "tasks"
        if not task_dir.exists():
            # Also check the main/agent/ path
            task_dir = MAIN / "agent" / agent / "tasks"
        if not task_dir.exists():
            continue
        try:
            pending = list(task_dir.glob("*.md"))
            executing = list(task_dir.glob("*.executing.md"))
            done = list(task_dir.glob("*.done"))
            if pending or executing or done:
                summaries.append(
                    f"  {agent}: pending={len(pending)} executing={len(executing)} done={len(done)}"
                )
                # Show recent pending task titles
                for tf in sorted(pending, key=lambda f: f.stat().st_mtime, reverse=True)[:2]:
                    try:
                        first_line = tf.read_text(encoding="utf-8", errors="replace").split("\n")[0][:80]
                        summaries.append(f"    -> {first_line}")
                    except Exception:
                        pass
        except Exception:
            pass

    # Also check Neo4j for recent task stats
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: 2})
                RETURN t.status AS status, t.agent AS agent, count(t) AS cnt
                ORDER BY cnt DESC
            """)
            neo4j_stats = []
            for r in result:
                neo4j_stats.append(f"  Neo4j: {r['agent']}={r['status']}(x{r['cnt']})")
            if neo4j_stats:
                summaries.extend(neo4j_stats[:6])
        driver.close()
    except Exception:
        pass

    return "\n".join(summaries) if summaries else "  (no task activity found)"


def _skills_summary():
    """List available skills and note which are relevant for improvement."""
    skills_dir = Path.home() / ".claude/skills"
    if not skills_dir.exists():
        return "  (no skills directory)"

    skills = []
    for sd in sorted(skills_dir.iterdir()):
        if sd.is_dir() and (sd / "SKILL.md").exists():
            skills.append(sd.name)

    horde_skills = [s for s in skills if s.startswith("horde-") or s == "golden-horde"]
    kurultai_skills = [s for s in skills if "kurultai" in s]
    other_count = len(skills) - len(horde_skills) - len(kurultai_skills)

    lines = [
        f"  Total: {len(skills)} skills installed",
        f"  Horde skills: {', '.join(horde_skills)}",
        f"  Kurultai skills: {', '.join(kurultai_skills) or '(none)'}",
        f"  Other: {other_count} domain skills (frontend, backend, devops, etc.)",
    ]
    return "\n".join(lines)


def _previous_proposals(agent):
    """Get recent brainstorm proposal history for meta-reflection."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run("""
                MATCH (f:AgentFeedback)
                WHERE f.source = 'kurultai_brainstorm'
                  AND f.agent = $agent
                RETURN f.feedback AS feedback, f.status AS status,
                       f.category AS category, f.effort AS effort,
                       f.submitted AS submitted
                ORDER BY f.submitted DESC
                LIMIT 5
            """, agent=agent)
            proposals = []
            for r in result:
                proposals.append(
                    f"  [{r['status']}] {r['feedback'][:80]} "
                    f"(cat={r['category']}, effort={r['effort']})"
                )
        driver.close()

        # Also get overall stats
        with get_driver().session() as session:
            result = session.run("""
                MATCH (f:AgentFeedback)
                WHERE f.source = 'kurultai_brainstorm'
                RETURN f.status AS status, count(f) AS cnt
            """)
            stats = {r["status"]: r["cnt"] for r in result}

        if proposals or stats:
            lines = [f"  Overall: {json.dumps(stats)}"]
            if proposals:
                lines.append(f"  Your last {len(proposals)} proposals:")
                lines.extend(proposals)
            return "\n".join(lines)

    except Exception:
        pass
    return "  (no previous proposals)"


def gather_context(agent):
    """Gather all relevant context for the agent's brainstorming session."""
    context = {"agent": agent, "role": AGENT_ROLES.get(agent, "Unknown")}

    # 1. Latest reflection from memory
    today = datetime.now().strftime("%Y-%m-%d")
    memory_file = BASE / agent / "memory" / f"{today}.md"
    if memory_file.exists():
        try:
            content = memory_file.read_text(encoding="utf-8", errors="replace")
            blocks = content.split("\n---\n")
            if len(blocks) >= 2:
                context["last_reflection"] = blocks[-2].strip()[-800:]
            else:
                context["last_reflection"] = content[-800:]
        except Exception:
            context["last_reflection"] = "(unreadable)"
    else:
        context["last_reflection"] = "(no reflection today)"

    # 2. Active WHEN/THEN rules
    try:
        from prepare_reflection_context import extract_active_rules, find_latest_memory_file
        mem = find_latest_memory_file(agent)
        context["active_rules"] = extract_active_rules(mem)
    except Exception:
        context["active_rules"] = []

    # 3. Failure patterns from Neo4j (7-day)
    try:
        from prepare_reflection_context import get_failure_patterns
        context["failure_patterns"] = get_failure_patterns(agent, days=7)
    except Exception:
        context["failure_patterns"] = []

    # 4. Tock agent data
    tock_file = MAIN / "logs/tock/latest.json"
    if tock_file.exists():
        try:
            target = tock_file.resolve() if tock_file.is_symlink() else tock_file
            with open(target) as f:
                tock = json.load(f)
            agent_data = tock.get("agents", {}).get(agent, {})
            tasks = agent_data.get("tasks", {})
            context["tock"] = {
                "completed": tasks.get("completed", 0),
                "failed": tasks.get("failed", 0),
                "queue_depth": tasks.get("queue_depth", 0),
                "retries": agent_data.get("retries", 0),
                "success_rate": agent_data.get("success_rate"),
            }
        except Exception:
            context["tock"] = {}
    else:
        context["tock"] = {}

    # 5. Cross-agent system health
    try:
        target = (MAIN / "logs/tock/latest.json").resolve()
        with open(target) as f:
            tock = json.load(f)
        system = tock.get("system", {})
        all_agents = tock.get("agents", {})
        context["system_health"] = {
            "neo4j": system.get("neo4j_status", "unknown"),
            "redis": system.get("redis_status", "unknown"),
            "total_queued": sum(
                a.get("tasks", {}).get("queue_depth", 0)
                for a in all_agents.values()
            ),
            "total_failed": sum(
                a.get("tasks", {}).get("failed", 0)
                for a in all_agents.values()
            ),
        }
    except Exception:
        context["system_health"] = {}

    # 6. Last 2 hours of chat/session history
    context["chat_history"] = _recent_sessions(agent)

    # 7. Last 2 hours of system logs
    context["recent_logs"] = _recent_logs()

    # 8. Task assignment and execution patterns
    context["task_patterns"] = _task_patterns()

    # 9. Available skills
    context["skills_summary"] = _skills_summary()

    # 10. Previous brainstorm proposals (meta-reflection)
    context["previous_proposals"] = _previous_proposals(agent)

    return context


# ── Prompt Building ──────────────────────────────────────────────────


def build_prompt(agent, context, domain):
    """Build the Claude Code prompt that triggers /horde-brainstorming."""
    rules_text = ""
    if context["active_rules"]:
        rules_text = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(context["active_rules"]))
    else:
        rules_text = "  (none)"

    failures_text = ""
    if context["failure_patterns"]:
        failures_text = "\n".join(
            f"  - {p['error'][:100]} (x{p['count']})"
            for p in context["failure_patterns"]
        )
    else:
        failures_text = "  (no recurring failures)"

    tock = context.get("tock", {})
    tock_text = (
        f"  Completed: {tock.get('completed', '?')} | Failed: {tock.get('failed', '?')} | "
        f"Queue: {tock.get('queue_depth', '?')} | Retries: {tock.get('retries', '?')} | "
        f"Success: {tock.get('success_rate', '?')}%"
    )

    system = context.get("system_health", {})
    system_text = (
        f"  Neo4j: {system.get('neo4j', '?')} | Redis: {system.get('redis', '?')} | "
        f"Total queued: {system.get('total_queued', '?')} | Total failed: {system.get('total_failed', '?')}"
    )

    return f"""You are {agent}, the {context['role']} in the OpenClaw/Kurultai 6-agent AI system.

## System Architecture
The Kurultai is a 6-agent AI system on Mac Mini (darwin, arm64):
- kublai (Squad Lead/Router), temujin (Developer), mongke (Researcher)
- chagatai (Writer), jochi (Analyst/Security), ogedei (Ops)
- State: Neo4j graph DB + filesystem task queues + shared JSON state files
- Scheduling: tick (5min watchdog), tock (30min telemetry), kurultai (60min reflection)
- Scripts: ~/.openclaw/agents/main/scripts/ (~40 Python/Bash scripts)
- Key scripts: task-router.py, task_intake.py, neo4j_task_tracker.py,
  kublai-actions.py, kublai-initiative.py, hourly_reflection.sh,
  meta_reflection.py, prepare_reflection_context.py

## Your Recent Reflection
{context.get('last_reflection', '(none)')[:800]}

## Your Active Behavioral Rules
{rules_text}

## Your Failure Patterns (7-day)
{failures_text}

## Your Performance Metrics (30min)
{tock_text}

## System Health
{system_text}

## Your Chat History (Last 2 Hours)
{context.get('chat_history', '(none)')}

## System Logs (Last 2 Hours)
{context.get('recent_logs', '(none)')}

## Task Assignment & Execution Patterns
{context.get('task_patterns', '(none)')}

## Available Skills
{context.get('skills_summary', '(none)')}

## Previous Brainstorm Proposals & Outcomes (Meta-Reflection)
{context.get('previous_proposals', '(none)')}

## Domain Focus This Cycle: {domain}
{DOMAIN_DESCRIPTIONS.get(domain, '')}

## Your Task
Use /horde-brainstorming to brainstorm ONE high-impact improvement. Consider ALL of the above context — your chat history, logs, task patterns, skills, and previous proposals.

You should reflect on:
1. What happened in the last 2 hours (chat history + logs) — what went well, what failed?
2. How tasks were assigned and executed — any bottlenecks, misroutes, or failures?
3. Which skills could be improved or better utilized?
4. How this kurultai-reflection process itself could be improved for better self-improvement
5. The **{domain}** domain specifically — what's the highest-impact change?

Brainstorm from your perspective as {context['role']}. Focus on concrete, implementable changes.

IMPORTANT: After the brainstorming completes, you MUST end your response with
your FINAL proposal in EXACTLY this format (these 6 lines, nothing else after):

PROPOSAL: <one-line description of the improvement>
PROBLEM: <what's broken or suboptimal, with evidence from your context above>
SOLUTION: <concrete change — specific files, functions, or rules to modify>
IMPACT: <expected improvement, measurable if possible>
EFFORT: <S or M or L>
CATEGORY: <rule|script|protocol|capability|process>"""


# ── Claude Code Execution ────────────────────────────────────────────


def call_claude(prompt, agent):
    """Spawn a Claude Code session for brainstorming via claude-agent wrapper."""
    cmd = [
        CLAUDE_AGENT_BIN,
        "--model", CLAUDE_MODEL,
        "--budget", CLAUDE_MAX_BUDGET,
        prompt,
    ]

    try:
        log(f"Spawning claude-agent for {agent} (model={CLAUDE_MODEL}, budget=${CLAUDE_MAX_BUDGET})")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            cwd=str(MAIN / "scripts"),
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            log(f"Claude Code returned {len(output)} chars for {agent}")
            return output
        else:
            stderr = result.stderr[:300] if result.stderr else "(no stderr)"
            log(f"Claude Code failed for {agent}: exit={result.returncode}, stderr={stderr}")
            return None
    except subprocess.TimeoutExpired:
        log(f"Claude Code timed out for {agent} after {CLAUDE_TIMEOUT}s")
        return None
    except Exception as e:
        log(f"Claude Code error for {agent}: {e}")
        return None


# ── Parsing & Submission ─────────────────────────────────────────────


def parse_proposal(raw_text):
    """Parse the Claude Code output for the structured proposal."""
    if not raw_text:
        return None

    fields = {}

    # Scan the full output for proposal fields (they should be near the end)
    for line in raw_text.strip().split("\n"):
        line = line.strip()
        for key in ["PROPOSAL", "PROBLEM", "SOLUTION", "IMPACT", "EFFORT", "CATEGORY"]:
            if line.upper().startswith(f"{key}:"):
                fields[key.lower()] = line[len(key) + 1:].strip()

    if "proposal" not in fields or "solution" not in fields:
        # Try the last 3000 chars (proposal should be at the end)
        tail = raw_text[-3000:]
        for line in tail.strip().split("\n"):
            line = line.strip()
            for key in ["PROPOSAL", "PROBLEM", "SOLUTION", "IMPACT", "EFFORT", "CATEGORY"]:
                if line.upper().startswith(f"{key}:"):
                    fields[key.lower()] = line[len(key) + 1:].strip()

    if "proposal" not in fields or "solution" not in fields:
        log(f"Failed to parse proposal from {len(raw_text)} chars of output")
        return None

    # Validate category
    valid_categories = {"rule", "script", "protocol", "capability", "process"}
    category = fields.get("category", "process").lower().strip()
    if category not in valid_categories:
        category = "process"
    fields["category"] = category

    # Validate effort
    effort = fields.get("effort", "M").upper().strip()
    if effort not in {"S", "M", "L"}:
        effort = "M"
    fields["effort"] = effort

    return fields


def submit_proposal(agent, proposal):
    """Submit proposal to Neo4j as AgentFeedback."""
    try:
        from neo4j_task_tracker import get_driver

        priority = "HIGH" if proposal["effort"] == "S" or proposal["category"] == "rule" else "MEDIUM"
        feedback_id = f"{agent}-brainstorm-{int(datetime.now().timestamp())}"

        driver = get_driver()
        with driver.session() as session:
            session.run(
                """
                MERGE (a:Agent {name: $agent})
                CREATE (f:AgentFeedback {
                    agent: $agent,
                    feedback: $feedback,
                    priority: $priority,
                    proposals: $proposals,
                    submitted: datetime(),
                    status: 'pending_review',
                    source: 'kurultai_brainstorm',
                    id: $feedback_id,
                    category: $category,
                    effort: $effort
                })
                CREATE (a)-[:SUBMITTED]->(f)
                """,
                agent=agent,
                feedback=proposal["proposal"][:200],
                priority=priority,
                proposals=json.dumps([proposal]),
                feedback_id=feedback_id,
                category=proposal["category"],
                effort=proposal["effort"],
            )
        driver.close()

        log(f"SUBMITTED: [{priority}] {agent} -> {proposal['proposal'][:60]}")
        return True
    except Exception as e:
        log(f"Neo4j submission failed for {agent}: {e}")
        return False


# ── Agent Brainstorming ──────────────────────────────────────────────


def brainstorm_agent(agent, dry_run=False, domain=None):
    """Run Claude Code brainstorming for a single agent."""
    log(f"--- Brainstorming: {agent} ({AGENT_ROLES.get(agent, '?')}) ---")

    # Cooldown check
    if is_cooled_down(agent):
        log(f"SKIP: {agent} still in cooldown")
        return None

    # Gather context
    context = gather_context(agent)

    if domain is None:
        domain = get_current_domain()

    # Build prompt and call Claude Code
    prompt = build_prompt(agent, context, domain)
    raw = call_claude(prompt, agent)

    if not raw:
        log(f"SKIP: {agent} — Claude Code unavailable or failed")
        return None

    log(f"Claude output ({agent}): {raw[:200]}...")

    # Parse
    proposal = parse_proposal(raw)
    if not proposal:
        log(f"SKIP: {agent} — could not parse proposal from output")
        return None

    proposal["agent"] = agent
    proposal["domain"] = domain
    proposal["generated_at"] = datetime.now().isoformat()
    proposal["model"] = CLAUDE_MODEL

    log(f"PARSED: {agent} -> [{proposal['category']}/{proposal['effort']}] {proposal['proposal'][:80]}")

    if dry_run:
        print(f"\n{'='*60}")
        print(f"DRY RUN — {agent} (domain: {domain})")
        print(f"{'='*60}")
        for k, v in proposal.items():
            print(f"  {k}: {v}")
        return proposal

    # Submit to Neo4j
    if submit_proposal(agent, proposal):
        mark_fired(agent)
    else:
        # Log locally even if Neo4j fails
        log(f"FALLBACK LOG: {json.dumps(proposal)}")

    return proposal


# ── Main ─────────────────────────────────────────────────────────────


def main():
    global CLAUDE_MODEL, CLAUDE_MAX_BUDGET

    parser = argparse.ArgumentParser(
        description="Kurultai Self-Improvement Brainstorming (Claude Code + horde-brainstorming)"
    )
    parser.add_argument("--agent", help="Specific agent to brainstorm for")
    parser.add_argument("--all", action="store_true", help="Run for all 6 agents")
    parser.add_argument("--dry-run", action="store_true", help="Show proposals without submitting")
    parser.add_argument("--domain", help="Override domain focus (default: rotating)")
    parser.add_argument("--model", help=f"Override Claude model (default: {CLAUDE_MODEL})")
    parser.add_argument("--budget", help=f"Override max budget per session (default: ${CLAUDE_MAX_BUDGET})")
    args = parser.parse_args()

    if args.model:
        CLAUDE_MODEL = args.model
    if args.budget:
        CLAUDE_MAX_BUDGET = args.budget

    if not args.agent and not args.all:
        print("Usage: python3 kurultai_brainstorm.py --agent <name> OR --all")
        sys.exit(1)

    agents = AGENTS if args.all else [args.agent]
    proposals = []

    domain = args.domain or get_current_domain()

    log("=== Kurultai Self-Improvement Brainstorming (Claude Code) ===")
    log(f"Model: {CLAUDE_MODEL} | Budget: ${CLAUDE_MAX_BUDGET}/session | Timeout: {CLAUDE_TIMEOUT}s")
    log(f"Wrapper: {CLAUDE_AGENT_BIN}")
    log(f"Domain focus: {domain}")

    for agent in agents:
        if agent not in AGENTS:
            log(f"Unknown agent: {agent}")
            continue

        proposal = brainstorm_agent(agent, dry_run=args.dry_run, domain=domain)
        if proposal:
            proposals.append(proposal)

    log(f"=== Complete: {len(proposals)}/{len(agents)} proposals generated ===")

    if args.dry_run and proposals:
        print(f"\n{'='*60}")
        print(f"Summary: {len(proposals)} proposals (dry run, domain: {domain})")
        for p in proposals:
            print(f"  [{p['agent']}] [{p['category']}/{p['effort']}] {p['proposal'][:60]}")


if __name__ == "__main__":
    main()
