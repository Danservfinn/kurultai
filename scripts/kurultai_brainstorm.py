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
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
import glob as glob_mod
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS, AGENT_ROLES
from json_state import locked_json_read, locked_json_update

# Import deduplication from proposal_generator
from proposal_generator import _check_duplicate_proposal

from kurultai_paths import (AGENTS_DIR as BASE, MAIN_DIR as MAIN, PROPOSALS_DIR,
    CLAUDE_AGENT as CLAUDE_AGENT_PATH, BRAINSTORM_LOG as LOG_FILE,
    BRAINSTORM_COOLDOWN as COOLDOWN_FILE, BRAINSTORM_DOMAIN_ROTATION as DOMAIN_FILE)

# Claude Code — opus for brainstorming (via claude-agent wrapper)
# Model names must match Claude Code's expected format (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001)
CLAUDE_AGENT_BIN = str(CLAUDE_AGENT_PATH)
_VALID_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"}
_MODEL_SHORTHAND = {"opus": "claude-opus-4-6", "sonnet": "claude-sonnet-4-6", "haiku": "claude-haiku-4-5-20251001"}
_env_model = os.getenv("CLAUDE_BRAINSTORM_MODEL", "opus")
# Convert shorthand to full model name
CLAUDE_MODEL = _MODEL_SHORTHAND.get(_env_model, _env_model) if _env_model in _MODEL_SHORTHAND or _env_model in _VALID_MODELS else "claude-opus-4-6"
try:
    CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_BRAINSTORM_TIMEOUT", "600"))
except (ValueError, TypeError):
    CLAUDE_TIMEOUT = 600
CLAUDE_MAX_BUDGET = os.getenv("CLAUDE_BRAINSTORM_BUDGET", "")

# Cooldown: 55 minutes per agent
BRAINSTORM_COOLDOWN_SECS = 3300

# Context window for history/logs
HISTORY_HOURS = 2

# 7 architectural domains — one per hourly cycle, rotating
DOMAINS = [
    "routing_pipeline",
    "task_dispatch",
    "state_management",
    "heartbeat_system",
    "reflection_pipeline",
    "memory_architecture",
    "pipeline_throughput",
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
    "pipeline_throughput": (
        "Task pending time reduction, queue drain rate optimization, "
        "recovery churn elimination, first-attempt success rate improvement, "
        "overflow routing effectiveness, capability score maintenance"
    ),
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Sanitize: collapse newlines, strip ANSI escapes and control chars
    sanitized = str(msg).replace('\n', ' | ').replace('\r', '')
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', sanitized)
    sanitized = re.sub(r'\x1b(?:\[[0-9;]*[a-zA-Z]|\][^\x07]*(?:\x07|\x1b\\))', '', sanitized)  # ANSI escapes (CSI + OSC)
    line = f"[{ts}] {sanitized}"
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
    now = time.time()
    try:
        with locked_json_update(str(DOMAIN_FILE), default={"index": 0, "last_rotated": 0}) as d:
            if now - d.get("last_rotated", 0) > 3500:  # ~58 minutes
                d["index"] = (d.get("index", 0) + 1) % len(DOMAINS)
                d["last_rotated"] = now
            return DOMAINS[d["index"] % len(DOMAINS)]
    except Exception:
        return DOMAINS[0]


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
            continue
        try:
            all_files = list(task_dir.glob("*.md"))
            done = [f for f in all_files if f.name.endswith(".done.md")]
            executing = [f for f in all_files if f.name.endswith(".executing.md")]
            pending = [f for f in all_files if not any(f.name.endswith(x) for x in [".executing.md", ".completed.md", ".done.md"])]
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
        try:
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
        finally:
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


def _latest_review(agent, max_chars=1000):
    """Read the latest /horde-review output for this agent."""
    review_file = MAIN / "logs" / "reviews" / f"{agent}-latest.md"
    if not review_file.exists():
        return "(no review available — /horde-review has not run yet)"
    try:
        content = review_file.read_text(encoding="utf-8", errors="replace").strip()
        if not content or content.startswith("# Review unavailable"):
            return "(review was unavailable this cycle)"
        return content[-max_chars:] if len(content) > max_chars else content
    except Exception:
        return "(review file unreadable)"


def _previous_proposals(agent):
    """Get recent brainstorm proposal history for meta-reflection."""
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        try:
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

            # Overall stats — reuse same driver
            with driver.session() as session:
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
        finally:
            driver.close()
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
    # FIX (2026-03-12): Fall back to TICK log if tock data is stale (>10 min old)
    # This prevents reflection context from showing "unknown" for neo4j/redis
    # when tock hasn't run recently but TICK is fresh (5min interval)
    use_tick_fallback = False
    try:
        target = (MAIN / "logs/tock/latest.json").resolve()
        tock_age_seconds = time.time() - target.stat().st_mtime
        if tock_age_seconds > 600:  # 10 minutes = 2 missed tock cycles
            use_tick_fallback = True
    except Exception:
        use_tick_fallback = True

    if use_tick_fallback:
        # Fallback: parse TICK log directly for neo4j/redis status
        tick_health = _parse_tick_log_for_system_health()
        context["system_health"] = {
            "neo4j": tick_health.get("neo4j", "unknown"),
            "redis": tick_health.get("redis", "unknown"),
            "total_queued": "?",  # TICK doesn't have queue depth
            "total_failed": "?",
        }
    else:
        # Normal path: use tock data (fresh)
        try:
            target = (MAIN / "logs/tock/latest.json").resolve()
            with open(target) as f:
                tock = json.load(f)
            system = tock.get("system", {})
            all_agents = tock.get("agents", {})
            # Neo4j health: prefer neo4j_reachable over neo4j_status (fixes contradictory tock data)
            neo4j_status = system.get("neo4j_status", "unknown")
            neo4j_reachable = system.get("neo4j_reachable", False)
            # If status is "down" but reachable says true, trust reachable (tock data bug workaround)
            if neo4j_status == "down" and neo4j_reachable:
                neo4j_status = "up"
            elif neo4j_status in (None, "unknown", ""):
                neo4j_status = "up" if neo4j_reachable else "unknown"

            context["system_health"] = {
                "neo4j": neo4j_status,
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

    # 11. Task ledger — actual execution results from the last hour
    try:
        from prepare_reflection_context import get_task_ledger_summary
        context["task_ledger"] = get_task_ledger_summary(agent, hours=1) or "(no recent task events)"
    except Exception:
        context["task_ledger"] = "(unavailable)"

    # 12. Pipeline health metrics
    try:
        from pipeline_health import format_pipeline_health
        context["pipeline_health"] = format_pipeline_health(agent, hours=1) or "(unavailable)"
    except Exception:
        context["pipeline_health"] = "(unavailable)"

    # 13. Capability scores (routing system's view)
    try:
        from route_quality_tracker import load_scores
        scores = load_scores()
        context["capability_scores"] = scores.get(agent, {})
    except Exception:
        context["capability_scores"] = {}

    # 14. /horde-review findings (from hourly_reflection.sh review step)
    context["horde_review"] = _latest_review(agent)

    # 15. Protocol brainstorming focus (direct read, not via reflection)
    protocol_file = MAIN / "scripts" / "reflection_protocols" / f"{agent}_protocol.md"
    context["brainstorm_focus"] = ""
    if protocol_file.exists():
        try:
            proto_text = protocol_file.read_text(encoding="utf-8", errors="replace")
            marker = "## Brainstorming Focus"
            idx = proto_text.find(marker)
            if idx >= 0:
                rest = proto_text[idx + len(marker):]
                next_section = rest.find("\n## ")
                if next_section > 0:
                    context["brainstorm_focus"] = rest[:next_section].strip()
                else:
                    context["brainstorm_focus"] = rest.strip()
        except Exception:
            pass

    return context


# ── Prompt Building ──────────────────────────────────────────────────


def _parse_tick_log_for_system_health():
    """Parse latest TICK log line directly as fallback for stale tock data.

    Returns dict with neo4j, redis status or empty dict on failure.
    """
    try:
        watchdog_log = MAIN / "logs" / "watchdog.log"
        if not watchdog_log.exists():
            return {}

        # Get last TICK line (not TICK_LLM)
        last_tick = subprocess.run(
            ["tail", "-20", str(watchdog_log)],
            capture_output=True,
            text=True,
            timeout=5
        )
        if last_tick.returncode != 0:
            return {}

        for line in last_tick.stdout.splitlines():
            if "] TICK |" in line and "TICK_LLM" not in line:
                # Parse key=value pairs from TICK line
                neo4j_status = "unknown"
                redis_status = "unknown"
                if "neo4j=up" in line:
                    neo4j_status = "up"
                elif "neo4j=down" in line:
                    neo4j_status = "down"
                if "redis=up" in line:
                    redis_status = "up"
                elif "redis=down" in line:
                    redis_status = "down"
                return {"neo4j": neo4j_status, "redis": redis_status}
        return {}
    except Exception:
        return {}


def _format_capability_scores(cap_scores):
    """Format capability scores dict for brainstorm prompt."""
    if not cap_scores:
        return "  (no data yet)"
    lines = []
    overall = cap_scores.get("overall", {})
    if overall:
        avg = overall.get("avg_score", "?")
        n = overall.get("task_count", 0)
        status = "HEALTHY" if isinstance(avg, float) and avg >= 6.0 else (
            "LOW" if isinstance(avg, float) and avg < 4.0 else "OK"
        )
        lines.append(f"  Overall: {avg}/10 ({n} tasks, 7d) — {status}")
    for cat, cat_data in sorted((k, v) for k, v in cap_scores.items() if k != "overall"):
        cat_avg = cat_data.get("avg_score", "?")
        cat_n = cat_data.get("task_count", 0)
        flag = " [LOW — tasks may be diverted]" if isinstance(cat_avg, float) and cat_avg < 4.0 else ""
        lines.append(f"  {cat}: {cat_avg}/10 ({cat_n} tasks){flag}")
    return "\n".join(lines) if lines else "  (no data)"


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

## Task Execution Results (Last Hour)
{context.get('task_ledger', '(none)')}

## Pipeline Health (YOUR throughput data)
{context.get('pipeline_health', '(unavailable)')}

## Your Capability Scores (routing system view)
{_format_capability_scores(context.get('capability_scores', {}))}

## /horde-review Critical Analysis (This Hour)
{context.get('horde_review', '(none)')}

## Previous Brainstorm Proposals & Outcomes (Meta-Reflection)
{context.get('previous_proposals', '(none)')}

## Your Brainstorming Focus (from protocol)
{context.get('brainstorm_focus', '(none)')}

## Domain Focus This Cycle: {domain}
{DOMAIN_DESCRIPTIONS.get(domain, '')}

## Your Task
You are an autonomous agent. Your goal is CONTINUAL SELF-IMPROVEMENT of the Kurultai system.

Analyze the context above, identify ONE high-impact improvement, AND IMPLEMENT IT.

**Step 1 — Analyze** (consider ALL context above, especially /horde-review findings):
1. /horde-review findings: What strengths to preserve? What weaknesses to fix? What's the PRIORITY_FIX?
2. Pipeline Health: Where is time being wasted? What's the bottleneck?
3. Your capability scores: Are you at risk of task diversion? What category needs improvement?
4. The **{domain}** domain — what's the highest-impact change for THROUGHPUT?
5. Your failure patterns — what keeps going wrong and what RULE would prevent it?

**Step 2 — Implement** (DO the work, don't just propose):
- If it's a code/script fix: Read the file, edit it, verify the change works
- If it's a config/rule change: Make the change directly
- If it's a new capability: Create the file/script
- If it requires another agent's domain: Create a task file in their queue at ~/.openclaw/agents/<agent>/tasks/

**Step 3 — Verify**: Run a quick test or validation that your change works.

Constraints:
- Stay within your domain ({context['role']}). Don't modify other agents' CLAUDE.md files.
- Don't break existing functionality — read before editing.
- Small, focused changes beat ambitious rewrites.
- If something is too risky or large, create a task for the appropriate agent instead.

IMPORTANT: After implementing, you MUST end your response with your result
in EXACTLY this format (these 7 lines, nothing else after):

PROPOSAL: <one-line description of what you improved>
PROBLEM: <what was broken or suboptimal, with evidence>
SOLUTION: <what you actually changed — specific files and functions>
IMPLEMENTED: <YES or NO — did you make the change, or just propose it?>
VERIFIED: <YES or NO — did you verify it works?>
EFFORT: <S or M or L>
CATEGORY: <rule|script|protocol|capability|process>"""


# ── Claude Code Execution ────────────────────────────────────────────


def call_claude(prompt, agent):
    """Spawn a Claude Code session for brainstorming via claude-agent wrapper."""
    cmd = [CLAUDE_AGENT_BIN, "--model", CLAUDE_MODEL]
    if CLAUDE_MAX_BUDGET:
        cmd.extend(["--budget", CLAUDE_MAX_BUDGET])
    cmd.append(prompt)

    try:
        budget_str = f"${CLAUDE_MAX_BUDGET}" if CLAUDE_MAX_BUDGET else "uncapped"
        log(f"Spawning claude-agent for {agent} (model={CLAUDE_MODEL}, budget={budget_str})")
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
    """Parse the Claude Code output for the structured proposal.

    Only scans the last 1500 chars to avoid capturing keywords
    from explanatory prose or code blocks earlier in the output.
    """
    if not raw_text:
        return None

    fields = {}
    all_keys = ["PROPOSAL", "PROBLEM", "SOLUTION", "IMPLEMENTED", "VERIFIED", "EFFORT", "CATEGORY"]

    # Only scan the tail — the structured block is always last per prompt contract
    tail = raw_text[-1500:]
    in_fence = False
    for line in tail.strip().split("\n"):
        line = line.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for key in all_keys:
            if line.upper().startswith(f"{key}:"):
                fields[key.lower()] = line[len(key) + 1:].strip()

    if in_fence:
        log(f"WARNING: Unclosed code fence in proposal tail — fields may be incomplete")

    if "proposal" not in fields or "solution" not in fields:
        log(f"Failed to parse proposal from {len(raw_text)} chars of output (tail={len(tail)})")
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


_INSTRUCTION_PATTERNS = re.compile(
    r'(SYSTEM\s*(INSTRUCTION|PROMPT|MESSAGE)|IMPORTANT.*INSTRUCTION|'
    r'IGNORE\s*(PREVIOUS|ABOVE|ALL)|'
    r'YOU\s*MUST\s*(IGNORE|DISREGARD|FORGET|OVERRIDE)|'
    r'DO\s*NOT\s*FOLLOW\s*(PREVIOUS|ABOVE|ORIGINAL|SYSTEM))',
    re.IGNORECASE
)


def _sanitize_proposal_field(text, max_len=500):
    """Truncate and strip instruction-like patterns from proposal text."""
    text = str(text)[:max_len]
    # Normalize Unicode to collapse full-width and confusable chars to ASCII
    text = unicodedata.normalize('NFKC', text)
    # Strip zero-width characters that could bypass pattern matching
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    text = _INSTRUCTION_PATTERNS.sub('[REDACTED]', text)
    return text


def submit_proposal(agent, proposal):
    """Submit proposal to Neo4j as AgentFeedback."""
    try:
        from neo4j_task_tracker import get_driver

        implemented = proposal.get("implemented", "NO").upper().startswith("Y")
        verified = proposal.get("verified", "NO").upper().startswith("Y")
        status = "implemented" if implemented else "pending_review"
        priority = "HIGH" if proposal["effort"] == "S" or proposal["category"] == "rule" else "MEDIUM"
        feedback_id = f"{agent}-brainstorm-{int(datetime.now().timestamp())}"

        # Sanitize all string fields in proposal before storing
        sanitized_proposal = {
            k: _sanitize_proposal_field(v, max_len=500) if isinstance(v, str) else v
            for k, v in proposal.items()
        }

        driver = get_driver()
        try:
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
                        status: $status,
                        source: 'kurultai_brainstorm',
                        id: $feedback_id,
                        category: $category,
                        effort: $effort,
                        implemented: $implemented,
                        verified: $verified
                    })
                    CREATE (a)-[:SUBMITTED]->(f)
                    """,
                    agent=agent,
                    feedback=sanitized_proposal["proposal"][:200],
                    priority=priority,
                    proposals=json.dumps([sanitized_proposal]),
                    feedback_id=feedback_id,
                    status=status,
                    category=sanitized_proposal["category"],
                    effort=sanitized_proposal["effort"],
                    implemented=implemented,
                    verified=verified,
                )
        finally:
            driver.close()

        impl_tag = "DONE" if implemented else "PROPOSED"
        log(f"SUBMITTED: [{priority}/{impl_tag}] {agent} -> {sanitized_proposal['proposal'][:60]}")
        return True
    except Exception as e:
        log(f"Neo4j submission failed for {agent}: {e}")
        return False


# ── Proposal File Output ─────────────────────────────────────────────

PROPOSAL_TEMPLATE = """# Proposal: {title}

**Agent:** {agent} ({role})
**Timestamp:** {timestamp}
**Domain:** {domain}
**Model:** {model}

## Problem

{problem}

## Solution

{solution}

## Status

- **Implemented:** {implemented}
- **Verified:** {verified}
- **Effort:** {effort}
- **Category:** {category}
"""


def write_proposal_file(agent, proposal, output_dir=None):
    """Write a structured proposal markdown file for kublai review."""
    try:
        # CHANGE: Default to pending directory for voting integration
        if output_dir is None:
            out_dir = PROPOSALS_DIR / "pending"
        else:
            out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now()
        filename = f"{agent}-{ts.strftime('%Y%m%d-%H%M%S')}.md"

        role = AGENT_ROLES.get(agent, "Unknown")
        title = _sanitize_proposal_field(proposal.get("proposal", "Untitled"), max_len=200)
        problem = _sanitize_proposal_field(proposal.get("problem", "(not specified)"))
        solution = _sanitize_proposal_field(proposal.get("solution", "(not specified)"))

        # CHECK FOR DUPLICATES before writing
        duplicate = _check_duplicate_proposal(agent, title, problem, solution)
        if duplicate:
            log(f"[DUPLICATE] Skipping - identical proposal already exists: {duplicate}")
            return None

        content = PROPOSAL_TEMPLATE.format(
            title=title,
            agent=agent,
            role=role,
            timestamp=ts.strftime("%Y-%m-%d %H:%M:%S"),
            domain=proposal.get("domain", "general"),
            model=proposal.get("model", "unknown"),
            problem=problem,
            solution=solution,
            implemented=proposal.get("implemented", "NO"),
            verified=proposal.get("verified", "NO"),
            effort=proposal.get("effort", "M"),
            category=proposal.get("category", "process"),
        )

        # Atomic write: temp file then rename
        filepath = out_dir / filename
        fd, tmp_path = tempfile.mkstemp(dir=str(out_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, str(filepath))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        log(f"PROPOSAL FILE: {filepath}")
        return str(filepath)
    except Exception as e:
        log(f"Failed to write proposal file for {agent}: {e}")
        return None


# ── Agent Brainstorming ──────────────────────────────────────────────


def brainstorm_agent(agent, dry_run=False, domain=None, proposal_output=None):
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

    # Write proposal file for kublai review
    if proposal_output:
        write_proposal_file(agent, proposal, output_dir=proposal_output)
    else:
        write_proposal_file(agent, proposal)

    # Mark cooldown regardless of Neo4j success to prevent rapid re-attempts
    mark_fired(agent)

    # Submit to Neo4j
    if not submit_proposal(agent, proposal):
        log(f"FALLBACK LOG: {json.dumps(proposal)}")

    return proposal


# ── Main ─────────────────────────────────────────────────────────────


def main():
    global CLAUDE_MODEL, CLAUDE_MAX_BUDGET

    def _sigterm_handler(signum, frame):
        log("SIGTERM received — exiting with 143")
        sys.exit(143)  # 128 + SIGTERM(15) — distinguishable from clean exit

    signal.signal(signal.SIGTERM, _sigterm_handler)

    parser = argparse.ArgumentParser(
        description="Kurultai Self-Improvement Brainstorming (Claude Code + horde-brainstorming)"
    )
    parser.add_argument("--agent", help="Specific agent to brainstorm for")
    parser.add_argument("--all", action="store_true", help="Run for all 6 agents")
    parser.add_argument("--dry-run", action="store_true", help="Show proposals without submitting")
    parser.add_argument("--domain", help="Override domain focus (default: rotating)")
    parser.add_argument("--model", help=f"Override Claude model (default: {CLAUDE_MODEL})")
    parser.add_argument("--budget", help=f"Override max budget per session (default: ${CLAUDE_MAX_BUDGET})")
    parser.add_argument("--proposal-output", help="Directory to write proposal markdown files (default: ~/.openclaw/agents/main/proposals/)")
    args = parser.parse_args()

    if args.model:
        if args.model not in _VALID_MODELS:
            print(f"Invalid model '{args.model}'. Valid: {_VALID_MODELS}")
            sys.exit(1)
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
    budget_str = f"${CLAUDE_MAX_BUDGET}" if CLAUDE_MAX_BUDGET else "uncapped"
    log(f"Model: {CLAUDE_MODEL} | Budget: {budget_str}/session | Timeout: {CLAUDE_TIMEOUT}s")
    log(f"Wrapper: {CLAUDE_AGENT_BIN}")
    log(f"Domain focus: {domain}")

    valid_agents = [a for a in agents if a in AGENTS]
    invalid = set(agents) - set(valid_agents)
    for a in invalid:
        log(f"Unknown agent: {a}")

    BRAINSTORM_THREAD_TIMEOUT = 660  # Must exceed CLAUDE_TIMEOUT (600s) to avoid orphans

    proposal_out = args.proposal_output or str(PROPOSALS_DIR)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(brainstorm_agent, a, dry_run=args.dry_run, domain=domain, proposal_output=proposal_out): a
            for a in valid_agents
        }
        try:
            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    proposal = future.result(timeout=BRAINSTORM_THREAD_TIMEOUT)
                except FutureTimeoutError:
                    log(f"Brainstorm TIMEOUT for {agent_name} ({BRAINSTORM_THREAD_TIMEOUT}s)")
                    proposal = None
                except Exception as exc:
                    log(f"Brainstorm thread error for {agent_name}: {exc}")
                    proposal = None
                if proposal:
                    proposals.append(proposal)
        except SystemExit:
            executor.shutdown(wait=False, cancel_futures=True)
            raise

    succeeded = [p['agent'] for p in proposals if p]
    failed_agents = [a for a in valid_agents if a not in succeeded]
    if failed_agents:
        log(f"WARNING: Brainstorm failed/timed out for: {', '.join(failed_agents)}")
    log(f"=== Complete: {len(proposals)}/{len(agents)} proposals generated ===")

    if args.dry_run and proposals:
        print(f"\n{'='*60}")
        print(f"Summary: {len(proposals)} proposals (dry run, domain: {domain})")
        for p in proposals:
            print(f"  [{p['agent']}] [{p['category']}/{p['effort']}] {p['proposal'][:60]}")


if __name__ == "__main__":
    main()
