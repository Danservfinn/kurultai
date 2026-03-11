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
import uuid
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

# Task completion standard validator
try:
    from task_completion_standard import (
        validate_completion_report,
        score_report_quality,
        extract_completion_summary,
    )
    HAS_COMPLETION_STANDARD = True
except ImportError:
    HAS_COMPLETION_STANDARD = False

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
    """Parse task frontmatter and content, including cross-agent context fields."""
    if not task_path.exists():
        return {}

    content = task_path.read_text()
    lines = content.split('\n')

    # Parse YAML frontmatter
    metadata = {}
    in_frontmatter = False
    body_start = 0
    context_history = []
    output_format = {}

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == '---':
            if not in_frontmatter:
                in_frontmatter = True
            else:
                body_start = i + 1
                break
        elif in_frontmatter:
            if ':' in line and not line.strip().startswith('-'):
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                metadata[key] = value

                # Parse context_history block
                if key == 'context_history':
                    # Continue parsing list items
                    i += 1
                    current_entry = {}
                    while i < len(lines):
                        inner = lines[i]
                        inner_stripped = inner.strip()
                        # Skip comment lines
                        if inner_stripped.startswith('#'):
                            i += 1
                            continue
                        # Check for end of context_history block
                        if inner and not inner[0].isspace() and ':' in inner_stripped and not inner_stripped.startswith('-'):
                            if current_entry:
                                context_history.append(current_entry)
                                current_entry = {}
                            break
                        if inner_stripped == '---':
                            if current_entry:
                                context_history.append(current_entry)
                                current_entry = {}
                            break
                        if inner_stripped.startswith('- agent:'):
                            if current_entry:
                                context_history.append(current_entry)
                            current_entry = {'agent': inner_stripped.split(':', 1)[1].strip()}
                        elif inner_stripped.startswith('attempt:') and current_entry:
                            current_entry['attempt'] = inner_stripped.split(':', 1)[1].strip().strip('"\'')
                        elif inner_stripped.startswith('deliverable:') and current_entry:
                            current_entry['deliverable'] = inner_stripped.split(':', 1)[1].strip().strip('"\'')
                        elif inner_stripped.startswith('findings:') and current_entry:
                            current_entry['findings'] = inner_stripped.split(':', 1)[1].strip().strip('"\'')
                        i += 1
                    # Don't append if already added by break condition
                    if current_entry and current_entry not in context_history:
                        context_history.append(current_entry)
                    continue  # Skip the normal i += 1 at end of loop

                # Parse output_format block
                if key == 'output_format':
                    i += 1
                    while i < len(lines):
                        inner = lines[i]
                        inner_stripped = inner.strip()
                        if inner and not inner[0].isspace() and ':' in inner_stripped:
                            break
                        if inner_stripped == '---':
                            break
                        if inner_stripped.startswith('human_summary:'):
                            output_format['human_summary'] = inner_stripped.split(':', 1)[1].strip().lower() in ('true', 'yes', '1')
                        elif inner_stripped.startswith('agent_full:'):
                            output_format['agent_full'] = inner_stripped.split(':', 1)[1].strip().lower() in ('true', 'yes', '1')
                        elif inner_stripped.startswith('deliverable:'):
                            output_format['deliverable'] = inner_stripped.split(':', 1)[1].strip().strip('"\'')
                        i += 1
                    continue
        i += 1

    # Add parsed complex fields to metadata
    if context_history:
        metadata['context_history'] = context_history
    if output_format:
        metadata['output_format'] = output_format

    return {
        'metadata': metadata,
        'body': '\n'.join(lines[body_start:]),
        'task_file': str(task_path)
    }


def parse_error_file(error_path: Path) -> dict:
    """Parse error file format (different from task files).

    Error file format:
    # Task Error Report

    **Task ID:** <task_id>
    **Agent:** <agent>
    **Error Type:** <error_type>
    **Timestamp:** <timestamp>

    ## Error Message
    ```
    <error_message>
    ```

    ## Output Content
    ```
    <output_content>
    ```
    """
    if not error_path.exists():
        return {}

    content = error_path.read_text()
    lines = content.split('\n')

    metadata = {
        'status': 'failed',  # Error files always indicate failure
        'error_file': str(error_path)
    }
    error_message = []
    output_content = []
    current_section = None
    in_code_block = False

    for line in lines:
        # Parse metadata fields (format: **Key:** value)
        if line.startswith('**') and ':**' in line:
            match = re.match(r'\*\*([^*]+):\*\*\s*(.*)', line)
            if match:
                key = match.group(1).lower().replace(' ', '_')
                value = match.group(2).strip()
                # Map to standard metadata keys
                if key == 'task_id':
                    metadata['task_id'] = value
                elif key == 'agent':
                    metadata['agent'] = value
                elif key == 'error_type':
                    metadata['error_type'] = value
                elif key == 'timestamp':
                    metadata['error_timestamp'] = value
                else:
                    metadata[key] = value
            continue

        # Detect section headers
        if line.startswith('## Error Message'):
            current_section = 'error_message'
            continue
        elif line.startswith('## Output Content'):
            current_section = 'output_content'
            continue

        # Track code blocks
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue

        # Collect content for current section
        if in_code_block:
            if current_section == 'error_message':
                error_message.append(line)
            elif current_section == 'output_content':
                output_content.append(line)

    # Store parsed sections
    metadata['error_message'] = '\n'.join(error_message).strip()
    metadata['output_content'] = '\n'.join(output_content).strip()

    # Extract task title from output content if available
    if metadata.get('output_content'):
        first_line = metadata['output_content'].split('\n')[0]
        # Try to extract meaningful task description
        if 'R008_VIOLATION' in metadata['output_content']:
            metadata['error_category'] = 'R008_VIOLATION'
            # Extract skill hint from error message
            skill_match = re.search(r"skill '([^']+)'", metadata['output_content'])
            if skill_match:
                metadata['skill_hint'] = skill_match.group(1)

    return {
        'metadata': metadata,
        'body': metadata.get('output_content', ''),
        'error_message': metadata.get('error_message', ''),
        'error_file': str(error_path)
    }


def lookup_task_title_from_ledger(task_id: str) -> Optional[str]:
    """Look up task title from the ledger if original task file doesn't exist."""
    ledger_path = Path.home() / '.openclaw' / 'tasks' / 'task-ledger.jsonl'
    if not ledger_path.exists():
        return None

    try:
        with open(ledger_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('task_id') == task_id and entry.get('task_summary'):
                        return entry['task_summary']
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return None


def is_error_file(file_path: Path) -> bool:
    """Detect if a file is an error file based on extension or content."""
    if not file_path.exists():
        return False

    # Check extension
    if file_path.suffix == '.md' and '.error' in file_path.name:
        return True

    # Check content for error file header
    try:
        with open(file_path, 'r') as f:
            first_line = f.readline()
            return first_line.strip() == '# Task Error Report'
    except:
        return False


def scan_session_file(agent: str, task_id: str) -> dict:
    """Scan agent session file for token usage, context window, and model info.

    Extracts:
    - Token usage (input, output, total)
    - Model identification (model_id, model_provider, combined model name)
    - Temperature and context window %
    """
    sessions_dir = AGENTS_BASE / agent / 'sessions'
    session_data = {
        'token_usage': {'input': 0, 'output': 0, 'total': 0},
        'context_window_percent': 0,
        'model': 'unknown',
        'model_id': None,
        'model_provider': None,
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
                            # Look for model change events (type: "model_change")
                            if entry.get('type') == 'model_change':
                                provider = entry.get('provider')
                                model_id = entry.get('modelId')
                                if provider and model_id:
                                    session_data['model_provider'] = provider
                                    session_data['model_id'] = model_id
                                    session_data['model'] = f"{provider}/{model_id}"
                            # Look for model snapshot events (customType: "model-snapshot")
                            if entry.get('customType') == 'model-snapshot':
                                data = entry.get('data', {})
                                provider = data.get('provider')
                                model_id = data.get('modelId')
                                if provider and model_id:
                                    session_data['model_provider'] = provider
                                    session_data['model_id'] = model_id
                                    session_data['model'] = f"{provider}/{model_id}"
                            # Legacy: look for direct 'model' field
                            if 'model' in entry and session_data['model'] == 'unknown':
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


def extract_prompt_construction(parsed_task: dict) -> dict:
    """Extract prompt construction metadata from parsed task.

    Returns dict with:
    - template_version: version of prompt template used
    - template_name: name of template
    - context_sources: list of sources providing context
    - constraint_count: number of explicit constraints
    - instruction_complexity: score based on instruction detail
    - estimated_tokens: rough token estimate
    """
    metadata = parsed_task.get('metadata', {})
    body = parsed_task.get('body', '')

    result = {
        'template_version': metadata.get('template_version', 'unknown'),
        'template_name': metadata.get('prompt_template', metadata.get('template', 'standard')),
        'context_sources': [],
        'constraint_count': 0,
        'instruction_complexity': 0,
        'estimated_tokens': 0
    }

    # Extract context sources from context_history or explicit sources
    context_history = metadata.get('context_history', [])
    if context_history:
        result['context_sources'] = [entry.get('agent', 'unknown') for entry in context_history]
    else:
        # Infer from other metadata
        if metadata.get('parent_research'):
            result['context_sources'].append('parent_research')
        if metadata.get('skill_hint'):
            result['context_sources'].append(f'skill:{metadata["skill_hint"]}')

    # Count constraints (lines with "MUST", "SHOULD", "MUST NOT", "Constraints:")
    constraint_patterns = [
        r'\bMUST\b', r'\bSHOULD\b', r'\bMUST NOT\b',
        r'constraint', r'requirement', r'^##+.*constraint'
    ]
    for pattern in constraint_patterns:
        result['constraint_count'] += len(re.findall(pattern, body, re.IGNORECASE))

    # Calculate instruction complexity
    lines = body.split('\n')
    code_blocks = len(re.findall(r'```', body)) // 2
    list_items = len(re.findall(r'^[\s]*[-*]\s', body, re.MULTILINE))
    result['instruction_complexity'] = min(100, (
        len([l for l in lines if len(l.strip()) > 50]) * 2 +
        code_blocks * 10 +
        list_items * 3
    ))

    # Estimate tokens (rough: 1 token ≈ 4 chars)
    result['estimated_tokens'] = len(body) // 4

    return result


def extract_task_params(parsed_task: dict) -> dict:
    """Extract task parameters from parsed task metadata.

    Returns dict with:
    - priority: task priority level
    - timeout_seconds: allocated timeout
    - skill_hint: suggested skill
    - effort_level: effort level if specified
    - thinking_enabled: whether thinking mode enabled
    """
    metadata = parsed_task.get('metadata', {})

    # Parse timeout to seconds
    timeout_str = metadata.get('timeout', '7200')
    try:
        timeout_seconds = int(timeout_str)
    except (ValueError, TypeError):
        timeout_seconds = 7200

    return {
        'priority': metadata.get('priority', 'normal'),
        'timeout_seconds': timeout_seconds,
        'skill_hint': metadata.get('skill_hint'),
        'effort_level': metadata.get('effort_level'),
        'thinking_enabled': metadata.get('thinking_enabled', 'false').lower() == 'true'
    }


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


def validate_workspace_completion(agent: str, task_id: str, task_metadata: dict) -> dict:
    """Validate workspace completion output against the Kurultai standard.

    Reads the workspace result file (task-*.md) and validates it against
    the completion report standard.

    Args:
        agent: Agent name
        task_id: Task ID (short or full)
        task_metadata: Task metadata for type detection

    Returns:
        dict with:
            - is_valid: bool
            - report_quality_score: float (0-100)
            - missing_sections: list
            - report_type: str
            - summary: str
            - content_length: int
            - recommendations: list
    """
    result = {
        'is_valid': True,
        'report_quality_score': 100,
        'missing_sections': [],
        'report_type': 'qa',
        'summary': '',
        'content_length': 0,
        'recommendations': [],
    }

    if not HAS_COMPLETION_STANDARD:
        result['recommendations'].append("Completion standard module not available")
        return result

    # Find workspace result file
    workspace = AGENTS_BASE / agent / 'workspace'
    if not workspace.exists():
        result['is_valid'] = False
        result['recommendations'].append("No workspace directory found")
        return result

    # Look for task-*.md files matching this task
    task_prefix = task_id[:12] if len(task_id) > 12 else task_id
    result_files = list(workspace.glob(f'task-{task_prefix}*.md'))

    if not result_files:
        result_files = list(workspace.glob('task-*.md'))

    if not result_files:
        result['is_valid'] = False
        result['recommendations'].append("No workspace result file found")
        return result

    # Read the most recent result file
    result_file = max(result_files, key=os.path.getmtime)
    try:
        with open(result_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except (IOError, OSError) as e:
        result['is_valid'] = False
        result['recommendations'].append(f"Could not read result file: {e}")
        return result

    result['content_length'] = len(content)

    # Validate against standard
    is_valid, missing, report_type = validate_completion_report(content, task_metadata)
    scores = score_report_quality(content, task_metadata)
    summary = extract_completion_summary(content)

    result.update({
        'is_valid': is_valid,
        'report_quality_score': scores['overall_score'],
        'missing_sections': missing,
        'report_type': report_type,
        'summary': summary,
        'recommendations': scores['recommendations'],
        'has_summary': scores['has_summary'],
        'has_changes': scores['has_changes'],
        'has_verification': scores['has_verification'],
    })

    return result


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
    if 'r008_violation' in error_lower or 'required skill' in error_lower and 'not invoked' in error_lower:
        analysis['category'] = 'R008_VIOLATION'
        analysis['is_retryable'] = True  # Can retry after invoking skill
    elif 'auth' in error_lower or '401' in error_lower or 'unauthorized' in error_lower:
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
        from neo4j_task_tracker import get_driver
        driver = get_driver()

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

    # Add Context History section for cross-agent clarity
    context_history = meta.get('context_history', [])
    if context_history:
        report += """
## Context History (Cross-Agent)

This task was previously worked on by other agents:

| Agent | What Was Tried | Deliverable | Findings |
|-------|----------------|-------------|----------|
"""
        for entry in context_history:
            agent_name = entry.get('agent', 'unknown')
            attempt = entry.get('attempt', 'N/A')[:50]
            deliverable = entry.get('deliverable', '-')
            findings = entry.get('findings', '-')[:40] if entry.get('findings') else '-'
            report += f"| {agent_name} | {attempt} | `{deliverable}` | {findings} |\n"

    # Add audience and clarification deadline if present
    audience = meta.get('audience')
    clarification_deadline = meta.get('clarification_deadline')
    if audience or clarification_deadline:
        report += "\n## Communication Settings\n\n"
        if audience:
            report += f"- **Audience:** {audience}\n"
        if clarification_deadline:
            report += f"- **Clarification Deadline:** {clarification_deadline}\n"

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


def append_ledger_event(task_id: str, agent: str, status: str, metrics: dict, session_data: dict = None):
    """Append TASK_REPORT_GENERATED and MODEL_USED events to ledger."""
    ledger_path = Path.home() / '.openclaw' / 'tasks' / 'task-ledger.jsonl'

    events = []

    # Main task report event
    events.append({
        'event': 'TASK_REPORT_GENERATED',
        'ts': datetime.now().isoformat(),
        'task_id': task_id,
        'agent': agent,
        'status': status,
        'metrics': metrics
    })

    # Model tracking event (if model data available)
    if session_data:
        model_id = session_data.get('model_id')
        model_provider = session_data.get('model_provider')
        if model_id and model_provider:
            events.append({
                'event': 'MODEL_USED',
                'ts': datetime.now().isoformat(),
                'task_id': task_id,
                'agent': agent,
                'model_id': model_id,
                'model_provider': model_provider,
                'model_full': session_data.get('model', f'{model_provider}/{model_id}'),
                'success': (status == 'completed'),
                'duration_seconds': metrics.get('duration_seconds', 0),
                'tokens_total': session_data.get('token_usage', {}).get('total', 0)
            })

    try:
        import fcntl
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                for event in events:
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
        from neo4j_task_tracker import get_driver

        driver = get_driver()

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

                    // Model tracking for analytics
                    t.model_id = $model_id,
                    t.model_provider = $model_provider,
                    t.model_success = $model_success,
                    t.model_duration_seconds = $duration_seconds,

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
                    t.related_count = $related_count,

                    // Prompt construction metadata
                    t.prompt_construction = $prompt_construction,
                    t.task_params = $task_params
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

                model_id=session_data.get('model_id'),
                model_provider=session_data.get('model_provider'),
                model_success=(status == 'completed'),

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
                related_count=len(task_context.get('related_tasks', [])),

                # Prompt construction and task parameters
                prompt_construction=json.dumps(task_context.get('prompt_construction', {})),
                task_params=json.dumps(task_context.get('task_params', {}))
            )

        driver.close()
        return True
    except Exception as e:
        print(f"Neo4j save failed: {e}", file=sys.stderr)
        return False


def record_task_outcome(task_id: str, agent: str, task: dict,
                        workspace_scan: dict, duration_seconds: float,
                        error_analysis: dict, validation_result: dict = None) -> bool:
    """Record TaskOutcome node with success dimensions.

    Args:
        task_id: Task identifier
        agent: Agent name
        task: Task dict with metadata
        workspace_scan: Workspace scan results
        duration_seconds: Task execution duration
        error_analysis: Error analysis results
        validation_result: Optional validation from validate_workspace_completion()
    """
    try:
        from neo4j_task_tracker import get_driver

        driver = get_driver()

        # Calculate success scores
        output_quality_score = _calculate_output_quality(workspace_scan, error_analysis)
        efficiency_score = _calculate_efficiency(task, duration_seconds)

        # Report quality score from validation
        report_quality_score = validation_result.get('report_quality_score', 100) if validation_result else 100
        report_is_valid = validation_result.get('is_valid', True) if validation_result else True

        # Default scores (agent can override via reflection)
        difficulty_score = 5  # Medium difficulty baseline
        clarity_score = 5     # Medium clarity baseline
        autonomy_score = 5    # Medium autonomy baseline

        with driver.session() as session:
            outcome_id = str(uuid.uuid4())[:12]
            session.run("""
                MERGE (t:Task {task_id: $task_id})
                CREATE (t)-[:HAS_OUTCOME]->(o:TaskOutcome {
                    outcome_id: $outcome_id,
                    task_id: $task_id,
                    agent: $agent,
                    recorded_at: datetime(),

                    // Success dimensions
                    output_quality_score: $output_quality_score,
                    efficiency_score: $efficiency_score,
                    difficulty_score: $difficulty_score,
                    clarity_score: $clarity_score,
                    autonomy_score: $autonomy_score,

                    // Report quality (Kurultai completion standard)
                    report_quality_score: $report_quality_score,
                    report_is_valid: $report_is_valid,

                    // Status (for quick filtering)
                    status: CASE WHEN $is_completed THEN 'success' ELSE 'failure' END,

                    // Error tracking
                    error_category: $error_category,
                    had_error: CASE WHEN $error_category IS NOT NULL THEN true ELSE false END
                })
            """,
            outcome_id=outcome_id, task_id=task_id, agent=agent,
            output_quality_score=output_quality_score, efficiency_score=efficiency_score,
            difficulty_score=difficulty_score, clarity_score=clarity_score, autonomy_score=autonomy_score,
            report_quality_score=report_quality_score, report_is_valid=report_is_valid,
            is_completed=(error_analysis.get('category') is None),
            error_category=error_analysis.get('category'))

        driver.close()
        return True
    except Exception as e:
        print(f"TaskOutcome creation failed: {e}", file=sys.stderr)
        return False


def _calculate_output_quality(workspace_scan: dict, error_analysis: dict) -> float:
    """Calculate output quality score (0-10) from observable metrics."""
    score = 0.0

    # Files created (up to 3 points)
    files_created = workspace_scan.get('stats', {}).get('files_created', 0)
    if files_created > 0:
        score += min(files_created * 0.5, 3.0)

    # Lines added (up to 2 points)
    lines_added = workspace_scan.get('stats', {}).get('lines_added', 0)
    if lines_added > 10:
        score += 2.0
    elif lines_added > 0:
        score += 1.0

    # Complexity (up to 3 points)
    complexity = workspace_scan.get('complexity', {})
    if complexity.get('tests', 0) > 0:
        score += 1.0
    if complexity.get('docs', 0) > 0:
        score += 0.5
    if complexity.get('functions', 0) > 0:
        score += 1.0
    if complexity.get('classes', 0) > 0:
        score += 0.5

    # No errors (2 points)
    if error_analysis.get('category') is None:
        score += 2.0

    return min(score, 10.0)


def _calculate_efficiency(task: dict, duration_seconds: float) -> float:
    """Calculate efficiency score (0-10) based on time usage."""
    meta = task.get('metadata', {})
    timeout = int(meta.get('timeout', 7200))

    if duration_seconds == 0:
        return 5.0  # Default

    # Calculate ratio: used / allowed
    ratio = duration_seconds / timeout

    # Efficiency: closer to 0.5 (used half the timeout) is better
    # > 1.0 = overtime (bad), < 0.1 = too fast/complexity underestimated
    if 0.3 <= ratio <= 0.8:
        return 10.0  # Sweet spot
    elif 0.8 < ratio <= 1.0:
        return 8.0   # Good but used most of time
    elif 1.0 < ratio <= 1.2:
        return 5.0   # Went over a bit
    elif ratio > 1.2:
        return 2.0   # Significantly over
    else:  # ratio < 0.3
        return 6.0   # Very fast, maybe too easy?


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

    # Determine if we're processing an error file
    is_error = False
    if args.task_file and args.task_file.exists():
        is_error = is_error_file(args.task_file)

    # Parse task or create minimal task dict
    if args.task_file and args.task_file.exists():
        if is_error:
            # Parse error file format
            task = parse_error_file(args.task_file)
            # Override status to failed for error files
            task['metadata']['status'] = 'failed'
            agent = task.get('metadata', {}).get('agent', args.agent or 'unknown')
            task_id = task.get('metadata', {}).get('task_id', args.task_id or 'unknown')
            parent_id = ''
            # Force status to failed
            args.status = 'failed'

            # Try to find and read the original task file to get the proper title
            original_task_file = AGENTS_BASE / agent / 'tasks' / f'{task_id}.md'
            if original_task_file.exists():
                original_task = parse_task_file(original_task_file)
                # Use original task body (title) but keep error metadata
                if original_task.get('body'):
                    task['body'] = original_task['body']
                    task['original_metadata'] = original_task.get('metadata', {})
            else:
                # Try to find task file with different naming patterns
                task_dir = AGENTS_BASE / agent / 'tasks'
                if task_dir.exists():
                    for pattern in [f'*{task_id}*', f'*{task_id.split("-")[1]}*']:
                        matches = list(task_dir.glob(pattern))
                        if matches:
                            original_task = parse_task_file(matches[0])
                            if original_task.get('body'):
                                task['body'] = original_task['body']
                                task['original_metadata'] = original_task.get('metadata', {})
                                break

                # If still no title, look up in ledger
                if task.get('body', '').startswith('[R008') or not task.get('body'):
                    title_from_ledger = lookup_task_title_from_ledger(task_id)
                    if title_from_ledger:
                        task['body'] = f"# {title_from_ledger}"

            # Set error output for analyze_error function
            # For error files, the actual error is in output_content, not error_message
            error_output = (
                task.get('metadata', {}).get('output_content', '') or
                task.get('error_message', '') or
                task.get('metadata', {}).get('error_message', '')
            )
            if error_output and not args.output:
                args.output = error_output
        else:
            # Parse normal task file format
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

    # Validate completion report quality (Kurultai standard)
    validation_result = None
    if HAS_COMPLETION_STANDARD and args.status == 'completed':
        validation_result = validate_workspace_completion(
            agent, task_id, task.get('metadata', {})
        )
        # Log validation results
        if not validation_result['is_valid']:
            print(f"[WARNING] Completion report validation failed:")
            for rec in validation_result.get('recommendations', [])[:5]:
                print(f"  - {rec}")
        if validation_result.get('report_quality_score', 100) < 70:
            print(f"[WARNING] Low report quality score: {validation_result['report_quality_score']}/100")

    # Get git diff
    git_diff = get_git_diff(agent) if ENABLE_GIT_DIFF else {'diff': '', 'stats': {}, 'files_by_type': {}}

    # Get agent state
    agent_state = get_agent_state(agent)

    # Analyze error if failed
    error_analysis = analyze_error(args.output) if args.status == 'failed' else {'category': None, 'error_hash': '', 'is_retryable': False}

    # Get task context
    task_context = get_task_context(task_id, agent, parent_id)

    # Extract prompt construction metadata and task parameters
    task_context['prompt_construction'] = extract_prompt_construction(task)
    task_context['task_params'] = extract_task_params(task)

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

    # Record task outcome with success dimensions
    record_task_outcome(
        task_id, agent, task, workspace_scan,
        duration_seconds, error_analysis, validation_result
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
    append_ledger_event(task_id, agent, args.status, metrics, session_data)

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
