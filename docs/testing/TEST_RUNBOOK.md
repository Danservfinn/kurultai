# Kublai Testing Suite - Test Runbook

Comprehensive guide for running and debugging tests in the Kublai Testing Suite.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running Specific Test Categories](#running-specific-test-categories)
3. [Debugging Failed Tests](#debugging-failed-tests)
4. [Common Issues and Solutions](#common-issues-and-solutions)
5. [Performance Benchmarking](#performance-benchmarking)
6. [CI/CD Integration](#cicd-integration)
7. [Test Fixtures](#test-fixtures)
8. [Pytest Markers](#pytest-markers)

---

## Quick Start

### Prerequisites

Ensure you have the required dependencies installed:

```bash
# Install production dependencies
pip install -r requirements.txt

# Install test dependencies
pip install -r test-requirements.txt

# Or install all at once
pip install pytest pytest-asyncio pytest-cov pytest-benchmark black ruff
```

### Run All Tests

Run the complete test suite with default configuration:

```bash
# Run all tests with verbose output and coverage
pytest

# Run all tests without coverage (faster)
pytest --no-cov

# Run all tests with minimal output
pytest --tb=no -q
```

### Quick Health Check

Run a quick validation to ensure the test environment is properly configured:

```bash
# Run a single unit test to verify setup
pytest tests/test_pre_flight.py::TestPreFlightCheck::test_init -v

# Check conftest.py loads correctly
pytest --collect-only -q | head -20
```

---

## Running Specific Test Categories

The test suite uses markers to categorize tests. See `pytest.ini` for the complete marker configuration.

### Unit Tests Only

Unit tests are fast, isolated tests that don't require external dependencies.

```bash
# Run only unit tests (excludes integration, security, performance, chaos)
pytest -m unit

# Run unit tests with no coverage for speed
pytest -m unit --no-cov

# Run unit tests in parallel (requires pytest-xdist)
pytest -m unit -n auto
```

**Unit Test Files:**
- `tests/test_openclaw_memory.py` - OperationalMemory core functionality
- `tests/test_delegation_protocol.py` - Agent delegation
- `tests/test_failover_monitor.py` - Failover and recovery
- `tests/test_meta_learning.py` - Meta-learning system
- `tests/test_reflection_memory.py` - Reflection and memory
- `tests/test_error_recovery.py` - Error recovery
- `tests/test_monitoring.py` - Monitoring and health
- `tests/test_pre_flight.py` - Pre-flight checks
- `tests/test_backend_analysis.py` - Backend analysis
- `tests/test_backend_collaboration.py` - Backend collaboration
- `tests/test_background_synthesis.py` - Background synthesis
- `tests/test_file_consistency.py` - File consistency
- `tests/test_improvements.py` - Improvements tracking
- `tests/test_integration.py` - Core integration tests
- `tests/test_intent_buffer.py` - Intent buffer
- `tests/test_intent_window.py` - Intent window
- `tests/test_memory_manager.py` - Memory manager
- `tests/test_notion_integration.py` - Notion integration
- `tests/test_notion_sync_extended.py` - Extended Notion sync
- `tests/test_priority_commands.py` - Priority commands
- `tests/test_priority_override.py` - Priority override
- `tests/test_security_audit.py` - Security audit
- `tests/test_semantic_analysis.py` - Semantic analysis
- `tests/test_dependency_analyzer.py` - Dependency analyzer
- `tests/test_topological_executor.py` - Topological executor

### Integration Tests Only

Integration tests verify component interactions and may require Neo4j or other external services.

```bash
# Run all integration tests
pytest -m integration

# Run specific integration test file
pytest tests/integration/test_delegation_workflow.py -v

# Run integration tests with detailed traceback
pytest -m integration --tb=long
```

**Integration Test Files:**
- `tests/integration/test_delegation_workflow.py` - Agent delegation workflows
- `tests/integration/test_orchestration_workflow.py` - Multi-goal orchestration
- `tests/integration/test_failover_workflow.py` - Failover scenarios
- `tests/integration/test_api_contracts.py` - API contract validation

### Security Tests

Security tests cover PII sanitization, injection prevention, and vulnerability scanning.

```bash
# Run all security tests
pytest -m security

# Run specific security test file
pytest tests/security/test_injection_prevention.py -v
pytest tests/security/test_pii_sanitization.py -v

# Run security tests with audit logging
pytest -m security --log-cli-level=DEBUG
```

**Security Test Files:**
- `tests/security/test_injection_prevention.py` - Cypher injection tests
- `tests/security/test_pii_sanitization.py` - PII detection and sanitization
- `tests/test_security_audit.py` - Security audit functionality (also unit tests)

### Performance Tests

Performance tests measure latency, throughput, and scalability under load.

```bash
# Run all performance tests
pytest -m performance

# Run performance tests with benchmark output
pytest tests/performance/test_load.py --benchmark-only

# Run DAG scalability tests
pytest tests/performance/test_dag_scalability.py -v

# Run with extended timeout (performance tests may be slow)
pytest -m performance --timeout=300
```

**Performance Test Files:**
- `tests/performance/test_load.py` - Load and concurrency testing
- `tests/performance/test_dag_scalability.py` - DAG scalability benchmarks

**Performance Targets:**
- P50 latency: < 100ms
- P95 latency: < 500ms
- P99 latency: < 1000ms
- Max concurrent operations: 100
- Throughput: 50 ops/second

### Chaos Tests

Chaos tests inject failures to verify system resilience.

```bash
# Run all chaos tests
pytest -m chaos

# Run specific chaos test file
pytest tests/chaos/test_failure_scenarios.py -v
pytest tests/chaos/test_data_corruption.py -v

# Run chaos tests with failure injection logging
pytest -m chaos --log-cli-level=DEBUG -s
```

**Chaos Test Files:**
- `tests/chaos/test_failure_scenarios.py` - Connection drops, timeouts, crashes
- `tests/chaos/test_data_corruption.py` - Data corruption scenarios

### Slow Tests

Some tests are marked as slow due to execution time.

```bash
# Run only slow tests
pytest -m slow

# Exclude slow tests (fast feedback loop)
pytest -m "not slow"

# Run slow tests with progress indication
pytest -m slow --tb=short -v
```

### Async Tests

Tests for async functionality are automatically marked with `asyncio`.

```bash
# Run async tests
pytest -m asyncio

# Run with asyncio debugging
pytest -m asyncio --asyncio-mode=auto -v
```

---

## Debugging Failed Tests

### Verbose Output

Get detailed information about test execution:

```bash
# Maximum verbosity
pytest -vvv

# Show local variables in tracebacks (enabled by default in pytest.ini)
pytest --showlocals

# Show full diff for assertion failures
pytest --tb=long

# Show short traceback
pytest --tb=short

# Show no traceback (just failure location)
pytest --tb=no

# Show traceback with captured output
pytest --tb=long -rP
```

### Run a Single Test

Isolate and debug specific tests:

```bash
# Run a specific test method
pytest tests/test_openclaw_memory.py::TestOperationalMemory::test_create_task -v

# Run a specific test class
pytest tests/test_openclaw_memory.py::TestOperationalMemory -v

# Run all tests matching a pattern
pytest -k "test_create" -v

# Run tests excluding a pattern
pytest -k "not slow" -v

# Run tests matching multiple patterns
pytest -k "create or claim" -v
```

### See Local Variables on Failure

The runbook configuration includes `--showlocals` by default. To enhance debugging:

```bash
# Show locals with full traceback
pytest --tb=long --showlocals

# Show locals and stop on first failure
pytest --tb=long --showlocals -x

# Show locals with PDB debugging on failure
pytest --tb=short --showlocals --pdb

# Show locals and capture all output
pytest --tb=long --showlocals -s
```

### Interactive Debugging

Use PDB for interactive debugging:

```bash
# Drop into PDB on failure
pytest --pdb

# Drop into PDB at first failure, then stop
pytest --pdb -x

# Use IPython debugger if available
pytest --pdb --pdbcls=IPython.terminal.debugger:TerminalPdb

# Set a breakpoint in your test code
# import pdb; pdb.set_trace()
```

### Capturing Output

```bash
# Show print statements during test execution
pytest -s

# Show captured output for all tests
pytest -rP

# Show captured output for failed tests only
pytest -rF

# Show captured output for passed tests only
pytest -rp

# Capture output but don't show it (default)
pytest --capture=fd

# Disable output capture entirely
pytest --capture=no
```

### Test Collection Debugging

```bash
# List all collected tests without running
pytest --collect-only

# List tests matching a pattern
pytest --collect-only -k "create"

# List tests with their markers
pytest --collect-only --verbose

# Show fixture setup
pytest --setup-show

# Show fixtures used by each test
pytest --fixtures-per-test
```

---

## Common Issues and Solutions

### Neo4j Connection Issues

**Problem:** Tests fail with Neo4j connection errors.

**Symptoms:**
```
neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information
```

**Solutions:**

1. **Use Fallback Mode (Recommended for Tests):**
   ```bash
   # Set environment variable before running tests
   export FALLBACK_MODE=true
   pytest

   # Or in Python code
   memory = OperationalMemory(fallback_mode=True)
   ```

2. **Start Local Neo4j Instance:**
   ```bash
   # Using Docker
   docker run -d \
     --name neo4j-test \
     -p 7687:7687 -p 7474:7474 \
     -e NEO4J_AUTH=neo4j/test_password \
     neo4j:5.13.0

   # Wait for Neo4j to be ready
   sleep 10

   # Run tests
   pytest
   ```

3. **Verify Neo4j Connection:**
   ```bash
   # Test connection manually
   python -c "
   from neo4j import GraphDatabase
   driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'test_password'))
   driver.verify_connectivity()
   print('Connection successful')
   driver.close()
   "
   ```

4. **Mock Neo4j in Unit Tests:**
   ```python
   # Tests use mock fixtures from conftest.py
   def test_with_mock_neo4j(mock_neo4j_driver, mock_neo4j_session):
       # Your test code here
       pass
   ```

### Mock Fixture Problems

**Problem:** Mock fixtures not working as expected.

**Symptoms:**
```
AttributeError: 'MagicMock' object has no attribute 'some_method'
```

**Solutions:**

1. **Verify Fixture is Requested:**
   ```python
   # Correct - fixture is requested as parameter
   def test_example(mock_neo4j_session):
       result = mock_neo4j_session.run("MATCH (n) RETURN n")
       assert result is not None
   ```

2. **Check Fixture Scope:**
   ```python
   # Default scope is 'function'
   @pytest.fixture(scope="module")  # Use module scope for expensive setups
   def expensive_fixture():
       return setup_expensive_thing()
   ```

3. **Use Factory Fixtures for Customization:**
   ```python
   # Use the factory pattern from conftest.py
   def test_custom_task(task_factory):
       task = task_factory(task_type="research", priority="high")
       assert task["priority"] == "high"
   ```

4. **Reset Mock State Between Tests:**
   ```python
   def test_with_reset(mock_neo4j_session):
       mock_neo4j_session.reset_mock()
       # Now mock is clean
   ```

### Async Test Issues

**Problem:** Async tests fail or hang.

**Symptoms:**
```
RuntimeError: Task got bad yield: <coroutine object ...>
```

**Solutions:**

1. **Use pytest-asyncio:**
   ```python
   import pytest

   @pytest.mark.asyncio
   async def test_async_function():
       result = await some_async_function()
       assert result is not None
   ```

2. **Check Asyncio Mode:**
   ```bash
   # Auto mode is configured in pytest.ini
   # --asyncio-mode=auto

   # Or specify manually
   pytest --asyncio-mode=auto
   ```

3. **Use Async Fixtures:**
   ```python
   import pytest_asyncio

   @pytest_asyncio.fixture
   async def async_client():
       client = await create_client()
       yield client
       await client.close()
   ```

4. **Handle Event Loop Issues:**
   ```python
   @pytest.fixture
   def event_loop():
       """Create an event loop for async tests."""
       loop = asyncio.new_event_loop()
       yield loop
       loop.close()
   ```

### Coverage Issues

**Problem:** Coverage report shows unexpected results.

**Solutions:**

1. **Check Coverage Configuration:**
   ```bash
   # Show coverage configuration
   pytest --cov-config=pytest.ini --cov

   # Run with specific coverage targets
   pytest --cov=openclaw_memory --cov=tools.multi_goal_orchestration
   ```

2. **Generate HTML Report:**
   ```bash
   # HTML report is generated automatically
   open htmlcov/index.html

   # Or generate explicitly
   pytest --cov-report=html
   ```

3. **Exclude Files from Coverage:**
   ```ini
   # In pytest.ini under [coverage:run]
   omit =
       tests/*
       */tests/*
   ```

4. **Fail Under Threshold:**
   ```bash
   # Coverage must be >= 80% (configured in pytest.ini)
   pytest --cov-fail-under=80
   ```

### Import Errors

**Problem:** Tests fail with import errors.

**Solutions:**

1. **Check Python Path:**
   ```bash
   # Ensure project root is in path
   export PYTHONPATH=/Users/kurultai/molt:$PYTHONPATH
   pytest
   ```

2. **Install Missing Dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r test-requirements.txt
   ```

3. **Check for Circular Imports:**
   ```bash
   # Use pytest to identify import issues
   pytest --collect-only 2>&1 | head -50
   ```

### RecursionError in Test Collection

**Problem:** Some test files fail to collect with `RecursionError: maximum recursion depth exceeded`.

**Symptoms:**
```
ERROR collecting tests/test_*.py - RecursionError: maximum recursion depth exceeded
```

**Affected Files:**
- `tests/test_backend_analysis.py`
- `tests/test_backend_collaboration.py`
- `tests/test_background_synthesis.py`
- `tests/test_delegation_protocol.py`
- `tests/test_dependency_analyzer.py`
- `tests/test_error_recovery.py`
- `tests/test_failover_monitor.py`
- `tests/test_file_consistency.py`
- `tests/test_improvements.py`
- `tests/test_integration.py`
- `tests/test_intent_buffer.py`
- `tests/test_intent_window.py`
- `tests/test_memory_manager.py`
- `tests/test_meta_learning.py`
- `tests/test_monitoring.py`
- `tests/test_notion_integration.py`
- `tests/test_openclaw_memory.py`
- `tests/test_priority_commands.py`
- `tests/test_priority_override.py`
- `tests/test_reflection_memory.py`
- `tests/test_security_audit.py`
- `tests/test_semantic_analysis.py`
- `tests/test_topological_executor.py`
- `tests/integration/test_delegation_workflow.py`
- `tests/performance/test_dag_scalability.py`

**Solutions:**

1. **Run Working Tests Only:**
   ```bash
   # Run only tests that don't have import issues
   pytest tests/test_pre_flight.py tests/security/ tests/chaos/ tests/integration/test_api_contracts.py tests/integration/test_failover_workflow.py tests/integration/test_orchestration_workflow.py tests/performance/test_load.py
   ```

2. **Increase Recursion Limit (Temporary Workaround):**
   ```bash
   python -c "import sys; sys.setrecursionlimit(2000)" -m pytest tests/test_*.py
   ```

3. **Check for Circular Imports in Source Code:**
   The recursion error typically indicates circular imports in the source modules being tested. Review imports in:
   - `openclaw_memory.py`
   - `tools/*.py`
   - `tools/security/*.py`

---

## Performance Benchmarking

### Running Benchmarks

The test suite includes performance benchmarks using `pytest-benchmark`.

```bash
# Run all benchmarks
pytest --benchmark-only

# Run benchmarks with specific tests
pytest tests/performance/test_load.py --benchmark-only

# Run with detailed benchmark output
pytest --benchmark-only --benchmark-verbose

# Save benchmark results to file
pytest --benchmark-only --benchmark-json=output.json
```

### Comparing Results

```bash
# Save baseline results
pytest --benchmark-only --benchmark-json=baseline.json

# Compare against baseline
pytest --benchmark-only --benchmark-compare=baseline.json

# Compare and fail if performance degrades
pytest --benchmark-only --benchmark-compare --benchmark-compare-fail=mean:20%
```

### Benchmark Configuration

```bash
# Set minimum rounds for statistical significance
pytest --benchmark-only --benchmark-min-rounds=10

# Set warmup rounds
pytest --benchmark-only --benchmark-warmup=true --benchmark-warmup-iterations=3

# Disable GC during benchmarks
pytest --benchmark-only --benchmark-disable-gc

# Sort benchmark results
pytest --benchmark-only --benchmark-sort=mean
```

### Benchmark Configuration

```python
# Example benchmark test
def test_task_creation_benchmark(benchmark):
    """Benchmark task creation performance."""
    memory = MockMemory()

    def create_task():
        return memory.create_task("test", "Benchmark task")

    result = benchmark(create_task)
    assert result is not None
```

### Interpreting Results

Benchmark output includes:
- **Mean**: Average execution time
- **StdDev**: Standard deviation (lower is more consistent)
- **Min/Max**: Best and worst case
- **Median**: Middle value
- **IQR**: Interquartile range (robust measure of spread)

Example output:
```
Name (time in us)         Mean              StdDev
--------------------------------------------------
test_task_creation      125.4567 (1.0)     12.3456
```

---

## Updating Benchmark Baselines

The benchmark baseline file (`benchmark-baseline.json`) contains the reference performance metrics used for regression detection in CI/CD pipelines.

### When to Update Baselines

Update the baseline file in the following scenarios:

#### 1. After Significant Performance Improvements
- When code optimizations result in measurable performance gains
- After algorithmic improvements that change expected execution times
- When refactoring leads to consistent performance changes

#### 2. When Adding New Performance Tests
- New benchmark tests must be included in the baseline
- Update baseline before merging PRs that add performance tests
- Ensure new tests have stable results before committing to baseline

#### 3. When Hardware/Environment Changes
- CI runner hardware changes (CPU, memory, disk)
- Python version upgrades in the test environment
- Operating system or dependency version changes that affect performance
- Infrastructure migrations (cloud provider, instance types)

#### 4. On Major Version Releases
- Establish new performance contracts for major releases
- Document expected performance characteristics
- Create historical reference points for future comparisons

### Generating New Baseline

To generate a new benchmark baseline file:

```bash
# Run performance tests and generate baseline file
pytest tests/performance/ --benchmark-only --benchmark-json=benchmark-baseline.json
```

**Best Practices:**
- Run on stable, dedicated hardware when possible
- Ensure no other processes are consuming significant resources
- Run multiple times to verify consistency before committing
- Include baseline updates in the same PR as performance-related changes
- Document the reason for baseline update in the commit message

### Comparing Against Baseline in CI

The CI pipeline automatically compares benchmark results against the baseline file:

```bash
# Compare current results against baseline
pytest tests/performance/ --benchmark-only --benchmark-compare=benchmark-baseline.json

# Fail if performance degrades beyond threshold
pytest tests/performance/ --benchmark-only \
  --benchmark-compare=benchmark-baseline.json \
  --benchmark-compare-fail=mean:20%
```

**CI Configuration Example:**
```yaml
# .github/workflows/tests.yml
- name: Run Performance Benchmarks
  run: |
    pytest tests/performance/ --benchmark-only \
      --benchmark-json=benchmark-results.json \
      --benchmark-compare=benchmark-baseline.json \
      --benchmark-compare-fail=mean:20%

- name: Upload Benchmark Results
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: benchmark-results
    path: benchmark-results.json
```

**Performance Regression Thresholds:**
- **Mean time**: Fail if > 20% slower than baseline
- **P95 latency**: Fail if > 30% slower than baseline
- **Throughput**: Fail if > 15% lower than baseline

### Baseline File Structure

The baseline file (`benchmark-baseline.json`) contains:
- **version**: Benchmark schema version
- **commit_info**: Git commit details when baseline was generated
- **benchmarks**: Array of test results with statistics
- **machine_info**: Hardware and environment details
- **datetime**: Timestamp of baseline generation

**Key Metrics Stored:**
- `mean`: Average execution time (primary comparison metric)
- `stddev`: Standard deviation (consistency check)
- `min`/`max`: Range bounds
- `median`: Middle value (robust to outliers)
- `ops`: Operations per second (throughput metric)

### PR Checklist for Performance Changes

When submitting PRs that affect performance tests or require baseline updates:

- [ ] Run benchmarks locally and verify results are stable
- [ ] Update `benchmark-baseline.json` if performance characteristics changed
- [ ] Document performance impact in PR description
- [ ] Verify CI benchmark comparison passes
- [ ] Include before/after performance numbers in PR
- [ ] Review threshold violations and justify if intentional

---

## CI/CD Integration

### Automatic Checks

The GitHub Actions workflow (`.github/workflows/tests.yml`) runs the following checks automatically:

1. **Code Formatting (Black)**
   ```bash
   black --check --diff .
   ```

2. **Linting (Ruff)**
   ```bash
   ruff check .
   ```

3. **Test Suite**
   ```bash
   pytest -v --tb=short
   ```

4. **Coverage Report**
   ```bash
   pytest --cov --cov-report=xml --cov-report=html
   ```

5. **Performance Benchmark Comparison**
   ```bash
   pytest tests/performance/ --benchmark-only \
     --benchmark-compare=benchmark-baseline.json \
     --benchmark-compare-fail=mean:20%
   ```

### Interpreting CI Results

**Green Checkmark:**
- All tests passed
- Code coverage >= 80%
- No formatting issues (warnings allowed)
- No linting errors (warnings allowed)
- Performance benchmarks within thresholds (if applicable)

**Red X:**
- One or more tests failed
- Coverage below threshold
- Critical linting errors
- Performance regression detected (>20% mean time increase)

**Yellow Warning:**
- Formatting issues (non-blocking)
- Non-critical linting warnings
- Performance variance detected but within acceptable range

### Running CI Checks Locally

Before pushing, run the same checks locally:

```bash
# Format code
black .

# Check formatting
black --check --diff .

# Run linter
ruff check .

# Run all tests
pytest -v --tb=short

# Run with coverage
pytest --cov --cov-fail-under=80

# Run benchmark comparison (if performance tests modified)
pytest tests/performance/ --benchmark-only \
  --benchmark-compare=benchmark-baseline.json \
  --benchmark-compare-fail=mean:20%
```

### Skipping CI for Documentation

Add `[skip ci]` to commit message to skip CI:

```bash
git commit -m "docs: update README [skip ci]"
```

### Matrix Testing

CI tests against multiple Python versions:
- Python 3.11
- Python 3.12
- Python 3.13

### Coverage Reporting

Coverage reports are automatically:
1. Uploaded to Codecov
2. Stored as artifacts (7-day retention)
3. Available in `htmlcov/` directory

View coverage report:
```bash
# After CI run, download artifacts
# Or generate locally
pytest --cov-report=html
open htmlcov/index.html
```

### Failed CI Debugging

When CI fails, reproduce locally:

```bash
# Match CI Python version
python --version  # Should match failing matrix version

# Run with same options as CI
pytest -v --tb=short

# Check if it's environment-specific
pip freeze > requirements-frozen.txt
diff requirements.txt requirements-frozen.txt
```

---

## Test Fixtures

The test suite provides comprehensive fixtures in `tests/conftest.py` and `tests/fixtures/` for consistent test data.

### Fixture Locations

- **`tests/conftest.py`** - Shared pytest fixtures (Neo4j mocks, data factories)
- **`tests/fixtures/__init__.py`** - Fixture package with helper functions
- **`tests/fixtures/test_data.py`** - Python-native test data structures

### Available Fixtures

#### Neo4j Mock Fixtures

```python
# Mock Neo4j driver
def test_with_driver(mock_neo4j_driver):
    driver = mock_neo4j_driver
    driver.verify_connectivity.return_value = None

# Mock Neo4j session
def test_with_session(mock_neo4j_session):
    result = mock_neo4j_session.run("MATCH (n) RETURN n")
    assert result is not None

# Mock OperationalMemory
def test_with_memory(mock_operational_memory):
    memory, mock_session = mock_operational_memory
    # Use memory with mocked session
```

#### Data Factory Fixtures

```python
# Task factory
def test_task_creation(task_factory):
    task = task_factory(
        task_type="research",
        status="pending",
        priority="high",
        assigned_to="jochi"
    )
    assert task["priority"] == "high"

# Agent factory
def test_agent_status(agent_factory):
    agent = agent_factory(
        agent_id="test-agent",
        role="backend_analyst",
        status="active"
    )
    assert agent["status"] == "active"

# Notification factory
def test_notification(notification_factory):
    notification = notification_factory(
        target_agent="jochi",
        source_agent="kublai",
        notification_type="task_delegated"
    )
    assert notification["type"] == "task_delegated"

# DAG node factory
def test_dag_node(dag_node_factory):
    node = dag_node_factory(
        node_id="task-1",
        title="Test Task",
        blocks=["task-2"],
        blocked_by=[]
    )
    assert node["id"] == "task-1"
```

#### Sample Data Fixtures

```python
# Sample task data
def test_task_processing(sample_task_data):
    assert sample_task_data["status"] == "pending"

# Sample completed task
def test_completed_task(sample_completed_task):
    assert sample_completed_task["status"] == "completed"

# Agent states
def test_agent_health(agent_states):
    assert agent_states["kublai"]["role"] == "orchestrator"

# PII samples
def test_pii_detection(pii_samples):
    emails = pii_samples["emails"]
    assert "user@example.com" in emails

# DAG structures
def test_dag_execution(dag_linear_nodes):
    assert len(dag_linear_nodes) == 4
```

### Using Fixture Data

```python
from tests.fixtures.test_data import (
    SAMPLE_TASKS,
    AGENT_CONFIGS,
    DAG_STRUCTURES,
    PII_TEST_DATA
)

def test_with_static_data():
    task = SAMPLE_TASKS["pending"]
    assert task["status"] == "pending"

    kublai = AGENT_CONFIGS["kublai"]
    assert kublai["role"] == "orchestrator"
```

### Fixture Helper Functions

```python
from tests.fixtures import generate_test_task, generate_test_notification

def test_task_generation():
    task = generate_test_task(
        task_type="code",
        status="in_progress",
        priority="critical"
    )
    assert task["priority"] == "critical"
```

---

## Pytest Markers

The test suite uses the following markers (defined in `pytest.ini`):

| Marker | Description | Auto-Applied |
|--------|-------------|--------------|
| `unit` | Unit tests (fast, isolated) | Yes - for tests in `tests/` root |
| `integration` | Integration tests (require external dependencies) | Yes - for tests in `tests/integration/` |
| `security` | Security tests (PII, injection, etc.) | Yes - for tests in `tests/security/` |
| `performance` | Performance tests (load, scalability) | Yes - for tests in `tests/performance/` |
| `chaos` | Chaos engineering tests (failure injection) | Yes - for tests in `tests/chaos/` |
| `slow` | Slow-running tests (may take >1 second) | Yes - for performance and chaos tests |
| `asyncio` | Async tests | Yes - for async test functions |

### Using Markers

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only security tests
pytest -m security

# Exclude slow tests
pytest -m "not slow"

# Combine markers
pytest -m "unit and not slow"

# Run multiple marker types
pytest -m "security or chaos"
```

### Custom Markers in Tests

```python
import pytest

@pytest.mark.slow
def test_long_running_operation():
    # Test that takes a while
    pass

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    pass

@pytest.mark.xfail(reason="Known bug")
def test_known_issue():
    pass
```

---

## Appendix: Test File Reference

### Core Test Files

| File | Description | Markers |
|------|-------------|---------|
| `tests/test_pre_flight.py` | Pre-flight environment checks | unit |
| `tests/test_openclaw_memory.py` | OperationalMemory core functionality | unit |
| `tests/test_delegation_protocol.py` | Agent delegation | unit |
| `tests/test_failover_monitor.py` | Failover and recovery | unit |
| `tests/test_meta_learning.py` | Meta-learning system | unit |
| `tests/test_reflection_memory.py` | Reflection and memory | unit |
| `tests/test_error_recovery.py` | Error recovery | unit |
| `tests/test_monitoring.py` | Monitoring and health | unit |
| `tests/test_backend_analysis.py` | Backend analysis | unit |
| `tests/test_backend_collaboration.py` | Backend collaboration | unit |
| `tests/test_background_synthesis.py` | Background synthesis | unit |
| `tests/test_file_consistency.py` | File consistency | unit |
| `tests/test_improvements.py` | Improvements tracking | unit |
| `tests/test_integration.py` | Core integration tests | unit |
| `tests/test_intent_buffer.py` | Intent buffer | unit |
| `tests/test_intent_window.py` | Intent window | unit |
| `tests/test_memory_manager.py` | Memory manager | unit |
| `tests/test_notion_integration.py` | Notion integration | unit |
| `tests/test_notion_sync_extended.py` | Extended Notion sync | unit |
| `tests/test_priority_commands.py` | Priority commands | unit |
| `tests/test_priority_override.py` | Priority override | unit |
| `tests/test_security_audit.py` | Security audit | unit |
| `tests/test_semantic_analysis.py` | Semantic analysis | unit |
| `tests/test_dependency_analyzer.py` | Dependency analyzer | unit |
| `tests/test_topological_executor.py` | Topological executor | unit |

### Integration Tests

| File | Description | Markers |
|------|-------------|---------|
| `tests/integration/test_delegation_workflow.py` | Delegation workflows | integration |
| `tests/integration/test_orchestration_workflow.py` | Orchestration workflows | integration |
| `tests/integration/test_failover_workflow.py` | Failover workflows | integration |
| `tests/integration/test_api_contracts.py` | API contracts | integration |

### Security Tests

| File | Description | Markers |
|------|-------------|---------|
| `tests/security/test_injection_prevention.py` | Injection attacks | security |
| `tests/security/test_pii_sanitization.py` | PII handling | security |
| `tests/test_security_audit.py` | Security audit | security, unit |

### Performance Tests

| File | Description | Markers |
|------|-------------|---------|
| `tests/performance/test_load.py` | Load testing | performance, slow |
| `tests/performance/test_dag_scalability.py` | DAG scalability | performance, slow |

### Chaos Tests

| File | Description | Markers |
|------|-------------|---------|
| `tests/chaos/test_failure_scenarios.py` | Failure injection | chaos, slow |
| `tests/chaos/test_data_corruption.py` | Data corruption | chaos, slow |

---

## Quick Reference Card

```bash
# Most common commands
pytest                              # Run all tests
pytest -m unit                      # Run unit tests only
pytest -m "not slow"                # Exclude slow tests
pytest -k "test_create"             # Run tests matching pattern
pytest -x                           # Stop on first failure
pytest --pdb                        # Debug on failure
pytest --no-cov                     # Skip coverage (faster)
pytest -s                           # Show print statements
pytest -v                           # Verbose output

# Debugging
pytest --tb=long                    # Full traceback
pytest --showlocals                 # Show local variables
pytest --setup-show                 # Show fixture setup
pytest --fixtures-per-test          # Show fixtures per test

# Performance
pytest --benchmark-only             # Run benchmarks
pytest --benchmark-json=out.json    # Save benchmark results

# Coverage
pytest --cov-report=html            # Generate HTML report
open htmlcov/index.html             # View coverage report

# Working tests (avoiding RecursionError files)
pytest tests/test_pre_flight.py tests/security/ tests/chaos/ tests/integration/test_api_contracts.py tests/integration/test_failover_workflow.py tests/integration/test_orchestration_workflow.py tests/performance/test_load.py
```

---

*Last updated: 2026-02-04*
*Test Suite Version: 1.1*
