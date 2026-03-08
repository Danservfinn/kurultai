#!/usr/bin/env python3
"""
backfill_prompt_tracking.py - Backfill prompt_construction and task_params for existing tasks.

Analyzes completed tasks in Neo4j and infers prompt construction metadata
from task body structure and existing metadata.

Usage:
    python3 backfill_prompt_tracking.py [--limit 100] [--dry-run]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# Try to import neo4j
try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    print("ERROR: neo4j package not installed. Run: pip install neo4j", file=sys.stderr)
    sys.exit(1)


def infer_template_from_body(body: str) -> tuple[str, str]:
    """Infer template name and version from task body structure.

    Returns: (template_name, template_version)
    """
    if not body:
        return "standard", "1.0"

    body_lower = body.lower()

    # Detect horde template patterns
    if "horde-implement" in body_lower or "/horde-implement" in body_lower:
        return "horde-implement", "1.0"
    if "horde-plan" in body_lower or "/horde-plan" in body_lower:
        return "horde-plan", "1.0"
    if "horde-review" in body_lower or "/horde-review" in body_lower:
        return "horde-review", "1.0"
    if "horde-debug" in body_lower or "/horde-debug" in body_lower:
        return "horde-debug", "1.0"
    if "horde-brainstorming" in body_lower or "/horde-brainstorming" in body_lower:
        return "horde-brainstorming", "1.0"
    if "horde-swarm" in body_lower or "/horde-swarm" in body_lower:
        return "horde-swarm", "1.0"

    # Detect skill-based patterns
    skill_match = re.search(r'skill[_-]hint:\s*/?(\w+)', body_lower)
    if skill_match:
        skill = skill_match.group(1)
        return f"skill-{skill}", "1.0"

    # Detect structured task patterns
    if "## success criteria" in body_lower or "success_criteria:" in body_lower:
        return "structured-success", "1.0"
    if "## constraints" in body_lower or "constraints:" in body_lower:
        return "structured-constraints", "1.0"
    if "## actionable steps" in body_lower:
        return "structured-steps", "1.0"

    # Default
    return "standard", "1.0"


def extract_context_sources(body: str, metadata: dict) -> list:
    """Extract context sources from task body and metadata."""
    sources = []

    # Handle None body
    if body is None:
        body = ""

    # Check for parent research context
    if metadata.get("parent_research"):
        sources.append("parent_research")

    # Check for skill_hint
    skill_hint = metadata.get("skill_hint")
    if skill_hint:
        sources.append(f"skill:{skill_hint}")

    # Check for context_history in body
    context_match = re.search(r'context_history:\s*\n((?:\s*-\s*agent:[^\n]+\n)+)', body, re.MULTILINE)
    if context_match:
        agents = re.findall(r'agent:\s*(\w+)', context_match.group(0))
        for agent in agents:
            sources.append(f"agent:{agent}")

    # Check for resource mentions
    if "memory:" in body.lower() or "context:" in body.lower():
        sources.append("memory")

    return sources if sources else ["task_body_only"]


def count_constraints(body: str) -> int:
    """Count constraint indicators in task body."""
    if not body:
        return 0

    # Ensure body is a string
    body = str(body)

    count = 0
    constraint_patterns = [
        r'\bMUST\b',
        r'\bSHOULD\b',
        r'\bMUST NOT\b',
        r'\bREQUIRED\b',
        r'constraint',
        r'requirement',
    ]

    for pattern in constraint_patterns:
        count += len(re.findall(pattern, body, re.IGNORECASE))

    # Count sections that sound like constraints
    count += len(re.findall(r'##+\s*(?:Constraints|Requirements|Rules|Boundaries)', body, re.IGNORECASE))

    return count


def calculate_instruction_complexity(body: str) -> int:
    """Calculate instruction complexity score (0-100)."""
    if not body:
        return 0

    body = str(body)
    lines = body.split('\n')
    score = 0

    # Long detailed lines
    long_lines = [l for l in lines if len(l.strip()) > 50]
    score += min(30, len(long_lines) * 2)

    # Code blocks
    code_blocks = len(re.findall(r'```', body)) // 2
    score += min(30, code_blocks * 10)

    # List items
    list_items = len(re.findall(r'^[\s]*[-*]\s', body, re.MULTILINE))
    score += min(20, list_items * 3)

    # Numbered lists
    numbered_items = len(re.findall(r'^\s*\d+\.\s', body, re.MULTILINE))
    score += min(10, numbered_items * 2)

    # Subsections
    subsections = len(re.findall(r'^##+\s', body, re.MULTILINE))
    score += min(10, subsections * 2)

    return min(100, score)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ≈ 4 characters)."""
    return len(str(text)) // 4 if text else 0


def backfill_task(driver, task_id: str, task_data: dict, dry_run: bool = False) -> dict:
    """Backfill prompt_construction and task_params for a single task."""
    body = task_data.get('body', '')
    metadata = {k: v for k, v in task_data.items() if k not in ['body']}

    # Infer template
    template_name, template_version = infer_template_from_body(body)

    # Extract context sources
    context_sources = extract_context_sources(body, metadata)

    # Calculate metrics
    constraint_count = count_constraints(body)
    instruction_complexity = calculate_instruction_complexity(body)
    estimated_tokens = estimate_tokens(body)

    # Build prompt_construction
    prompt_construction = {
        'template_version': template_version,
        'template_name': template_name,
        'context_sources': context_sources,
        'constraint_count': constraint_count,
        'instruction_complexity': instruction_complexity,
        'estimated_tokens': estimated_tokens
    }

    # Build task_params
    timeout_str = metadata.get('timeout', '7200')
    try:
        timeout_seconds = int(timeout_str)
    except (ValueError, TypeError):
        timeout_seconds = 7200

    # Get thinking_enabled value safely
    thinking_enabled = metadata.get('thinking_enabled', 'false') or 'false'
    thinking_enabled = str(thinking_enabled).lower() == 'true'

    task_params = {
        'priority': metadata.get('priority', 'normal'),
        'timeout_seconds': timeout_seconds,
        'skill_hint': metadata.get('skill_hint'),
        'effort_level': metadata.get('effort_level'),
        'thinking_enabled': thinking_enabled
    }

    if dry_run:
        return {
            'task_id': task_id,
            'prompt_construction': prompt_construction,
            'task_params': task_params,
            'dry_run': True
        }

    # Write to Neo4j
    # Note: Neo4j properties must be primitive types, so store complex objects as JSON strings
    try:
        with driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.prompt_construction = $prompt_construction,
                    t.task_params = $task_params,
                    t.template_version = $template_version,
                    t.prompt_template = $template_name
            """,
            task_id=task_id,
            prompt_construction=json.dumps(prompt_construction),
            task_params=json.dumps(task_params),
            template_version=template_version,
            template_name=template_name
            )
        return {
            'task_id': task_id,
            'status': 'success',
            'prompt_construction': prompt_construction,
            'task_params': task_params
        }
    except Exception as e:
        return {
            'task_id': task_id,
            'status': 'error',
            'error': str(e)
        }


def main():
    parser = argparse.ArgumentParser(description='Backfill prompt tracking data')
    parser.add_argument('--limit', type=int, default=100, help='Number of tasks to backfill (default: 100)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without writing')
    parser.add_argument('--status', default='COMPLETED', help='Task status to filter (default: COMPLETED)')
    args = parser.parse_args()

    # Neo4j connection
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "myStrongPassword123")

    print(f"Connecting to Neo4j at {uri}...")
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=10)

    try:
        with driver.session() as session:
            # Fetch tasks needing backfill
            print(f"Fetching up to {args.limit} {args.status} tasks...")
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = $status
                  AND (t.prompt_construction IS NULL OR t.task_params IS NULL)
                RETURN t.task_id AS task_id,
                       t.body AS body,
                       t.priority AS priority,
                       t.skill_hint AS skill_hint,
                       t.title AS title
                ORDER BY t.created DESC
                LIMIT $limit
            """, status=args.status, limit=args.limit)

            tasks = [record.data() for record in result]

        if not tasks:
            print("No tasks found needing backfill.")
            return

        print(f"Found {len(tasks)} tasks to backfill.\n")

        # Process each task
        results = {'success': 0, 'error': 0}
        for i, task in enumerate(tasks, 1):
            task_id = task.pop('task_id')
            print(f"[{i}/{len(tasks)}] Processing {task_id}...", end=' ')

            result = backfill_task(driver, task_id, task, args.dry_run)

            if args.dry_run:
                print(f"\n  Template: {result['prompt_construction']['template_name']}")
                print(f"  Complexity: {result['prompt_construction']['instruction_complexity']}")
                print(f"  Constraints: {result['prompt_construction']['constraint_count']}")
            elif result.get('status') == 'success':
                results['success'] += 1
                print(f"OK (template: {result['prompt_construction']['template_name']})")
            else:
                results['error'] += 1
                print(f"ERROR: {result.get('error')}")

        print(f"\n{'='*50}")
        if args.dry_run:
            print(f"DRY RUN - {len(tasks)} tasks would be updated")
        else:
            print(f"Complete: {results['success']} succeeded, {results['error']} failed")

    finally:
        driver.close()


if __name__ == '__main__':
    main()
