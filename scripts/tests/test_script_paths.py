#!/usr/bin/env python3
"""
Test: Validate all script references in the codebase point to existing files.

This catches filename mismatch bugs (e.g., task-report-hook.py vs task_report_hook.py)
before they cause runtime failures.

Run: python3 scripts/tests/test_script_paths.py
"""

import re
import sys
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from script_paths import SCRIPTS, validate_all_scripts_exist


def test_all_registered_scripts_exist():
    """All scripts in SCRIPTS dict should exist on disk."""
    missing = validate_all_scripts_exist(SCRIPTS_DIR)
    if missing:
        print(f"FAIL: Missing scripts: {missing}")
        return False
    print(f"PASS: All {len(SCRIPTS)} registered scripts exist")
    return True


def test_no_duplicate_filenames():
    """No two script names should map to the same filename."""
    filenames = list(SCRIPTS.values())
    duplicates = set([f for f in filenames if filenames.count(f) > 1])
    if duplicates:
        print(f"FAIL: Duplicate filenames: {duplicates}")
        return False
    print("PASS: No duplicate filenames")
    return True


def find_hardcoded_script_references():
    """
    Find all hardcoded script references in Python files.
    
    Returns:
        List of (file_path, line_number, referenced_script) tuples
    """
    references = []
    
    # Pattern to match string literals that look like script filenames
    pattern = re.compile(r'["\']([\w-]+\.py)["\']')
    
    for py_file in SCRIPTS_DIR.glob("*.py"):
        if py_file.name in ("test_script_paths.py", "script_paths.py"):
            continue
            
        try:
            content = py_file.read_text()
            for i, line in enumerate(content.split("\n"), 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue
                    
                for match in pattern.finditer(line):
                    script_name = match.group(1)
                    # Skip non-script files and common false positives
                    skip_names = (
                        "__init__.py", "setup.py", "config.py", "test.py",
                        "script.py", "main.py", "app.py", "run_spider.py",
                        "example.py", "sample.py"
                    )
                    if script_name in skip_names:
                        continue
                    # Skip if it's clearly not a Kurultai script (no underscore/hyphen pattern)
                    if "_" not in script_name and "-" not in script_name and script_name.count("_") + script_name.count("-") == 0:
                        continue
                    references.append((py_file, i, script_name))
        except Exception:
            pass
    
    return references


def test_hardcoded_references_valid():
    """
    All hardcoded script references should point to existing files.
    
    This catches bugs where code references a script that doesn't exist
    or has the wrong name (hyphens vs underscores).
    """
    references = find_hardcoded_script_references()
    invalid = []
    
    for file_path, line_num, script_name in references:
        script_path = SCRIPTS_DIR / script_name
        if not script_path.exists():
            # Check if there's a similar name (helps with hyphen/underscore confusion)
            similar = [s for s in SCRIPTS_DIR.glob("*.py") 
                      if s.name.replace("_", "-").replace("-", "_") == script_name.replace("_", "-").replace("-", "_")]
            if similar:
                invalid.append(f"{file_path.name}:{line_num} - '{script_name}' not found (did you mean {similar[0].name}?)")
            else:
                invalid.append(f"{file_path.name}:{line_num} - '{script_name}' not found")
    
    if invalid:
        print("FAIL: Invalid script references:")
        for ref in invalid:
            print(f"  {ref}")
        return False
    
    print(f"PASS: All {len(references)} hardcoded references are valid")
    return True


def main():
    print("=" * 60)
    print("Script Paths Validation Test")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(("Registered scripts exist", test_all_registered_scripts_exist()))
    results.append(("No duplicate filenames", test_no_duplicate_filenames()))
    results.append(("Hardcoded references valid", test_hardcoded_references_valid()))
    
    print()
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n✓ All validation tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
