#!/usr/bin/env python3
"""
neo4j_v2_validator.py — Completion validation: structural + semantic checks.

Prevents hollow completions (the glm-5 problem) by requiring:
1. Non-trivial output length
2. Problem/Solution/Rationale sections present

Usage:
    from neo4j_v2_validator import validate_completion
    valid, parsed = validate_completion(output_text)
    # parsed = {"problem": "...", "solution": "...", "rationale": "..."}
    # or parsed = {"reason": "why it failed"}
"""

import re
import logging

logger = logging.getLogger(__name__)

# Minimum output length to be considered substantive
MIN_OUTPUT_LENGTH = 50
# Minimum section content length
MIN_SECTION_LENGTH = 10


def _extract_section(text: str, header: str) -> str:
    """Extract content under a markdown header.

    Looks for patterns like:
        **Problem**: content
        ## Problem\ncontent
        Problem: content
    """
    patterns = [
        # **Header**: content (until next ** or ## or end)
        rf'\*\*{header}\*\*[:\s]*(.+?)(?=\*\*[A-Z]|\n##|\n\*\*|\Z)',
        # ## Header\ncontent
        rf'##\s*{header}\s*\n(.+?)(?=\n##|\Z)',
        # Header: content (line-based)
        rf'^{header}[:\s]+(.+?)(?=\n[A-Z][a-z]+[:\s]|\Z)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE | re.MULTILINE)
        if match:
            content = match.group(1).strip()
            # Remove trailing markdown artifacts
            content = re.sub(r'\n---\s*$', '', content).strip()
            if len(content) >= MIN_SECTION_LENGTH:
                return content
    return ""


def _has_delivery_receipt(output: str) -> bool:
    """Check for a Signal Delivery section with exit_code: 0.

    Looks for patterns like:
        ## Signal Delivery
        ...
        exit_code: 0
    or
        **Signal Delivery**: ... exit_code: 0
    """
    # Find ## Signal Delivery section
    delivery_match = re.search(
        r'##\s*Signal\s+Delivery\b(.+?)(?=\n##|\Z)',
        output,
        re.DOTALL | re.IGNORECASE
    )
    if delivery_match:
        section = delivery_match.group(1)
        if re.search(r'exit_code\s*:\s*0\b', section):
            return True
    # Also accept inline bold format
    inline_match = re.search(
        r'\*\*Signal\s+Delivery\*\*[^*]*exit_code\s*:\s*0',
        output,
        re.IGNORECASE | re.DOTALL
    )
    return bool(inline_match)


def validate_completion(output: str, require_delivery_section: bool = False) -> tuple[bool, dict]:
    """Validate task completion output.

    Checks:
    1. Output is non-empty and substantive
    2. Contains Problem, Solution, and Rationale sections
    3. If require_delivery_section=True, also requires a ## Signal Delivery
       section with exit_code: 0 (used for delivery tasks)

    Returns:
        (is_valid, parsed_or_error) tuple.
        If valid: parsed = {"problem": str, "solution": str, "rationale": str}
        If invalid: parsed = {"reason": str}
    """
    if not output or len(output.strip()) < MIN_OUTPUT_LENGTH:
        return False, {"reason": f"empty or too short ({len(output.strip()) if output else 0} chars, min {MIN_OUTPUT_LENGTH})"}

    # Delivery section check runs before everything else — no bypasses apply
    if require_delivery_section and not _has_delivery_receipt(output):
        return False, {"reason": "delivery task requires ## Signal Delivery section with exit_code: 0"}

    problem = _extract_section(output, "Problem")
    solution = _extract_section(output, "Solution")
    rationale = _extract_section(output, "Rationale")

    missing = []
    if not problem:
        missing.append("Problem")
    if not solution:
        missing.append("Solution")
    if not rationale:
        missing.append("Rationale")

    if missing:
        # Fallback: if output is very long and substantive, accept it
        # even without explicit sections (handles legacy output formats).
        # NOTE: This bypass does NOT apply to delivery tasks — those require
        # explicit sections AND a verified delivery receipt.
        if len(output.strip()) > 500 and output.count('\n') > 10 and not require_delivery_section:
            logger.info("Output lacks sections but is substantive — auto-extracting")
            lines = output.strip().split('\n')
            # Use first paragraph as problem, middle as solution, last as rationale
            third = max(1, len(lines) // 3)
            if not problem:
                problem = '\n'.join(lines[:third]).strip()[:500]
            if not solution:
                solution = '\n'.join(lines[third:2*third]).strip()[:2000]
            if not rationale:
                rationale = '\n'.join(lines[2*third:]).strip()[:500]
        else:
            return False, {"reason": f"missing sections: {', '.join(missing)}"}

    return True, {
        "problem": problem[:1000],
        "solution": solution[:5000],
        "rationale": rationale[:1000],
    }


def validate_delegation_gate(store, task_id: str) -> tuple[bool, list[str]]:
    """Check that all child tasks are in terminal state.

    Returns (all_terminal, blocking_task_ids).
    """
    with store.driver.session() as session:
        result = session.run("""
            MATCH (t:Task {task_id: $id})-[:SPAWNED*1..]->(child:Task)
            WHERE child.status IN ['PENDING', 'WORKING']
            RETURN child.task_id AS cid
        """, id=task_id)
        blocking = [rec["cid"] for rec in result]
    return len(blocking) == 0, blocking
