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
from kurultai_paths import TASK_LEDGER
from kurultai_ledger import read_ledger
from rule_registry import get_active_rules as _registry_rules, format_rules_block as _format_registry_rules

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


# Claude project memory directory where detailed reflections are stored
_CLAUDE_PROJECT_MEMORY = (
    Path.home()
    / ".claude/projects/-Users-kublai--openclaw-agents-main/memory"
)


def find_reflection_files(agent):
    """Find agent reflection files in Claude project memory.

    Returns list of Paths sorted newest first. These files contain
    structured ## Active Rules sections that the daily memory files lack.
    """
    if not _CLAUDE_PROJECT_MEMORY.exists():
        return []
    files = sorted(
        _CLAUDE_PROJECT_MEMORY.glob(f"{agent}-reflection-*.md"), reverse=True
    )
    return files


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

    # Look for explicit ACTIVE RULES section (any heading depth)
    active_section = re.search(
        r"#{1,4} (?:ACTIVE |Active |YOUR BEHAVIORAL )?RULES.*?\n(.*?)(?=\n#{1,4} |\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if active_section:
        for line in active_section.group(1).strip().split("\n"):
            line = line.strip()
            if line and re.search(r"WHEN\b", line, re.IGNORECASE):
                # Clean up numbering and bold markers
                cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
                cleaned = re.sub(r"^\*{2}\([^)]*\)\*{2}\s*", "", cleaned)
                rules.append(cleaned)

    # Scan for WHEN/THEN patterns after NEW RULE headers (standard reflection format)
    if not rules:
        for match in re.finditer(
            r"(?:NEW RULE|Rule \d+|WHEN)\b[\*:\s]*(WHEN\b.+?)(?=\n\n|\n\d+[\.\)]|$|\n\*\*|\n#)",
            content,
            re.IGNORECASE,
        ):
            rule = match.group(1).strip()
            if len(rule) > 10 and not re.search(
                r"\[trigger\]|\[action\]|\[old default\]|\[default\]", rule, re.IGNORECASE
            ):
                rules.append(rule)

    # Ultimate fallback: scan every line for WHEN...THEN patterns
    if not rules:
        for line in content.split("\n"):
            line = line.strip()
            if re.search(r"\bWHEN\b.+\bTHEN\b", line, re.IGNORECASE):
                # Clean markdown formatting (order matters: list markers first, then bold)
                cleaned = re.sub(r"^-\s*", "", line)
                cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
                cleaned = re.sub(r"^\*{2,}[^*]+\*{2,}[:\s]*", "", cleaned)
                cleaned = cleaned.strip()
                if len(cleaned) > 10 and not re.search(
                    r"\[trigger\]|\[action\]|\[old default\]|\[default\]",
                    cleaned,
                    re.IGNORECASE,
                ):
                    rules.append(cleaned)

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


AUDIT_CACHE = BASE / "main/logs/routing-audit-latest.json"
OVERFLOW_LOG = BASE / "main/logs/routing-overflow.jsonl"
CAPABILITY_SCORES = BASE / "main/logs/capability-scores.json"
SKILL_STATS = BASE / "main/logs/skill-stats.json"


def get_task_ledger_summary(agent, hours=1):
    """Summarize task ledger events for an agent over the last N hours."""
    try:
        all_events = read_ledger(hours=hours)
    except Exception:
        return None

    events = [entry for entry in all_events if entry.get("agent") == agent]

    if not events:
        return "No task events in the last hour."

    # Group events by task_id to deduplicate retried tasks
    from collections import defaultdict
    tasks = defaultdict(list)
    for e in events:
        tid = e.get("task_id")
        if tid:
            tasks[tid].append(e)

    # Determine final state per unique task
    final_completed = []  # (task_id, duration, retried)
    final_failed = []     # (task_id, error)
    for tid, task_events in tasks.items():
        event_types = [ev.get("event") for ev in task_events]
        has_completed = "COMPLETED" in event_types
        has_failed = "FAILED" in event_types
        has_recovered = "RECOVERED" in event_types
        retried = has_recovered or (has_failed and has_completed)

        if has_completed:
            # Find the COMPLETED event for duration
            comp_event = next(ev for ev in task_events if ev.get("event") == "COMPLETED")
            final_completed.append((tid, comp_event.get("execution_time_s", "?"), retried))
        elif has_failed:
            fail_event = next(ev for ev in reversed(task_events) if ev.get("event") == "FAILED")
            final_failed.append((tid, (fail_event.get("error") or "unknown")[:80]))

    unique_executed = len([tid for tid, evts in tasks.items()
                          if any(ev.get("event") in ("EXECUTING", "COMPLETED", "FAILED") for ev in evts)])
    retried_count = sum(1 for _, _, r in final_completed if r) + \
                    sum(1 for tid, _ in final_failed
                        if any(ev.get("event") == "RECOVERED" for ev in tasks[tid]))

    lines = [f"- Executed: {unique_executed} | Completed: {len(final_completed)} | Failed: {len(final_failed)}"
             + (f" | Retried: {retried_count}" if retried_count else "")]

    for tid, duration, retried in final_completed[:3]:
        retry_tag = " (retried)" if retried else ""
        lines.append(f"  OK: task={tid[:8]} ({duration}s){retry_tag}")

    for tid, error in final_failed[:3]:
        lines.append(f"  FAIL: task={tid[:8]} — {error}")

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


def get_peer_digest(agent, hours=1):
    """Summarize other agents' activity for cross-agent context.

    Returns ~150 tokens of markdown or None if no data.
    """
    try:
        all_events = read_ledger(hours=hours)
    except Exception:
        return None

    cutoff = datetime.now() - timedelta(hours=hours)
    peer_events = {}  # agent -> {ok, fail}
    overflow_events = []

    for entry in all_events:
        peer = entry.get("agent")
        if not peer or peer == agent:
            continue
        ev = entry.get("event")
        if peer not in peer_events:
            peer_events[peer] = {"ok": 0, "fail": 0}
        if ev == "COMPLETED":
            peer_events[peer]["ok"] += 1
        elif ev == "FAILED":
            peer_events[peer]["fail"] += 1

    if not peer_events:
        return None

    # Read overflow events touching this agent
    if OVERFLOW_LOG.exists():
        try:
            with open(OVERFLOW_LOG, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    ts_str = entry.get("ts", "")
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts < cutoff:
                            continue
                    except (ValueError, TypeError):
                        continue
                    if entry.get("to") == agent or entry.get("from") == agent:
                        overflow_events.append(entry)
        except Exception:
            pass

    lines = [f"## Peer Activity (cross-agent, last {hours}h)"]
    for peer, counts in sorted(peer_events.items()):
        fail_str = f" FAIL:{counts['fail']}" if counts["fail"] else ""
        lines.append(f"- {peer}: {counts['ok']} ok{fail_str}")

    if overflow_events:
        lines.append("Overflow events:")
        for oe in overflow_events[:3]:
            lines.append(
                f"- {oe.get('from','?')}->{oe.get('to','?')}: {oe.get('title','?')[:50]} ({oe.get('reason','')})"
            )

    return "\n".join(lines)


def get_capability_scores_block(agent):
    """Load and format this agent's capability scores from route_quality_tracker.

    Returns a markdown block or None.
    """
    if not CAPABILITY_SCORES.exists():
        return None

    try:
        with open(CAPABILITY_SCORES) as f:
            scores = json.load(f)
    except Exception:
        return None

    # Staleness check (2h)
    try:
        mtime = CAPABILITY_SCORES.stat().st_mtime
        import time as _time
        if _time.time() - mtime > 7200:
            return None
    except Exception:
        pass

    agent_scores = scores.get(agent, {})
    if not agent_scores:
        return None

    overall = agent_scores.get("overall", {})
    avg = overall.get("avg_score", None)
    total = overall.get("task_count", 0)
    if avg is None:
        return None

    status = "HEALTHY" if avg >= 6.0 else ("LOW" if avg < 4.0 else "OK")
    lines = [f"## Your Quality Rating (routing system view)"]
    lines.append(f"Overall: {avg:.1f}/10 ({total} tasks, 7d) — {status}")

    categories = {k: v for k, v in agent_scores.items() if k != "overall"}
    for cat, cat_data in sorted(categories.items()):
        cat_avg = cat_data.get("avg_score", 0)
        cat_count = cat_data.get("task_count", 0)
        cat_status = "ok" if cat_avg >= 6.0 else "LOW — tasks may be diverted"
        lines.append(f"  {cat} tasks: {cat_avg:.1f}/10 ({cat_count} tasks) [{cat_status}]")

    return "\n".join(lines)



def get_skill_telemetry_block(agent, hours=2):
    """
    Returns skill performance block for reflection.
    Shows at most 3 skills: lowest performers first.
    Returns None if fewer than 3 skill uses or data is stale (>2h).
    """
    if not SKILL_STATS.exists():
        return None
    try:
        import time as _t
        if _t.time() - SKILL_STATS.stat().st_mtime > 7200:
            return None
        data = json.loads(SKILL_STATS.read_text())
        agent_data = data.get("agents", {}).get(agent, {})
        if not agent_data or sum(v.get("uses_7d", 0) for v in agent_data.values()) < 3:
            return None
    except Exception:
        return None

    sorted_skills = sorted(
        agent_data.items(),
        key=lambda x: x[1].get("success_rate", 1.0)
    )

    lines = ["## Skill Performance (7d)"]
    shown = 0
    for skill, stats in sorted_skills[:3]:
        sr = stats.get("success_rate")
        if sr is None:
            continue
        q = stats.get("avg_output_quality", 0)
        action = stats.get("recommended_action", "keep")
        flag = " <- LOW" if action != "keep" else ""
        trend = stats.get("trend", "stable")
        cc = stats.get("claude_code_rate", 1.0)
        lines.append(f"- {skill}: {sr:.0%} ok, q={q:.1f}/3, cc={cc:.0%} [{action.upper()}{flag}] trend:{trend}")
        shown += 1

    if shown == 0:
        return None

    return "\n".join(lines)


def get_action_quality_block(agent, hours=2):
    """
    Reads most recent ACTION_SCORED event for agent.
    Returns markdown block with per-category scores and worst flag.
    """
    events = read_ledger(hours=hours * 4)
    action_scored = [e for e in events
                     if e.get("event") == "ACTION_SCORED" and e.get("agent") == agent]
    if not action_scored:
        return None

    latest = max(action_scored, key=lambda x: x.get("ts", ""))
    scores = {
        "memory": latest.get("memory_score"),
        "reflection": latest.get("reflection_score"),
        "output": latest.get("output_score"),
        "decision": latest.get("decision_score"),
        "tool": latest.get("tool_score"),
    }
    worst = latest.get("worst_category")
    flag = latest.get("worst_flag")
    cc_rate = latest.get("claude_code_rate")

    lines = [f"## Action Quality ({hours}h)"]
    for cat, score in scores.items():
        if score is None:
            continue
        bar = ["--", "ok", "good", "great"][min(3, int(score))]
        lines.append(f"- {cat}: {score}/3 [{bar}]")
    if cc_rate is not None:
        lines.append(f"- claude_code_usage: {cc_rate:.0%}")
    if worst and flag:
        lines.append(f"Focus: {worst} ({flag})")

    return "\n".join(lines)


def generate_context(agent, hours=1):
    """Generate the compact reflection context for an agent."""
    role = AGENT_ROLES.get(agent, "Unknown")
    model = AGENT_MODELS.get(agent, "Unknown")
    now = datetime.now()

    # Track which data sources contributed vs were empty/failed
    _sources = {}  # name -> "ok" | "empty" | "error"

    # Gather all data — prefer structured rule registry, fall back to regex extraction
    memory_file = find_latest_memory_file(agent)

    # Primary: structured rule registry (survives daily log rotation)
    active_rules = _registry_rules(agent)

    # Fallback 1: regex extraction from daily memory files
    if not active_rules:
        active_rules = extract_active_rules(memory_file)

    # Fallback 2: Claude project reflection files
    if not active_rules:
        for ref_file in find_reflection_files(agent):
            active_rules = extract_active_rules(ref_file)
            if active_rules:
                break

    _sources["rules"] = "ok" if active_rules else "empty"

    last_commitment = extract_last_commitment(memory_file)
    if not last_commitment:
        for ref_file in find_reflection_files(agent):
            last_commitment = extract_last_commitment(ref_file)
            if last_commitment:
                break
    _sources["commitment"] = "ok" if last_commitment else "empty"

    tock_data = read_tock_data()
    _sources["tock"] = "ok" if tock_data else "empty"
    failure_patterns = get_failure_patterns(agent)
    _sources["neo4j_failures"] = "ok" if failure_patterns else "empty"
    protocol = load_protocol(agent)
    _sources["protocol"] = "ok" if protocol else "empty"

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

    # Pipeline Health — throughput metrics
    try:
        from pipeline_health import format_pipeline_health
        health_block = format_pipeline_health(agent, hours=hours)
        if health_block:
            lines.append(health_block)
            lines.append("")
            _sources["pipeline_health"] = "ok"
        else:
            _sources["pipeline_health"] = "empty"
    except Exception:
        _sources["pipeline_health"] = "error"

    # Routing audit + scorecard (kublai only — not budget-capped, important for router)
    if agent == "kublai":
        audit_block = get_routing_audit(hours=hours)
        if audit_block:
            lines.append(audit_block)
            lines.append("")
            _sources["routing_audit"] = "ok"
        else:
            _sources["routing_audit"] = "empty"

        try:
            from score_tasks import score_all_tasks, generate_summary
            score_all_tasks(hours=hours)
            scorecard = generate_summary(hours=hours)
            if scorecard and "No scored tasks" not in scorecard:
                lines.append(scorecard)
                lines.append("")
                _sources["scorecard"] = "ok"
            else:
                _sources["scorecard"] = "empty"
        except Exception:
            _sources["scorecard"] = "error"

    # Capability scores
    try:
        cap_block = get_capability_scores_block(agent)
        if cap_block:
            lines.append(cap_block)
            lines.append("")
            _sources["capability_scores"] = "ok"
        else:
            _sources["capability_scores"] = "empty"
    except Exception:
        _sources["capability_scores"] = "error"

    # Skill telemetry
    skill_block = get_skill_telemetry_block(agent, hours=hours)
    if skill_block:
        lines.append(skill_block)
        lines.append("")
        _sources["skill_telemetry"] = "ok"
    else:
        _sources["skill_telemetry"] = "empty"

    # Action quality
    action_block = get_action_quality_block(agent, hours=hours)
    if action_block:
        lines.append(action_block)
        lines.append("")
        _sources["action_quality"] = "ok"
    else:
        _sources["action_quality"] = "empty"

    # Peer digest — cross-agent activity
    try:
        peer_block = get_peer_digest(agent, hours=hours)
        if peer_block:
            lines.append(peer_block)
            lines.append("")
            _sources["peer_digest"] = "ok"
        else:
            _sources["peer_digest"] = "empty"
    except Exception:
        _sources["peer_digest"] = "error"

    # Rule proposals from peers
    try:
        from neo4j_task_tracker import get_driver
        driver = get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (p:RuleProposal)
                WHERE p.target_agent = $agent AND p.status = 'pending'
                RETURN p.source_agent AS src, p.rule_text AS rule,
                       p.invocations AS inv, p.reason AS reason
                ORDER BY p.created DESC LIMIT 3
                """,
                agent=agent,
            )
            proposals = list(result)
        driver.close()
        if proposals:
            prop_lines = ["## Proposed Rules From Peers (consider adopting)"]
            for p in proposals:
                prop_lines.append(
                    f"- From {p['src']} (used {p['inv']}x): {p['rule']}"
                )
                if p.get("reason"):
                    prop_lines.append(f"  Reason: {p['reason']}")
            lines.append("\n".join(prop_lines))
            lines.append("")
            _sources["peer_rules"] = "ok"
        else:
            _sources["peer_rules"] = "empty"
    except Exception:
        _sources["peer_rules"] = "error"

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

    # Data quality diagnostic — shows which sources contributed
    ok_sources = [s for s, v in _sources.items() if v == "ok"]
    empty_sources = [s for s, v in _sources.items() if v == "empty"]
    error_sources = [s for s, v in _sources.items() if v == "error"]
    total = len(_sources)
    ok_count = len(ok_sources)

    lines.append(f"## Data Quality ({ok_count}/{total} sources active)")
    if error_sources:
        lines.append(f"- FAILED: {', '.join(error_sources)}")
    if empty_sources:
        lines.append(f"- Empty: {', '.join(empty_sources)}")
    lines.append("")

    # Emit pipeline event for observability
    try:
        from neo4j_task_tracker import get_tracker
        context_text = "\n".join(lines)
        get_tracker().emit_pipeline_event(
            "HOURLY_DIGEST", agent=agent,
            payload={
                "context_chars": len(context_text),
                "hours": hours,
                "sources_ok": ok_count,
                "sources_total": total,
                "sources_error": error_sources,
            },
        )
    except Exception:
        pass

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
