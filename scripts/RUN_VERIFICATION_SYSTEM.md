# Run Quality Gate Verification System

> **Purpose**: Execute the complete quality gate verification system after test fixes are complete
> **Prerequisites**: All test fixes must be committed and pushed
> **Estimated Time**: 5-10 minutes for full verification

---

## Quick Reference

```bash
# Quick check (fastest, skips coverage)
python scripts/verify_quality_gates.py --skip-coverage

# Full verification (recommended before deployment)
python scripts/verify_quality_gates.py --verbose

# CI/CD integration (JSON output)
python scripts/verify_quality_gates.py --json-output results.json

# Stop on first failure (debugging)
python scripts/verify_quality_gates.py --verbose --fail-fast
```

---

## Pre-Flight Checklist

Before running verification, ensure:

- [ ] All test fixes are committed: `git status` shows clean working directory
- [ ] Dependencies are installed: `pip install -r requirements.txt -r test-requirements.txt`
- [ ] Neo4j is running (for integration tests): `docker ps | grep neo4j` or verify Neo4j Aura connection
- [ ] Environment variables are set: `cat .env | grep -E "NEO4J|OPENCLAW"`

---

## Step-by-Step Verification

### Step 1: Environment Validation (30 seconds)

```bash
# Verify Python version (3.11, 3.12, or 3.13)
python --version

# Verify dependencies
pip list | grep -E "pytest|neo4j|pydantic"

# Verify environment variables
python -c "import os; print('OPENCLAW_GATEWAY_TOKEN:', 'SET' if os.getenv('OPENCLAW_GATEWAY_TOKEN') else 'MISSING')"
python -c "import os; print('NEO4J_URI:', os.getenv('NEO4J_URI', 'MISSING'))"
```

**Expected Output:**
```
Python 3.12.x
pytest 8.x.x
neo4j 5.x.x
pydantic 2.x.x
OPENCLAW_GATEWAY_TOKEN: SET
NEO4J_URI: bolt://...
```

---

### Step 2: Quick Verification (1-2 minutes)

Run the fast check to catch obvious issues:

```bash
python scripts/verify_quality_gates.py --skip-coverage --verbose
```

**What This Checks:**
- All tests pass (no failures, no errors)
- Static analysis passes (ruff, black)
- Type checking passes (mypy)

**Success Criteria:**
```
════════════════════════════════════════════════════════════
           QUALITY GATES VERIFICATION REPORT
════════════════════════════════════════════════════════════

Overall Status: PASS

Summary:
  Passed:  8/8 gates
  Failed:  0 gates
  Skipped: 0 gates
  Errors:  0 gates

All quality gates passed! ✅
```

**If Failed:**
- See [Troubleshooting Guide](#troubleshooting) below
- Fix issues before proceeding to full verification

---

### Step 3: Full Verification (3-5 minutes)

Run complete verification including coverage:

```bash
python scripts/verify_quality_gates.py --verbose
```

**What This Checks:**
- Everything from quick check, PLUS:
- Overall coverage >= 80%
- Critical modules >= 90%:
  - `openclaw_memory.py`
  - `tools/multi_goal_orchestration.py`
- Security modules >= 90%

**Success Criteria:**
```
════════════════════════════════════════════════════════════
           QUALITY GATES VERIFICATION REPORT
════════════════════════════════════════════════════════════

Overall Status: PASS

Summary:
  Passed:  12/12 gates
  Failed:  0 gates
  Skipped: 0 gates
  Errors:  0 gates

Gate Details:
  ✅ GATE-1: Test Execution - All tests passed
  ✅ GATE-2: Overall Coverage - 85.3% (threshold: 80%)
  ✅ GATE-3: Critical Module Coverage - 92.1% (threshold: 90%)
  ✅ GATE-4: Security Module Coverage - 94.2% (threshold: 90%)
  ✅ GATE-5: Ruff Linting - No errors
  ✅ GATE-6: Black Formatting - No issues
  ✅ GATE-7: Type Checking - No errors
  ...

All quality gates passed! ✅
```

---

### Step 4: CI/CD Simulation (Optional, 5-10 minutes)

Run the full CI pipeline locally:

```bash
# Run the local CI script
./scripts/run_tests.sh

# Or run GitHub Actions workflow locally with act (if installed)
act -j quality-gates
```

**What This Checks:**
- All quality gates across Python 3.11, 3.12, 3.13
- Security scanning (bandit, safety)
- Performance benchmarks

---

## Troubleshooting

### Issue: "Tests failing"

```bash
# Run tests with details to see failures
python -m pytest tests/ -v --tb=short

# Run specific failing test
python -m pytest tests/test_openclaw_memory.py::TestTaskLifecycle::test_create_task -v

# Check if it's a fixture issue
python -m pytest tests/ -v --fixtures
```

**Fix:**
- See `tests/TEST_FIX_REPORT.md` for specific fixes
- Update fixtures in `tests/conftest.py` if needed

---

### Issue: "Coverage below threshold"

```bash
# Generate coverage report
python -m pytest tests/ --cov --cov-report=term-missing

# Check specific module coverage
python -m pytest tests/ --cov=openclaw_memory --cov-report=term-missing

# See HTML report
python -m pytest tests/ --cov --cov-report=html
open htmlcov/index.html
```

**Fix:**
- Add tests for uncovered lines
- See `tests/COVERAGE_GAP_ANALYSIS.md` for gaps

---

### Issue: "Linting errors"

```bash
# Auto-fix most issues
ruff check . --fix

# Check remaining issues
ruff check .

# Format code
black .
```

**Fix:**
- Run auto-fixers: `ruff check . --fix && black .`
- Manually fix remaining issues

---

### Issue: "Type check errors"

```bash
# Run mypy
mypy openclaw_memory.py tools/

# Check specific file
mypy openclaw_memory.py
```

**Fix:**
- Add type annotations
- Create `pyproject.toml` with mypy config if missing

---

### Issue: "Security scan failed"

```bash
# Run bandit
bandit -r tools/ security/

# Run safety check
safety check

# Run pip-audit
pip-audit
```

**Fix:**
- Update vulnerable dependencies
- Fix security issues identified by bandit

---

## Verification Exit Codes

| Exit Code | Meaning | Action |
|-----------|---------|--------|
| 0 | All gates passed | Ready for deployment |
| 1 | Gates failed | Fix issues and re-run |
| 2 | Script error | Check Python environment |
| 130 | Interrupted | Re-run verification |

---

## Documentation References

- **Quality Gates Detail**: `docs/testing/QUALITY_GATES.md`
- **Fix Instructions**: `tests/TEST_FIX_REPORT.md`
- **Coverage Analysis**: `tests/COVERAGE_GAP_ANALYSIS.md`
- **Test Runbook**: `docs/testing/TEST_RUNBOOK.md`
- **CI/CD Workflow**: `.github/workflows/quality-gates.yml`

---

## Post-Verification Steps

After all gates pass:

1. **Commit verification results** (if JSON output):
   ```bash
   git add results.json
   git commit -m "ci: quality gates verification passed"
   ```

2. **Push to trigger CI**:
   ```bash
   git push origin main
   ```

3. **Verify CI passes**:
   - Check GitHub Actions tab
   - All jobs should be green ✅

4. **Deploy** (if CI passes):
   ```bash
   # Follow deployment procedures
   # See docs/plans/kublai-infrastructure-checklist.md
   ```

---

## Emergency Override

If you need to bypass a gate (emergencies only):

```bash
# Document the override
python scripts/verify_quality_gates.py --verbose 2>&1 | tee override-justification.txt

# Create override ticket
echo "Gate override requested" >> OVERRIDE_LOG.md

# Requires approval from:
# - Technical Lead
# - Security Team (if security gate)
```

See `docs/testing/QUALITY_GATES.md` section "Gate Override Process" for full procedure.

---

## Support

If verification fails and you cannot resolve:

1. Check `tests/TEST_FIX_REPORT.md` for known issues
2. Review `docs/testing/QUALITY_GATES.md` troubleshooting section
3. Run with `--verbose` flag for detailed output
4. Capture full output: `python scripts/verify_quality_gates.py --verbose 2>&1 | tee debug.log`
