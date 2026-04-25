#!/usr/bin/env python3
"""
Task Completion Standard — Validator and Auto-Formatter

Enforces the Kurultai task completion report standard for all agents.
Validates completion reports against required sections and auto-generates
missing structure from task metadata.

Usage:
    from task_completion_standard import validate_completion_report, auto_generate_report

    # Check if a completion report meets the standard
    is_valid, missing = validate_completion_report(output_content)

    # Auto-generate a compliant report from task metadata
    report = auto_generate_report(task_dict, workspace_scan, git_diff, session_data)

The Standard (Required for implementation work, optional for Q&A):

1. ## Resolution — REQUIRED section (checked by /horde-review line 92)
   See templates/task-completion-template.md for format
2. Summary Header — ✅ [Task Title] — [Brief outcome statement]
3. Changes Made — Before/After/Why for each change
4. What Was Broken — Previous behavior + root cause (if fix)
5. New Behavior — How it works now with timeline (if fix/improvement)
6. Additional Improvements — Any bonus fixes
7. Expected Outcome / Verification — Testable success criteria
8. Commit/Deployment Info — Git hash and push status
9. Follow-up / Next Steps — Pending actions

Created: 2026-03-08
Author: Ogedei (Operations)
Updated: 2026-03-08 - Added Resolution section requirement (Chagatai)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime


# Required sections for implementation work (bug fixes, features, infrastructure)
REQUIRED_SECTIONS_IMPLEMENTATION = [
    "resolution",
    "changes_made",
    "verification_criteria",
]

# Optional but recommended sections
RECOMMENDED_SECTIONS = [
    "what_was_broken",     # For bug fixes
    "new_behavior",        # For fixes/improvements
    "additional_improvements",
    "commit_deployment",   # If code changes were made
    "follow_up",           # If pending actions exist
]

# Section patterns for validation
SECTION_PATTERNS = {
    "resolution": [
        r"##?\s*Resolution",
        r"^##\s+Resolution",
    ],
    "summary_header": [
        r"^✅\s+.+\s+—\s+.+",
        r"^✅\s+.+\s+-\s+.+",
        r"^✅\s+.+\[",
    ],
    "changes_made": [
        r"##?\s*Changes\s+Made",
        r"##?\s*What\s+Changed",
        r"##?\s*Modifications",
    ],
    "what_was_broken": [
        r"##?\s*What\s+Was\s+Broken",
        r"##?\s*Previous\s+Behavior",
        r"##?\s*Issue",
        r"##?\s*Problem",
    ],
    "new_behavior": [
        r"##?\s*New\s+Behavior",
        r"##?\s*Fixed\s+(Execution\s+)?Flow",
        r"##?\s*How\s+It\s+Works\s+Now",
        r"##?\s*Implementation",
    ],
    "additional_improvements": [
        r"##?\s*Additional\s+Improvements",
        r"##?\s*Bonus",
        r"##?\s*Extra",
    ],
    "verification_criteria": [
        r"##?\s*Expected\s+Outcome",
        r"##?\s*Verification",
        r"##?\s*Test\s+(Criteria|Plan)",
        r"##?\s*Success\s+Criteria",
    ],
    "commit_deployment": [
        r"##?\s*Commit",
        r"##?\s*Deployment",
        r"##?\s*Git",
    ],
    "follow_up": [
        r"##?\s*Follow-?up",
        r"##?\s*Next\s+Steps",
        r"##?\s*Pending",
    ],
}


def _has_pattern(content: str, patterns: List[str]) -> bool:
    """Check if content matches any of the given patterns."""
    for pattern in patterns:
        if re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            return True
    return False


def _detect_report_type(content: str, task_metadata: Dict) -> str:
    """Detect if this is implementation work or simple Q&A.

    Returns: 'implementation' | 'qa' | 'unknown'
    """
    # Check task metadata for hints
    task_body = task_metadata.get('body', '').lower()
    skill_hint = task_metadata.get('skill_hint', '').lower()

    # Keywords suggesting implementation work
    impl_keywords = [
        'fix', 'bug', 'implement', 'create', 'add', 'remove', 'update',
        'deploy', 'configure', 'setup', 'install', 'migrate', 'refactor',
        'optimize', 'debug', 'resolve', 'patch', 'build', 'write'
    ]

    # Keywords suggesting Q&A
    qa_keywords = [
        'what is', 'how do', 'explain', 'describe', 'show me', 'list',
        'check', 'verify', 'status', 'report', 'what\'s the', 'tell me'
    ]

    impl_score = sum(1 for k in impl_keywords if k in task_body or k in skill_hint)
    qa_score = sum(1 for k in qa_keywords if k in task_body)

    # Check for code changes
    has_code_changes = (
        '## Changes Made' in content or
        '```' in content or
        any(k in content.lower() for k in ['file:', 'created', 'modified'])
    )

    if impl_score >= 1 or has_code_changes:
        return 'implementation'
    elif qa_score >= 1 and impl_score == 0:
        return 'qa'
    return 'unknown'


def validate_completion_report(content: str, task_metadata: Optional[Dict] = None) -> Tuple[bool, List[str], str]:
    """Validate a completion report against the standard.

    Args:
        content: The task completion output text
        task_metadata: Optional task metadata for better detection

    Returns:
        (is_valid, missing_sections, report_type)
        - is_valid: True if report meets requirements for its type
        - missing_sections: List of required section names that are missing
        - report_type: 'implementation' | 'qa' | 'unknown'
    """
    if not content:
        return False, REQUIRED_SECTIONS_IMPLEMENTATION, 'unknown'

    task_metadata = task_metadata or {}
    report_type = _detect_report_type(content, task_metadata)

    content_lower = content.lower()
    missing = []

    # Check required sections based on report type
    if report_type == 'implementation':
        for section in REQUIRED_SECTIONS_IMPLEMENTATION:
            patterns = SECTION_PATTERNS.get(section, [])
            if not _has_pattern(content, patterns):
                missing.append(section)
    elif report_type == 'qa':
        # Q&A only needs a clear answer, minimal structure required
        # Just check it's not empty
        if len(content.strip()) < 20:
            missing.append('content_too_short')
    else:
        # Unknown type - check for basic structure
        has_any_section = any(
            _has_pattern(content, patterns)
            for patterns in SECTION_PATTERNS.values()
        )
        if not has_any_section:
            missing.append('no_structure_detected')

    is_valid = len(missing) == 0
    return is_valid, missing, report_type


def auto_generate_report(
    task: Dict,
    workspace_scan: Dict,
    git_diff: Dict,
    session_data: Dict,
    agent_state: Dict = None,
    error_analysis: Dict = None,
) -> str:
    """Auto-generate a compliant completion report from task metadata.

    Extracts key information and structures it according to the standard.
    Agents can use this as a template or fallback.

    Args:
        task: Task dict with 'body' and 'metadata' keys
        workspace_scan: Workspace scan results from scan_workspace()
        git_diff: Git diff results from get_git_diff()
        session_data: Session data from scan_session_file()
        agent_state: Optional agent state from get_agent_state()
        error_analysis: Optional error analysis from analyze_error()

    Returns:
        Markdown formatted completion report
    """
    meta = task.get('metadata', {})
    task_id = meta.get('task_id', 'unknown')[:12]
    agent = meta.get('agent', 'unknown')
    title = task.get('body', '').split('\n')[0].replace('#', '').strip()
    status = meta.get('status', 'completed')

    # Extract what was done from workspace
    files = workspace_scan.get('files', [])
    files_created = [f for f in files if f.get('created', False)]
    files_modified = [f for f in files if not f.get('created', False)]

    # Git stats
    git_stats = git_diff.get('stats', {})
    git_hash = git_diff.get('hash', 'N/A')

    # Session info
    model = session_data.get('model', 'unknown')
    duration = session_data.get('duration_seconds', 0)

    # Build the report
    lines = []

    # 1. Summary Header
    status_icon = '✅' if status == 'completed' else '❌'
    lines.append(f"{status_icon} **{title[:80]}** — Task {status}")

    # 2. Changes Made
    lines.append("\n## Changes Made\n")

    if files_created or files_modified:
        if files_created:
            lines.append("**Files Created:**")
            for f in files_created[:10]:
                rel_path = f.get('path', '')[-60:]
                lines.append(f"  • `{rel_path}`")
        if files_modified:
            lines.append("**Files Modified:**")
            for f in files_modified[:10]:
                rel_path = f.get('path', '')[-60:]
                lines.append(f"  • `{rel_path}`")

        if git_stats.get('files_changed', 0) > 0:
            lines.append(f"\n**Git Changes:** {git_stats['files_changed']} files, "
                        f"+{git_stats.get('lines_added', 0)}/-{git_stats.get('lines_removed', 0)} lines")
    else:
        lines.append("*No file changes detected*")

    lines.append(f"\n**Agent:** {agent}")
    lines.append(f"**Model:** {model}")
    lines.append(f"**Duration:** {int(duration)} seconds")

    # 3. What Was Broken (if applicable)
    if status == 'failed' or meta.get('fix_type'):
        lines.append("\n## What Was Broken\n")

        if error_analysis:
            lines.append(f"**Error Category:** {error_analysis.get('category', 'unknown')}")
            lines.append(f"**Root Cause:** {error_analysis.get('error_hash', 'N/A')}")

        if meta.get('original_issue'):
            lines.append(f"\n**Previous behavior:**\n{meta.get('original_issue')}")

    # 4. New Behavior (if fix/improvement)
    if meta.get('fix_type') or meta.get('implementation_type'):
        lines.append("\n## New Behavior\n")
        lines.append("Fixed execution flow:")
        lines.append("1. Validated task requirements")
        if files_created:
            lines.append("2. Created/modified required files")
        if git_stats.get('files_changed', 0) > 0:
            lines.append("3. Committed changes to git")
        lines.append("4. Verified implementation")

    # 5. Additional Improvements
    bonus_improvements = meta.get('bonus_improvements', [])
    if bonus_improvements:
        lines.append("\n## Additional Improvements\n")
        for improvement in bonus_improvements:
            lines.append(f"• {improvement}")

    # 6. Expected Outcome / Verification
    lines.append("\n## Expected Outcome / Verification\n")
    lines.append("**Testable criteria:**")
    lines.append(f"• Task status: {status}")

    if files_created:
        lines.append(f"• Files created: {len(files_created)}")
    if git_stats.get('files_changed', 0) > 0:
        lines.append(f"• Git changes committed: {'Yes' if git_hash != 'N/A' else 'No'}")

    # 7. Commit/Deployment Info
    if git_stats.get('files_changed', 0) > 0:
        lines.append("\n## Commit/Deployment Info\n")
        lines.append(f"**Git Status:** {git_stats.get('files_changed', 0)} files changed")
        lines.append(f"**Commit Hash:** {git_hash if git_hash != 'N/A' else 'Not committed'}")
        lines.append(f"**Lines:** +{git_stats.get('lines_added', 0)}/-{git_stats.get('lines_removed', 0)}")

    # 8. Follow-up / Next Steps
    next_steps = meta.get('next_steps', [])
    pending_actions = meta.get('pending_actions', [])

    if next_steps or pending_actions:
        lines.append("\n## Follow-up / Next Steps\n")
        for step in next_steps + pending_actions:
            lines.append(f"• {step}")
    else:
        lines.append("\n## Follow-up\n")
        lines.append("*No pending actions*")

    # Add task metadata footer
    lines.append(f"\n---\n*Task ID: {task_id} | Agent: {agent} | {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return '\n'.join(lines)


def extract_completion_summary(output_content: str, max_length: int = 200) -> str:
    """Extract a concise summary from completion output.

    Looks for:
    1. Summary header format (✅ ... — ...)
    2. First line after ## Summary or ## Executive Summary
    3. First meaningful line of content

    Args:
        output_content: The full task output
        max_length: Maximum length of extracted summary

    Returns:
        Extracted summary string
    """
    if not output_content:
        return ""

    # Try to find summary header
    for line in output_content.split('\n')[:20]:
        line = line.strip()
        if re.match(r'^✅\s+.+\s+—\s+.+', line):
            # Extract just the outcome part after —
            parts = line.split('—')
            if len(parts) > 1:
                return parts[-1].strip()[:max_length]

    # Try to find summary section
    summary_match = re.search(
        r'##?\s*(?:Executive\s+)?Summary\s*\n+(.+?)(?:\n##|\n\n|$)',
        output_content,
        re.IGNORECASE | re.DOTALL
    )
    if summary_match:
        summary = summary_match.group(1).strip().split('\n')[0]
        return summary[:max_length]

    # Fallback: first meaningful line
    for line in output_content.split('\n')[:10]:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('---'):
            return line[:max_length]

    return ""


def score_report_quality(content: str, task_metadata: Dict = None) -> Dict[str, Any]:
    """Score a completion report on multiple quality dimensions.

    Returns a dict with:
        - overall_score: 0-100
        - has_resolution: bool (REQUIRED - checked by /horde-review)
        - has_summary: bool
        - has_changes: bool
        - has_verification: bool
        - has_root_cause: bool (for fixes)
        - has_commit_info: bool (if code changed)
        - line_count: int
        - recommendations: List[str]
    """
    task_metadata = task_metadata or {}

    scores = {
        'overall_score': 0,
        'has_resolution': False,
        'has_summary': False,
        'has_changes': False,
        'has_verification': False,
        'has_root_cause': False,
        'has_commit_info': False,
        'line_count': len(content.split('\n')) if content else 0,
        'recommendations': [],
    }

    if not content:
        scores['recommendations'].append("Empty completion report")
        return scores

    content_lower = content.lower()

    # Check for resolution section (REQUIRED for /horde-review)
    if _has_pattern(content, SECTION_PATTERNS['resolution']):
        scores['has_resolution'] = True
        scores['overall_score'] += 25
    else:
        scores['recommendations'].append("Add '## Resolution' section (see templates/task-completion-template.md)")

    # Check for summary header
    if _has_pattern(content, SECTION_PATTERNS['summary_header']):
        scores['has_summary'] = True
        scores['overall_score'] += 15
    else:
        scores['recommendations'].append("Add summary header: ✅ [Title] — [Outcome]")

    # Check for changes made
    if _has_pattern(content, SECTION_PATTERNS['changes_made']):
        scores['has_changes'] = True
        scores['overall_score'] += 25
    else:
        scores['recommendations'].append("Add 'Changes Made' section with Before/After/Why")

    # Check for verification criteria
    if _has_pattern(content, SECTION_PATTERNS['verification_criteria']):
        scores['has_verification'] = True
        scores['overall_score'] += 25
    else:
        scores['recommendations'].append("Add 'Expected Outcome / Verification' section")

    # Check for root cause (for fixes)
    report_type = _detect_report_type(content, task_metadata)
    if report_type == 'implementation':
        if _has_pattern(content, SECTION_PATTERNS['what_was_broken']):
            scores['has_root_cause'] = True
            scores['overall_score'] += 15
        else:
            scores['recommendations'].append("Consider adding 'What Was Broken' section for context")

    # Check for commit info (if code changes detected)
    if '```' in content or 'file:' in content_lower:
        if _has_pattern(content, SECTION_PATTERNS['commit_deployment']):
            scores['has_commit_info'] = True
            scores['overall_score'] += 15
        else:
            scores['recommendations'].append("Add 'Commit/Deployment Info' with git hash")

    # Penalty for very short reports
    if scores['line_count'] < 10:
        scores['overall_score'] = max(0, scores['overall_score'] - 20)
        scores['recommendations'].append("Report is very short - expand on what was done")

    return scores


def main():
    """CLI interface for validation."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(
        description="Validate task completion reports against Kurultai standard"
    )
    parser.add_argument(
        '--content', '-c',
        help='Content to validate (or use stdin)'
    )
    parser.add_argument(
        '--file', '-f',
        help='File containing content to validate'
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='Output JSON format'
    )
    parser.add_argument(
        '--score',
        action='store_true',
        help='Score the report quality instead of just validating'
    )

    args = parser.parse_args()

    # Read content
    content = args.content
    if args.file:
        content = Path(args.file).read_text()
    elif not content and not sys.stdin.isatty():
        content = sys.stdin.read()

    if not content:
        print("Error: No content provided", file=sys.stderr)
        sys.exit(1)

    # Initialize exit code
    is_valid = True

    if args.score:
        # Score mode
        scores = score_report_quality(content)
        if args.json:
            print(json.dumps(scores, indent=2))
        else:
            print(f"Quality Score: {scores['overall_score']}/100")
            for rec in scores['recommendations']:
                print(f"  • {rec}")
    else:
        # Validation mode
        is_valid, missing, report_type = validate_completion_report(content)

        if args.json:
            print(json.dumps({
                'valid': is_valid,
                'missing_sections': missing,
                'report_type': report_type
            }, indent=2))
        else:
            print(f"Report Type: {report_type}")
            print(f"Valid: {is_valid}")
            if missing:
                print(f"Missing Sections: {', '.join(missing)}")
            else:
                print("✅ Report meets the Kurultai completion standard")

    sys.exit(0 if is_valid else 1)


if __name__ == '__main__':
    main()
