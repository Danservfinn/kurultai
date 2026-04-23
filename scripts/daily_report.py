#!/usr/bin/env python3
"""
Unified Daily Report Generator

Merges 5 near-duplicate scripts into one parameterized tool:
  - daily_goal_progress.py
  - daily_goal_report.py
  - daily_progress_report.py
  - daily_progress_summary.py
  - goal_progress_report.py

Modes (via --mode):
  goal-progress   Project-based progress from Neo4j (Project→Component→Phase).
                  Default mode. Equivalent to the former daily_goal_progress.py.

  progress-report Like goal-progress but adds critical-failure tracking and
                  overall system health. Equivalent to daily_goal_report.py.

  progress-summary  Filesystem-based scan of agent task directories (no Neo4j).
                    Useful when Neo4j is down. Equivalent to
                    daily_progress_report.py.

  agent-performance  Agent-centric stats (completed/failed/pending per agent)
                     from Neo4j. Equivalent to goal_progress_report.py.

Usage:
  python3 daily_report.py                          # default: goal-progress
  python3 daily_report.py --mode progress-report
  python3 daily_report.py --mode progress-summary
  python3 daily_report.py --mode agent-performance
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NEO4J_USER = "neo4j"
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD")
NEO4J_ADDR = os.environ.get("NEO4J_URI", "bolt://localhost:7687")

MAIN_DIR = Path("/Users/kublai/.openclaw/agents/main")
AGENTS_DIR = Path("/Users/kublai/.openclaw/agents")
TOCK_LATEST = MAIN_DIR / "logs" / "tock" / "latest.json"

# Hard-coded goals used only by the filesystem (progress-summary) mode.
GOALS = {
    "Parse": {
        "keywords": ["parse", "parsethe", "parse media", "parsethe.media"],
        "deadline": "2026-06-09",
        "target_mrr": 1500,
    },
    "LLM Survivor": {
        "keywords": ["llm survivor", "llmsurvivor", "tribal", "llmsurvivor.kurult"],
        "deadline": "2026-04-12",
    },
    "Heartbeat Master": {
        "keywords": ["heartbeat", "heartbeats", "master", "daemon", "watchdog"],
        "deadline": None,
    },
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def run_cypher(query):
    """Execute a Cypher query via cypher-shell and return parsed rows."""
    if not NEO4J_PASS:
        raise EnvironmentError("NEO4J_PASSWORD environment variable not set")

    cmd = [
        "cypher-shell",
        "-a", NEO4J_ADDR,
        "-u", NEO4J_USER,
        "-p", NEO4J_PASS,
        query,
        "--format", "plain",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return []

    lines = result.stdout.strip().split("\n")
    if len(lines) < 2:
        return []

    header = [h.strip() for h in lines[0].split(", ")]

    rows = []
    for line in lines[1:]:
        if not line.strip():
            continue
        values = []
        in_quotes = False
        current = ""
        for char in line:
            if char == '"' and (not current or current[-1] != '\\'):
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                values.append(current.strip().strip('"'))
                current = ""
            else:
                current += char
        values.append(current.strip().strip('"'))
        if len(values) == len(header):
            rows.append(dict(zip(header, values)))

    return rows


def _days_remaining(target_date):
    """Return days remaining until *target_date* (ISO string) or None."""
    if not target_date or target_date == "NULL":
        return None
    try:
        if "T" in target_date:
            target_date = target_date.split("T")[0]
        target = datetime.strptime(target_date, "%Y-%m-%d")
        return max(0, (target - datetime.now()).days)
    except Exception:
        return None


def _pct(complete, total):
    if total == 0:
        return 0
    return min(100, round(complete / total * 100))

# ---------------------------------------------------------------------------
# Mode: goal-progress  (was daily_goal_progress.py)
# ---------------------------------------------------------------------------

def _get_active_projects():
    return run_cypher(
        'MATCH (p:Project {status: "in_progress"}) '
        'RETURN p.name AS name, p.goal AS goal, '
        'p.target_date AS target_date, p.target_revenue AS target_revenue, '
        'p.priority AS priority'
    )


def _get_component_stats(project_name):
    rows = run_cypher(
        f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_COMPONENT]->(c:Component) '
        f'RETURN c.status AS status, count(c) AS cnt'
    )
    stats = {"complete": 0, "in_progress": 0, "pending": 0, "total": 0}
    for r in rows:
        s = r.get("status", "pending")
        n = int(r.get("cnt", 0))
        if s in stats:
            stats[s] = n
        stats["total"] += n
    return stats


def _get_phase_progress(project_name):
    return run_cypher(
        f'MATCH (p:Project {{name: "{project_name}"}})-[:HAS_PHASE]->(ph:Phase) '
        f'RETURN ph.name AS name, ph.status AS status ORDER BY ph.name'
    )


def _get_task_stats_for_project(project_name):
    safe = project_name.replace('"', '\\"')
    rows = run_cypher(
        f'MATCH (t:Task) WHERE t.title CONTAINS "{safe}" '
        f'OR t.title CONTAINS "{project_name.split()[0].lower()}" '
        f'RETURN t.status AS status, count(t) AS cnt'
    )
    stats = {"COMPLETED": 0, "FAILED": 0, "BLOCKED": 0, "in_progress": 0, "total": 0}
    for r in rows:
        s = r.get("status", "unknown")
        n = int(r.get("cnt", 0))
        if s in stats:
            stats[s] = n
        stats["total"] += n
    return stats


def _get_recent_wins(project_name, days=7):
    safe = project_name.replace('"', '\\"')
    rows = run_cypher(
        f'MATCH (t:Task {{status: "COMPLETED"}}) '
        f'WHERE (t.title CONTAINS "{safe}" OR t.title CONTAINS "Parse") '
        f'AND t.created > (datetime() - duration({{days: {days}}})) '
        f'RETURN t.title AS title ORDER BY t.created DESC LIMIT 5'
    )
    return [r.get("title", "")[:60] for r in rows]


def _get_stalled_tasks(project_name, hours=48):
    safe = project_name.replace('"', '\\"')
    rows = run_cypher(
        f'MATCH (t:Task) WHERE (t.title CONTAINS "{safe}" OR t.title CONTAINS "Parse") '
        f'AND t.status IN ["FAILED", "BLOCKED", "ORPHANED"] '
        f'AND t.updated < (datetime() - duration({{hours: {hours}}})) '
        f'RETURN t.title AS title, t.status AS status LIMIT 3'
    )
    return [f"{r.get('title', '')[:50]} ({r.get('status', '?')})" for r in rows]


def _get_critical_failures():
    rows = run_cypher(
        'MATCH (t:Task) WHERE t.status = "FAILED" '
        'AND t.updated > (datetime() - duration({hours: 24})) '
        'AND NOT t.title CONTAINS "TEST" '
        'RETURN t.title AS title, t.agent AS agent ORDER BY t.updated DESC LIMIT 5'
    )
    return rows


def _next_milestone(phases):
    for ph in phases:
        if ph.get("status") != "complete":
            return f"Complete {ph.get('name', 'next phase')}"
    return "All phases complete"


def _weighted_progress(comp):
    total = comp.get("total", 0)
    if total == 0:
        return 0
    w = comp.get("complete", 0) * 1.0 + comp.get("in_progress", 0) * 0.5
    return min(100, round(w / total * 100))


def _system_health():
    rows = run_cypher('MATCH (t:Task) RETURN t.status AS status, count(t) AS cnt')
    total = completed = failed = 0
    for r in rows:
        n = int(r.get("cnt", 0))
        total += n
        if r.get("status") == "COMPLETED":
            completed = n
        elif r.get("status") == "FAILED":
            failed = n
    rate = round((completed / total * 100) if total > 0 else 0)
    return total, completed, failed, rate


def mode_goal_progress():
    """Original daily_goal_progress.py logic."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📊 Daily Progress {today}", ""]

    projects = _get_active_projects()
    if not projects:
        lines += ["## No Active Projects",
                   "- No projects with status 'in_progress' found in Neo4j", ""]
    else:
        for proj in projects:
            name = proj.get("name", "Unknown")
            goal = proj.get("goal", "")
            target_date = proj.get("target_date")
            target_revenue = proj.get("target_revenue")

            comp = _get_component_stats(name)
            progress = _weighted_progress(comp)
            days_left = _days_remaining(target_date)
            phases = _get_phase_progress(name)
            nxt = _next_milestone(phases)
            ts = _get_task_stats_for_project(name)
            wins = _get_recent_wins(name)
            blockers = _get_stalled_tasks(name)

            lines.append(f"## {name}")
            if days_left is not None:
                lines.append(f"- Progress: {progress}% complete, {days_left} days remaining")
            else:
                lines.append(f"- Progress: {progress}% complete (ongoing)")
            if goal:
                lines.append(f"- Goal: {goal}")
            if "Parse" in name and target_revenue and target_revenue != "NULL":
                lines.append(f"- 💰 Target MRR: ${target_revenue} (first paying customer)")
            if ts["total"] > 0:
                lines.append(
                    f"- 📋 Tasks: {ts.get('COMPLETED', 0)} completed, "
                    f"{ts.get('in_progress', 0)} in progress, {ts.get('FAILED', 0)} failed"
                )
            if wins:
                lines.append(f"- ✅ Wins: {', '.join(wins)}")
            elif progress == 100:
                lines.append("- ✅ Wins: All components complete")
            elif ts.get("COMPLETED", 0) > 0:
                lines.append(f"- ✅ Wins: {ts.get('COMPLETED', 0)} related task(s) completed")
            else:
                lines.append("- ✅ Wins: Initializing")
            if blockers:
                lines.append(f"- ⚠️ Blockers: {', '.join(blockers)}")
            else:
                lines.append("- ⚠️ Blockers: None identified")
            if progress >= 100:
                lines.append("- 📍 Next: Project complete - ready for launch")
            elif comp["total"] == 0:
                lines.append("- 📍 Next: Define components and phases for tracking")
            elif days_left is not None and days_left < 7:
                lines.append(f"- 📍 Next: CRITICAL - {nxt} (deadline in {days_left} days)")
            elif days_left is not None and days_left < 14:
                lines.append(f"- 📍 Next: URGENT - {nxt} ({days_left} days remaining)")
            else:
                lines.append(f"- 📍 Next: {nxt}")
            lines.append("")

    # System health tail
    total, completed, failed, rate = _system_health()
    lines += ["---", "## System Health",
              f"- 📈 Success Rate: {rate}% ({completed}/{total})",
              f"- ⚠️ Failed: {failed}",
              f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST"]

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Mode: progress-report  (was daily_goal_report.py — adds critical failures)
# ---------------------------------------------------------------------------

def _get_recent_tasks_global(days=7):
    rows = run_cypher(
        f'MATCH (t:Task {{status: "COMPLETED"}}) '
        f'WHERE t.created > datetime().minusDays({days}) '
        f'RETURN t.title AS title, t.agent AS agent ORDER BY t.created DESC LIMIT 10'
    )
    return rows


def _get_stalled_global():
    rows = run_cypher(
        'MATCH (t:Task) WHERE t.status IN ["FAILED", "ORPHANED"] '
        'AND t.updated < (datetime() - duration({hours: 48})) '
        'RETURN t.title AS title, t.status AS status, t.agent AS agent'
    )
    return rows


def mode_progress_report():
    """Like goal-progress but with global critical-failure tracking."""
    today = datetime.now().strftime("%Y-%m-%d")
    projects = _get_active_projects()
    recent = _get_recent_tasks_global()
    stalled = _get_stalled_global()
    crits = _get_critical_failures()

    lines = [f"📊 Daily Progress {today}", ""]

    for proj in projects:
        name = proj.get("name", "Unknown")
        target_date = proj.get("target_date")
        days_left = _days_remaining(target_date)

        comp = _get_component_stats(name)
        total_c = comp["total"]
        complete_c = comp["complete"]
        in_prog_c = comp["in_progress"]
        pct = _pct(complete_c, total_c)
        phases = _get_phase_progress(name)
        nxt = _next_milestone(phases)

        lines.append(f"## {name}")
        bit = f"- Progress: {pct}% complete"
        if days_left is not None:
            bit += f", {days_left} days remaining"
        elif total_c == 0:
            bit += " (no components tracked)"
        lines.append(bit)
        lines.append(f"- Goal: {proj.get('goal', '')}")

        # Wins
        related = [t for t in recent
                   if name.split()[0].lower() in t.get("title", "").lower()
                   or "OpenRouter" in t.get("title", "")]
        if related:
            lines.append(f"- ✅ Wins: {', '.join(t['title'][:50] for t in related[:3])}")
        elif pct == 100:
            lines.append("- ✅ Wins: Component migration complete")
        elif recent:
            lines.append(f"- ✅ Wins: {recent[0].get('title', '')[:60]}...")
        else:
            lines.append("- ✅ Wins: Initializing")

        if stalled:
            lines.append(f"- ⚠️ Blockers: {len(stalled)} stalled - {stalled[0].get('title', '')[:50]}...")
        else:
            lines.append("- ⚠️ Blockers: None identified")

        if total_c == 0:
            lines.append("- 📍 Next: Define components and phases")
        elif pct == 100:
            lines.append("- 📍 Next: Project complete - ready for launch")
        else:
            lines.append(f"- 📍 Next: {nxt}")
        lines.append("")

    if not projects:
        lines += ["## System Status",
                   "- No active projects tracked in Neo4j",
                   f"- ✅ Recent completions: {len(recent)} tasks in last 7 days"]
        if stalled:
            lines.append(f"- ⚠️ Blockers: {len(stalled)} stalled task(s)")
        lines.append("- 📍 Next: Initialize project tracking")

    # System health
    total, completed, failed, rate = _system_health()
    orphaned = sum(1 for s in stalled if s.get("status") == "ORPHANED")
    lines += ["---", "## System Health",
              f"- 📈 Task Success Rate: {rate}% ({completed}/{total} completed)",
              f"- ⚠️ Failed: {failed}, Orphaned: {orphaned}"]
    if crits:
        lines.append("- 🔴 Critical Failures (24h):")
        for c in crits[:3]:
            lines.append(f"  - {c.get('title', '')[:60]} ({c.get('agent', '')})")
    if stalled:
        lines.append(f"- 🕒 Stalled (>48h): {len(stalled)} task(s)")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Mode: progress-summary  (was daily_progress_report.py — filesystem-based)
# ---------------------------------------------------------------------------

def _read_tock():
    if not TOCK_LATEST.exists():
        return {}
    try:
        with open(TOCK_LATEST) as f:
            return json.load(f)
    except Exception:
        return {}


def _scan_agent_tasks():
    agents = ["kublai", "temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui"]
    tasks = []
    for agent in agents:
        task_dir = AGENTS_DIR / agent / "tasks"
        if not task_dir.exists():
            continue
        for fpath in task_dir.glob("*.md"):
            if ".archived" in str(fpath):
                continue
            fname = fpath.name
            if ".failed" in fname:
                status = "FAILED"
            elif any(x in fname for x in (".completed", ".done", ".resolved")):
                status = "COMPLETED"
            elif ".executing" in fname:
                status = "EXECUTING"
            else:
                status = "PENDING"
            try:
                content = fpath.read_text(errors="replace")
                m = re.search(r'^# Task:\s*(.+)$', content, re.MULTILINE)
                title = m.group(1).strip() if m else fname
                cm = re.search(r'^created:\s*(.+)$', content, re.MULTILINE)
                created = cm.group(1).strip() if cm else None
            except Exception:
                title, created = fname, None
            tasks.append({"agent": agent, "status": status,
                          "title": title, "created": created, "file": fname})
    return tasks


def _task_stats_for_goal(keywords, all_tasks):
    matching = [t for t in all_tasks
                if any(kw.lower() in f"{t['title']} {t['file']}".lower()
                       for kw in keywords)]
    total = len(matching)
    completed = sum(1 for t in matching if t["status"] == "COMPLETED")
    in_progress = sum(1 for t in matching if t["status"] in ("EXECUTING", "PENDING"))
    failed = sum(1 for t in matching if t["status"] == "FAILED")

    seven = datetime.now() - timedelta(days=7)
    wins = []
    for t in matching:
        if t["status"] == "COMPLETED" and t["created"]:
            try:
                dt = datetime.fromisoformat(t["created"].replace("Z", ""))
                if dt > seven:
                    wins.append(t["title"][:60])
            except Exception:
                pass
    wins = wins[:5]

    blockers = []
    seen = set()
    for t in matching:
        key = t["title"][:50]
        if t["status"] == "FAILED" and key not in seen:
            seen.add(key)
            blockers.append(f"{key} (failed)")
        elif t["status"] == "PENDING" and t["created"]:
            try:
                dt = datetime.fromisoformat(t["created"].replace("Z", ""))
                if dt < datetime.now() - timedelta(hours=48) and key not in seen:
                    seen.add(key)
                    blockers.append(f"{key} (stale)")
            except Exception:
                pass
    blockers = blockers[:3]

    return {"total": total, "completed": completed,
            "in_progress": in_progress, "failed": failed,
            "wins": wins, "blockers": blockers}


def mode_progress_summary():
    """Filesystem-based progress summary (no Neo4j required)."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📊 Daily Progress {today}", ""]

    tock = _read_tock()
    all_tasks = _scan_agent_tasks()

    for gname, gcfg in GOALS.items():
        st = _task_stats_for_goal(gcfg["keywords"], all_tasks)
        prog = _pct(st["completed"], st["total"])
        rem = _days_remaining(gcfg.get("deadline"))

        lines.append(f"## {gname}")
        if rem is not None:
            lines.append(f"- Progress: {prog}% complete, {rem} days remaining")
        else:
            lines.append(f"- Progress: {prog}% complete (ongoing)")
        if gname == "Parse":
            m = tock.get("parse_metrics", {})
            lines.append(f"- 💰 MRR: ${m.get('mrr', 0):,} | "
                         f"Users: {m.get('paying_users', 0)} | "
                         f"Conv: {m.get('conversion_rate', 0):.1f}%")
        lines.append(f"- 📋 Tasks: {st['completed']}/{st['total']} completed, "
                     f"{st['in_progress']} in progress, {st['failed']} failed")
        lines.append(f"- ✅ Wins: {', '.join(st['wins']) or 'None this week'}")
        lines.append(f"- ⚠️ Blockers: {', '.join(st['blockers']) or 'None'}")
        if prog < 100 and rem is not None:
            if rem < 7:
                lines.append(f"- 📍 Next: CRITICAL - deadline in {rem} days")
            elif rem < 14:
                lines.append(f"- 📍 Next: URGENT - accelerate progress ({rem} days)")
            elif rem < 30:
                lines.append("- 📍 Next: On track - maintain momentum")
            else:
                lines.append("- 📍 Next: Steady progress toward goal")
        elif prog >= 100:
            lines.append("- 📍 Next: Goal complete!")
        else:
            lines.append("- 📍 Next: Ongoing maintenance and improvement")
        lines.append("")

    cron = tock.get("cron", {})
    lines.append("---")
    if cron:
        lines.append(f"System: {cron.get('healthy', 0)}/{cron.get('total_jobs', 0)} cron jobs healthy")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} EST")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Mode: agent-performance  (was goal_progress_report.py)
# ---------------------------------------------------------------------------

def _get_task_stats_by_agent():
    rows = run_cypher(
        'MATCH (t:Task) WHERE t.created >= datetime() - duration("P7D") '
        'WITH t.assigned_to AS agent, count(t) AS total, '
        'sum(CASE WHEN t.status = "COMPLETED" THEN 1 ELSE 0 END) AS completed, '
        'sum(CASE WHEN t.status = "FAILED" THEN 1 ELSE 0 END) AS failed, '
        'sum(CASE WHEN t.status = "PENDING" THEN 1 ELSE 0 END) AS pending '
        'RETURN agent, total, completed, failed, pending, '
        'round(toFloat(completed) / total * 100, 1) AS rate ORDER BY total DESC'
    )
    return [r for r in rows if r.get("agent")]


def _get_global_wins(limit=5):
    return run_cypher(
        f'MATCH (t:Task {{status: "COMPLETED"}}) '
        f'WHERE t.completed_at >= datetime() - duration("P7D") '
        f'RETURN t.title AS title, t.assigned_to AS agent '
        f'ORDER BY t.completed_at DESC LIMIT {limit}'
    )


def _get_blocked_tasks():
    return run_cypher(
        'MATCH (t:Task {status: "PENDING"}) '
        'WHERE t.created < datetime() - duration("P1D") '
        'RETURN t.title AS title, t.assigned_to AS agent ORDER BY t.created ASC LIMIT 10'
    )


def _get_failed_tasks():
    return run_cypher(
        'MATCH (t:Task {status: "FAILED"}) '
        'WHERE t.created >= datetime() - duration("P7D") '
        'RETURN t.title AS title, t.assigned_to AS agent ORDER BY t.created DESC LIMIT 5'
    )


def mode_agent_performance():
    """Agent-centric report with per-agent completion rates."""
    today = datetime.now().strftime("%B %d, %Y")
    lines = [f"📊 Daily Progress - {today}", ""]

    agent_stats = _get_task_stats_by_agent()
    wins = _get_global_wins()
    blocked = _get_blocked_tasks()
    failed = _get_failed_tasks()

    # Agent Performance
    if agent_stats:
        lines.append("## 📈 Agent Performance (7 days)")
        for s in agent_stats:
            lines.append(
                f"\n**{s.get('agent', '?').capitalize()}**: "
                f"{s.get('rate', 0)}% complete "
                f"({s.get('completed', 0)}/{s.get('total', 0)} tasks) • "
                f"{s.get('failed', 0)} failed, {s.get('pending', 0)} pending"
            )

    # Wins
    if wins:
        lines.append("\n## ✅ Recent Wins")
        for w in wins[:5]:
            lines.append(f"- {w.get('title', '')} ({w.get('agent', '')})")

    # Blocked
    if blocked:
        lines.append("\n## ⚠️ Stalled Tasks (>24h pending)")
        for t in blocked[:5]:
            lines.append(f"- {t.get('title', '')} ({t.get('agent', '')})")

    # Failed
    if failed:
        lines.append("\n## ❌ Recent Failures")
        for t in failed:
            lines.append(f"- {t.get('title', '')} ({t.get('agent', '')})")

    # Summary
    tc = sum(int(s.get("completed", 0)) for s in agent_stats)
    tt = sum(int(s.get("total", 0)) for s in agent_stats)
    ov = round(tc / tt * 100, 1) if tt > 0 else 0
    lines.append(f"\n---\n**Weekly Summary**: {tc}/{tt} tasks completed ({ov}%)")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

MODES = {
    "goal-progress":      mode_goal_progress,
    "progress-report":    mode_progress_report,
    "progress-summary":   mode_progress_summary,
    "agent-performance":  mode_agent_performance,
}


def main():
    parser = argparse.ArgumentParser(description="Unified Daily Report Generator")
    parser.add_argument(
        "--mode", "-m",
        choices=list(MODES.keys()),
        default="goal-progress",
        help="Report mode (default: goal-progress)",
    )
    args = parser.parse_args()

    try:
        report = MODES[args.mode]()
        print(report)
    except EnvironmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
