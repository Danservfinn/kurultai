#!/usr/bin/env python3
"""
validate_completion_report.py — Validate task completion reports follow the template.

Checks for:
1. Required "## Resolution" heading
2. Minimum 3 headings total
3. Required subsections: What Was Done, Files Changed, Verification

Usage:
    python3 validate_completion_report.py <task_file_path>

Exit codes:
    0 = Valid completion report
    1 = Missing required sections
    2 = File not found or read error
"""

import re
import sys
from pathlib import Path


# Required heading patterns
REQUIRED_MAIN_HEADING = r"^##\s+Resolution"
REQUIRED_SUBSECTIONS = {
    "What Was Done": r"^###\s+What Was Done",
    "Files Changed": r"^###\s+Files Changed",
    "Verification": r"^###\s+Verification",
}

# Minimum heading count (including ## Resolution)
MIN_HEADING_COUNT = 3


def extract_execution_output(content: str) -> str:
    """Extract the execution output section from a task file.

    The completion report appears AFTER "## Execution Output", AFTER the metadata
    (Model/Duration/Status/---), and continues until the next "##" heading or EOF.
    """
    # Find ## Execution Output section
    match = re.search(r"## Execution Output\s*\n(.*)", content, re.DOTALL)
    if not match:
        return content

    full_output = match.group(1)

    # Remove metadata header: **Model:**...**Duration:**...**Status:**...---...
    # This pattern captures everything up to and including the first "---" on its own line
    full_output = re.sub(r"^\*\*Model:\*\*.+?---\s*\n", "", full_output, flags=re.DOTALL)

    # Stop at next major section (## heading not part of completion report)
    # Look for ## not followed by a completion subsection (###)
    match = re.search(r"\n##[^\n#]", full_output)
    if match:
        full_output = full_output[:match.start()]

    return full_output.strip()


def count_headings(text: str) -> int:
    """Count markdown headings (level 2 or higher)."""
    return len(re.findall(r"^##+\s+\S", text, re.MULTILINE))


def validate_completion_report(content: str) -> tuple[bool, list[str]]:
    """Validate completion report against template requirements.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Extract execution output (where completion report should be)
    execution_output = extract_execution_output(content)

    # Check for required ## Resolution heading
    if not re.search(REQUIRED_MAIN_HEADING, execution_output, re.MULTILINE):
        errors.append("Missing required heading: ## Resolution")

    # Count headings
    heading_count = count_headings(execution_output)
    if heading_count < MIN_HEADING_COUNT:
        errors.append(f"Insufficient headings: found {heading_count}, need at least {MIN_HEADING_COUNT}")

    # Check for required subsections
    for section_name, pattern in REQUIRED_SUBSECTIONS.items():
        if not re.search(pattern, execution_output, re.MULTILINE):
            errors.append(f"Missing required subsection: ### {section_name}")

    return len(errors) == 0, errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_completion_report.py <task_file_path>", file=sys.stderr)
        sys.exit(2)

    task_path = Path(sys.argv[1])
    if not task_path.exists():
        print(f"Error: File not found: {task_path}", file=sys.stderr)
        sys.exit(2)

    try:
        content = task_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(2)

    is_valid, errors = validate_completion_report(content)

    if is_valid:
        print("✓ Completion report template is valid")
        sys.exit(0)
    else:
        print("✗ Completion report template validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
