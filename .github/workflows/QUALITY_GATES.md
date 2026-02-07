# Quality Gates Workflow

This document describes the GitHub Actions workflow that enforces quality gates on every PR and push to the main branch.

## Status Badges

Add these badges to your README.md:

```markdown
![Quality Gates](https://github.com/OWNER/REPO/workflows/Quality%20Gates/badge.svg)
![Security Scan](https://github.com/OWNER/REPO/workflows/Security%20Scan/badge.svg)
![Performance Benchmark](https://github.com/OWNER/REPO/workflows/Performance%20Benchmark/badge.svg)
```

## Workflow Overview

The quality gates workflow consists of three main jobs:

### 1. Quality Gates Job

Runs on Python 3.11, 3.12, and 3.13 matrix.

**Steps:**
- Checkout code with full history
- Set up Python with pip caching
- Install dependencies from `requirements.txt` and `test-requirements.txt`
- Install linting tools (black, ruff, isort, mypy)
- Run code formatting checks (Black, Ruff, isort)
- Run type checking with mypy
- Run tests with pytest and generate coverage reports
- Upload coverage report as artifact
- Post PR comment with results (Python 3.12 only)

**Outputs:**
- Coverage reports (HTML and XML)
- Test results summary
- Code formatting status

### 2. Security Scan Job

Runs security checks on the codebase.

**Tools:**
- **Bandit**: Security linter for Python code
  - Scans for common security issues
  - Reports by severity (High, Medium, Low)
  - Fails on high severity issues

- **Safety**: Dependency vulnerability scanner
  - Checks installed packages against known vulnerability databases
  - Reports CVEs and security advisories

- **pip-audit**: Alternative dependency scanner
  - Uses PyPA's advisory database
  - Complements Safety checks

**Outputs:**
- Security reports (JSON and text formats)
- Vulnerability counts by tool
- Fails workflow if high severity issues found

### 3. Performance Benchmark Job

Runs performance benchmarks and compares against baseline.

**Features:**
- Runs pytest-benchmark tests from `tests/performance/`
- Generates benchmark report in JSON format
- Compares results against baseline from main branch
- Fails if performance regression > 10%
- Reports improvements > 10%

**Baseline Management:**
- Baseline stored as `benchmark-baseline.json` in main branch
- Update baseline by committing new results after performance improvements

## Trigger Conditions

The workflow runs on:

1. **Pull Requests** to `main` or `master` branches
2. **Push** to `main` or `master` branches
3. **Manual Dispatch** with options to skip specific jobs:
   - Skip tests (for emergency fixes)
   - Skip security scan (for emergency fixes)
   - Skip performance benchmarks (for emergency fixes)

## Branch Protection Rules

To enforce quality gates before merge, configure these branch protection rules:

### Required Settings

1. **Require status checks to pass before merging**
   - Enable "Require status checks to pass before merging"
   - Search for and select these status checks:
     - `Quality Gates Summary` (final aggregation job)
     - `Quality Gates (Python 3.11)`
     - `Quality Gates (Python 3.12)`
     - `Quality Gates (Python 3.13)`
     - `Security Scan`
     - `Performance Benchmark`

2. **Require pull request reviews before merging**
   - Enable "Require a pull request before merging"
   - Set "Required number of approvals" to 1
   - Optionally enable "Dismiss stale PR approvals when new commits are pushed"

3. **Require branches to be up to date before merging**
   - Enable "Require branches to be up to date before merging"
   - This ensures the PR branch is tested against the latest main

4. **Require conversation resolution before merging**
   - Enable "Require conversation resolution before merging"
   - Ensures all review comments are addressed

### Optional Settings

- **Require signed commits**: Enable for enhanced security
- **Include administrators**: Apply rules to admin users as well
- **Restrict pushes that create files**: Limit who can push to protected branches

## Configuration

### Python Versions

The workflow tests against Python 3.11, 3.12, and 3.13. Modify the matrix in the workflow file to change versions:

```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12', '3.13']
```

### Coverage Threshold

The minimum coverage threshold is set in `pytest.ini`:

```ini
[coverage:report]
fail_under = 80
```

### Performance Regression Threshold

The performance regression threshold is set in the workflow:

```yaml
# In the compare step, change the 10% threshold
if change_pct > 10:
    regressions.append(...)
```

### Security Severity Levels

Bandit severity levels that fail the build:
- **High**: Always fails
- **Medium**: Warns but doesn't fail
- **Low**: Reports only

## Artifacts

The workflow generates these artifacts:

1. **Coverage Report** (`coverage-report-{run_id}`)
   - HTML coverage report
   - XML coverage report for external tools
   - pytest JSON report

2. **Security Reports** (`security-reports-{run_id}`)
   - Bandit reports (JSON and text)
   - Safety reports (JSON and text)
   - pip-audit report (JSON)

3. **Benchmark Reports** (`benchmark-reports-{run_id}`)
   - Benchmark results (JSON)
   - Comparison report (Markdown)

Artifacts are retained for 14 days.

## Notifications

### PR Comments

The workflow automatically posts a comment on PRs with:
- Black formatting status
- Ruff linting status
- Import sorting status
- Test status
- Coverage percentage

The comment is updated on subsequent runs.

### Failure Notifications

When jobs fail:
- Summary job reports overall status
- Failed job details are logged
- PR comments include failure information

## Troubleshooting

### Common Issues

1. **Tests fail on specific Python version**
   - Check version-specific compatibility
   - Review matrix strategy fail-fast setting

2. **Security scan false positives**
   - Add `# nosec` comments with justification
   - Configure bandit exclusions in `.bandit` file

3. **Performance benchmarks flaky**
   - Increase warmup iterations
   - Use more stable test environment
   - Adjust regression threshold

4. **Coverage not uploading to Codecov**
   - Verify `CODECOV_TOKEN` secret is set
   - Check Codecov service status

### Emergency Bypass

For critical hotfixes, use manual dispatch with skip options:

1. Go to Actions > Quality Gates > Run workflow
2. Select branch
3. Check skip options as needed
4. Run workflow

**Note**: Emergency bypasses should be rare and documented.

## Related Files

- `.github/workflows/quality-gates.yml` - Main workflow definition
- `pytest.ini` - pytest and coverage configuration
- `requirements.txt` - Production dependencies
- `test-requirements.txt` - Test dependencies
- `tests/performance/` - Performance benchmark tests

## Maintenance

### Updating Tools

Update tool versions in the workflow or `test-requirements.txt`:

```bash
pip install --upgrade black ruff bandit safety pytest-benchmark
```

### Adding New Checks

To add a new quality check:

1. Add a new step to the appropriate job
2. Set an output for status tracking
3. Update the PR comment script to include the new check
4. Update this documentation

### Baseline Updates

To update the performance baseline:

1. Run benchmarks locally: `pytest tests/performance/ --benchmark-only --benchmark-json=benchmark-baseline.json`
2. Commit the new baseline to main: `git add benchmark-baseline.json && git commit -m "Update performance baseline"`
3. Push to main

## Support

For issues with the quality gates workflow:

1. Check the workflow logs in GitHub Actions
2. Review artifact reports for detailed information
3. Run checks locally to reproduce issues
4. File an issue with the workflow output and error messages
