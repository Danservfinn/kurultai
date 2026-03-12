# Script Naming Conventions

**Purpose:** Prevent filename mismatch bugs like `task-report-hook.py` vs `task_report_hook.py`

## Central Registry

All script filenames are registered in `scripts/script_paths.py`:

```python
from scripts.script_paths import SCRIPTS, get_script_path

# Use the registry
hook_path = get_script_path("task_report_hook")
# Returns: Path("task_report_hook.py")
```

## Naming Rules

### Python Modules (underscores)
- Use **underscores** for Python module files: `task_report_hook.py`
- Matches Python import convention: `import task_report_hook`
- Examples:
  - `task_report_hook.py` ✓
  - `task-report-hook.py` ✗

### CLI Tools (hyphens allowed)
- Use **hyphens** for shell scripts and CLI tools: `watchdog-gather.sh`
- Matches Unix CLI convention: `watchdog-gather --help`
- Examples:
  - `hourly_reflection.sh` ✓ (internal script)
  - `validate-fallback-chain.sh` ✓ (CLI tool)

### Consistency Within Files
- If a script is called via subprocess, use the registry
- If a script is imported, use underscore naming

## Updating the Registry

When adding a new script:

1. Add to `SCRIPTS` dict in `script_paths.py`:
   ```python
   "my_new_script": "my_new_script.py",
   ```

2. Run validation:
   ```bash
   python3 scripts/script_paths.py
   ```

3. Update references in existing code to use `get_script_path()`

## Validation

### Pre-commit Check
```bash
python3 scripts/script_paths.py
```

### Test Suite
```bash
python3 scripts/tests/test_script_paths.py
```

### What It Checks
1. All registered scripts exist on disk
2. No duplicate filenames
3. Hardcoded references point to valid files

## Migration Status

| File | Status | Notes |
|------|--------|-------|
| task-watcher.py | ✓ Migrated | Uses `get_script_path()` |
| kurultai_voting.py | ✓ Migrated | Uses `get_script_path()` in `run_script()` |
| agent-task-handler.py | Pending | Still uses hardcoded paths |
| hourly_reflection.sh | Pending | Shell script, harder to migrate |

## Known Issues

None currently. Report any filename mismatches to the Kurultai.

## Related Documentation

- `ARCHITECTURE.md` - System overview
- `TOOLS.md` - Tool usage guide
- `scripts/tests/test_script_paths.py` - Validation tests
