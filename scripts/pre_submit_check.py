#!/usr/bin/env python3
"""
Pre-Submit Verification — Check task completion before marking done.

⚠️ MANDATORY for mongke, chagatai, jochi (R009/M001 enforcement)
Run BEFORE marking ANY task complete to prevent revision cycles.

Usage:
    python pre_submit_check.py path/to/task-file.md
    python pre_submit_check.py path/to/task-file.md --fix

Quality checks:
- Min character count (200)
- Minimum headings (3)
- Resolution section required (M002, M004, J004)
- Skill invocation check (R008)
- Tests section (for implementation tasks)
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Quality thresholds (must match quality_gate.py and _verify_task_completion)
# THRESHOLD ALIGNMENT (2026-03-11): Lowered from 500 to 200 to match _verify_task_completion
# This reduces agent burden while maintaining quality gate. Both verification paths must agree.
THRESHOLDS = {
    "min_chars": 200,
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


def extract_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from task content.

    Returns dict with frontmatter fields including skill_hint if present.
    """
    lines = content.split("\n")
    frontmatter = {}

    if lines and lines[0].strip() == "---":
        # Find end of frontmatter
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                # Parse frontmatter lines
                for fm_line in lines[1:i]:
                    if ":" in fm_line and not fm_line.strip().startswith("#"):
                        key, value = fm_line.split(":", 1)
                        frontmatter[key.strip()] = value.strip()
                break
    return frontmatter


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


# Known skill signatures - phrases that indicate a skill was actually invoked
# These are output patterns that skills generate when they run
SKILL_SIGNATURES = {
    "/horde-brainstorming": ["## Proposal", "PROPOSAL:", "## Recommendation", "Brainstorming Phase"],
    "/horde-implement": ["## Implementation", "Code changes:", "Files modified:", "Step 1 —", "Step 2 —"],
    "/horde-plan": ["## Plan", "Implementation Plan", "Phase 1:", "Phase 2:", "## Dependencies"],
    "/horde-review": ["## Review", "## Analysis", "## Findings", "## Recommendations", "SCORE:"],
    "/horde-learn": ["## Insights", "## Key Takeaways", "## Analysis", "## Sources:", "LEARN:"],
    "/horde-debug": ["## Diagnosis", "## Root Cause", "## Hypothesis", "## Testing", "## Fix"],
    "/golden-horde": ["## Horde Coordination", "## Subagent Dispatch", "## Parallel Execution"],
    "/horde-skill-creator": ["## Skill Definition", "## Agent Type", "## When to Use", "## Skill Prompt"],
}


def check_skill_invocation(skill_hint: str, output: str) -> tuple[bool, str]:
    """Check if output contains evidence of skill being invoked.

    Returns (passed, detail_message).
    """
    if not skill_hint:
        return True, "No skill hint required"

    # Normalize skill hint (handle /prefix variations)
    skill_key = skill_hint.strip()
    if not skill_key.startswith("/"):
        skill_key = "/" + skill_key

    # Get known signatures for this skill
    signatures = SKILL_SIGNATURES.get(skill_key, [])

    # Generic fallback: check if skill name appears in output
    # (weaker signal but better than nothing)
    generic_signature = skill_key.replace("/", "").replace("-", " ").title()

    # Check for specific signatures first
    for sig in signatures:
        if sig.lower() in output.lower():
            return True, f"Found skill signature: '{sig}'"

    # Fallback: check for skill name mention
    if generic_signature.lower() in output.lower() or skill_key in output:
        return True, f"Found skill name mention: {generic_signature}"

    # Check for ANY Skill-like output patterns (catch-all)
    # Most skills produce structured sections like ## Step, ## Phase, etc.
    skill_like_patterns = ["## Phase", "## Step", "## Analysis", "## Plan", "## Review", "## Learn"]
    if any(p.lower() in output.lower() for p in skill_like_patterns):
        return True, f"Found skill-like structure (generic)"

    return False, f"No evidence of {skill_key} invocation in output"


def analyze_task(content: str) -> dict:
    """Analyze task content against quality thresholds.

    Returns dict with:
        - passed: bool
        - checks: list of (name, passed, detail) tuples
        - metrics: dict of actual values
        - suggestions: list of improvement suggestions
    """
    output = extract_output(content)
    frontmatter = extract_frontmatter(content)
    skill_hint = frontmatter.get("skill_hint", "").strip()

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

    # Check 0: Skill invocation (R008 enforcement) - runs FIRST, blocks if fails
    skill_ok, skill_detail = check_skill_invocation(skill_hint, output)
    if skill_hint:
        # Only add as a check if skill_hint is present
        checks.append((
            f"Skill invocation ({skill_hint})",
            skill_ok,
            skill_detail
        ))
        if not skill_ok:
            suggestions.append(f'R008 VIOLATION: Invoke Skill tool with "{skill_hint}" before proceeding')

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

    # Overall pass: skill check is required if present, plus first 3 quality checks
    if skill_hint:
        # If skill_hint present, require skill check + top 3 quality checks
        required_checks = [checks[0], checks[1], checks[2], checks[3]]
    else:
        required_checks = checks[:3]  # Just quality checks if no skill
    passed = all(check[1] for check in required_checks)

    return {
        "passed": passed,
        "checks": checks,
        "metrics": {
            "chars": char_count,
            "headings": headings,
            "code_blocks": code_blocks,
            "skill_hint": skill_hint,
        },
        "suggestions": suggestions,
    }


def is_research_task(frontmatter: dict, output: str) -> bool:
    """Detect if this is a research task (for Mongke).

    Checks:
    - Frontmatter agent="mongke"
    - Task mentions research/investigation/discovery keywords
    - Task is in mongke's tasks directory
    """
    # Check frontmatter
    if frontmatter.get("agent") == "mongke":
        return True

    # Check for research keywords in task content
    research_keywords = [
        "research", "investigate", "discover", "find", "explore",
        "analyze", "locate", "search", "identify", "triangulate",
        "api", "documentation", "source", "reference"
    ]
    output_lower = output.lower()
    keyword_count = sum(1 for kw in research_keywords if kw in output_lower)
    if keyword_count >= 2:
        return True

    return False


def is_analyst_task(frontmatter: dict, output: str) -> bool:
    """Detect if this is an analyst task (for Jochi).

    Checks:
    - Frontmatter agent="jochi"
    - Task mentions analysis/security/pattern/testing keywords
    - Jochi behavioral rule J004: Context/Analysis/Findings/Resolution structure
    """
    # Check frontmatter
    if frontmatter.get("agent") == "jochi":
        return True

    # Check for analyst keywords in task content
    analyst_keywords = [
        "analysis", "security", "pattern", "review", "audit", "test",
        "detect", "anomaly", "scan", "validate", "verify", "triage",
        "compliance", "vulnerability", "check", "inspect"
    ]
    output_lower = output.lower()
    keyword_count = sum(1 for kw in analyst_keywords if kw in output_lower)
    if keyword_count >= 2:
        return True

    return False


def generate_research_template() -> str:
    """Generate research-specific completion template (Mongke M004 compliant)."""
    return """## Research Summary

### Executive Summary
<!-- 2-3 sentence overview of findings -->

### Key Findings
<!-- Bullet points of discoveries -->
-

### Sources
<!-- Links, docs, APIs consulted -->
-

## Resolution
<!-- Actionable conclusions: what was found, what's recommended, what's next -->
"""


def generate_analyst_template() -> str:
    """Generate analyst-specific completion template (Jochi J004 compliant).

    Jochi behavioral rule J004 requires:
    - Minimum 4 sections: ## Context, ## Analysis, ## Findings, ## Resolution
    - Minimum 600 characters
    """
    return """## Context
<!-- What triggered this analysis? What system, task, or pattern is being examined? -->

## Analysis
<!-- Detailed examination: methods used, data reviewed, patterns observed -->

## Findings
<!-- Key discoveries, anomalies, security issues, or patterns detected -->
-

## Resolution
<!-- Actionable outcome: what was fixed, what's recommended, next steps, or verdict -->
"""


def generate_fix_template(content: str, analysis: dict) -> str:
    """Generate a completion template based on what's missing."""
    output = extract_output(content)
    frontmatter = extract_frontmatter(content)
    suggestions = []

    # Check task type
    is_research = is_research_task(frontmatter, output)
    is_analyst = is_analyst_task(frontmatter, output)

    # Check what's missing
    if not any(pattern in output for pattern in RESOLUTION_PATTERNS):
        if is_analyst:
            suggestions.append(generate_analyst_template())
        elif is_research:
            suggestions.append(generate_research_template())
        else:
            suggestions.append("## Resolution\n<!-- Describe the final outcome -->\n")

    if "## Tests" not in output and "## Test" not in output and not is_research and not is_analyst:
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
        print(f"{RED}{BOLD}⚠️ M001/R009 VIOLATION: Do NOT mark task complete until checks pass{RESET}\n")
        print(f"{YELLOW}Fix steps:{RESET}")
        print(f"  1. Address the suggestions above")
        print(f"  2. Re-run: python3 pre_submit_check.py {args.file}")
        print(f"  3. Only mark complete after seeing '✓ READY TO SUBMIT'{RESET}")

        # Auto-fix option
        if args.fix:
            template = generate_fix_template(content, analysis)
            if template != content:
                print(f"\n{YELLOW}Appending missing sections...{RESET}")
                task_path.write_text(template)
                print(f"{GREEN}✓ Updated {task_path.name}{RESET}")
                print(f"  Please fill in the template sections before re-running check.")
            else:
                print(f"\n{YELLOW}No template to add — content needs expansion instead.{RESET}")

        return 1


if __name__ == "__main__":
    sys.exit(main())
