#!/usr/bin/env python3
"""
test_routing.py — CLI tool for testing and validating the Kurultai task routing system.

This tool provides multiple modes for testing routing behavior:
- Single test: Test routing for a single task title
- Batch mode: Parse routing-test-prompts.md and run all test cases
- Compare mode: Show top agent candidates with keyword match scores
- Audit mode: Comprehensive routing audit with queue depths

All routing logic is imported from task_intake.py (no duplication).

Usage:
    python test_routing.py --title "Fix the login bug" --expected jochi
    python test_routing.py --batch-file docs/routing-test-prompts.md
    python test_routing.py --compare "Research competitors and design API"
    python test_routing.py --audit
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Import routing functions from task_intake.py
sys.path.insert(0, str(Path(__file__).parent))
from task_intake import route_by_text, detect_skill_hint, classify_task_domain, AGENT_KEYWORDS
from kurultai_paths import VALID_AGENTS

# Import helper for keyword matching if needed
from task_intake import _kw_match


def format_timestamp() -> str:
    """Return ISO 8601 timestamp."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def test_single_routing(title: str, expected_agent: str = None) -> dict:
    """Test routing for a single task title.

    Args:
        title: Task title text to route
        expected_agent: Optional expected agent for comparison

    Returns:
        Dict with: input, routed_to, expected, match, skill_hint, domain, timestamp
    """
    routed_agent = route_by_text(title)
    skill_hint = detect_skill_hint(routed_agent, title)
    domain = classify_task_domain(title, skill_hint)

    result = {
        "input": title,
        "routed_to": routed_agent,
        "expected": expected_agent,
        "match": expected_agent is None or routed_agent == expected_agent,
        "skill_hint": skill_hint,
        "domain": domain,
        "timestamp": format_timestamp(),
    }

    return result


def compare_agents(title: str) -> dict:
    """Show top 3 agent candidates with keyword match scores.

    Also displays which disambiguation rules fired.

    Args:
        title: Task title to analyze

    Returns:
        Dict with candidates, scores, matched_keywords, and disambiguation_info
    """
    text_lower = title.lower()

    # Score each agent by keyword matches
    agent_scores = []
    for agent, keywords in AGENT_KEYWORDS.items():
        matched = [kw for kw in keywords if _kw_match(kw, text_lower)]
        if matched:
            agent_scores.append({
                "agent": agent,
                "score": len(matched),
                "matched_keywords": matched[:10],  # Limit to first 10 for readability
            })

    # Sort by score descending
    agent_scores.sort(key=lambda x: x["score"], reverse=True)
    top_3 = agent_scores[:3]

    # Check for disambiguation rules (import from task_intake)
    from task_intake import _DISAMBIGUATION, _phrase_match

    disambiguation_fired = None
    for rule, target in _DISAMBIGUATION:
        if isinstance(rule, str):
            if _phrase_match(rule, text_lower):
                disambiguation_fired = f"Rule: {rule} -> {target}"
                break
        elif isinstance(rule, set):
            if all(_kw_match(kw, text_lower) for kw in rule):
                disambiguation_fired = f"Rule: {' + '.join(rule)} -> {target}"
                break

    result = {
        "input": title,
        "routed_to": route_by_text(title),
        "top_candidates": top_3,
        "disambiguation": disambiguation_fired,
        "timestamp": format_timestamp(),
    }

    return result


def parse_test_prompts_md(content: str) -> list:
    """Parse routing-test-prompts.md format to extract test cases.

    Expected format:
    ### N. agent (DOMAIN)
    > Task title here

    **Expected:** agent | **Skill hint:** skill_name
    or
    **Expected:** agent (NOT other) | **Skill hint:** skill_name

    Args:
        content: Markdown content from routing-test-prompts.md

    Returns:
        List of dicts with id, title, expected_agent, skill_hint
    """
    test_cases = []

    # Split by test case headers (### N.)
    blocks = re.split(r'\n###\s+(\d+)\.\s+', content)

    for i in range(1, len(blocks), 2):  # Skip header before first block
        if i + 1 >= len(blocks):
            break

        case_id = blocks[i]
        block_content = blocks[i + 1]

        # Extract title (line starting with >, get content after > until newline)
        # Use ^ to ensure > is at start of a line
        title_match = re.search(r'\n>\s*(.+?)\s*\n', block_content)
        if not title_match:
            continue

        title = title_match.group(1).strip()

        # Extract expected agent (first word after **Expected:**)
        expected_match = re.search(r'\*\*Expected:\*\*\s*(\w+)', block_content)
        expected = expected_match.group(1) if expected_match else None

        # Extract skill hint (everything after **Skill hint:** until end of line)
        skill_hint_match = re.search(r'\*\*Skill hint:\*\*\s*(.+?)(?:\n|$)', block_content)
        skill_hint = skill_hint_match.group(1).strip() if skill_hint_match else None
        # Handle "none" as None and strip trailing |
        if skill_hint:
            skill_hint = skill_hint.rstrip("|").strip()
            if skill_hint.lower() == "none":
                skill_hint = None

        if title and expected:
            test_cases.append({
                "id": int(case_id),
                "title": title,
                "expected_agent": expected,
                "skill_hint": skill_hint,
            })

    return test_cases


def run_batch_tests(test_cases: list) -> list:
    """Run batch routing tests and return results.

    Args:
        test_cases: List of test case dicts

    Returns:
        List of test result dicts with pass/fail status
    """
    results = []
    for case in test_cases:
        result = test_single_routing(case["title"], case["expected_agent"])
        result["case_id"] = case["id"]
        result["expected_skill_hint"] = case.get("skill_hint")
        results.append(result)

    return results


def generate_batch_summary(results: list) -> dict:
    """Generate pass/fail summary from batch test results.

    Args:
        results: List of test result dicts

    Returns:
        Summary dict with total, passed, failed, pass_rate
    """
    total = len(results)
    passed = sum(1 for r in results if r["match"])
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0

    # Group failures by agent
    failures_by_agent = {}
    for r in results:
        if not r["match"]:
            agent = r.get("expected", "unknown")
            failures_by_agent.setdefault(agent, []).append(r["case_id"])

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(pass_rate, 1),
        "failures_by_agent": failures_by_agent,
    }


def run_audit(test_cases: list = None) -> dict:
    """Run comprehensive routing audit.

    Args:
        test_cases: Optional list of test cases to validate

    Returns:
        Comprehensive audit report
    """
    audit = {
        "timestamp": format_timestamp(),
        "routing_version": "keyword_router",
        "valid_agents": sorted(VALID_AGENTS),
        "queue_depths": {},
        "test_results": None,
    }

    # Get queue depths if available
    try:
        from task_intake import get_all_agent_queue_depths
        audit["queue_depths"] = get_all_agent_queue_depths()
    except Exception as e:
        audit["queue_depths_error"] = str(e)

    # Run test cases if provided
    if test_cases:
        results = run_batch_tests(test_cases)
        audit["test_results"] = {
            "summary": generate_batch_summary(results),
            "details": results,
        }

    return audit


def main():
    parser = argparse.ArgumentParser(
        description="Test and validate Kurultai task routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single test
  %(prog)s --title "Fix the login bug" --expected jochi

  # Batch test from prompts file
  %(prog)s --batch-file docs/routing-test-prompts.md

  # Compare candidates for a task
  %(prog)s --compare "Research competitors and design API"

  # Full audit
  %(prog)s --audit

  # Output to file
  %(prog)s --title "Test task" --output results.json
        """
    )

    parser.add_argument("--title", "-t", help="Task title to route")
    parser.add_argument("--expected", "-e", help="Expected agent (for validation)")
    parser.add_argument("--batch-file", "-b", help="Path to routing-test-prompts.md")
    parser.add_argument("--compare", "-c", help="Show top 3 candidates for this title")
    parser.add_argument("--audit", "-a", action="store_true", help="Run comprehensive audit")
    parser.add_argument("--output", "-o", help="Output file path (JSON format)")
    parser.add_argument("--jsonl", action="store_true", help="Output JSONL format (batch mode only)")

    args = parser.parse_args()

    # Validate arguments
    modes = sum([
        bool(args.title),
        bool(args.batch_file),
        bool(args.compare),
        args.audit,
    ])

    if modes == 0:
        parser.print_help()
        return 0

    if modes > 1:
        parser.error("Only one mode can be specified at a time")

    result = None

    # Single test mode
    if args.title:
        result = test_single_routing(args.title, args.expected)

    # Batch mode
    elif args.batch_file:
        batch_path = Path(args.batch_file)
        if not batch_path.exists():
            print(f"Error: File not found: {args.batch_file}", file=sys.stderr)
            return 1

        content = batch_path.read_text()
        test_cases = parse_test_prompts_md(content)

        if not test_cases:
            print(f"Warning: No test cases found in {args.batch_file}", file=sys.stderr)
            return 1

        results = run_batch_tests(test_cases)
        summary = generate_batch_summary(results)

        if args.jsonl:
            # JSONL output
            output_lines = [json.dumps(r) for r in results]
            output = "\n".join(output_lines)
        else:
            # JSON with summary
            result = {
                "summary": summary,
                "results": results,
            }
            output = json.dumps(result, indent=2)

        # Handle output for batch mode
        if args.output:
            Path(args.output).write_text(output)
            print(f"Results written to {args.output}")
        else:
            print(output)

        # Always print summary
        print(f"\nSummary: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']}%)", file=sys.stderr)
        return 0 if summary["failed"] == 0 else 1

    # Compare mode
    elif args.compare:
        result = compare_agents(args.compare)

    # Audit mode
    elif args.audit:
        # Load default test cases if available
        default_prompts = Path(__file__).parent.parent / "docs" / "routing-test-prompts.md"
        test_cases = []

        if default_prompts.exists():
            content = default_prompts.read_text()
            test_cases = parse_test_prompts_md(content)

        result = run_audit(test_cases)

    # Output result
    if result is not None:
        output = json.dumps(result, indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Results written to {args.output}")
        else:
            print(output)

        # Return exit code based on match status
        if "match" in result and not result["match"]:
            return 1
        if "test_results" in result:
            return 0 if result["test_results"]["summary"]["failed"] == 0 else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
