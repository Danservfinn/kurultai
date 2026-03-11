#!/usr/bin/env python3
"""
Pre-Submit Verification — Check task completion before marking done.

This is a PRE-SUBMIT tool agents can run BEFORE marking a task complete.
It catches quality gate issues BEFORE they cause revision cycles.

Usage:
    python pre_submit_check.py path/to/task-file.md
    python pre_submit_check.py path/to/task-file.md --fix

Quality checks:
- Min character count (500)
- Minimum headings (3)
- Resolution section required
- Tests section (for implementation tasks)
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Quality thresholds (must match quality_gate.py)
THRESHOLDS = {
    "min_chars": 500,
    "min_headings": 3,
    "must_have_resolution": True,
}

# Resolution section patterns (must match quality_gate.py)
RESOLUTION_PATTERNS = [
    "## Resolution",
    "**Status:**",
    "## Result",
    "## Summary",
]

# ANSI colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_check(name: str, passed: bool, detail: str = ""):
    """Print a check result with color."""
    status = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
    detail_color = GREEN if passed else YELLOW
    print(f"  {status} {BOLD}{name}{RESET}")
    if detail:
        print(f"     {detail_color}{detail}{RESET}")


def extract_output(content: str) -> str:
    """Extract task output from markdown file (removes frontmatter)."""
    lines = content.split("\n")

    # Check for YAML frontmatter
    if lines and lines[0].strip() == "---":
        # Find end of frontmatter
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                return "\n".join(lines[i + 1 :])
        return "\n".join(lines[1:])

    return content


def analyze_task(content: str) -> dict:
    """Analyze task content against quality thresholds.

    Returns dict with:
        - passed: bool
        - checks: list of (name, passed, detail) tuples
        - metrics: dict of actual values
        - suggestions: list of improvement suggestions
    """
    output = extract_output(content)

    # Metrics
    char_count = len(output.strip())
    headings = len(re.findall(r"^#+\s", output, re.MULTILINE))
    code_blocks = len(re.findall(r"```", output)) // 2

    # Check for resolution section
    has_resolution = any(pattern in output for pattern in RESOLUTION_PATTERNS)

    # Check for tests section (for implementation tasks)
    has_tests = "## Tests" in output or "## Test" in output or "test" in output.lower()

    # Check for standard proposal format sections
    has_proposal = all(
        pattern in output
        for pattern in ["PROPOSAL:", "PROBLEM:", "SOLUTION:", "IMPLEMENTED:", "VERIFIED:"]
    )

    checks = []
    suggestions = []

    # Check 1: Character count
    chars_ok = char_count >= THRESHOLDS["min_chars"]
    checks.append((
        "Content length",
        chars_ok,
        f"{char_count} chars (need {THRESHOLDS['min_chars']})" if not chars_ok else f"{char_count} chars"
    ))
    if not chars_ok:
        suggestions.append(f"Add {THRESHOLDS['min_chars'] - char_count} more characters")

    # Check 2: Headings
    headings_ok = headings >= THRESHOLDS["min_headings"]
    checks.append((
        "Structure (headings)",
        headings_ok,
        f"{headings} headings (need {THRESHOLDS['min_headings']})" if not headings_ok else f"{headings} headings"
    ))
    if not headings_ok:
        suggestions.append(f"Add {THRESHOLDS['min_headings'] - headings} more sections")

    # Check 3: Resolution section
    resolution_ok = has_resolution
    checks.append((
        "Resolution section",
        resolution_ok,
        "Found ## Resolution or **Status:**" if resolution_ok else "Missing ## Resolution section"
    ))
    if not resolution_ok:
        suggestions.append('Add "## Resolution" section with outcome')

    # Check 4: Code blocks (optional but noted)
    checks.append((
        "Code examples",
        code_blocks > 0,
        f"{code_blocks} code block(s)" if code_blocks > 0 else "No code blocks (optional)"
    ))

    # Overall pass
    passed = all(check[1] for check in checks[:3])  # First 3 are required

    return {
        "passed": passed,
        "checks": checks,
        "metrics": {
            "chars": char_count,
            "headings": headings,
            "code_blocks": code_blocks,
        },
        "suggestions": suggestions,
    }


def generate_fix_template(content: str, analysis: dict) -> str:
    """Generate a completion template based on what's missing."""
    output = extract_output(content)
    suggestions = []

    # Check what's missing
    if not any(pattern in output for pattern in RESOLUTION_PATTERNS):
        suggestions.append("## Resolution\n<!-- Describe the final outcome -->\n")

    if "## Tests" not in output and "## Test" not in output:
        suggestions.append("## Tests\n<!-- Describe how you verified the solution -->\n")

    if not suggestions:
        return content  # Nothing to add

    # Append suggestions
    template = "\n\n" + "\n".join(suggestions)
    return content + template


def main():
    parser = argparse.ArgumentParser(
        description="Pre-submit verification before marking task complete",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pre_submit_check.py path/to/task.md
  python pre_submit_check.py path/to/task.md --fix
        """
    )
    parser.add_argument("file", help="Path to task file to check")
    parser.add_argument(
        "--fix", "-f",
        action="store_true",
        help="Append missing sections to file (interactive)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed metrics"
    )
    args = parser.parse_args()

    task_path = Path(args.file)

    if not task_path.exists():
        print(f"{RED}Error: File not found: {task_path}{RESET}")
        return 1

    # Read content
    try:
        content = task_path.read_text()
    except Exception as e:
        print(f"{RED}Error reading file: {e}{RESET}")
        return 1

    # Analyze
    analysis = analyze_task(content)

    # Print header
    print(f"\n{BOLD}Pre-Submit Check: {task_path.name}{RESET}")
    print(f"{'─' * 60}")

    # Print checks
    for name, passed, detail in analysis["checks"]:
        print_check(name, passed, detail)

    # Print suggestions if any
    if analysis["suggestions"]:
        print(f"\n{YELLOW}Suggestions to fix:{RESET}")
        for i, suggestion in enumerate(analysis["suggestions"], 1):
            print(f"  {i}. {suggestion}")

    # Verbose metrics
    if args.verbose:
        print(f"\n{BOLD}Metrics:{RESET}")
        for key, value in analysis["metrics"].items():
            print(f"  {key}: {value}")

    # Final verdict
    print(f"{'─' * 60}")
    if analysis["passed"]:
        print(f"{GREEN}{BOLD}✓ READY TO SUBMIT{RESET}")
        return 0
    else:
        print(f"{RED}{BOLD}✗ NEEDS REVISION BEFORE SUBMIT{RESET}")

        # Auto-fix option
        if args.fix:
            template = generate_fix_template(content, analysis)
            if template != content:
                print(f"\n{YELLOW}Appending missing sections...{RESET}")
                task_path.write_text(template)
                print(f"{GREEN}✓ Updated {task_path.name}{RESET}")
                print(f"  Please fill in the template sections before submitting.")
            else:
                print(f"\n{YELLOW}No template to add — content needs expansion instead.{RESET}")

        return 1


if __name__ == "__main__":
    sys.exit(main())
