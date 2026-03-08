#!/usr/bin/env python3
"""
Prompt Template Validation Script

Validates the prompt_templates.json library for:
- JSON syntax correctness
- Required field presence
- Valid status values
- Sequential version numbers
- Section structure consistency

Usage:
    python3 validate_templates.py
    python3 validate_templates.py --template agent-protocol-v2
    python3 validate_templates.py --verbose
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


# Configuration
TEMPLATE_PATH = Path.home() / ".openclaw" / "agents" / "main" / "data" / "prompt_templates.json"

# Validation rules
REQUIRED_TOP_LEVEL = ["version", "last_updated", "description", "templates", "metadata"]
REQUIRED_TEMPLATE_FIELDS = [
    "version", "created", "status", "structure", "sections",
    "avg_quality", "sample_size", "recommended_for"
]
VALID_STATUSES = ["active", "deprecated", "experimental"]
VALID_AGENTS = ["temujin", "mongke", "chagatai", "jochi", "ogedei", "tolui", "kublai", "all"]
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ValidationResult:
    """Container for validation results."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def add_error(self, message: str):
        self.errors.append(f"❌ ERROR: {message}")

    def add_warning(self, message: str):
        self.warnings.append(f"⚠️  WARNING: {message}")

    def add_pass(self, message: str):
        self.passed.append(f"✓ {message}")

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_issues(self) -> int:
        return len(self.errors) + len(self.warnings)


def load_templates(path: Path) -> Dict[str, Any]:
    """Load template library from JSON file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Template file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}")


def validate_date(date_string: str, field_name: str = "Date") -> bool:
    """Validate date string format (YYYY-MM-DD)."""
    if not DATE_PATTERN.match(date_string):
        return False
    try:
        datetime.strptime(date_string, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_top_level(data: Dict[str, Any], result: ValidationResult) -> None:
    """Validate top-level structure."""
    for field in REQUIRED_TOP_LEVEL:
        if field not in data:
            result.add_error(f"Missing required top-level field: {field}")
        else:
            result.add_pass(f"Top-level field present: {field}")

    # Validate last_updated format
    if "last_updated" in data:
        if not validate_date(data["last_updated"], "last_updated"):
            result.add_error(f"Invalid date format for last_updated: {data['last_updated']}")
        else:
            # Check not in future
            try:
                last_updated = datetime.strptime(data["last_updated"], "%Y-%m-%d")
                if last_updated > datetime.now():
                    result.add_warning("last_updated date is in the future")
            except:
                pass


def validate_metadata(metadata: Dict[str, Any], result: ValidationResult) -> None:
    """Validate metadata section."""
    required_meta = ["total_templates", "active_templates", "deprecated_templates", "default_template"]

    for field in required_meta:
        if field not in metadata:
            result.add_error(f"Missing required metadata field: {field}")
        else:
            result.add_pass(f"Metadata field present: {field}")

    # Validate counts match actual templates
    if "total_templates" in metadata and "templates" in metadata:
        actual_count = len(metadata.get("templates", {}))
        declared_count = metadata.get("total_templates", 0)
        if actual_count != declared_count:
            result.add_warning(
                f"total_templates ({declared_count}) != actual template count ({actual_count})"
            )

    # Validate default_template exists
    if "default_template" in metadata and "templates" in metadata:
        default = metadata["default_template"]
        if default not in metadata.get("templates", {}):
            result.add_error(f"default_template '{default}' not found in templates")


def validate_template_field_types(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate field types for a template."""
    type_requirements = {
        "version": int,
        "created": str,
        "status": str,
        "structure": list,
        "sections": dict,
        "avg_quality": (float, type(None)),
        "sample_size": int,
        "recommended_for": list,
    }

    for field, expected_type in type_requirements.items():
        if field in template:
            if not isinstance(template[field], expected_type):
                result.add_error(
                    f"Template '{name}': field '{field}' has wrong type "
                    f"(expected {expected_type}, got {type(template[field]).__name__})"
                )


def validate_template_structure(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate template structure consistency."""
    # Check structure array matches sections keys
    if "structure" in template and "sections" in template:
        structure_sections = set(template["structure"])
        available_sections = set(template["sections"].keys())

        missing = structure_sections - available_sections
        if missing:
            result.add_error(
                f"Template '{name}': structure references sections not defined: {missing}"
            )

        extra = available_sections - structure_sections
        if extra:
            result.add_warning(
                f"Template '{name}': sections defined but not in structure: {extra}"
            )


def validate_template_status(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate template status and related fields."""
    status = template.get("status")

    if status not in VALID_STATUSES:
        result.add_error(
            f"Template '{name}': invalid status '{status}' (must be one of {VALID_STATUSES})"
        )
    else:
        result.add_pass(f"Template '{name}': valid status '{status}'")

    # Deprecated templates must have replaced_by field
    if status == "deprecated" and "replaced_by" not in template:
        result.add_warning(
            f"Template '{name}': deprecated but missing 'replaced_by' field"
        )

    # Non-deprecated templates should not have replaced_by
    if status != "deprecated" and "replaced_by" in template:
        result.add_warning(
            f"Template '{name}': has 'replaced_by' but status is '{status}'"
        )


def validate_template_dates(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate template date fields."""
    # Validate created date
    created = template.get("created")
    if created and not validate_date(created, "created"):
        result.add_error(f"Template '{name}': invalid created date format '{created}'")

    # Validate deprecated date if present
    deprecated = template.get("deprecated")
    if deprecated and not validate_date(deprecated, "deprecated"):
        result.add_error(f"Template '{name}': invalid deprecated date format '{deprecated}'")

    # Check deprecated date is after created date
    if created and deprecated:
        try:
            created_date = datetime.strptime(created, "%Y-%m-%d")
            deprecated_date = datetime.strptime(deprecated, "%Y-%m-%d")
            if deprecated_date <= created_date:
                result.add_error(
                    f"Template '{name}': deprecated date must be after created date"
                )
        except:
            pass


def validate_template_recommended_agents(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate recommended_for agent list."""
    recommended = template.get("recommended_for", [])

    if not isinstance(recommended, list):
        result.add_error(f"Template '{name}': recommended_for must be a list")
        return

    if not recommended:
        result.add_warning(f"Template '{name}': recommended_for is empty")

    for agent in recommended:
        if agent not in VALID_AGENTS:
            result.add_warning(
                f"Template '{name}': unknown agent '{agent}' in recommended_for "
                f"(known agents: {VALID_AGENTS})"
            )


def validate_template_quality_fields(template: Dict[str, Any], name: str, result: ValidationResult) -> None:
    """Validate quality and sample size fields."""
    avg_quality = template.get("avg_quality")
    sample_size = template.get("sample_size")

    # avg_quality should be between 0 and 10 if not null
    if avg_quality is not None:
        if not isinstance(avg_quality, (int, float)):
            result.add_error(f"Template '{name}': avg_quality must be numeric or null")
        elif not (0 <= avg_quality <= 10):
            result.add_warning(
                f"Template '{name}': avg_quality {avg_quality} outside 0-10 range"
            )

    # sample_size should be non-negative
    if sample_size is not None:
        if not isinstance(sample_size, int):
            result.add_error(f"Template '{name}': sample_size must be an integer")
        elif sample_size < 0:
            result.add_error(f"Template '{name}': sample_size cannot be negative")

    # If sample_size is 0, avg_quality should be null
    if sample_size == 0 and avg_quality is not None:
        result.add_warning(
            f"Template '{name}': sample_size is 0 but avg_quality is {avg_quality} (should be null)"
        )


def validate_version_consistency(templates: Dict[str, Any], result: ValidationResult) -> None:
    """Validate version numbers are sequential within template families."""
    # Group by template family (name without version suffix)
    families: Dict[str, List[Dict]] = {}

    for name, template in templates.items():
        # Extract family name (e.g., "agent-protocol" from "agent-protocol-v2")
        match = re.match(r'(.+)-v\d+$', name)
        if match:
            family = match.group(1)
        else:
            family = name

        if family not in families:
            families[family] = []
        families[family].append({"name": name, "version": template.get("version")})

    for family, members in families.items():
        if len(members) > 1:
            versions = sorted(m["version"] for m in members if m["version"] is not None)
            for i in range(1, len(versions)):
                if versions[i] != versions[i-1] + 1:
                    result.add_warning(
                        f"Family '{family}': non-sequential versions detected: {versions}"
                    )


def validate_single_template(name: str, templates: Dict[str, Any], result: ValidationResult) -> None:
    """Validate a single template."""
    if name not in templates:
        result.add_error(f"Template '{name}' not found")
        return

    template = templates[name]

    # Check required fields
    for field in REQUIRED_TEMPLATE_FIELDS:
        if field not in template:
            result.add_error(f"Template '{name}': missing required field '{field}'")

    # Validate field types
    validate_template_field_types(template, name, result)

    # Validate structure consistency
    validate_template_structure(template, name, result)

    # Validate status
    validate_template_status(template, name, result)

    # Validate dates
    validate_template_dates(template, name, result)

    # Validate recommended agents
    validate_template_recommended_agents(template, name, result)

    # Validate quality fields
    validate_template_quality_fields(template, name, result)

    # Validate sections have content
    if "sections" in template:
        for section_name, section_content in template["sections"].items():
            if not isinstance(section_content, str):
                result.add_error(
                    f"Template '{name}': section '{section_name}' must be a string"
                )
            elif not section_content.strip():
                result.add_warning(
                    f"Template '{name}': section '{section_name}' is empty"
                )


def validate_all_templates(data: Dict[str, Any], result: ValidationResult) -> None:
    """Validate all templates in the library."""
    templates = data.get("templates", {})

    if not templates:
        result.add_error("No templates defined in library")
        return

    for name in templates:
        validate_single_template(name, templates, result)

    # Validate cross-template consistency
    validate_version_consistency(templates, result)


def print_result(result: ValidationResult, verbose: bool = False) -> int:
    """Print validation results and return exit code."""
    if result.is_valid and result.total_issues == 0:
        print("✓ Template library is valid!")
        if verbose:
            for msg in result.passed:
                print(f"  {msg}")
        return 0
    elif result.is_valid:
        print(f"⚠️  Template library valid with {len(result.warnings)} warning(s)")
        for msg in result.warnings:
            print(f"  {msg}")
        if verbose:
            print(f"\nPassed checks: {len(result.passed)}")
        return 0
    else:
        print(f"❌ Template library has {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
        print()
        print("Errors:")
        for msg in result.errors:
            print(f"  {msg}")
        if result.warnings:
            print("\nWarnings:")
            for msg in result.warnings:
                print(f"  {msg}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Validate prompt template library")
    parser.add_argument(
        "--template",
        type=str,
        help="Validate only the specified template"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed validation output"
    )
    parser.add_argument(
        "--path",
        type=str,
        default=str(TEMPLATE_PATH),
        help=f"Path to template file (default: {TEMPLATE_PATH})"
    )

    args = parser.parse_args()
    result = ValidationResult()

    try:
        # Load templates
        data = load_templates(Path(args.path))
        result.add_pass("JSON syntax is valid")

        # Validate top-level structure
        validate_top_level(data, result)

        # Validate metadata
        if "metadata" in data:
            validate_metadata(data["metadata"], result)

        # Validate templates
        if args.template:
            validate_single_template(args.template, data.get("templates", {}), result)
        else:
            validate_all_templates(data, result)

        # Print results
        return print_result(result, args.verbose)

    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
