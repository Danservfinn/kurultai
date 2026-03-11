#!/usr/bin/env python3
"""
Report Analyzer - Extract insights from task completion reports for reflections.

Analyzes completed task reports to extract:
- Problems solved
- Solutions built
- Testing performed
- Verification results
- Patterns and trends

Usage:
    python3 report_analyzer.py --agent temujin --hours 1
    python3 report_analyzer.py --all-agents --hours 1
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_tracker, get_driver
from agents_config import AGENT_ROLES

# Model detection
def get_model():
    """Get the default model from main agent config."""
    try:
        agents_dir = Path.home() / ".openclaw" / "agents"
        settings_file = agents_dir / "main" / ".claude" / "settings.json"
        if settings_file.exists():
            with open(settings_file) as f:
                config = json.load(f)
            return config.get("env", {}).get("ANTHROPIC_MODEL", "unknown")
    except Exception:
        pass
    return "unknown"

MODEL = get_model()


class ReportAnalyzer:
    """Analyze task completion reports for reflection integration."""

    def __init__(self):
        self.driver = get_driver()
        self.tracker = get_tracker()

    def close(self):
        """Close database connections."""
        self.driver.close()
        self.tracker.close()

    # ============================================================
    # Task Gathering
    # ============================================================

    def gather_completed_tasks(self, agent: str, hours: int = 1) -> List[Dict]:
        """Get all tasks completed by this agent in the last N hours.

        Args:
            agent: Agent name
            hours: Hours to look back

        Returns:
            List of task dicts with report data
        """
        # Try Neo4j first for task metadata
        tasks = []
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.agent = $agent
                  AND t.status = 'COMPLETED'
                  AND t.completed_at > datetime() - duration({hours: $hours})
                RETURN
                    t.task_id AS task_id,
                    t.title AS title,
                    t.skill_hint AS skill_hint,
                    t.priority AS priority,
                    t.actual_duration_seconds AS duration,
                    t.total_tokens AS tokens,
                    t.verification_score AS verification_score,
                    t.lines_added AS lines_added,
                    t.lines_removed AS lines_removed,
                    t.files_modified AS files_modified,
                    t.files_created AS files_created,
                    t.completed_at AS completed_at
                ORDER BY t.completed_at DESC
            """, agent=agent, hours=hours)

            for record in result:
                task = dict(record)
                tasks.append(task)

        # Enrich with report_text from filesystem (Neo4j doesn't store it)
        reports_dir = Path("/Users/kublai/.openclaw/agents/main/reports/completed")
        if reports_dir.exists():
            cutoff = datetime.now() - timedelta(hours=hours)
            for report_path in reports_dir.glob("*.md"):
                if report_path.name.startswith("."):
                    continue

                # Check if this report belongs to this agent and is within time window
                try:
                    content = report_path.read_text(encoding="utf-8", errors="replace")
                    # Extract agent from content
                    for line in content.split("\n")[:50]:
                        if line.startswith("**Agent:**"):
                            report_agent = line.split("**Agent:**")[1].strip().lower()
                            if report_agent != agent.lower():
                                break
                        elif line.startswith("**Completed:**"):
                            try:
                                completed_str = line.split("**Completed:**")[1].strip()
                                completed_dt = datetime.strptime(completed_str, "%Y-%m-%d %H:%M:%S")
                                if completed_dt < cutoff:
                                    break
                            except ValueError:
                                pass
                    else:
                        # Report matches agent and time - find matching task or add new
                        task_id = report_path.stem
                        # Find existing task or create new entry
                        matched_task = next((t for t in tasks if t.get("task_id", "").startswith(task_id)), None)
                        if matched_task:
                            matched_task["report_text"] = content
                        else:
                            # Create task from file if not in Neo4j (stale sync)
                            tasks.append({
                                "task_id": task_id,
                                "title": self._extract_title_from_report(content),
                                "report_text": content,
                                "completed_at": cutoff,  # Fallback timestamp
                            })
                except Exception:
                    continue

        return tasks

    def _extract_title_from_report(self, content: str) -> str:
        """Extract task title from report markdown."""
        for line in content.split("\n")[:20]:
            line = line.strip()
            if line.startswith("**Title:**"):
                return line.split("**Title:**")[1].strip()
            elif line.startswith("#") and not line.startswith("##"):
                return line.lstrip("#").strip()
        return "Unknown task"

    def gather_all_completed_tasks(self, hours: int = 1) -> Dict[str, List[Dict]]:
        """Get completed tasks for all agents.

        Returns:
            Dict mapping agent name to list of completed tasks
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'COMPLETED'
                  AND t.completed_at > datetime() - duration({hours: $hours})
                RETURN
                    t.agent AS agent,
                    t.task_id AS task_id,
                    t.title AS title,
                    t.skill_hint AS skill_hint,
                    t.priority AS priority,
                    t.actual_duration_seconds AS duration,
                    t.total_tokens AS tokens,
                    t.verification_score AS verification_score,
                    t.lines_added AS lines_added,
                    t.lines_removed AS lines_removed,
                    t.files_modified AS files_modified,
                    t.files_created AS files_created,
                    t.completed_at AS completed_at
                ORDER BY t.completed_at DESC
            """, hours=hours)

            by_agent = defaultdict(list)
            for record in result:
                agent = record.get("agent", "unknown")
                by_agent[agent].append(dict(record))

            return dict(by_agent)

    # ============================================================
    # Report Parsing
    # ============================================================

    def parse_report_sections(self, report_text: Optional[str]) -> Dict[str, Any]:
        """Parse a task report into structured sections.

        Extracts:
        - Problem: What was the issue being solved
        - Solution: What was built/done to solve it
        - Testing: What tests were run
        - Verification: How success was verified
        - Resolution: REQUIRED section for completion (checked by /horde-review)

        Args:
            report_text: Raw report markdown text

        Returns:
            Dict with problem, solution, testing, verification, resolution fields
        """
        if not report_text:
            return {
                "problem": None,
                "solution": None,
                "testing": None,
                "verification": None,
                "resolution": None,
            }

        sections = {
            "problem": None,
            "solution": None,
            "testing": None,
            "verification": None,
            "resolution": None,
        }

        # Pattern 1: Standard section headers
        patterns = {
            "problem": [
                r"##\s*Problem\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*Issue\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*What was (?:the )?problem\s*\n(.*?)(?=\n##|\Z)",
                r"\*\*Problem:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)",
            ],
            "solution": [
                r"##\s*Solution\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*Implementation\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*What was (?:the )?solution\s*\n(.*?)(?=\n##|\Z)",
                r"\*\*Solution:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)",
            ],
            "testing": [
                r"##\s*Testing\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*Tests?\s*(?:Run|Performed)?\s*\n(.*?)(?=\n##|\Z)",
                r"\*\*Testing:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)",
            ],
            "verification": [
                r"##\s*Verification\s*\n(.*?)(?=\n##|\Z)",
                r"##\s*How (?:was )?success verified\s*\n(.*?)(?=\n##|\Z)",
                r"\*\*Verification:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)",
            ],
            "resolution": [
                r"##\s*Resolution\s*\n(.*?)(?=\n##|\Z)",
                r"\*\*Resolution:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)",
            ],
        }

        for section, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, report_text, re.DOTALL | re.IGNORECASE)
                if match:
                    content = match.group(1).strip()
                    # Truncate to reasonable length
                    if len(content) > 500:
                        content = content[:500] + "..."
                    sections[section] = content
                    break

        return sections

    def extract_summary_from_title(self, title: Optional[str]) -> str:
        """Extract a brief summary from task title."""
        if not title:
            return "Unknown task"
        # Remove common prefixes
        title = re.sub(r"^(Task:|Implement|Fix|Create|Update|Add|Remove):\s*", "", title, flags=re.IGNORECASE)
        return title[:100]

    # ============================================================
    # Analysis Functions
    # ============================================================

    def analyze_reports(self, tasks: List[Dict]) -> Dict[str, Any]:
        """Analyze completed task reports for reflection input.

        Args:
            tasks: List of completed task dicts

        Returns:
            Dict with:
            - problems_solved: List of problem descriptions
            - solutions_built: List of solution descriptions
            - testing_performed: List of testing descriptions
            - verification_results: List of verification descriptions
            - missing_resolution: List of task_ids missing required ## Resolution section
            - patterns: Detected patterns
            - success_rate: Task success rate
            - quality_score: Average quality score
        """
        if not tasks:
            return {
                "problems_solved": [],
                "solutions_built": [],
                "testing_performed": [],
                "verification_results": [],
                "missing_resolution": [],
                "patterns": [],
                "success_rate": None,
                "quality_score": None,
                "total_tasks": 0,
            }

        problems = []
        solutions = []
        testing = []
        verification = []
        missing_resolution = []
        quality_scores = []
        durations = []

        for task in tasks:
            # Parse report sections
            sections = self.parse_report_sections(task.get("report_text"))

            if sections.get("problem"):
                problems.append({
                    "task_id": task.get("task_id", "unknown")[:8],
                    "description": sections["problem"],
                })

            if sections.get("solution"):
                solutions.append({
                    "task_id": task.get("task_id", "unknown")[:8],
                    "description": sections["solution"],
                })

            if sections.get("testing"):
                testing.append({
                    "task_id": task.get("task_id", "unknown")[:8],
                    "description": sections["testing"],
                })

            if sections.get("verification"):
                verification.append({
                    "task_id": task.get("task_id", "unknown")[:8],
                    "description": sections["verification"],
                })

            # Check for REQUIRED resolution section (checked by /horde-review)
            if not sections.get("resolution"):
                missing_resolution.append({
                    "task_id": task.get("task_id", "unknown")[:8],
                    "title": task.get("title", "Unknown task")[:80],
                })

            # Collect metrics
            if task.get("verification_score"):
                quality_scores.append(task["verification_score"])
            if task.get("duration"):
                durations.append(task["duration"])

        # Detect patterns
        patterns = self._detect_patterns(tasks, problems, solutions)

        return {
            "problems_solved": problems[:5],  # Limit to 5 for reflection
            "solutions_built": solutions[:5],
            "testing_performed": testing[:5],
            "verification_results": verification[:5],
            "missing_resolution": missing_resolution,
            "patterns": patterns,
            "success_rate": 100.0,  # All tasks passed (we only query COMPLETED)
            "quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else None,
            "avg_duration": sum(durations) / len(durations) if durations else None,
            "total_tasks": len(tasks),
        }

    def _detect_patterns(self, tasks: List[Dict], problems: List, solutions: List) -> List[Dict]:
        """Detect patterns across completed tasks.

        Looks for:
        - Recurring problem types
        - Common solution approaches
        - Skill usage patterns
        - File modification patterns
        """
        patterns = []

        # Skill usage patterns
        skill_counts = defaultdict(int)
        for task in tasks:
            if task.get("skill_hint"):
                skill_counts[task["skill_hint"]] += 1

        for skill, count in sorted(skill_counts.items(), key=lambda x: -x[1])[:3]:
            patterns.append({
                "type": "skill_usage",
                "description": f"Used {skill} {count} times",
                "count": count,
            })

        # File modification patterns
        file_types = defaultdict(int)
        for task in tasks:
            for f in (task.get("files_modified") or []):
                ext = Path(f).suffix or "unknown"
                file_types[ext] += 1
            for f in (task.get("files_created") or []):
                ext = Path(f).suffix or "unknown"
                file_types[ext] += 1

        for ext, count in sorted(file_types.items(), key=lambda x: -x[1])[:3]:
            if ext and ext != "unknown":
                patterns.append({
                    "type": "file_type",
                    "description": f"Modified {ext} files {count} times",
                    "count": count,
                })

        # Code change patterns
        total_added = sum(t.get("lines_added") or 0 for t in tasks)
        total_removed = sum(t.get("lines_removed") or 0 for t in tasks)

        if total_added > 0 or total_removed > 0:
            patterns.append({
                "type": "code_changes",
                "description": f"+{total_added}/-{total_removed} lines across {len(tasks)} tasks",
                "added": total_added,
                "removed": total_removed,
            })

        return patterns

    # ============================================================
    # Reflection Integration
    # ============================================================

    def generate_reflection_block(self, agent: str, hours: int = 1) -> str:
        """Generate markdown block for reflection prompt.

        Args:
            agent: Agent name
            hours: Hours to look back

        Returns:
            Markdown string with task completion summary
        """
        tasks = self.gather_completed_tasks(agent, hours)
        analysis = self.analyze_reports(tasks)

        if not tasks:
            return f"## Task Completion Summary\nNo tasks completed in the last {hours} hour(s).\n"

        lines = [
            f"## Task Completion Summary (Last {hours}h)",
            f"**Total Completed:** {analysis['total_tasks']}",
            f"**Model:** {MODEL}",
        ]

        if analysis.get("quality_score"):
            lines.append(f"**Avg Quality Score:** {analysis['quality_score']:.1f}/10")

        if analysis.get("avg_duration"):
            lines.append(f"**Avg Duration:** {analysis['avg_duration']:.0f}s")

        lines.append("")

        # CRITICAL: Missing resolution sections (checked by /horde-review)
        # This is the PRIORITY_FIX from review analysis
        if analysis.get("missing_resolution"):
            lines.append("### ⚠️ MISSING RESOLUTION SECTIONS")
            lines.append(f"**{len(analysis['missing_resolution'])} task(s) missing required ## Resolution section**")
            lines.append("See `templates/task-completion-template.md` for format")
            for m in analysis["missing_resolution"][:5]:
                lines.append(f"- [{m['task_id']}] {m['title']}")
            if len(analysis["missing_resolution"]) > 5:
                lines.append(f"... and {len(analysis['missing_resolution']) - 5} more")
            lines.append("")
            lines.append("**ACTION REQUIRED:** Add `## Resolution` section to these task reports")
            lines.append("")

        # Problems solved
        if analysis["problems_solved"]:
            lines.append("### Problems Solved")
            for p in analysis["problems_solved"][:3]:
                lines.append(f"- [{p['task_id']}] {p['description'][:150]}")
            lines.append("")

        # Solutions built
        if analysis["solutions_built"]:
            lines.append("### Solutions Built")
            for s in analysis["solutions_built"][:3]:
                lines.append(f"- [{s['task_id']}] {s['description'][:150]}")
            lines.append("")

        # Testing performed
        if analysis["testing_performed"]:
            lines.append("### Testing Performed")
            for t in analysis["testing_performed"][:3]:
                lines.append(f"- [{t['task_id']}] {t['description'][:150]}")
            lines.append("")

        # Verification results
        if analysis["verification_results"]:
            lines.append("### Verification Results")
            for v in analysis["verification_results"][:3]:
                lines.append(f"- [{v['task_id']}] {v['description'][:150]}")
            lines.append("")

        # Patterns detected
        if analysis["patterns"]:
            lines.append("### Patterns Detected")
            for p in analysis["patterns"][:3]:
                lines.append(f"- {p['description']}")
            lines.append("")

        return "\n".join(lines)

    def generate_system_summary(self, hours: int = 1) -> str:
        """Generate system-wide task summary for Kublai reflection.

        Returns:
            Markdown string with system-wide task metrics
        """
        by_agent = self.gather_all_completed_tasks(hours)

        if not by_agent:
            return f"## System Task Summary\nNo tasks completed in the last {hours} hour(s).\n"

        total_tasks = sum(len(tasks) for tasks in by_agent.values())

        lines = [
            f"## System Task Summary (Last {hours}h)",
            f"**Total Completed:** {total_tasks} tasks across {len(by_agent)} agents",
            f"**Model:** {MODEL}",
            "",
            "### By Agent",
        ]

        for agent, tasks in sorted(by_agent.items(), key=lambda x: -len(x[1])):
            analysis = self.analyze_reports(tasks)
            quality = f", q={analysis['quality_score']:.1f}" if analysis.get("quality_score") else ""
            lines.append(f"- {agent}: {len(tasks)} tasks{quality}")

        lines.append("")

        # System-wide patterns
        all_tasks = []
        for tasks in by_agent.values():
            all_tasks.extend(tasks)

        patterns = self._detect_patterns(all_tasks, [], [])

        if patterns:
            lines.append("### System Patterns")
            for p in patterns[:5]:
                lines.append(f"- {p['description']}")
            lines.append("")

        return "\n".join(lines)


# ============================================================
# Main Entry Point
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Analyze task reports for reflections")
    parser.add_argument("--agent", help="Specific agent name")
    parser.add_argument("--all-agents", action="store_true", help="Analyze all agents")
    parser.add_argument("--hours", type=int, default=1, help="Hours to look back")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--reflection-block", action="store_true", help="Generate reflection markdown block")

    args = parser.parse_args()

    analyzer = ReportAnalyzer()

    try:
        if args.all_agents:
            if args.reflection_block:
                print(analyzer.generate_system_summary(args.hours))
            else:
                by_agent = analyzer.gather_all_completed_tasks(args.hours)
                result = {
                    agent: analyzer.analyze_reports(tasks)
                    for agent, tasks in by_agent.items()
                }
                print(json.dumps(result, indent=2, default=str))
        elif args.agent:
            if args.reflection_block:
                print(analyzer.generate_reflection_block(args.agent, args.hours))
            else:
                tasks = analyzer.gather_completed_tasks(args.agent, args.hours)
                analysis = analyzer.analyze_reports(tasks)
                if args.json:
                    print(json.dumps(analysis, indent=2, default=str))
                else:
                    print(f"Tasks completed: {analysis['total_tasks']}")
                    print(f"Problems solved: {len(analysis['problems_solved'])}")
                    print(f"Solutions built: {len(analysis['solutions_built'])}")
                    print(f"Testing performed: {len(analysis['testing_performed'])}")
                    print(f"Verification results: {len(analysis['verification_results'])}")
        else:
            print("Specify --agent <name> or --all-agents")
            sys.exit(1)

    finally:
        analyzer.close()


if __name__ == "__main__":
    main()