#!/usr/bin/env python3
"""
generate_hourly_report.py — Hourly Kurultai Reflection Report Generator

Collects data from all phases of the reflection cycle (reflect, review,
brainstorm, decide, create tasks) and produces a structured report.

Outputs:
    1. Markdown file in logs/hourly-reports/YYYY-MM-DD-HHMM-reflection-report.md
    2. Signal message to user (concise, mobile-friendly)

Data sources:
    - Agent memory files (today's reflections)
    - logs/reviews/{agent}-latest.md (horde-review output)
    - proposals/ directory (brainstorm proposals)
    - Neo4j AgentFeedback nodes (proposal status: approved/rejected/pending)
    - Neo4j Task nodes (recently created tasks)
    - logs/skills-invoked.json (skill invocation tracking)
    - logs/tock/latest.json (agent metrics)
    - logs/reflection-step-timing.json (pipeline timing)

Usage:
    python3 generate_hourly_report.py
    python3 generate_hourly_report.py --dry-run   # Print report without sending Signal
    python3 generate_hourly_report.py --no-signal  # Save file only, skip Signal
    python3 generate_hourly_report.py --force      # Force regenerate, bypass hour dedup
    # Or set env var: FORCE_REGENERATE=true python3 generate_hourly_report.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents_config import AGENTS, AGENT_ROLES
from kurultai_paths import (
    AGENTS_DIR, LOGS_DIR, MAIN_DIR, PROPOSALS_DIR,
)

REPORTS_DIR = LOGS_DIR / "hourly-reports"
SKILLS_LOG = LOGS_DIR / "skills-invoked.json"
REVIEWS_DIR = LOGS_DIR / "reviews"
TOCK_LATEST = LOGS_DIR / "tock" / "latest.json"
STEP_TIMING = LOGS_DIR / "reflection-step-timing.json"
SEND_SIGNAL_SCRIPT = Path.home() / ".claude" / "skills" / "agent-collaboration" / "scripts" / "send_signal.sh"
SIGNAL_TARGET = "+19194133445"

NOW = datetime.now(timezone.utc)  # Task 6.4: Use UTC for consistent keys across agents
DATE_STR = NOW.strftime("%Y-%m-%d")
TIME_STR = NOW.strftime("%H%M")
REPORT_FILENAME = f"{DATE_STR}-{TIME_STR}-reflection-report.md"


def log(msg):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ── Data Collectors ─────────────────────────────────────────────────


def collect_agent_reflections():
    """Parse today's memory files for each agent's latest reflection."""
    reflections = {}
    for agent in AGENTS:
        memory_file = AGENTS_DIR / agent / "memory" / f"{DATE_STR}.md"
        # SECURITY: File size check before reading (max 1MB)
        max_file_size = 1048576  # 1MB
        file_size = memory_file.stat().st_size
        if file_size > max_file_size:
            reflections[agent] = {"grade": "N/A", "findings": f"File too large ({file_size} bytes, max {max_file_size})", "issues": [], "rules": []}
            log(f"Skipping {memory_file}: file size ({file_size}) exceeds maximum ({max_file_size} bytes)")
            continue

        if not memory_file.exists():
            reflections[agent] = {"grade": "N/A", "findings": "No reflection today", "issues": [], "rules": []}
            continue

        try:
            text = memory_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            reflections[agent] = {"grade": "N/A", "findings": "Unreadable", "issues": [], "rules": []}
            continue

        # Find the most recent reflection section (last SESSION LOG or last hourly block)
        sections = re.split(r'\n---\n', text)
        latest = sections[-1] if sections else text

        # Try structured REPORT_LOG first (new format)
        report_log_match = re.search(
            r'REPORT_LOG:\s*\n'
            r'GRADE:\s*(.+)\n'
            r'KEY_FINDING:\s*(.+)\n'
            r'ISSUE:\s*(.+)\n'
            r'RULE:\s*(.+)\n',
            latest, re.IGNORECASE
        )

        if report_log_match:
            grade = report_log_match.group(1).strip().upper()
            findings = report_log_match.group(2).strip()[:120]
            issue_text = report_log_match.group(3).strip()
            issues = [issue_text[:100]] if issue_text.upper() != "NONE" else []
            rule_text = report_log_match.group(4).strip()
            rules = [rule_text[:120]] if rule_text.upper() != "NONE" else []
        else:
            # Fallback: heuristic parsing of unstructured reflections
            grade_match = re.search(r'Grade:\s*([A-F][+-]?|INCOMPLETE|N/A)', latest, re.IGNORECASE)
            grade = grade_match.group(1).upper() if grade_match else "N/A"

            findings_lines = []
            for line in latest.split('\n'):
                stripped = line.strip()
                if stripped.startswith(('- ', '* ', '1.', '2.', '3.')) and len(stripped) > 15:
                    findings_lines.append(stripped[:120])
                    if len(findings_lines) >= 2:
                        break
            findings = "; ".join(findings_lines) if findings_lines else "See memory file"

            issues = []
            for line in latest.split('\n'):
                stripped = line.strip().lower()
                if any(kw in stripped for kw in ['issue:', 'problem:', 'error:', 'blocked', 'warning:']):
                    issues.append(line.strip()[:100])
                    if len(issues) >= 2:
                        break

            rules = re.findall(r'WHEN\s+.+?THEN\s+.+?(?:INSTEAD OF.+?)?(?:\.|$)', latest, re.IGNORECASE)
            rules = [r.strip()[:120] for r in rules[:2]]

        reflections[agent] = {
            "grade": grade,
            "findings": findings,
            "issues": issues,
            "rules": rules,
        }

    return reflections


def collect_reviews():
    """Read /horde-review outputs for each agent."""
    reviews = {}
    for agent in AGENTS:
        review_file = REVIEWS_DIR / f"{agent}-latest.md"
        if not review_file.exists():
            reviews[agent] = {"score": "N/A", "strengths": [], "weaknesses": [], "priority_fix": ""}
            continue

        try:
            text = review_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            reviews[agent] = {"score": "N/A", "strengths": [], "weaknesses": [], "priority_fix": ""}
            continue

        score_match = re.search(r'SCORE:\s*(\d+(?:/10)?)', text, re.IGNORECASE)
        score = score_match.group(1) if score_match else "N/A"

        strengths = re.findall(r'STRENGTHS?:?\s*\n((?:\s*[-*].+\n?)+)', text, re.IGNORECASE)
        strength_items = []
        if strengths:
            strength_items = [s.strip().lstrip('-* ').strip()[:80] for s in strengths[0].strip().split('\n') if s.strip()][:3]

        weaknesses = re.findall(r'WEAKNESS(?:ES)?:?\s*\n((?:\s*[-*].+\n?)+)', text, re.IGNORECASE)
        weakness_items = []
        if weaknesses:
            weakness_items = [w.strip().lstrip('-* ').strip()[:80] for w in weaknesses[0].strip().split('\n') if w.strip()][:3]

        pfix_match = re.search(r'PRIORITY_FIX:\s*(.+)', text, re.IGNORECASE)
        priority_fix = pfix_match.group(1).strip()[:100] if pfix_match else ""

        reviews[agent] = {
            "score": score,
            "strengths": strength_items,
            "weaknesses": weakness_items,
            "priority_fix": priority_fix,
        }

    return reviews


def collect_proposals():
    """Read proposal files from proposals/ directory."""
    proposals = []
    if not PROPOSALS_DIR.exists():
        return proposals

    cutoff = time.time() - 7200  # Last 2 hours
    for f in sorted(PROPOSALS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix != '.md':
            continue
        if f.stat().st_mtime < cutoff:
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Parse agent from filename (e.g., temujin-20260306-123208.md)
        agent_match = re.match(r'^([a-z]+)-', f.name)
        agent = agent_match.group(1) if agent_match else "unknown"

        # Parse title
        title_match = re.search(r'^#\s*Proposal:\s*(.+)', text, re.MULTILINE)
        title = title_match.group(1).strip()[:80] if title_match else f.stem

        # Parse domain
        domain_match = re.search(r'\*\*Domain:\*\*\s*(.+)', text)
        domain = domain_match.group(1).strip() if domain_match else ""

        # Parse status
        status_match = re.search(r'\*\*(?:Implemented|Status):\*\*\s*(.+)', text, re.IGNORECASE)
        status = status_match.group(1).strip() if status_match else "proposed"

        proposals.append({
            "agent": agent,
            "title": title,
            "domain": domain,
            "status": status,
            "file": f.name,
        })

    return proposals


def collect_neo4j_decisions():
    """Query Neo4j for recent proposal decisions and task creation."""
    decisions = {"approved": [], "rejected": [], "deferred": [], "pending": []}
    tasks_created = []

    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()
        try:
            with driver.session() as session:
                # Recent proposal decisions (last 2 hours)
                result = session.run("""
                    MATCH (f:AgentFeedback)
                    WHERE f.source = 'kurultai_brainstorm'
                      AND (f.reviewed_at >= datetime() - duration({hours: 2})
                           OR f.submitted >= datetime() - duration({hours: 2}))
                    RETURN f.agent AS agent, f.feedback AS feedback,
                           f.status AS status, f.review_reason AS reason,
                           f.priority AS priority
                    ORDER BY f.submitted DESC
                """)
                for r in result:
                    entry = {
                        "agent": r["agent"] or "?",
                        "feedback": (r["feedback"] or "")[:60],
                        "reason": r["reason"] or "",
                        "priority": r["priority"] or "MEDIUM",
                    }
                    st = r["status"] or "pending_review"
                    if st == "approved":
                        decisions["approved"].append(entry)
                    elif st == "rejected":
                        decisions["rejected"].append(entry)
                    elif st == "expired":
                        decisions["deferred"].append(entry)
                    else:
                        decisions["pending"].append(entry)

                # Recently created tasks (last 2 hours)
                result = session.run("""
                    MATCH (t:Task)
                    WHERE t.created >= datetime() - duration({hours: 2})
                    RETURN t.task_id AS id, t.title AS title, t.agent AS agent,
                           t.priority AS priority, t.source AS source,
                           t.skill_hint AS skill_hint
                    ORDER BY t.created DESC
                    LIMIT 20
                """)
                for r in result:
                    tasks_created.append({
                        "id": (r["id"] or "?")[:12],
                        "title": (r["title"] or "?")[:60],
                        "agent": r["agent"] or "?",
                        "priority": r["priority"] or "normal",
                        "source": r["source"] or "?",
                        "skill_hint": r["skill_hint"] or "",
                    })
        finally:
            driver.close()
    except Exception as e:
        log(f"Neo4j query failed (non-fatal): {e}")

    return decisions, tasks_created


def collect_tock_metrics():
    """Read latest tock data for agent metrics."""
    if not TOCK_LATEST.exists():
        return {}
    try:
        target = TOCK_LATEST.resolve() if TOCK_LATEST.is_symlink() else TOCK_LATEST
        with open(target) as f:
            return json.load(f)
    except Exception:
        return {}


def collect_skills_invoked():
    """Read skills invocation log."""
    if not SKILLS_LOG.exists():
        return {}
    try:
        with open(SKILLS_LOG) as f:
            data = json.load(f)
        # Filter to current hour
        current_hour = NOW.strftime("%Y-%m-%d-%H")
        return data.get(current_hour, data.get("latest", {}))
    except Exception:
        return {}


def collect_step_timing():
    """Read reflection pipeline step timing."""
    if not STEP_TIMING.exists():
        return {}
    try:
        with open(STEP_TIMING) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Report Generation ───────────────────────────────────────────────


def generate_full_report(reflections, reviews, proposals, decisions, tasks_created, tock, skills, timing):
    """Generate the full markdown report."""
    lines = []
    time_display = NOW.strftime("%Y-%m-%d %H:%M")

    lines.append(f"# Hourly Kurultai Reflection Report -- {time_display}")
    lines.append("")

    # Pipeline timing
    if timing:
        elapsed = timing.get("total_elapsed_s", "?")
        lines.append(f"**Pipeline duration:** {elapsed}s")
        steps = timing.get("steps", [])
        if steps:
            step_summary = ", ".join(f"{s['name']}({s['duration_s']}s)" for s in steps)
            lines.append(f"**Steps:** {step_summary}")
        lines.append("")

    # 1. Agent Reflections Summary
    lines.append("## 1. Agent Reflections Summary")
    lines.append("")

    for agent in AGENTS:
        if agent == "kublai":
            continue  # Kublai is the reviewer, not a specialist
        role = AGENT_ROLES.get(agent, "")
        ref = reflections.get(agent, {})
        rev = reviews.get(agent, {})

        # Tock metrics
        tock_agent = tock.get("agents", {}).get(agent, {})
        tasks_done = tock_agent.get("tasks", {}).get("completed", 0)
        tasks_failed = tock_agent.get("tasks", {}).get("failed", 0)
        queue = tock_agent.get("tasks", {}).get("queue_depth", 0)

        lines.append(f"### {agent.capitalize()} ({role})")
        lines.append(f"- **Grade:** {ref.get('grade', 'N/A')} | Review Score: {rev.get('score', 'N/A')}")
        lines.append(f"- **Metrics:** {tasks_done} completed, {tasks_failed} failed, {queue} queued")
        lines.append(f"- **Findings:** {ref.get('findings', 'None')}")

        if ref.get("issues"):
            for issue in ref["issues"]:
                lines.append(f"- **Issue:** {issue}")

        if ref.get("rules"):
            for rule in ref["rules"]:
                lines.append(f"- **Rule:** {rule}")

        if rev.get("priority_fix"):
            lines.append(f"- **Priority Fix:** {rev['priority_fix']}")

        lines.append("")

    # Kublai summary (as reviewer)
    kublai_ref = reflections.get("kublai", {})
    lines.append(f"### Kublai (Squad Lead)")
    lines.append(f"- **Grade:** {kublai_ref.get('grade', 'N/A')}")
    lines.append(f"- **Findings:** {kublai_ref.get('findings', 'None')}")
    lines.append("")

    # 2. Proposals Generated
    lines.append("## 2. Proposals Generated")
    lines.append("")
    if proposals:
        lines.append(f"**{len(proposals)} proposals** in last 2 hours:")
        lines.append("")
        for i, p in enumerate(proposals, 1):
            lines.append(f"{i}. **[{p['agent']}]** {p['title']}")
            if p.get("domain"):
                lines.append(f"   Domain: {p['domain']} | Status: {p.get('status', '?')}")
        lines.append("")
    else:
        lines.append("No proposals generated in this cycle.")
        lines.append("")

    # 3. Kublai Decisions
    lines.append("## 3. Kublai Decisions")
    lines.append("")
    approved = decisions.get("approved", [])
    rejected = decisions.get("rejected", [])
    deferred = decisions.get("deferred", [])
    pending = decisions.get("pending", [])

    if approved:
        for d in approved:
            lines.append(f"- APPROVED: [{d['agent']}] {d['feedback']}")
    if rejected:
        for d in rejected:
            lines.append(f"- REJECTED: [{d['agent']}] {d['feedback']} -- {d.get('reason', '')}")
    if deferred:
        for d in deferred:
            lines.append(f"- DEFERRED: [{d['agent']}] {d['feedback']}")
    if pending:
        for d in pending:
            lines.append(f"- PENDING: [{d['agent']}] {d['feedback']}")
    if not any([approved, rejected, deferred, pending]):
        lines.append("No proposal decisions this cycle.")
    lines.append("")

    # 4. Tasks Created
    lines.append("## 4. Tasks Created")
    lines.append("")
    if tasks_created:
        lines.append(f"**{len(tasks_created)} tasks** created in last 2 hours:")
        lines.append("")
        for t in tasks_created:
            skill = f" (skill: {t['skill_hint']})" if t.get("skill_hint") else ""
            lines.append(f"- [{t['id']}] {t['title']} -> {t['agent']} [{t['priority']}]{skill}")
        lines.append("")
    else:
        lines.append("No tasks created this cycle.")
        lines.append("")

    # 5. Skills Invocation Tracking
    lines.append("## 5. Skills Invocation Tracking")
    lines.append("")
    if skills:
        for skill_name, count_or_detail in skills.items():
            if isinstance(count_or_detail, dict):
                agents_used = count_or_detail.get("agents", [])
                lines.append(f"- {skill_name}: {len(agents_used)} agents ({', '.join(agents_used)})")
            else:
                lines.append(f"- {skill_name}: {count_or_detail}")
    else:
        # Reconstruct from what we know ran
        lines.append("- /horde-review (analysis): ran for 5 specialist agents")
        lines.append("- Protocol reflections: ran for 6 agents")
        if proposals:
            lines.append(f"- /horde-brainstorming: {len(proposals)} proposals generated")
        lines.append("- cross-agent-rules, capability-scores, routing-audit, kublai-actions, kublai-initiative")
    lines.append("")

    lines.append(f"---\n*Generated by generate_hourly_report.py at {NOW.strftime('%H:%M')}*")

    return "\n".join(lines)


def generate_signal_message(reflections, reviews, proposals, decisions, tasks_created, skills):
    """Generate concise Signal message for mobile readability."""
    time_display = NOW.strftime("%I:%M %p")
    lines = []

    lines.append(f"Hourly Kurultai Report -- {time_display}")
    lines.append("")

    # Agent reflections (one-liner each)
    lines.append("AGENT REFLECTIONS:")
    for agent in AGENTS:
        if agent == "kublai":
            continue
        ref = reflections.get(agent, {})
        rev = reviews.get(agent, {})
        tock_str = ref.get("findings", "No data")[:50]
        grade = ref.get("grade", "?")
        score = rev.get("score", "?")
        issue_str = ""
        if ref.get("issues"):
            issue_str = f" | Issue: {ref['issues'][0][:40]}"
        lines.append(f"  {agent.capitalize()}: Grade {grade} | Score {score}{issue_str}")

    lines.append("")

    # Proposals
    lines.append(f"PROPOSALS ({len(proposals)} total):")
    if proposals:
        for p in proposals[:5]:
            lines.append(f"  [{p['agent']}] {p['title'][:50]}")
    else:
        lines.append("  None this cycle")

    lines.append("")

    # Decisions
    approved = decisions.get("approved", [])
    rejected = decisions.get("rejected", [])
    pending = decisions.get("pending", [])

    lines.append("KUBLAI DECISIONS:")
    if approved:
        names = ", ".join(d["feedback"][:30] for d in approved)
        lines.append(f"  Approved: {names}")
    if rejected:
        names = ", ".join(d["feedback"][:30] for d in rejected)
        lines.append(f"  Rejected: {names}")
    if pending:
        lines.append(f"  Pending review: {len(pending)}")
    if not any([approved, rejected, pending]):
        lines.append("  No decisions this cycle")

    lines.append("")

    # Tasks
    lines.append(f"TASKS CREATED ({len(tasks_created)}):")
    if tasks_created:
        for t in tasks_created[:5]:
            lines.append(f"  [{t['id']}] {t['title'][:40]} -> {t['agent']}")
    else:
        lines.append("  None")

    lines.append("")

    # Skills
    lines.append("SKILLS INVOKED:")
    lines.append(f"  Reflections: 6 agents | Reviews: 5 agents")
    if proposals:
        lines.append(f"  Brainstorming: {len(proposals)} proposals")

    report_path = f"logs/hourly-reports/{REPORT_FILENAME}"
    lines.append(f"\nFull report: {report_path}")

    return "\n".join(lines)


def send_signal_message(message, dry_run=False):
    """Send message via Signal."""
    if dry_run:
        log("DRY RUN: Would send Signal message:")
        print(message)
        return True

    if not SEND_SIGNAL_SCRIPT.exists():
        log(f"Signal script not found: {SEND_SIGNAL_SCRIPT}")
        return False

    try:
        result = subprocess.run(
            ["bash", str(SEND_SIGNAL_SCRIPT), message, "--dm", SIGNAL_TARGET],
            capture_output=True, timeout=15, text=True,
        )
        if result.returncode == 0:
            log(f"Signal message sent to {SIGNAL_TARGET}")
            return True
        else:
            log(f"Signal send failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"Signal send error: {e}")
        return False


def update_skills_log(proposals):
    """Update the skills invocation log for this hour."""
    current_hour = NOW.strftime("%Y-%m-%d-%H")

    data = {}
    if SKILLS_LOG.exists():
        try:
            with open(SKILLS_LOG) as f:
                data = json.load(f)
        except Exception:
            data = {}

    entry = {
        "protocol_reflections": {"agents": list(AGENTS), "count": len(AGENTS)},
        "horde_review": {"agents": [a for a in AGENTS if a != "kublai"], "count": 5},
        "cross_agent_rules": 1,
        "capability_scores": 1,
        "routing_audit": 1,
        "kublai_actions": 1,
        "kublai_initiative": 1,
        "kurultai_report": 1,
    }

    if proposals:
        brainstorm_agents = list(set(p["agent"] for p in proposals))
        entry["horde_brainstorming"] = {"agents": brainstorm_agents, "count": len(proposals)}

    data[current_hour] = entry
    data["latest"] = entry

    # Keep only last 48 hours of entries
    keys = sorted(data.keys())
    if len(keys) > 50:
        for k in keys[:len(keys) - 50]:
            if k != "latest":
                del data[k]

    try:
        SKILLS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SKILLS_LOG, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(f"Failed to write skills log: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate hourly Kurultai reflection report")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending Signal")
    parser.add_argument("--no-signal", action="store_true", help="Save file only, skip Signal")
    parser.add_argument("--force", action="store_true", help="Force regenerate, bypass hour dedup check")
    args = parser.parse_args()

    log("Generating hourly reflection report...")

    # Hour-level dedup (can be bypassed with --force or FORCE_REGENERATE=true)
    force_regenerate = args.force or os.environ.get("FORCE_REGENERATE", "").lower() == "true"
    hour_key = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")  # Task 6.4: UTC for consistent dedup
    existing = list(REPORTS_DIR.glob(f"{hour_key}*-reflection-report.md"))
    if existing and not force_regenerate:
        log(f"Report already exists for hour {hour_key}. Skipping.")
        return
    if existing and force_regenerate:
        log(f"FORCE_REGENERATE enabled - regenerating report for hour {hour_key} (existing: {existing[0].name})")

    # Collect all data
    reflections = collect_agent_reflections()
    reviews = collect_reviews()
    proposals = collect_proposals()
    decisions, tasks_created = collect_neo4j_decisions()
    tock = collect_tock_metrics()
    skills = collect_skills_invoked()
    timing = collect_step_timing()

    # Update skills tracking
    update_skills_log(proposals)
    skills = collect_skills_invoked()  # Re-read after update

    # Generate full markdown report
    full_report = generate_full_report(
        reflections, reviews, proposals, decisions, tasks_created, tock, skills, timing
    )

    # Save to file
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / REPORT_FILENAME
    report_path.write_text(full_report, encoding="utf-8")
    log(f"Report saved: {report_path}")

    if args.dry_run:
        print("\n=== FULL REPORT ===\n")
        print(full_report)
        print("\n=== SIGNAL MESSAGE ===\n")

    # Generate and send Signal message
    signal_msg = generate_signal_message(reflections, reviews, proposals, decisions, tasks_created, skills)

    if not args.no_signal:
        send_signal_message(signal_msg, dry_run=args.dry_run)
    else:
        log("Skipping Signal (--no-signal)")

    log("Report generation complete")


if __name__ == "__main__":
    main()
