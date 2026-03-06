#!/usr/bin/env python3
"""
Prepare Reflection Context - Option B implementation.

Reads an agent's last memory file, extracts active WHEN/THEN rules and last
commitment, reads tock/latest.json for system context (replacing redundant
CLI calls), and queries Neo4j for 7-day failure patterns.

Outputs compact markdown suitable for injection into a reflection prompt.

Usage:
    python3 prepare_reflection_context.py --agent temujin
    python3 prepare_reflection_context.py --agent kublai --hours 1
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS, AGENT_ROLES, AGENT_MODELS

BASE = Path.home() / ".openclaw/agents"
TOCK_LATEST = BASE / "main/logs/tock/latest.json"
PROTOCOLS_DIR = BASE / "main/scripts/reflection_protocols"
MAX_ACTIVE_RULES = 7


def find_latest_memory_file(agent):
    """Find the most recent memory file for an agent."""
    memory_dir = BASE / agent / "memory"
    if not memory_dir.exists():
        return None

    # Look for date-named files, most recent first
    files = sorted(memory_dir.glob("*.md"), reverse=True)
    for f in files:
        if re.match(r"\d{4}-\d{2}-\d{2}\.md", f.name):
            return f
    return files[0] if files else None


def extract_active_rules(memory_file):
    """Extract WHEN/THEN rules from the memory file.

    Looks for patterns like:
    - WHEN ... THEN ... INSTEAD OF ...
    - Rule N: WHEN ...
    - Lines in an ACTIVE RULES section
    """
    if not memory_file or not memory_file.exists():
        return []

    try:
        content = memory_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    rules = []

    # Look for explicit ACTIVE RULES section
    active_section = re.search(
        r"## ACTIVE RULES.*?\n(.*?)(?=\n## |\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if active_section:
        for line in active_section.group(1).strip().split("\n"):
            line = line.strip()
            if line and re.search(r"WHEN\b", line, re.IGNORECASE):
                # Clean up numbering
                cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
                rules.append(cleaned)

    # Also scan for WHEN/THEN patterns in the broader file (from REFLECTION sections)
    if not rules:
        for match in re.finditer(
            r"(?:NEW RULE|Rule \d+|WHEN)\b[:\s]*(WHEN\b.+?)(?=\n\d+\.|$|\n\*\*|\n##)",
            content,
            re.IGNORECASE,
        ):
            rule = match.group(1).strip()
            # Skip template placeholders (contain [trigger], [action], etc.)
            if len(rule) > 10 and not re.search(r"\[trigger\]|\[action\]|\[old default\]|\[default\]", rule, re.IGNORECASE):
                rules.append(rule)

    # Deduplicate and cap
    seen = set()
    unique_rules = []
    for r in rules:
        normalized = r.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique_rules.append(r)

    return unique_rules[:MAX_ACTIVE_RULES]


def extract_last_commitment(memory_file):
    """Extract the most recent commitment/decision from the memory file."""
    if not memory_file or not memory_file.exists():
        return None

    try:
        content = memory_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Look for the last WORST MOMENT + NEW RULE block (from Option B format)
    commitments = re.findall(
        r"\*\*NEW RULE:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)", content, re.DOTALL
    )
    if commitments:
        # Filter out template placeholders
        real = [c.strip()[:200] for c in commitments
                if not re.search(r"\[trigger\]|\[action\]|\[old default\]|\[default\]", c, re.IGNORECASE)]
        if real:
            return real[-1]

    # Fallback: look for Decision/Commitment/Plan patterns
    for pattern in [
        r"(?:COMMITMENT|Decision|Next|Plan):\s*(.+?)(?=\n\*\*|\n##|\Z)",
        r"(?:I will|I commit to)\s+(.+?)(?:\.|$)",
    ]:
        matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
        if matches:
            return matches[-1].strip()[:200]

    return None


def read_tock_data():
    """Read system context from tock/latest.json instead of re-running CLI commands."""
    if not TOCK_LATEST.exists():
        return None

    try:
        target = TOCK_LATEST.resolve() if TOCK_LATEST.is_symlink() else TOCK_LATEST
        if not target.exists():
            return None
        with open(target) as f:
            return json.load(f)
    except Exception:
        return None


def get_failure_patterns(agent, days=7):
    """Query Neo4j for the agent's recurring failure patterns over N days."""
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (t:Task)
                WHERE t.agent = $agent
                  AND t.status = 'failed'
                  AND t.created > datetime() - duration({days: $days})
                  AND t.error IS NOT NULL
                RETURN t.error AS error, count(t) AS count
                ORDER BY count DESC
                LIMIT 5
                """,
                agent=agent,
                days=days,
            )
            patterns = [
                {"error": r["error"][:100], "count": r["count"]} for r in result
            ]
        driver.close()
        return patterns
    except Exception:
        return []


def format_tock_agent_summary(tock_data, agent):
    """Format compact agent metrics from tock data."""
    if not tock_data:
        return "No tock data available."

    agent_data = tock_data.get("agents", {}).get(agent, {})
    if not agent_data:
        return f"No tock data for {agent}."

    t = agent_data.get("tasks", {})
    s = agent_data.get("session", {})
    sr = agent_data.get("success_rate")
    sr_str = f"{sr}%" if sr is not None else "N/A"

    queues = tock_data.get("queues", {})
    delegations = tock_data.get("delegation", {})

    lines = [
        f"Tasks(30m): {t.get('completed',0)} done, {t.get('failed',0)} failed, {t.get('pending',0)} pending, {t.get('queue_depth',0)} queued",
        f"Success rate: {sr_str} | Retries: {agent_data.get('retries',0)}",
        f"Session: {s.get('pct_used',0)}% ctx used",
        f"System: {queues.get('total_pending',0)} total queued | {delegations.get('count_30m',0)} delegations(30m)",
    ]

    # LLM assessment if available
    assessment = tock_data.get("llm_assessment", {})
    if assessment.get("severity") and assessment["severity"] != "LOW":
        lines.append(
            f"Alert: severity={assessment['severity']} bottleneck={assessment.get('bottleneck','none')}"
        )

    return "\n".join(lines)


def load_protocol(agent):
    """Load the role-specific reflection protocol."""
    protocol_file = PROTOCOLS_DIR / f"{agent}_protocol.md"
    if protocol_file.exists():
        return protocol_file.read_text(encoding="utf-8")
    return None


TASK_LEDGER = Path.home() / ".openclaw/tasks/task-ledger.jsonl"
AUDIT_CACHE = BASE / "main/logs/routing-audit-latest.json"


def get_task_ledger_summary(agent, hours=1):
    """Summarize task ledger events for an agent over the last N hours."""
    if not TASK_LEDGER.exists():
        return None

    cutoff = datetime.now() - timedelta(hours=hours)
    events = []

    try:
        with open(TASK_LEDGER, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                # Filter by agent and time
                if entry.get("agent") != agent:
                    continue
                ts_str = entry.get("ts", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
                events.append(entry)
    except Exception:
        return None

    if not events:
        return "No task events in the last hour."

    completed = [e for e in events if e.get("event") == "COMPLETED"]
    failed = [e for e in events if e.get("event") == "FAILED"]
    executing = [e for e in events if e.get("event") == "EXECUTING"]

    lines = [f"- Executed: {len(executing)} | Completed: {len(completed)} | Failed: {len(failed)}"]

    for e in completed[:3]:
        duration = e.get("execution_time_s", "?")
        lines.append(f"  OK: task={e.get('task_id', '?')[:8]} ({duration}s)")

    for e in failed[:3]:
        error = (e.get("error") or "unknown")[:80]
        lines.append(f"  FAIL: task={e.get('task_id', '?')[:8]} — {error}")

    return "\n".join(lines)


def get_routing_audit(hours=1):
    """Get routing audit data for kublai's reflection.

    Reads from cache written by routing_audit_action.py (runs earlier in the
    hourly pipeline). Falls back to generating fresh if cache is missing.
    """
    try:
        from routing_audit import format_for_reflection

        # Prefer cached result (written by routing_audit_action.py)
        if AUDIT_CACHE.exists():
            import json as _json
            with open(AUDIT_CACHE) as f:
                report = _json.load(f)
            if report.get("total_routed", 0) > 0:
                return format_for_reflection(report)

        # Fallback: generate fresh (e.g. if called outside hourly pipeline)
        from routing_audit import generate_audit
        report = generate_audit(hours=hours)
        if report.get("total_routed", 0) > 0:
            return format_for_reflection(report)
        return None
    except Exception:
        return None


def generate_context(agent, hours=1):
    """Generate the compact reflection context for an agent.

    This is the main entry point. Returns markdown string (~800 tokens target).
    """
    role = AGENT_ROLES.get(agent, "Unknown")
    model = AGENT_MODELS.get(agent, "Unknown")
    now = datetime.now()

    # Gather all data
    memory_file = find_latest_memory_file(agent)
    active_rules = extract_active_rules(memory_file)
    last_commitment = extract_last_commitment(memory_file)
    tock_data = read_tock_data()
    failure_patterns = get_failure_patterns(agent)
    protocol = load_protocol(agent)

    lines = []

    # Header
    lines.append(f"# Reflection: {agent.capitalize()}")
    lines.append(f"**Role:** {role} | **Model:** {model}")
    lines.append(f"**Time:** {now.strftime('%Y-%m-%d %H:%M')} | **Period:** Last {hours}h")
    lines.append("")

    # System metrics (from tock — replaces redundant CLI calls)
    lines.append("## System Metrics (from Tock)")
    lines.append(format_tock_agent_summary(tock_data, agent))
    lines.append("")

    # Routing audit (kublai only — real routing/execution data)
    if agent == "kublai":
        audit_block = get_routing_audit(hours=hours)
        if audit_block:
            lines.append(audit_block)
            lines.append("")

        # Task quality scorecard (kublai only)
        try:
            from score_tasks import score_all_tasks, generate_summary
            score_all_tasks(hours=hours)  # Score any unscored tasks first
            scorecard = generate_summary(hours=hours)
            if scorecard and "No scored tasks" not in scorecard:
                lines.append(scorecard)
                lines.append("")
        except Exception:
            pass

    # Active rules — THE key self-improvement signal
    lines.append("## YOUR BEHAVIORAL RULES (self-generated — you MUST follow these)")
    if active_rules:
        for i, rule in enumerate(active_rules, 1):
            lines.append(f"{i}. {rule}")
        lines.append("")
        lines.append(
            "At the end of this reflection, you MUST evaluate whether you followed each rule above."
        )
    else:
        lines.append("(No active rules yet. You will create your first one below.)")
    lines.append("")

    # Last commitment
    lines.append("## Your Last Commitment")
    if last_commitment:
        lines.append(f"> {last_commitment}")
        lines.append("")
        lines.append("Did you follow through? Assess honestly with evidence.")
    else:
        lines.append("(No previous commitment found. This is your first reflection with this format.)")
    lines.append("")

    # Failure patterns
    if failure_patterns:
        lines.append("## Your Failure Patterns (7-day)")
        for p in failure_patterns:
            lines.append(f"- `{p['error']}` x{p['count']}")
        lines.append("")

    # Task ledger — what actually happened since last reflection
    ledger_summary = get_task_ledger_summary(agent, hours=hours)
    if ledger_summary:
        lines.append("## Task Execution Results (from ledger)")
        lines.append(ledger_summary)
        lines.append("")

    # Error clusters from tock (cross-agent visibility)
    if tock_data:
        errors = tock_data.get("errors", {}).get("clusters", [])
        if errors:
            lines.append("## System Error Clusters (30m)")
            for e in errors[:3]:
                lines.append(
                    f"- `{str(e.get('error',''))[:60]}` x{e.get('count',0)} agents={e.get('agents',[])}"
                )
            lines.append("")

    # Protocol (role-specific questions + reflection template)
    if protocol:
        lines.append(protocol)
    else:
        # Fallback generic protocol
        lines.append("## REFLECTION (complete all 5)")
        lines.append("")
        lines.append("1. **WORST MOMENT:** Your single worst decision this session. (max 30 words)")
        lines.append("2. **ROOT CAUSE:** The behavioral pattern that caused it. (max 20 words)")
        lines.append("3. **NEW RULE:** WHEN [trigger] THEN [action] INSTEAD OF [default]. (max 30 words)")
        lines.append("4. **VERIFICATION:** How will you know you followed this rule? (binary YES/NO check)")
        lines.append("5. **PREVIOUS RULES:** For each active rule — did you follow it? YES or NO.")
    lines.append("")

    # What you can do here
    lines.append("## Actions Available")
    lines.append("- Write your reflection + new rule to memory")
    lines.append("- Submit feedback to Kublai (priority: CRITICAL/HIGH/MEDIUM/LOW)")
    lines.append("- Propose a task for another agent")
    lines.append("")
    lines.append("## What NOT To Do")
    lines.append("- Do not repeat system status back (you already have it above)")
    lines.append("- Focus on WHAT CHANGED and WHAT YOU WILL DO DIFFERENTLY")
    lines.append("- Do not use hedge words (try, maybe, potentially, aim to)")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Prepare reflection context for an agent")
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of markdown")
    args = parser.parse_args()

    context = generate_context(args.agent, args.hours)

    if args.json:
        print(json.dumps({"agent": args.agent, "context": context}))
    else:
        print(context)


if __name__ == "__main__":
    main()
