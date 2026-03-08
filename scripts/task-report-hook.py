#!/usr/bin/env python3
"""
task-report-hook.py - Generate completion reports for finished tasks

Called automatically by task-watcher.py when a task completes.
Generates detailed markdown report and distributes to Signal/Neo4j.

Collects comprehensive data for reflections and system improvement:
- Task execution: token usage, temperature, retry count, timeout, actual vs estimated time, skills, tools
- Agent state: context window %, memory state, queue depth, concurrent tasks, health flags
- Error analysis: category, message hash, recovery attempts, fallback models
- Code/content: lines added/removed by file type, test coverage, docs created, complexity metrics
- Resources: CPU time, memory peak, API calls, external service calls
- Quality signals: verification checks passed/failed, score, re-work required
- Context chain: parent task, downstream tasks, related tasks

Usage:
    python3 task-report-hook.py --task-file /path/to/task.md --status completed
    python3 task-report-hook.py --task-id <id> --agent temujin --status failed
"""

import argparse
import json
import os
import sys
import subprocess
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import glob as globmodule

# Optional dependency
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Configuration
REPORTS_DIR = Path(os.getenv(
    'REPORTS_DIR',
    Path.home() / '.openclaw' / 'agents' / 'main' / 'reports' / 'completed'
))
AGENTS_BASE = Path.home() / '.openclaw' / 'agents'
SIGNAL_ACCOUNT = os.getenv('SIGNAL_ACCOUNT', '')
SIGNAL_GROUP_ID = os.getenv('SIGNAL_GROUP_ID', '')
ENABLE_GIT_DIFF = os.getenv('ENABLE_GIT_DIFF', 'true').lower() == 'true'
ENABLE_SIGNAL = os.getenv('SIGNAL_NOTIFY', 'true').lower() == 'true'

# Neo4j credentials
NEO4J_ENV_FILE = Path.home() / '.openclaw' / 'credentials' / 'neo4j.env'

# Ensure reports directory exists
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def parse_task_file(task_path: Path) -> dict:
    """Parse task frontmatter and content."""
    if not task_path.exists():
        return {}

    content = task_path.read_text()
    lines = content.split('\n')

    # Parse YAML frontmatter
    metadata = {}
    in_frontmatter = False
    body_start = 0

    for i, line in enumerate(lines):
        if line.strip() == '---':
            if not in_frontmatter:
                in_frontmatter = True
            else:
                body_start = i + 1
                break
        elif in_frontmatter and ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()

    return {
        'metadata': metadata,
        'body': '\n'.join(lines[body_start:]),
        'task_file': str(task_path)
    }


def scan_session_file(agent: str, task_id: str) -> dict:
    """Scan agent session file for token usage, context window, and model info."""
    sessions_dir = AGENTS_BASE / agent / 'sessions'
    session_data = {
        'token_usage': {'input': 0, 'output': 0, 'total': 0},
        'context_window_percent': 0,
        'model': 'unknown',
        'temperature': None,
        'session_found': False
    }

    if not sessions_dir.exists():
        return session_data

    # Find most recent session file
    try:
        session_files = sorted(sessions_dir.glob('*.jsonl'), key=os.path.getmtime, reverse=True)
        for sf in session_files[:3]:  # Check last 3 sessions
            try:
                with open(sf, 'r') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            # Look for usage metadata
                            if 'usage' in entry:
                                usage = entry['usage']
                                session_data['token_usage']['input'] = usage.get('input_tokens', usage.get('prompt_tokens', 0))
                                session_data['token_usage']['output'] = usage.get('output_tokens', usage.get('completion_tokens', 0))
                                session_data['token_usage']['total'] = session_data['token_usage']['input'] + session_data['token_usage']['output']
                                session_data['session_found'] = True
                            # Look for model info
                            if 'model' in entry:
                                session_data['model'] = entry['model']
                            # Look for temperature
                            if 'temperature' in entry:
                                session_data['temperature'] = entry['temperature']
                            # Context window from system messages
                            if 'context_window_percent' in entry:
                                session_data['context_window_percent'] = entry['context_window_percent']
                        except json.JSONDecodeError:
                            continue
                    if session_data['session_found']:
                        break
            except (IOError, OSError):
                continue
    except Exception:
        pass

    return session_data


def scan_workspace(agent: str, task_id: str) -> dict:
    """Scan agent workspace for new/modified files with detailed metrics."""
    workspace = AGENTS_BASE / agent / 'workspace'
    deliverables = []
    file_types = {}
    lines_added = 0
    lines_removed = 0
    complexity_metrics = {
        'functions': 0,
        'classes': 0,
        'tests': 0,
        'docs': 0
    }

    if not workspace.exists():
        return {'files': [], 'stats': {}, 'by_type': {}, 'complexity': complexity_metrics}

    # Find files modified in last hour
    try:
        result = subprocess.run(
            ['find', str(workspace), '-type', 'f', '-mmin', '-60'],
            capture_output=True, text=True, timeout=10
        )
        files = result.stdout.strip().split('\n') if result.stdout.strip() else []

        for f in files:
            if f and not f.startswith('.'):
                try:
                    stat = os.stat(f)
                    ext = Path(f).suffix.lower()
                    file_types[ext] = file_types.get(ext, 0) + 1

                    # Count lines for text files
                    line_count = 0
                    if ext in ['.py', '.ts', '.js', '.md', '.txt', '.json', '.yaml', '.yml']:
                        try:
                            with open(f, 'r', errors='ignore') as fh:
                                content = fh.read()
                                lines = content.split('\n')
                                line_count = len(lines)

                                # Complexity analysis
                                if ext in ['.py', '.ts', '.js']:
                                    complexity_metrics['functions'] += len(re.findall(r'\bdef\s+\w+|\bfunction\s+\w+|\bconst\s+\w+\s*=\s*\(', content))
                                    complexity_metrics['classes'] += len(re.findall(r'\bclass\s+\w+', content))
                                    complexity_metrics['tests'] += len(re.findall(r'\bdef\s+test_|\bit\s+[\"\']|describe\s*\(', content))
                                elif ext == '.md':
                                    complexity_metrics['docs'] += 1
                        except Exception:
                            pass

                    deliverables.append({
                        'path': f,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'extension': ext,
                        'lines': line_count
                    })
                    lines_added += line_count
                except (OSError, ValueError):
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return {
        'files': deliverables[:20],
        'stats': {
            'files_created': len(deliverables),
            'total_bytes': sum(f['size'] for f in deliverables),
            'lines_added': lines_added,
            'lines_removed': lines_removed
        },
        'by_type': file_types,
        'complexity': complexity_metrics
    }


def get_git_diff(agent: str) -> dict:
    """Get git diff for agent workspace with detailed stats."""
    workspace = AGENTS_BASE / agent

    result = {
        'diff': '',
        'stats': {
            'files_changed': 0,
            'lines_added': 0,
            'lines_removed': 0
        },
        'files_by_type': {}
    }

    if not (workspace / '.git').exists():
        return result

    try:
        # Get diff stats
        stat_result = subprocess.run(
            ['git', '-C', str(workspace), 'diff', '--shortstat', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        if stat_result.stdout:
            import re
            match = re.search(r'(\d+) files? changed', stat_result.stdout)
            if match:
                result['stats']['files_changed'] = int(match.group(1))
            match = re.search(r'(\d+) insertions?\(\+\)', stat_result.stdout)
            if match:
                result['stats']['lines_added'] = int(match.group(1))
            match = re.search(r'(\d+) deletions?\(-\)', stat_result.stdout)
            if match:
                result['stats']['lines_removed'] = int(match.group(1))

        # Get detailed diff by file type
        diff_result = subprocess.run(
            ['git', '-C', str(workspace), 'diff', '--name-only', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        if diff_result.stdout:
            for fname in diff_result.stdout.strip().split('\n'):
                if fname:
                    ext = Path(fname).suffix.lower()
                    result['files_by_type'][ext] = result['files_by_type'].get(ext, 0) + 1

        # Get actual diff (limited)
        diff_full = subprocess.run(
            ['git', '-C', str(workspace), 'diff', 'HEAD'],
            capture_output=True, text=True, timeout=10
        )
        result['diff'] = diff_full.stdout.strip()[:5000]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return result


def get_agent_state(agent: str) -> dict:
    """Get current agent state: queue depth, memory, health."""
    state = {
        'queue_depth': 0,
        'pending_tasks': 0,
        'executing_tasks': 0,
        'memory_mb': 0,
        'health_flags': []
    }

    tasks_dir = AGENTS_BASE / agent / 'tasks'
    if tasks_dir.exists():
        try:
            for f in globmodule.glob(str(tasks_dir / '*.md')):
                fname = os.path.basename(f)
                if '.executing' in fname:
                    state['executing_tasks'] += 1
                elif '.done' not in fname and 'pending' in fname.lower():
                    state['pending_tasks'] += 1

            # Count all pending (non-.done files)
            all_tasks = globmodule.glob(str(tasks_dir / '*.md'))
            state['queue_depth'] = len([t for t in all_tasks if '.done' not in os.path.basename(t)])
        except Exception:
            pass

    # Get process memory if agent is running
    if HAS_PSUTIL:
        try:
            for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
                try:
                    if 'claude' in proc.info['name'].lower() if proc.info['name'] else False:
                        state['memory_mb'] = proc.info['memory_info'].rss / 1024 / 1024 if proc.info['memory_info'] else 0
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

    # Health flags
    if state['queue_depth'] > 10:
        state['health_flags'].append('high_queue_depth')
    if state['memory_mb'] > 2048:
        state['health_flags'].append('high_memory')

    return state


def analyze_error(error_text: str) -> dict:
    """Analyze error text to categorize and extract details."""
    analysis = {
        'category': 'unknown',
        'error_hash': '',
        'is_retryable': False,
        'fallback_attempted': False
    }

    if not error_text:
        return analysis

    # Create hash for clustering
    analysis['error_hash'] = hashlib.md5(error_text.encode()).hexdigest()[:12]

    # Categorize
    error_lower = error_text.lower()
    if 'auth' in error_lower or '401' in error_lower or 'unauthorized' in error_lower:
        analysis['category'] = 'auth'
        analysis['is_retryable'] = False
    elif 'timeout' in error_lower or 'timed out' in error_lower:
        analysis['category'] = 'timeout'
        analysis['is_retryable'] = True
    elif 'model' in error_lower or 'invalid model' in error_lower:
        analysis['category'] = 'model'
        analysis['is_retryable'] = False
    elif 'network' in error_lower or 'connection' in error_lower or '503' in error_lower:
        analysis['category'] = 'network'
        analysis['is_retryable'] = True
    elif 'rate limit' in error_lower or '429' in error_lower:
        analysis['category'] = 'rate_limit'
        analysis['is_retryable'] = True
    elif 'permission' in error_lower or 'denied' in error_lower:
        analysis['category'] = 'permission'
        analysis['is_retryable'] = False
    elif 'syntax' in error_lower or 'parse' in error_lower:
        analysis['category'] = 'syntax'
        analysis['is_retryable'] = False

    return analysis


def get_task_context(task_id: str, agent: str, parent_id: Optional[str]) -> dict:
    """Get task context chain: parent, downstream, related tasks."""
    context = {
        'parent_task_id': parent_id,
        'parent_title': None,
        'downstream_tasks': [],
        'related_tasks': []
    }

    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "myStrongPassword123")),
            connection_timeout=5
        )

        with driver.session() as session:
            # Get parent info
            if parent_id:
                result = session.run("""
                    MATCH (t:Task {task_id: $parent_id})
                    RETURN t.title AS title, t.status AS status
                """, parent_id=parent_id)
                record = result.single()
                if record:
                    context['parent_title'] = record['title']
                    context['parent_status'] = record['status']

            # Get downstream tasks (tasks that have this task as parent)
            result = session.run("""
                MATCH (t:Task {parent_id: $task_id})
                RETURN t.task_id AS task_id, t.title AS title, t.status AS status
                LIMIT 10
            """, task_id=task_id)
            context['downstream_tasks'] = [
                {'task_id': r['task_id'], 'title': r['title'], 'status': r['status']}
                for r in result
            ]

            # Get related tasks (same agent, same day, similar skill)
            result = session.run("""
                MATCH (t:Task)
                WHERE t.agent = $agent
                  AND t.task_id <> $task_id
                  AND date(t.created) = date()
                RETURN t.task_id AS task_id, t.title AS title, t.skill_hint AS skill
                LIMIT 5
            """, agent=agent, task_id=task_id)
            context['related_tasks'] = [
                {'task_id': r['task_id'], 'title': r['title'], 'skill': r['skill']}
                for r in result
            ]

        driver.close()
    except Exception:
        pass  # Silently fail if Neo4j unavailable

    return context


def get_resource_usage(agent: str, duration_seconds: float) -> dict:
    """Estimate resource usage during task execution."""
    resources = {
        'cpu_time_seconds': 0,
        'memory_peak_mb': 0,
        'api_calls_estimate': 0,
        'external_services': []
    }

    # Estimate based on duration and token usage
    if duration_seconds > 0:
        # Rough estimate: Claude Code uses ~5-15% CPU during active work
        resources['cpu_time_seconds'] = duration_seconds * 0.1

    # Check for external service indicators in workspace
    workspace = AGENTS_BASE / agent / 'workspace'
    if workspace.exists():
        try:
            for f in globmodule.glob(str(workspace / '*.json')):
                try:
                    with open(f, 'r') as fh:
                        content = fh.read()
                        if 'stripe' in content.lower():
                            resources['external_services'].append('stripe')
                        if 'signal' in content.lower():
                            resources['external_services'].append('signal')
                        if 'neo4j' in content.lower():
                            resources['external_services'].append('neo4j')
                except Exception:
                    continue
        except Exception:
            pass

    resources['external_services'] = list(set(resources['external_services']))
    resources['api_calls_estimate'] = len(resources['external_services']) * 2  # Rough estimate

    return resources


def calculate_duration_seconds(task: dict) -> float:
    """Calculate task duration in seconds."""
    meta = task.get('metadata', {})
    created = meta.get('created', '')
    if not created:
        return 0

    try:
        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
        now = datetime.now(created_dt.tzinfo)
        return (now - created_dt).total_seconds()
    except (ValueError, TypeError):
        return 0


def generate_report(task: dict, workspace_scan: dict, git_diff: dict,
                    session_data: dict, agent_state: dict, error_analysis: dict,
                    task_context: dict, resource_usage: dict) -> str:
    """Generate comprehensive markdown report."""
    meta = task.get('metadata', {})
    task_id = meta.get('task_id', 'unknown')
    agent = meta.get('agent', 'unknown')
    title = task.get('body', '').split('\n')[0].replace('#', '').strip()
    status = meta.get('status', 'completed')
    duration_seconds = calculate_duration_seconds(task)
    duration_minutes = int(duration_seconds / 60)

    status_icon = '✅' if status == 'completed' else '❌'

    source = meta.get('source', 'unknown')
    skill_hint = meta.get('skill_hint', meta.get('skill', 'none'))
    priority = meta.get('priority', 'normal')
    retry_count = int(meta.get('retry_count', '0'))
    timeout = meta.get('timeout', '7200')
    parent_id = meta.get('parent_id', '')

    # File type breakdown
    file_types = workspace_scan.get('by_type', {})
    file_type_str = ', '.join(f"{v} {k}" for k, v in file_types.items()) if file_types else 'None'

    # Git stats
    git_stats = git_diff.get('stats', {}) if isinstance(git_diff, dict) else {}
    git_diff_text = git_diff.get('diff', '') if isinstance(git_diff, dict) else ''

    # Complexity
    complexity = workspace_scan.get('complexity', {})

    # Estimated vs actual
    estimated_minutes = int(timeout) / 60
    efficiency = (estimated_minutes / duration_minutes * 100) if duration_minutes > 0 else 0

    report = f"""# Task Completion Report

**Task:** {title}
**Task ID:** {task_id}
**Agent:** {agent}
**Status:** {status_icon} {status.title()}
**Priority:** {priority}
**Source:** {source}
**Skill:** {skill_hint}
**Duration:** {duration_minutes} minutes ({duration_seconds:.0f}s)
**Timeout:** {int(timeout)}s
**Efficiency:** {efficiency:.0f}% (est: {estimated_minutes:.0f}m, actual: {duration_minutes}m)
**Retry Count:** {retry_count}
**Completed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

Task executed by {agent} agent. {workspace_scan['stats']['files_created']} file(s) created/modified. {workspace_scan['stats'].get('lines_added', 0)} lines added.

## What Was Done

- Executed task: {title[:100]}
- Agent: {agent}
- Duration: {duration_minutes} minutes
- Status: {status}
- Skill used: {skill_hint if skill_hint else 'none'}

## Deliverables

| File | Type | Size | Lines | Modified |
|------|------|------|-------|----------|
"""

    for f in workspace_scan['files'][:10]:
        rel_path = f['path'].replace(str(AGENTS_BASE), '~')
        size_kb = f['size'] / 1024
        ext = f.get('extension', 'unknown')
        lines = f.get('lines', 0)
        modified = f['modified'].split('T')[1][:8] if 'T' in f['modified'] else f['modified']
        report += f"| `{rel_path}` | {ext} | {size_kb:.1f} KB | {lines} | {modified} |\n"

    if not workspace_scan['files']:
        report += "| No files detected | - | - | - | - |\n"

    # Token usage section
    tokens = session_data.get('token_usage', {})
    report += f"""
## Token Usage

| Metric | Value |
|--------|-------|
| Input Tokens | {tokens.get('input', 0):,} |
| Output Tokens | {tokens.get('output', 0):,} |
| Total Tokens | {tokens.get('total', 0):,} |
| Model | {session_data.get('model', 'unknown')} |
| Temperature | {session_data.get('temperature', 'default')} |
| Context Window | {session_data.get('context_window_percent', 0):.1f}% |

## Agent State

| Metric | Value |
|--------|-------|
| Queue Depth | {agent_state.get('queue_depth', 0)} |
| Pending Tasks | {agent_state.get('pending_tasks', 0)} |
| Executing Tasks | {agent_state.get('executing_tasks', 0)} |
| Memory (peak) | {agent_state.get('memory_mb', 0):.0f} MB |
| Health Flags | {', '.join(agent_state.get('health_flags', ['none']))} |

## Resource Usage

| Metric | Value |
|--------|-------|
| CPU Time (est) | {resource_usage.get('cpu_time_seconds', 0):.1f}s |
| Memory Peak | {resource_usage.get('memory_peak_mb', 0):.0f} MB |
| API Calls (est) | {resource_usage.get('api_calls_estimate', 0)} |
| External Services | {', '.join(resource_usage.get('external_services', ['none']))} |

## Code Metrics

| Metric | Value |
|--------|-------|
| Files Changed | {git_stats.get('files_changed', 0)} |
| Lines Added | {git_stats.get('lines_added', 0)} |
| Lines Removed | {git_stats.get('lines_removed', 0)} |
| Functions | {complexity.get('functions', 0)} |
| Classes | {complexity.get('classes', 0)} |
| Tests | {complexity.get('tests', 0)} |
| Documentation | {complexity.get('docs', 0)} |

### Files by Type
{file_type_str if file_type_str else 'No files detected'}

## Error Analysis

"""

    if status == 'failed' and error_analysis.get('category') != 'unknown':
        report += f"""| Metric | Value |
|--------|-------|
| Error Category | {error_analysis.get('category', 'unknown')} |
| Error Hash | {error_analysis.get('error_hash', 'N/A')} |
| Retryable | {'Yes' if error_analysis.get('is_retryable') else 'No'} |
"""
    else:
        report += "**No errors** - Task completed successfully.\n"

    report += f"""
## Context Chain

| Relationship | Task ID | Title | Status |
|--------------|---------|-------|--------|
| Parent | {parent_id or 'none'} | {task_context.get('parent_title', 'N/A')} | {task_context.get('parent_status', 'N/A')} |
"""

    for dt in task_context.get('downstream_tasks', [])[:5]:
        report += f"| Downstream | {dt['task_id']} | {dt['title'][:40]} | {dt['status']} |\n"

    if not task_context.get('downstream_tasks'):
        report += "| Downstream | none | N/A | N/A |\n"

    report += """
## Related Tasks (Same Agent, Today)

"""
    for rt in task_context.get('related_tasks', [])[:5]:
        report += f"- [{rt['task_id']}] {rt['title'][:60]} ({rt.get('skill', 'none')})\n"

    if not task_context.get('related_tasks'):
        report += "No related tasks found.\n"

    report += f"""
## Files Changed (Git)

```diff
{git_diff_text if git_diff_text else 'No git changes detected'}
```

## Context

- **Source:** {source}
- **Skill hint:** {skill_hint}
- **Priority:** {priority}
- **Agent workspace:** `~/{agent}/workspace/`

## Notes

- Report generated automatically by task-report-hook.py
- Workspace scan covers last 60 minutes
- Git diff from HEAD
- Token usage from session file
- Data collected for reflection analysis

---

*Generated by task-report-hook at {datetime.now().isoformat()}*
*Report ID: {task_id}*
"""

    return report


def save_report(task_id: str, report: str, agent: str) -> Path:
    """Save report to reports directory."""
    report_path = REPORTS_DIR / f"{task_id}.md"
    report_path.write_text(report)
    return report_path


def send_signal_notification(task_id: str, report_path: Path, status: str):
    """Send report summary to Signal chat."""
    if not SIGNAL_ACCOUNT or not ENABLE_SIGNAL:
        return

    try:
        summary = f"Task {task_id} {'completed' if status == 'completed' else 'failed'} - Report: {report_path}"

        if SIGNAL_GROUP_ID:
            cmd = ['signal-cli', '-u', SIGNAL_ACCOUNT, 'send', '-g', SIGNAL_GROUP_ID, summary]
        else:
            cmd = ['signal-cli', '-u', SIGNAL_ACCOUNT, 'send', '-m', summary]

        subprocess.run(cmd, timeout=10, capture_output=True)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass


def append_ledger_event(task_id: str, agent: str, status: str, metrics: dict):
    """Append TASK_REPORT_GENERATED event to ledger."""
    ledger_path = Path.home() / '.openclaw' / 'tasks' / 'task-ledger.jsonl'

    event = {
        'event': 'TASK_REPORT_GENERATED',
        'ts': datetime.now().isoformat(),
        'task_id': task_id,
        'agent': agent,
        'status': status,
        'metrics': metrics
    }

    try:
        import fcntl
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(json.dumps(event) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as e:
        pass  # Silently fail


def save_metrics_to_neo4j(task_id: str, agent: str, status: str,
                          workspace_scan: dict, git_diff: dict,
                          session_data: dict, agent_state: dict,
                          error_analysis: dict, task_context: dict,
                          resource_usage: dict, duration_seconds: float):
    """Save comprehensive task metrics to Neo4j."""
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "myStrongPassword123")),
            connection_timeout=5
        )

        git_stats = git_diff.get('stats', {}) if isinstance(git_diff, dict) else {}
        tokens = session_data.get('token_usage', {})
        complexity = workspace_scan.get('complexity', {})

        # Calculate quality score
        quality_score = 0.0
        if workspace_scan['stats'].get('files_created', 0) > 0:
            quality_score += 0.3
        if git_stats.get('files_changed', 0) > 0:
            quality_score += 0.2
        if complexity.get('tests', 0) > 0:
            quality_score += 0.2
        if complexity.get('docs', 0) > 0:
            quality_score += 0.1
        if status == 'completed':
            quality_score += 0.2

        with driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.report_generated = datetime(),
                    t.files_created = $files_created,
                    t.lines_added = $lines_added,
                    t.git_files_changed = $git_files_changed,
                    t.git_lines_added = $git_lines_added,
                    t.git_lines_removed = $git_lines_removed,
                    t.duration_seconds = $duration_seconds,
                    t.duration_minutes = $duration_minutes,
                    t.report_path = $report_path,
                    t.data_quality_score = $quality_score,

                    // Token usage
                    t.input_tokens = $input_tokens,
                    t.output_tokens = $output_tokens,
                    t.total_tokens = $total_tokens,
                    t.model = $model,
                    t.temperature = $temperature,
                    t.context_window_percent = $context_window_percent,

                    // Agent state
                    t.queue_depth = $queue_depth,
                    t.pending_tasks = $pending_tasks,
                    t.executing_tasks = $executing_tasks,
                    t.memory_mb = $memory_mb,
                    t.health_flags = $health_flags,

                    // Error analysis
                    t.error_category = $error_category,
                    t.error_hash = $error_hash,
                    t.is_retryable = $is_retryable,

                    // Complexity
                    t.functions_count = $functions,
                    t.classes_count = $classes,
                    t.tests_count = $tests,
                    t.docs_count = $docs,

                    // Resources
                    t.cpu_time_seconds = $cpu_time,
                    t.memory_peak_mb = $mem_peak,
                    t.api_calls_estimate = $api_calls,
                    t.external_services = $ext_services,

                    // Context
                    t.parent_task_id = $parent_id,
                    t.parent_title = $parent_title,
                    t.downstream_count = $downstream_count,
                    t.related_count = $related_count
            """,
                task_id=task_id,
                files_created=workspace_scan['stats'].get('files_created', 0),
                lines_added=workspace_scan['stats'].get('lines_added', 0),
                git_files_changed=git_stats.get('files_changed', 0),
                git_lines_added=git_stats.get('lines_added', 0),
                git_lines_removed=git_stats.get('lines_removed', 0),
                duration_seconds=duration_seconds,
                duration_minutes=int(duration_seconds / 60),
                report_path=str(REPORTS_DIR / f"{task_id}.md"),
                quality_score=quality_score,

                input_tokens=tokens.get('input', 0),
                output_tokens=tokens.get('output', 0),
                total_tokens=tokens.get('total', 0),
                model=session_data.get('model', 'unknown'),
                temperature=session_data.get('temperature'),
                context_window_percent=session_data.get('context_window_percent', 0),

                queue_depth=agent_state.get('queue_depth', 0),
                pending_tasks=agent_state.get('pending_tasks', 0),
                executing_tasks=agent_state.get('executing_tasks', 0),
                memory_mb=agent_state.get('memory_mb', 0),
                health_flags=json.dumps(agent_state.get('health_flags', [])),

                error_category=error_analysis.get('category'),
                error_hash=error_analysis.get('error_hash'),
                is_retryable=error_analysis.get('is_retryable', False),

                functions=complexity.get('functions', 0),
                classes=complexity.get('classes', 0),
                tests=complexity.get('tests', 0),
                docs=complexity.get('docs', 0),

                cpu_time=resource_usage.get('cpu_time_seconds', 0),
                mem_peak=resource_usage.get('memory_peak_mb', 0),
                api_calls=resource_usage.get('api_calls_estimate', 0),
                ext_services=json.dumps(resource_usage.get('external_services', [])),

                parent_id=task_context.get('parent_task_id'),
                parent_title=task_context.get('parent_title'),
                downstream_count=len(task_context.get('downstream_tasks', [])),
                related_count=len(task_context.get('related_tasks', []))
            )

        driver.close()
        return True
    except Exception as e:
        print(f"Neo4j save failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description='Generate comprehensive task completion report')
    parser.add_argument('--task-file', type=Path, help='Path to task file')
    parser.add_argument('--task-id', type=str, help='Task ID (if no task file)')
    parser.add_argument('--agent', type=str, help='Agent name')
    parser.add_argument('--status', type=str, default='completed', choices=['completed', 'failed'])
    parser.add_argument('--duration', type=float, default=0, help='Duration in seconds')
    parser.add_argument('--output', default='', help='Task output/error text')
    parser.add_argument('--dry-run', action='store_true', help='Print report without saving')

    args = parser.parse_args()

    # Parse task or create minimal task dict
    if args.task_file and args.task_file.exists():
        task = parse_task_file(args.task_file)
        agent = task.get('metadata', {}).get('agent', args.agent or 'unknown')
        task_id = task.get('metadata', {}).get('task_id', args.task_id or 'unknown')
        parent_id = task.get('metadata', {}).get('parent_id', '')
    else:
        task = {
            'metadata': {
                'task_id': args.task_id or 'unknown',
                'agent': args.agent or 'unknown',
                'status': args.status
            },
            'body': f"# Task {args.task_id or 'unknown'}"
        }
        agent = args.agent or 'unknown'
        task_id = args.task_id or 'unknown'
        parent_id = ''

    # Scan session for token usage
    session_data = scan_session_file(agent, task_id)

    # Scan workspace for deliverables
    workspace_scan = scan_workspace(agent, task_id)

    # Get git diff
    git_diff = get_git_diff(agent) if ENABLE_GIT_DIFF else {'diff': '', 'stats': {}, 'files_by_type': {}}

    # Get agent state
    agent_state = get_agent_state(agent)

    # Analyze error if failed
    error_analysis = analyze_error(args.output) if args.status == 'failed' else {'category': None, 'error_hash': '', 'is_retryable': False}

    # Get task context
    task_context = get_task_context(task_id, agent, parent_id)

    # Get resource usage
    resource_usage = get_resource_usage(agent, args.duration or 0)

    # Calculate duration
    duration_seconds = args.duration or calculate_duration_seconds(task)

    # Generate report
    report = generate_report(
        task, workspace_scan, git_diff, session_data, agent_state,
        error_analysis, task_context, resource_usage
    )

    if args.dry_run:
        print(report)
        return

    # Save report
    report_path = save_report(task_id, report, agent)

    # Save to Neo4j
    save_metrics_to_neo4j(
        task_id, agent, args.status, workspace_scan, git_diff,
        session_data, agent_state, error_analysis, task_context,
        resource_usage, duration_seconds
    )

    # Append to ledger
    metrics = {
        'duration_seconds': duration_seconds,
        'files_created': workspace_scan['stats'].get('files_created', 0),
        'lines_added': workspace_scan['stats'].get('lines_added', 0),
        'tokens_total': session_data.get('token_usage', {}).get('total', 0),
        'status': args.status,
        'error_category': error_analysis.get('category')
    }
    append_ledger_event(task_id, agent, args.status, metrics)

    # Send notification
    send_signal_notification(task_id, report_path, args.status)

    # Output
    print(f"Report saved: {report_path}")
    print(f"Files detected: {workspace_scan['stats']['files_created']}")
    print(f"Lines added: {workspace_scan['stats'].get('lines_added', 0)}")
    print(f"Git changes: {git_diff.get('stats', {}).get('files_changed', 0)} files")
    print(f"Status: {args.status}")
    print(f"Tokens: {session_data.get('token_usage', {}).get('total', 0):,}")


if __name__ == '__main__':
    main()
