#!/usr/bin/env python3
"""
Kublai Initiative — Proactive self-directed action engine.

Closes the "What do I want to do?" loop by:
1. Reading the latest reflection outputs from all 6 agents
2. Reading current goals from MEMORY.md
3. Reading system state from tock/latest.json
4. Asking the local LLM to decide ONE proactive action
5. Creating a real task file from the answer
6. Logging the initiative as a hypothesis in Neo4j

Called at the end of hourly_reflection.sh, after all agents reflect.

Usage:
    python3 kublai-initiative.py
    python3 kublai-initiative.py --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from json_state import locked_json_read, locked_json_update

BASE = Path.home() / ".openclaw/agents"
MAIN = BASE / "main"
TOCK_LATEST = MAIN / "logs/tock/latest.json"
MEMORY_FILE = MAIN / "MEMORY.md"
INITIATIVE_LOG = MAIN / "logs/kublai-initiative.log"
COOLDOWN_FILE = MAIN / "logs/initiative-cooldown.json"
AGENT_DIR = MAIN / "agent"

AGENTS = ["kublai", "mongke", "chagatai", "temujin", "jochi", "ogedei"]

from task_router import route_by_category, route_by_text, CATEGORY_ROUTING

# Minimum 45 minutes between initiatives to prevent thrashing
INITIATIVE_COOLDOWN_SECS = 2700


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(INITIATIVE_LOG.parent, exist_ok=True)
    with open(INITIATIVE_LOG, "a") as f:
        f.write(line + "\n")


def is_cooled_down():
    """Check if we're still in cooldown from last initiative."""
    data = locked_json_read(str(COOLDOWN_FILE), default={})
    last = data.get("last_initiative", 0)
    return (time.time() - last) < INITIATIVE_COOLDOWN_SECS


def mark_fired():
    with locked_json_update(str(COOLDOWN_FILE)) as data:
        data["last_initiative"] = time.time()


def read_agent_reflections():
    """Read today's reflection outputs from all agents (last entry each)."""
    today = datetime.now().strftime("%Y-%m-%d")
    summaries = {}

    for agent in AGENTS:
        memory_file = BASE / agent / "memory" / f"{today}.md"
        if not memory_file.exists():
            summaries[agent] = "(no reflection today)"
            continue

        try:
            content = memory_file.read_text(encoding="utf-8", errors="replace")
            # Get the last reflection block (between last two "---" markers)
            blocks = content.split("\n---\n")
            if len(blocks) >= 2:
                last_block = blocks[-2].strip()  # -1 is often empty after trailing ---
                # Truncate to keep prompt manageable
                summaries[agent] = last_block[:500]
            else:
                summaries[agent] = content[-500:]
        except Exception:
            summaries[agent] = "(unreadable)"

    return summaries


def read_goals():
    """Read active projects and goals from MEMORY.md."""
    if not MEMORY_FILE.exists():
        return "No MEMORY.md found."

    try:
        content = MEMORY_FILE.read_text(encoding="utf-8", errors="replace")
        # Extract Active Projects section
        match = re.search(
            r"## Active Projects\s*\n(.*?)(?=\n---|\Z)", content, re.DOTALL
        )
        if match:
            return match.group(1).strip()[:600]
        return content[:400]
    except Exception:
        return "Unable to read MEMORY.md"


def read_tock_summary():
    """Read compact system state from tock."""
    if not TOCK_LATEST.exists():
        return "No tock data."

    try:
        target = TOCK_LATEST.resolve() if TOCK_LATEST.is_symlink() else TOCK_LATEST
        with open(target) as f:
            tock = json.load(f)

        agents = tock.get("agents", {})
        queues = tock.get("queues", {})
        assessment = tock.get("llm_assessment", {})

        lines = []
        for name, data in agents.items():
            t = data.get("tasks", {})
            lines.append(
                f"  {name}: done={t.get('completed',0)} fail={t.get('failed',0)} "
                f"queue={t.get('queue_depth',0)}"
            )

        lines.append(f"Total queued: {queues.get('total_pending',0)}")
        lines.append(f"Severity: {assessment.get('severity','?')}")
        lines.append(f"Bottleneck: {assessment.get('bottleneck','none')}")

        return "\n".join(lines)
    except Exception as e:
        return f"Tock read error: {e}"


def ask_llm_for_initiative(reflections, goals, system_state):
    """Ask the local LLM to decide ONE proactive action."""
    reflection_text = "\n\n".join(
        f"**{name}:** {summary}" for name, summary in reflections.items()
    )

    prompt = f"""You are Kublai, Squad Lead of a 6-agent AI system. You just completed hourly reflections.

## Current Goals
{goals}

## System State
{system_state}

## Agent Reflections (summaries)
{reflection_text}

## Your Question: "What do I want to do next?"

Based on the reflections, goals, and system state, decide ONE proactive action that will have the highest impact. This should NOT be a reaction to an error (kublai-actions.py handles that). This should be a PROACTIVE initiative — something that moves the system forward toward its goals.

Respond in EXACTLY this format (no extra text, no thinking tags):
ACTION: <one sentence describing the specific action>
AGENT: <which agent should do it: kublai|temujin|mongke|chagatai|jochi|ogedei>
PRIORITY: <high|normal|low>
RATIONALE: <one sentence explaining why this is the highest-impact action right now>
EXPECTED_OUTCOME: <one sentence describing what success looks like>"""

    try:
        resp = requests.post(
            "http://localhost:1234/v1/chat/completions",
            json={
                "model": "qwen3.5-9b-mlx",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Kublai, a decisive AI squad leader. Respond only in the exact format requested. No thinking tags. Be specific and actionable.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.4,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip thinking tags if present
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return text
        else:
            log(f"LLM returned status {resp.status_code}")
            return None
    except Exception as e:
        log(f"LLM call failed: {e}")
        return None


def heuristic_initiative(reflections, goals, system_state):
    """Heuristic fallback when LLM is unavailable.

    Scans goals for "Next:" items and system state for bottlenecks,
    and produces the most obvious high-value action.
    """
    # Check if any goals have a clear "Next:" action
    if goals:
        for line in goals.split("\n"):
            line = line.strip()
            if line.lower().startswith("- next:") or line.lower().startswith("next:"):
                action = line.split(":", 1)[1].strip()
                if action:
                    # Route using canonical router
                    agent = route_by_text(action)
                    if agent == "subagent":
                        agent = "kublai"

                    return (
                        f"ACTION: {action}\n"
                        f"AGENT: {agent}\n"
                        f"PRIORITY: normal\n"
                        f"RATIONALE: Next step from active goals in MEMORY.md\n"
                        f"EXPECTED_OUTCOME: Progress toward stated project goals"
                    )

    # Check system state for bottlenecks
    if "queue=" in system_state:
        for line in system_state.split("\n"):
            if "queue=" in line and "queue=0" not in line:
                return (
                    "ACTION: Review and process pending task queue backlog\n"
                    "AGENT: kublai\n"
                    "PRIORITY: normal\n"
                    "RATIONALE: Tasks are queued but not being processed\n"
                    "EXPECTED_OUTCOME: Queue backlog reduced to zero"
                )

    # Default: advance the top-priority goal
    return (
        "ACTION: Review Parse monetization blockers and create next implementation task\n"
        "AGENT: temujin\n"
        "PRIORITY: normal\n"
        "RATIONALE: Default initiative — advance the highest-priority active goal\n"
        "EXPECTED_OUTCOME: Clear next step identified and task created for Parse progress"
    )


def parse_initiative(raw_text):
    """Parse the LLM response into structured fields."""
    if not raw_text:
        return None

    fields = {}
    for line in raw_text.strip().split("\n"):
        line = line.strip()
        for key in ["ACTION", "AGENT", "PRIORITY", "RATIONALE", "EXPECTED_OUTCOME"]:
            if line.upper().startswith(f"{key}:"):
                fields[key.lower()] = line[len(key) + 1 :].strip()

    if "action" not in fields or "agent" not in fields:
        log(f"Failed to parse initiative: {raw_text[:200]}")
        return None

    # Validate agent name
    agent = fields["agent"].lower().strip()
    if agent not in AGENTS:
        # Try to route by keyword using canonical router
        for keyword, routed_agent in CATEGORY_ROUTING.items():
            if keyword in fields["action"].lower():
                agent = routed_agent
                break
        else:
            agent = "kublai"
    fields["agent"] = agent

    # Validate priority
    priority = fields.get("priority", "normal").lower().strip()
    if priority not in ["high", "normal", "low"]:
        priority = "normal"
    fields["priority"] = priority

    return fields


MAX_TASK_DEPTH = 3


def create_task(agent, priority, title, body, depth=0):
    """Create a task file in an agent's task queue."""
    if depth >= MAX_TASK_DEPTH:
        log(f"REJECT: depth={depth} >= {MAX_TASK_DEPTH} for '{title[:60]}' — preventing runaway chain")
        return None

    task_dir = AGENT_DIR / agent / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)

    epoch = int(time.time())
    filename = f"{priority}-{epoch}.md"
    filepath = task_dir / filename

    content = f"""---
agent: {agent}
priority: {priority}
created: {datetime.now().isoformat()}
source: kublai-initiative
type: proactive
depth: {depth}
---

# Task: {title}

{body}
"""
    filepath.write_text(content)
    log(f"TASK CREATED: {priority} task for {agent}: {title} (depth={depth})")
    return str(filepath)


def log_hypothesis(action, expected_outcome):
    """Log the initiative as a hypothesis in Neo4j for future validation."""
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        with driver.session() as session:
            session.run(
                """
                CREATE (h:Hypothesis {
                    action: $action,
                    expected_outcome: $expected_outcome,
                    created: datetime(),
                    source: 'kublai-initiative',
                    status: 'pending',
                    validated: false
                })
                """,
                action=action,
                expected_outcome=expected_outcome,
            )
        driver.close()
        log("HYPOTHESIS: Logged to Neo4j")
    except Exception as e:
        log(f"HYPOTHESIS: Neo4j logging failed: {e}")


def log_initiative_to_memory(initiative):
    """Append the initiative to Kublai's memory file."""
    today = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H:%M")
    memory_file = BASE / "kublai" / "memory" / f"{today}.md"

    entry = f"""

---

## {time_str} - Kublai Initiative (Self-Directed)

**Action:** {initiative['action']}
**Assigned to:** {initiative['agent']}
**Priority:** {initiative['priority']}
**Rationale:** {initiative.get('rationale', 'N/A')}
**Expected outcome:** {initiative.get('expected_outcome', 'N/A')}

---
"""
    try:
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_file, "a") as f:
            f.write(entry)
        log(f"MEMORY: Initiative logged to {memory_file}")
    except Exception as e:
        log(f"MEMORY: Failed to write: {e}")


def main():
    parser = argparse.ArgumentParser(description="Kublai Initiative — proactive action engine")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without acting")
    args = parser.parse_args()

    log("=== Kublai Initiative Engine ===")

    # Cooldown check
    if is_cooled_down():
        log("SKIP: Still in cooldown from last initiative")
        print("INITIATIVE: Skipped (cooldown)")
        return

    # Gather context
    reflections = read_agent_reflections()
    goals = read_goals()
    system_state = read_tock_summary()

    log(f"Context gathered: {len(reflections)} reflections, goals={len(goals)}ch, state={len(system_state)}ch")

    # Ask the LLM
    raw = ask_llm_for_initiative(reflections, goals, system_state)
    if not raw:
        log("LLM unavailable — using heuristic fallback")
        raw = heuristic_initiative(reflections, goals, system_state)

    log(f"LLM response: {raw[:200]}")

    # Parse
    initiative = parse_initiative(raw)
    if not initiative:
        log("SKIP: Could not parse LLM response")
        print("INITIATIVE: Parse failed")
        return

    log(f"PARSED: action='{initiative['action'][:80]}' agent={initiative['agent']} priority={initiative['priority']}")

    if args.dry_run:
        print(f"DRY RUN — would create {initiative['priority']} task for {initiative['agent']}:")
        print(f"  Action: {initiative['action']}")
        print(f"  Rationale: {initiative.get('rationale', 'N/A')}")
        print(f"  Expected: {initiative.get('expected_outcome', 'N/A')}")
        return

    # Execute: create task, log hypothesis, update memory
    task_body = f"""## Proactive Initiative from Kublai

**What:** {initiative['action']}

**Why:** {initiative.get('rationale', 'Identified as highest-impact proactive action during hourly reflection.')}

**Expected outcome:** {initiative.get('expected_outcome', 'System improvement toward active goals.')}

## Action Required
1. Execute the action described above
2. Report results
3. If the action requires follow-up, create a new task
"""

    create_task(
        initiative["agent"],
        initiative["priority"],
        initiative["action"][:80],
        task_body,
    )

    log_hypothesis(
        initiative["action"],
        initiative.get("expected_outcome", "Unknown"),
    )

    log_initiative_to_memory(initiative)
    mark_fired()

    print(f"INITIATIVE: {initiative['priority']} task created for {initiative['agent']}: {initiative['action'][:80]}")


if __name__ == "__main__":
    main()
