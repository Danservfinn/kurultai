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
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path.home() / ".openclaw/agents"
TOCK_LATEST = BASE / "main/logs/tock/latest.json"
PROTOCOLS_DIR = BASE / "main/scripts/reflection_protocols"
MAX_ACTIVE_RULES = 7

AGENT_ROLES = {
    "kublai": "Squad Lead / Router",
    "temujin": "Developer (code, builds, infrastructure)",
    "mongke": "Researcher (web research, API discovery)",
    "chagatai": "Writer (documentation, creative content)",
    "jochi": "Analyst (testing, security, pattern recognition)",
    "ogedei": "Ops (monitoring, health checks, failover)",
}

AGENT_MODELS = {
    "kublai": "bailian/qwen3.5-plus",
    "mongke": "bailian/MiniMax-M2.5",
    "chagatai": "bailian/kimi-k2.5",
    "temujin": "bailian/MiniMax-M2.5",
    "jochi": "bailian/qwen3.5-plus",
    "ogedei": "bailian/qwen3.5-plus",
}


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
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            "bolt://localhost:7687", auth=("neo4j", "myStrongPassword123")
        )
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
