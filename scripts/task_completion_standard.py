#!/usr/bin/env python3
"""
Task Completion Standard — Validates task reports have required sections.

Ensures every task completion report contains:
  1. Problem section — What was broken/needed
  2. Solution section — What was actually built/changed
  3. Testing section — How it was verified
  4. Verification section — How we know it works

Usage:
    from task_completion_standard import validate_completion_report, score_report_quality

    is_valid, missing_sections, report_type = validate_completion_report(content, metadata)
    quality_score, breakdown = score_report_quality(content)
"""

import re
from typing import Dict, List, Tuple, Optional


# Required sections for implementation tasks
REQUIRED_SECTIONS = {
    "problem": {
        "patterns": [r"^##\s*Problem\b", r"^#\s*Problem\b", r"^\*\*Problem:\*\*"],
        "min_content_chars": 50,
        "description": "What was broken/needed? Why did this task exist?"
    },
    "solution": {
        "patterns": [r"^##\s*Solution\b", r"^#\s*Solution\b", r"^\*\*Solution:\*\*"],
        "min_content_chars": 100,
        "description": "What was actually built/changed? Key design decisions?"
    },
    "testing": {
        "patterns": [r"^##\s*Testing\b", r"^#\s*Testing\b", r"^\*\*Testing:\*\*", r"^##\s*Test\s", r"^##\s*Tests\b"],
        "min_content_chars": 30,
        "description": "Unit tests? Integration tests? Specific test cases and results?"
    },
    "verification": {
        "patterns": [r"^##\s*Verification\b", r"^#\s*Verification\b", r"^\*\*Verification:\*\*", r"^##\s*How (to )?[Vv]erify", r"^##\s*Evidence"],
        "min_content_chars": 30,
        "description": "How do we KNOW it works? What metrics confirm success?"
    }
}

# Optional but recommended sections
OPTIONAL_SECTIONS = {
    "caveats": {
        "patterns": [r"^##\s*Caveats", r"^##\s*Follow-?up", r"^##\s*Limitations", r"^##\s*Known Issues"],
        "description": "Known limitations, technical debt, follow-up tasks"
    },
    "files_modified": {
        "patterns": [r"^##\s*Files?\s+(Modified|Changed|Created)", r"^\*\*Files Modified:\*\*", r"^##\s*Changes"],
        "description": "List of files created/modified"
    }
}

# Task types and their requirements
TASK_TYPE_REQUIREMENTS = {
    "implementation": {
        "required": ["problem", "solution", "testing", "verification"],
        "min_quality_score": 60
    },
    "bugfix": {
        "required": ["problem", "solution", "testing", "verification"],
        "min_quality_score": 60
    },
    "research": {
        "required": ["problem", "solution"],  # Research may not have traditional testing
        "min_quality_score": 50
    },
    "documentation": {
        "required": ["problem", "solution"],
        "min_quality_score": 40
    },
    "trivial": {
        "required": ["solution"],  # Minimal requirement for trivial tasks
        "min_quality_score": 30
    }
}

# Patterns that indicate a trivial task (exempt from full requirements)
TRIVIAL_PATTERNS = [
    r"fix typo",
    r"update comment",
    r"add logging",
    r"minor formatting",
    r"bump version",
    r"quick fix",
    r"simple change"
]

# Patterns that indicate an implementation task
IMPLEMENTATION_PATTERNS = [
    r"implement",
    r"build",
    r"create",
    r"develop",
    r"add feature",
    r"fix bug",
    r"refactor",
    r"migrate",
    r"integrate",
    r"update.*require",
    r"enhance"
]


def extract_section_content(content: str, section_name: str) -> Tuple[bool, str]:
    """Extract content after a section header until the next section.

    Returns:
        Tuple of (found, content) where content is the text after the header
    """
    section_config = REQUIRED_SECTIONS.get(section_name) or OPTIONAL_SECTIONS.get(section_name, {})
    patterns = section_config.get("patterns", [rf"^##\s*{section_name.title()}\b"])

    # Find the section header
    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if match:
            # Get content after this match until the next ## header
            start = match.end()
            remaining = content[start:]

            # Find the next ## header
            next_section = re.search(r'^##\s+\S', remaining, re.MULTILINE)
            if next_section:
                section_content = remaining[:next_section.start()]
            else:
                section_content = remaining

            return True, section_content.strip()

    return False, ""


def classify_task_type(content: str, metadata: Dict) -> str:
    """Classify the task type based on content and metadata.

    Returns:
        One of: "implementation", "bugfix", "research", "documentation", "trivial"
    """
    content_lower = content.lower()

    # Check metadata first
    domain = metadata.get("domain", "").lower()
    if domain in ["research", "analysis"]:
        return "research"
    if domain in ["documentation", "writing"]:
        return "documentation"

    # Check for trivial patterns
    for pattern in TRIVIAL_PATTERNS:
        if re.search(pattern, content_lower):
            return "trivial"

    # Check for bugfix patterns
    if re.search(r"\b(fix|bug|issue|error|broken)\b", content_lower):
        return "bugfix"

    # Check for implementation patterns
    for pattern in IMPLEMENTATION_PATTERNS:
        if re.search(pattern, content_lower):
            return "implementation"

    # Default to implementation for unknown types
    return "implementation"


def validate_completion_report(content: str, metadata: Optional[Dict] = None) -> Tuple[bool, List[str], str]:
    """Validate that a completion report has required sections.

    Args:
        content: The task completion report content
        metadata: Optional metadata about the task (domain, priority, etc.)

    Returns:
        Tuple of (is_valid, missing_sections, task_type)
    """
    if metadata is None:
        metadata = {}

    # Classify task type
    task_type = classify_task_type(content, metadata)

    # Get requirements for this task type
    requirements = TASK_TYPE_REQUIREMENTS.get(task_type, TASK_TYPE_REQUIREMENTS["implementation"])
    required_sections = requirements["required"]

    # Check each required section
    missing = []
    for section_name in required_sections:
        section_config = REQUIRED_SECTIONS.get(section_name, {})
        found, section_content = extract_section_content(content, section_name)

        if not found:
            missing.append(section_name)
        elif section_config.get("min_content_chars"):
            # Check minimum content length
            if len(section_content.replace("\n", "").replace(" ", "")) < section_config["min_content_chars"]:
                missing.append(f"{section_name} (too brief)")

    is_valid = len(missing) == 0
    return is_valid, missing, task_type


def score_report_quality(content: str, metadata: Optional[Dict] = None) -> Dict:
    """Score the quality of a completion report.

    Args:
        content: The task completion report content
        metadata: Optional metadata about the task

    Returns:
        Dict with 'overall_score' (0-100), 'breakdown', 'recommendations', etc.
    """
    if metadata is None:
        metadata = {}

    breakdown = {
        "sections_score": 0,
        "content_score": 0,
        "completeness_score": 0,
        "total": 0,
        "missing_sections": [],
        "recommendations": []
    }

    # Classify and get requirements
    task_type = classify_task_type(content, metadata)
    requirements = TASK_TYPE_REQUIREMENTS.get(task_type, TASK_TYPE_REQUIREMENTS["implementation"])

    # Score sections (40% of total)
    required_sections = requirements["required"]
    sections_found = 0
    for section_name in required_sections:
        found, section_content = extract_section_content(content, section_name)
        if found:
            sections_found += 1
        else:
            breakdown["missing_sections"].append(section_name)

    if required_sections:
        sections_score = (sections_found / len(required_sections)) * 40
    else:
        sections_score = 40
    breakdown["sections_score"] = sections_score

    # Score content depth (30% of total)
    content_score = 0
    for section_name in required_sections:
        found, section_content = extract_section_content(content, section_name)
        if found and len(section_content) > 50:
            content_score += 10  # Up to 40 points max (4 sections * 10)

    # Cap at 30
    content_score = min(content_score, 30)
    breakdown["content_score"] = content_score

    # Score completeness indicators (30% of total)
    completeness_score = 0

    # Check for code examples (10 points)
    if re.search(r'```', content):
        completeness_score += 10

    # Check for files mentioned (5 points)
    if re.search(r'\b(modified|created|changed|updated)\b.*\.(py|ts|tsx|js|md)', content, re.IGNORECASE):
        completeness_score += 5

    # Check for test results (5 points)
    if re.search(r'(passed|failed|✓|✗|PASSED|FAILED|tests?)', content, re.IGNORECASE):
        completeness_score += 5

    # Check for metrics/numbers (5 points)
    if re.search(r'\d+\s*(lines|files|ms|seconds?|minutes?|%)', content):
        completeness_score += 5

    # Check optional sections (5 points each, max 15)
    for section_name in OPTIONAL_SECTIONS:
        found, _ = extract_section_content(content, section_name)
        if found:
            completeness_score += 5

    completeness_score = min(completeness_score, 30)
    breakdown["completeness_score"] = completeness_score

    # Total score
    total = sections_score + content_score + completeness_score
    breakdown["total"] = total

    # Generate recommendations
    if total < 60:
        for section in breakdown["missing_sections"]:
            config = REQUIRED_SECTIONS.get(section, {})
            desc = config.get("description", f"Add {section} section")
            breakdown["recommendations"].append(f"Add '{section}' section: {desc}")

        if breakdown["content_score"] < 20:
            breakdown["recommendations"].append("Expand section content with more details")

        if breakdown["completeness_score"] < 15:
            breakdown["recommendations"].append("Add code examples, test results, or file references")

    # Return dict format expected by completion-audit.py
    return {
        "overall_score": total,
        "breakdown": breakdown,
        "recommendations": breakdown["recommendations"],
        "missing_sections": breakdown["missing_sections"]
    }


def generate_report_template(task_type: str = "implementation") -> str:
    """Generate a template for a completion report.

    Args:
        task_type: Type of task (implementation, bugfix, research, etc.)

    Returns:
        Template string for the report
    """
    templates = {
        "implementation": """## Problem
[What was broken/needed? Why did this task exist? What was the impact of not fixing this?]

## Solution
[What was actually built/changed? Key design decisions? Files created/modified? Lines of code changed?]

## Testing
[Unit tests written? Integration tests run? Regression tests performed? Specific test cases and results?]

## Verification
[Before vs After comparison. How do we KNOW it works? What metrics confirm success?]

## Caveats / Follow-up (Optional)
[Known limitations? Technical debt introduced? Follow-up tasks needed?]
""",
        "bugfix": """## Problem
[What was the bug? How did it manifest? What was the root cause?]

## Solution
[What was changed to fix it? Why this approach?]

## Testing
[How was the fix verified? Test cases? Edge cases?]

## Verification
[Before vs After. How do we know the fix works?]
""",
        "research": """## Problem
[What question needed answering? Why was this research needed?]

## Solution
[Key findings? Data sources used? Analysis performed?]

## Testing
[How were findings validated? Cross-referenced?]

## Verification
[How do we know the research is accurate? Evidence?]
""",
        "documentation": """## Problem
[What documentation was missing or outdated? Why was it needed?]

## Solution
[What was documented? Where? Key additions?]

## Testing
[Was documentation reviewed? Tested for accuracy?]

## Verification
[How do we know the documentation is correct?]
"""
    }

    return templates.get(task_type, templates["implementation"])


if __name__ == "__main__":
    # Self-test with sample content
    sample_good = """
## Problem
The task completion reports were shallow checkbox lists that didn't communicate what was accomplished.

## Solution
Created task_completion_standard.py module with validation for required sections: Problem, Solution, Testing, Verification.

## Testing
Unit tests added for all validation functions. Tested against 50 sample task reports.

## Verification
Before: 0% reports had required sections. After: 100% compliance enforced.
"""

    sample_bad = """
I fixed the thing. It works now.
"""

    print("Testing good report:")
    valid, missing, rtype = validate_completion_report(sample_good, {})
    print(f"  Valid: {valid}, Missing: {missing}, Type: {rtype}")
    score, breakdown = score_report_quality(sample_good, {})
    print(f"  Score: {score}")

    print("\nTesting bad report:")
    valid, missing, rtype = validate_completion_report(sample_bad, {})
    print(f"  Valid: {valid}, Missing: {missing}, Type: {rtype}")
    score, breakdown = score_report_quality(sample_bad, {})
    print(f"  Score: {score}")
    print(f"  Recommendations: {breakdown['recommendations']}")
