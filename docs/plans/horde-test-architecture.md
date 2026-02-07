# horde-test: Comprehensive Testing Skill Architecture

> **Status**: Design Document
> **Date**: 2026-02-05
> **Author**: Backend System Architect
> **Prerequisites**: horde-swarm, horde-plan, horde-implement, horde-review

---

## Executive Summary

`horde-test` is a specialized skill in the Kurultai skills marketplace that leverages `horde-swarm` to execute comprehensive testing plans. It serves as the testing and validation engine for the horde ecosystem, particularly integrated with `horde-implement` Phase 6 (Testing and Validation).

**Key Innovation**: Transform testing from a sequential, time-consuming bottleneck into a parallelized, intelligent validation pipeline using specialized testing subagents.

---

## 1. Core Architecture

### 1.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HORDE-TEST ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────────────────┐  │
│  │ Test Plan    │───▶│ Test Plan Parser │───▶│ Dependency Analyzer      │  │
│  │ Input        │    │ & Validator      │    │                          │  │
│  └──────────────┘    └──────────────────┘    └────────────┬─────────────┘  │
│                                                           │                 │
│                                                           ▼                 │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    TEST ORCHESTRATION ENGINE                          │  │
│  ├──────────────────────────────────────────────────────────────────────┤  │
│  │                                                                       │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌────────┐ │  │
│  │  │ Test Case   │    │ Test Case   │    │ Test Case   │    │ Test   │ │  │
│  │  │ Scheduler   │───▶│ Dispatcher  │───▶│ Executor    │───▶│ Result │ │  │
│  │  │             │    │ (Swarm)     │    │ (Parallel)  │    │ Store  │ │  │
│  │  └─────────────┘    └─────────────┘    └─────────────┘    └────────┘ │  │
│  │                                                               │       │  │
│  │  ┌──────────────────────────────────────────────────────────────┐    │  │
│  │  │                    RESULT AGGREGATOR                          │◀───┘  │
│  │  ├──────────────────────────────────────────────────────────────┤       │
│  │  │ • Coverage Analysis    • Failure Clustering   • Insights      │       │
│  │  │ • Trend Detection      • Recommendations      • Reports       │       │
│  │  └──────────────────────────────────────────────────────────────┘       │
│  │                                                                          │
│  └──────────────────────────────────────────────────────────────────────────┘
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    HORDE-SWARM INTEGRATION                            │  │
│  ├──────────────────────────────────────────────────────────────────────┤  │
│  │                                                                       │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐ │  │
│  │   │ Unit Test   │   │ Integration │   │ E2E Test    │   │ Security │ │  │
│  │   │ Specialist  │   │ Specialist  │   │ Specialist  │   │ Auditor  │ │  │
│  │   └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘ │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌──────────┐ │  │
│  │   │ Performance │   │ Contract    │   │ Chaos       │   │ Mutation │ │  │
│  │   │ Engineer    │   │ Validator   │   │ Engineer    │   │ Tester   │ │  │
│  │   └─────────────┘   └─────────────┘   └─────────────┘   └──────────┘ │  │
│  │                                                                       │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Breakdown

#### 1.2.1 Test Plan Parser & Validator

**Purpose**: Parse and validate incoming testing plans.

```python
@dataclass
class ParsedTestPlan:
    """Validated test plan ready for execution."""
    plan_id: str
    version: str
    target: TestTarget
    test_suites: List[TestSuite]
    dependencies: List[TestDependency]
    coverage_targets: CoverageTargets
    execution_config: ExecutionConfig
    metadata: Dict[str, Any]

class TestPlanParser:
    """Parses and validates test plans from various formats."""

    SUPPORTED_FORMATS = ["json", "yaml", "markdown", "toml"]
    SCHEMA_VERSION = "1.0.0"

    def parse(self, plan_input: Union[str, Dict], format_hint: Optional[str] = None) -> ParsedTestPlan:
        """
        Parse test plan from input.

        Args:
            plan_input: Raw test plan (string or dict)
            format_hint: Optional format override

        Returns:
            Parsed and validated test plan

        Raises:
            TestPlanValidationError: If plan is invalid
        """
        # 1. Detect format
        format_type = format_hint or self._detect_format(plan_input)

        # 2. Parse to dict
        raw_plan = self._parse_to_dict(plan_input, format_type)

        # 3. Validate schema
        self._validate_schema(raw_plan)

        # 4. Validate semantic constraints
        self._validate_semantics(raw_plan)

        # 5. Build ParsedTestPlan
        return self._build_plan(raw_plan)

    def _validate_schema(self, plan: Dict) -> None:
        """Validate against JSON schema."""
        schema = self._load_schema()
        jsonschema.validate(plan, schema)

    def _validate_semantics(self, plan: Dict) -> None:
        """Validate semantic constraints."""
        errors = []

        # Check for circular dependencies
        if self._has_circular_deps(plan.get("dependencies", [])):
            errors.append("Circular dependencies detected")

        # Check coverage targets are achievable
        if not self._validate_coverage_targets(plan.get("coverage", {})):
            errors.append("Invalid coverage targets")

        # Check test cases have required fields
        for suite in plan.get("suites", []):
            for test in suite.get("tests", []):
                if not self._validate_test_case(test):
                    errors.append(f"Invalid test case: {test.get('id', 'unknown')}")

        if errors:
            raise TestPlanValidationError(errors)
```

#### 1.2.2 Dependency Analyzer

**Purpose**: Analyze test dependencies and build execution DAG.

```python
@dataclass
class TestDependency:
    """Dependency between test cases."""
    test_id: str
    depends_on: str
    dependency_type: str  # "data", "state", "service", "file"
    optional: bool = False

class DependencyAnalyzer:
    """Analyzes test dependencies and builds execution graph."""

    def analyze(self, test_plan: ParsedTestPlan) -> TestExecutionGraph:
        """
        Build execution graph from test plan.

        Returns:
            TestExecutionGraph with parallelization opportunities identified
        """
        graph = TestExecutionGraph()

        # Add all test cases as nodes
        for suite in test_plan.test_suites:
            for test in suite.tests:
                graph.add_node(TestNode(
                    id=test.id,
                    suite_id=suite.id,
                    test_type=test.type,
                    estimated_duration=test.estimated_duration,
                    resource_requirements=test.resources,
                    priority=test.priority
                ))

        # Add explicit dependencies
        for dep in test_plan.dependencies:
            graph.add_edge(dep.depends_on, dep.test_id, dep.dependency_type)

        # Detect implicit dependencies
        implicit_deps = self._detect_implicit_dependencies(test_plan)
        for dep in implicit_deps:
            graph.add_edge(dep.depends_on, dep.test_id, "implicit")

        # Validate no cycles
        if cycles := graph.detect_cycles():
            raise CircularDependencyError(cycles)

        # Calculate parallel groups
        graph.parallel_groups = self._calculate_parallel_groups(graph)

        return graph

    def _detect_implicit_dependencies(self, plan: ParsedTestPlan) -> List[TestDependency]:
        """Detect implicit dependencies based on test characteristics."""
        implicit = []

        # Tests modifying shared state
        state_modifying = []
        for suite in plan.test_suites:
            for test in suite.tests:
                if test.modifies_shared_state:
                    state_modifying.append(test)

        # Create dependencies: state-modifying tests must run sequentially
        for i in range(len(state_modifying) - 1):
            implicit.append(TestDependency(
                test_id=state_modifying[i + 1].id,
                depends_on=state_modifying[i].id,
                dependency_type="state"
            ))

        # Tests requiring same exclusive resource
        resource_tests = defaultdict(list)
        for suite in plan.test_suites:
            for test in suite.tests:
                for resource in test.resources:
                    if resource.exclusive:
                        resource_tests[resource.name].append(test)

        for resource_name, tests in resource_tests.items():
            for i in range(len(tests) - 1):
                implicit.append(TestDependency(
                    test_id=tests[i + 1].id,
                    depends_on=tests[i].id,
                    dependency_type="resource"
                ))

        return implicit
```

#### 1.2.3 Test Case Scheduler

**Purpose**: Schedule test execution for optimal parallelization.

```python
class TestScheduler:
    """Schedules test execution to maximize parallelization."""

    def __init__(self, max_parallel: int = 10):
        self.max_parallel = max_parallel

    def schedule(self, graph: TestExecutionGraph) -> TestSchedule:
        """
        Create execution schedule from dependency graph.

        Strategy:
        1. Topological sort to respect dependencies
        2. Group independent tests into waves
        3. Balance waves by estimated duration
        4. Prioritize by priority and coverage impact
        """
        schedule = TestSchedule()
        remaining = set(graph.nodes.keys())
        completed = set()
        wave = 0

        while remaining:
            wave += 1
            wave_tests = []

            # Find all tests with satisfied dependencies
            for test_id in remaining:
                deps = graph.get_dependencies(test_id)
                if all(d in completed for d in deps):
                    wave_tests.append(graph.nodes[test_id])

            if not wave_tests:
                raise UnsatisfiableDependenciesError(remaining)

            # Sort by priority and estimated duration
            wave_tests.sort(key=lambda t: (-t.priority, t.estimated_duration))

            # Limit parallel execution
            if len(wave_tests) > self.max_parallel:
                # Move excess to next wave
                scheduled = wave_tests[:self.max_parallel]
                deferred = wave_tests[self.max_parallel:]
            else:
                scheduled = wave_tests
                deferred = []

            # Add wave to schedule
            schedule.add_wave(TestWave(
                number=wave,
                tests=[t.id for t in scheduled],
                estimated_duration=max(t.estimated_duration for t in scheduled),
                parallelizable=len(scheduled) > 1
            ))

            # Update tracking
            for test in scheduled:
                remaining.remove(test.id)
                completed.add(test.id)

        return schedule
```

#### 1.2.4 Test Dispatcher (horde-swarm Integration)

**Purpose**: Dispatch tests to horde-swarm for parallel execution.

```python
class TestDispatcher:
    """Dispatches tests to horde-swarm for parallel execution."""

    # Subagent type mapping for test types
    AGENT_MAPPING = {
        "unit": "testing:unit-tester",
        "integration": "testing:integration-tester",
        "e2e": "testing:e2e-tester",
        "performance": "testing:performance-engineer",
        "security": "security-auditor",
        "contract": "testing:contract-validator",
        "chaos": "testing:chaos-engineer",
        "mutation": "testing:mutation-tester",
        "accessibility": "testing:a11y-tester",
        "visual": "testing:visual-regression",
    }

    def __init__(self, swarm_gateway: str):
        self.gateway = swarm_gateway

    async def dispatch_wave(
        self,
        wave: TestWave,
        test_plan: ParsedTestPlan,
        context: TestContext
    ) -> List[TestResult]:
        """
        Dispatch a wave of tests to horde-swarm.

        Args:
            wave: The test wave to execute
            test_plan: Full test plan for context
            context: Execution context (environment, secrets, etc.)

        Returns:
            List of test results
        """
        tasks = []

        for test_id in wave.tests:
            test = self._get_test_by_id(test_plan, test_id)
            agent_type = self.AGENT_MAPPING.get(test.type, "testing:general-tester")

            # Build prompt for subagent
            prompt = self._build_test_prompt(test, test_plan, context)

            # Create Task for horde-swarm
            task = Task(
                subagent_type=agent_type,
                prompt=prompt,
                description=f"Execute {test.type} test: {test.name}",
                timeout=test.timeout or 300,
                metadata={
                    "test_id": test_id,
                    "test_type": test.type,
                    "suite_id": test.suite_id,
                    "wave": wave.number
                }
            )
            tasks.append(task)

        # Execute in parallel via horde-swarm
        results = await asyncio.gather(
            *[self._execute_with_retry(t) for t in tasks],
            return_exceptions=True
        )

        # Process results
        test_results = []
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                test_results.append(TestResult(
                    test_id=task.metadata["test_id"],
                    status="error",
                    error=str(result),
                    duration=0
                ))
            else:
                test_results.append(self._parse_result(result, task.metadata))

        return test_results

    def _build_test_prompt(
        self,
        test: TestCase,
        plan: ParsedTestPlan,
        context: TestContext
    ) -> str:
        """Build comprehensive prompt for test subagent."""

        prompt_parts = [
            f"# Test Execution: {test.name}",
            f"",
            f"## Test Information",
            f"- ID: {test.id}",
            f"- Type: {test.type}",
            f"- Priority: {test.priority}",
            f"- Timeout: {test.timeout}s",
            f"",
            f"## Target",
            f"```",
            f"{self._format_target(plan.target)}",
            f"```",
            f"",
            f"## Test Specification",
            f"```yaml",
            f"{yaml.dump(test.specification)}",
            f"```",
        ]

        # Add setup instructions
        if test.setup:
            prompt_parts.extend([
                f"",
                f"## Setup",
                f"```",
                f"{test.setup}",
                f"```"
            ])

        # Add environment context
        prompt_parts.extend([
            f"",
            f"## Environment",
            f"```yaml",
            f"{yaml.dump(context.environment)}",
            f"```"
        ])

        # Add execution instructions
        prompt_parts.extend([
            f"",
            f"## Execution Instructions",
            f"1. Execute the test according to the specification",
            f"2. Capture all output, logs, and artifacts",
            f"3. Measure performance metrics if applicable",
            f"4. Return structured results in the format below",
            f"",
            f"## Expected Output Format",
            f"```json",
            f"{self._get_output_format_template(test.type)}",
            f"```"
        ])

        return "\n".join(prompt_parts)
```

---

## 2. Test Plan Format Specification

### 2.1 Schema Overview

```yaml
# horde-test Plan Schema v1.0.0

# Required metadata
plan:
  id: "unique-plan-identifier"
  version: "1.0.0"
  name: "Comprehensive API Testing"
  description: "Full test suite for user service API"
  created_at: "2026-02-05T10:00:00Z"
  author: "test-author"

# Target under test
target:
  type: "api"  # api, service, frontend, library, infrastructure
  name: "user-service"
  version: "2.1.0"
  location:
    type: "url"  # url, git, filesystem, container
    value: "https://api.example.com/v2"
  credentials:
    type: "environment"  # environment, vault, inline (not recommended)
    reference: "USER_SERVICE_API_KEY"

# Test suites
test_suites:
  - id: "auth-tests"
    name: "Authentication Tests"
    description: "Test authentication flows"
    type: "security"  # unit, integration, e2e, performance, security, contract
    priority: "critical"  # critical, high, medium, low
    parallelizable: true
    tests:
      - id: "auth-001"
        name: "Valid login returns token"
        type: "integration"
        priority: "critical"
        timeout: 30
        specification:
          given:
            - "Valid user credentials"
          when:
            - "POST /auth/login with credentials"
          then:
            - "Status is 200"
            - "Response contains JWT token"
            - "Token expires in 3600s"
        assertions:
          - type: "status_code"
            expected: 200
          - type: "json_path"
            path: "$.token"
            exists: true
          - type: "json_path"
            path: "$.expires_in"
            expected: 3600

      - id: "auth-002"
        name: "Invalid credentials rejected"
        type: "integration"
        priority: "critical"
        timeout: 30
        specification:
          given:
            - "Invalid password"
          when:
            - "POST /auth/login"
          then:
            - "Status is 401"
            - "Error message is generic"

  - id: "load-tests"
    name: "Performance Tests"
    type: "performance"
    priority: "high"
    parallelizable: false  # Resource intensive, run sequentially
    tests:
      - id: "perf-001"
        name: "Login endpoint load test"
        type: "performance"
        priority: "high"
        timeout: 300
        specification:
          tool: "k6"  # k6, artillery, locust, custom
          scenario:
            stages:
              - duration: "1m"
                target: 100
              - duration: "3m"
                target: 100
              - duration: "1m"
                target: 0
            thresholds:
              - metric: "http_req_duration"
                condition: "p(95) < 200"
              - metric: "http_req_failed"
                condition: "rate < 0.01"

# Explicit dependencies between tests
dependencies:
  - test: "auth-002"
    depends_on: "auth-001"
    type: "data"  # data, state, service, file
    optional: false

  - test: "user-profile-001"
    depends_on: "auth-001"
    type: "data"
    optional: false

# Coverage targets
coverage:
  required:
    line_coverage: 80
    branch_coverage: 70
    function_coverage: 90
  desired:
    line_coverage: 90
    branch_coverage: 85
    function_coverage: 95

# Execution configuration
execution:
  environment: "staging"  # local, dev, staging, production
  parallelization:
    max_concurrent: 10
    strategy: "optimal"  # optimal, aggressive, conservative
  retries:
    max_attempts: 3
    backoff: "exponential"
  resources:
    cpu: "2"
    memory: "4Gi"
    timeout: 1800  # 30 minutes

# Reporting configuration
reporting:
  formats: ["json", "html", "junit", "markdown"]
  destination:
    type: "s3"  # s3, gcs, azure, filesystem, webhook
    path: "s3://test-reports/horde-test/"
  notifications:
    on_failure: ["slack", "email"]
    on_success: ["slack"]
```

### 2.2 Test Type Specifications

#### 2.2.1 Unit Tests

```yaml
test:
  type: "unit"
  specification:
    framework: "pytest"  # pytest, jest, junit, go-test
    test_path: "tests/unit/"
    pattern: "test_*.py"
    coverage:
      enabled: true
      report_type: "branch"
    isolation:
      method: "docker"  # docker, process, thread
      dependencies:
        - "postgres:14"
        - "redis:7"
```

#### 2.2.2 Integration Tests

```yaml
test:
  type: "integration"
  specification:
    scope: "api"  # api, database, message_queue, external_service
    services:
      - name: "api"
        endpoint: "http://localhost:8080"
        health_check: "/health"
      - name: "database"
        image: "postgres:14"
        migrations: "migrations/"
    fixtures:
      - name: "test_users"
        source: "fixtures/users.sql"
    cleanup:
      strategy: "transaction"  # transaction, truncate, delete
```

#### 2.2.3 End-to-End Tests

```yaml
test:
  type: "e2e"
  specification:
    framework: "playwright"  # playwright, cypress, selenium
    browsers: ["chromium", "firefox", "webkit"]
    viewport:
      width: 1280
      height: 720
    scenarios:
      - name: "User checkout flow"
        steps:
          - action: "navigate"
            url: "/products"
          - action: "click"
            selector: "[data-testid='add-to-cart']"
          - action: "click"
            selector: "[data-testid='checkout']"
          - action: "fill"
            selector: "#email"
            value: "test@example.com"
          - action: "click"
            selector: "[data-testid='complete-purchase']"
          - action: "assert"
            selector: "[data-testid='success-message']"
            visible: true
```

#### 2.2.4 Performance Tests

```yaml
test:
  type: "performance"
  specification:
    tool: "k6"
    script: "tests/performance/load_test.js"
    scenarios:
      smoke:
        executor: "constant-vus"
        vus: 10
        duration: "1m"
      load:
        executor: "ramping-vus"
        stages:
          - duration: "2m"
            target: 100
          - duration: "5m"
            target: 100
          - duration: "2m"
            target: 0
      stress:
        executor: "ramping-vus"
        stages:
          - duration: "2m"
            target: 200
          - duration: "5m"
            target: 200
          - duration: "2m"
            target: 400
          - duration: "5m"
            target: 400
          - duration: "2m"
            target: 0
    thresholds:
      http_req_duration: ["p(95)<500", "p(99)<1000"]
      http_req_failed: ["rate<0.01"]
```

#### 2.2.5 Security Tests

```yaml
test:
  type: "security"
  specification:
    scanners:
      - tool: "owasp-zap"
        spider: true
        ajax_spider: true
        active_scan: true
        policies:
          - "sqli"
          - "xss"
          - "path-traversal"
      - tool: "semgrep"
        rules:
          - "p/owasp-top-ten"
          - "p/cwe-top-25"
      - tool: "dependency-check"
        severity: "medium"
    auth:
      type: "jwt"
      token_endpoint: "/auth/login"
      credentials:
        username: "${TEST_USER}"
        password: "${TEST_PASSWORD}"
```

---

## 3. Parallel Execution Strategy

### 3.1 Subagent Type Definitions

```python
# Subagent types for horde-swarm integration

TESTING_SUBAGENTS = {
    "testing:unit-tester": {
        "description": "Specialized in unit test execution and coverage analysis",
        "capabilities": ["unit-testing", "coverage-analysis", "mock-creation"],
        "optimal_for": ["unit", "component"],
        "parallelizable": True,
        "max_concurrent": 20
    },
    "testing:integration-tester": {
        "description": "Specialized in integration test execution",
        "capabilities": ["integration-testing", "service-orchestration", "fixture-management"],
        "optimal_for": ["integration", "api"],
        "parallelizable": True,
        "max_concurrent": 10
    },
    "testing:e2e-tester": {
        "description": "Specialized in end-to-end test execution",
        "capabilities": ["browser-automation", "user-flow-testing", "visual-regression"],
        "optimal_for": ["e2e", "ui", "workflow"],
        "parallelizable": True,
        "max_concurrent": 5
    },
    "testing:performance-engineer": {
        "description": "Specialized in performance testing and analysis",
        "capabilities": ["load-testing", "stress-testing", "profiling", "bottleneck-analysis"],
        "optimal_for": ["performance", "load", "stress", "spike"],
        "parallelizable": False,  # Resource intensive
        "max_concurrent": 2
    },
    "security-auditor": {
        "description": "Security-focused testing and vulnerability assessment",
        "capabilities": ["penetration-testing", "vulnerability-scanning", "compliance-check"],
        "optimal_for": ["security", "penetration", "compliance"],
        "parallelizable": True,
        "max_concurrent": 5
    },
    "testing:contract-validator": {
        "description": "API contract and schema validation",
        "capabilities": ["openapi-validation", "schema-testing", "backward-compatibility"],
        "optimal_for": ["contract", "api", "schema"],
        "parallelizable": True,
        "max_concurrent": 15
    },
    "testing:chaos-engineer": {
        "description": "Chaos engineering and resilience testing",
        "capabilities": ["failure-injection", "resilience-testing", "disaster-recovery"],
        "optimal_for": ["chaos", "resilience", "disaster-recovery"],
        "parallelizable": False,
        "max_concurrent": 1
    },
    "testing:mutation-tester": {
        "description": "Mutation testing for test quality assessment",
        "capabilities": ["mutation-testing", "test-quality-analysis"],
        "optimal_for": ["mutation", "quality"],
        "parallelizable": True,
        "max_concurrent": 8
    },
    "testing:a11y-tester": {
        "description": "Accessibility testing and compliance",
        "capabilities": ["a11y-testing", "wcag-compliance", "screen-reader-testing"],
        "optimal_for": ["accessibility", "a11y"],
        "parallelizable": True,
        "max_concurrent": 10
    },
    "testing:general-tester": {
        "description": "General-purpose testing for unclassified tests",
        "capabilities": ["general-testing", "test-execution"],
        "optimal_for": ["*"],
        "parallelizable": True,
        "max_concurrent": 10
    }
}
```

### 3.2 Dependency Resolution

```python
class DependencyResolver:
    """Resolves test dependencies and determines execution order."""

    DEPENDENCY_RULES = {
        # Test type compatibility matrix
        # If test A depends on test B, what types are compatible?
        "data": {
            "description": "Test A requires data produced by test B",
            "compatible_types": ["unit", "integration", "e2e"],
            "execution_order": "sequential"
        },
        "state": {
            "description": "Test A modifies state that test B depends on",
            "compatible_types": ["unit", "integration", "e2e"],
            "execution_order": "sequential",
            "isolation_required": True
        },
        "service": {
            "description": "Test A requires service started by test B",
            "compatible_types": ["integration", "e2e", "performance"],
            "execution_order": "sequential"
        },
        "file": {
            "description": "Test A requires file produced by test B",
            "compatible_types": ["*"],
            "execution_order": "sequential"
        },
        "resource": {
            "description": "Tests share an exclusive resource",
            "compatible_types": ["*"],
            "execution_order": "sequential",
            "isolation_required": True
        }
    }

    def resolve_execution_groups(self, tests: List[TestCase], dependencies: List[TestDependency]) -> List[ExecutionGroup]:
        """
        Group tests into execution groups based on dependencies.

        Returns:
            List of ExecutionGroup, where each group can run in parallel
            internally, but groups must run sequentially.
        """
        # Build dependency graph
        graph = nx.DiGraph()
        for test in tests:
            graph.add_node(test.id, test=test)

        for dep in dependencies:
            graph.add_edge(dep.depends_on, dep.test_id, type=dep.dependency_type)

        # Find strongly connected components (cycles)
        sccs = list(nx.strongly_connected_components(graph))
        for scc in sccs:
            if len(scc) > 1:
                raise CircularDependencyError(f"Cycle detected: {scc}")

        # Topological sort to get execution order
        try:
            execution_order = list(nx.topological_sort(graph))
        except nx.NetworkXUnfeasible:
            raise CircularDependencyError("Circular dependency detected")

        # Group tests into parallelizable waves
        groups = []
        executed = set()

        while execution_order:
            # Find all tests whose dependencies are satisfied
            ready = []
            remaining = []

            for test_id in execution_order:
                deps = list(graph.predecessors(test_id))
                if all(d in executed for d in deps):
                    ready.append(test_id)
                else:
                    remaining.append(test_id)

            if not ready:
                raise UnsatisfiableDependenciesError(remaining)

            # Group ready tests by isolation requirements
            isolated_tests = []
            parallel_tests = []

            for test_id in ready:
                test = graph.nodes[test_id]["test"]
                if self._requires_isolation(test, graph):
                    isolated_tests.append(test)
                else:
                    parallel_tests.append(test)

            # Create execution group
            groups.append(ExecutionGroup(
                parallel_tests=parallel_tests,
                isolated_tests=isolated_tests,
                can_parallelize=len(parallel_tests) > 1
            ))

            executed.update(ready)
            execution_order = remaining

        return groups
```

---

## 4. Integration with horde-implement

### 4.1 Phase 6: Testing and Validation

`horde-implement` Phase 6 delegates testing to `horde-test` through a well-defined interface.

```python
class HordeImplementIntegration:
    """Integration point between horde-implement and horde-test."""

    # Phase 6 entry point
    async def execute_testing_phase(
        self,
        implementation_result: ImplementationResult,
        test_requirements: TestRequirements
    ) -> TestingPhaseResult:
        """
        Execute Phase 6: Testing and Validation.

        Called by horde-implement after code implementation.

        Args:
            implementation_result: Output from implementation phase
            test_requirements: Testing requirements from planning phase

        Returns:
            TestingPhaseResult with test results and recommendations
        """
        # 1. Generate test plan from implementation
        test_plan = await self._generate_test_plan(
            implementation_result,
            test_requirements
        )

        # 2. Execute tests via horde-test
        test_results = await self._execute_test_plan(test_plan)

        # 3. Analyze results
        analysis = await self._analyze_results(test_results, test_requirements)

        # 4. Generate recommendations
        recommendations = self._generate_recommendations(analysis)

        # 5. Determine if implementation passes
        passed = self._determine_pass_status(analysis, test_requirements)

        return TestingPhaseResult(
            passed=passed,
            test_results=test_results,
            coverage=analysis.coverage,
            issues=analysis.issues,
            recommendations=recommendations,
            retry_recommended=not passed and analysis.retry_warranted
        )

    async def _generate_test_plan(
        self,
        implementation: ImplementationResult,
        requirements: TestRequirements
    ) -> TestPlan:
        """Generate comprehensive test plan from implementation."""

        suites = []

        # Unit tests for new code
        if requirements.unit_tests:
            suites.append(TestSuite(
                id="unit-tests",
                type="unit",
                tests=self._generate_unit_tests(implementation),
                priority="critical"
            ))

        # Integration tests for API changes
        if requirements.integration_tests and implementation.has_api_changes:
            suites.append(TestSuite(
                id="integration-tests",
                type="integration",
                tests=self._generate_integration_tests(implementation),
                priority="critical"
            ))

        # Security tests for security-sensitive code
        if requirements.security_tests and implementation.security_relevant:
            suites.append(TestSuite(
                id="security-tests",
                type="security",
                tests=self._generate_security_tests(implementation),
                priority="critical"
            ))

        # Performance tests for performance-critical code
        if requirements.performance_tests and implementation.performance_relevant:
            suites.append(TestSuite(
                id="performance-tests",
                type="performance",
                tests=self._generate_performance_tests(implementation),
                priority="high"
            ))

        return TestPlan(
            id=f"test-plan-{implementation.task_id}",
            target=TestTarget(
                type="service",
                name=implementation.service_name,
                location=implementation.deployment_url
            ),
            test_suites=suites,
            coverage=requirements.coverage_targets,
            execution=ExecutionConfig(
                environment=requirements.test_environment,
                parallelization=ParallelizationConfig(
                    max_concurrent=10,
                    strategy="optimal"
                )
            )
        )

    async def _execute_test_plan(self, plan: TestPlan) -> TestExecutionResult:
        """Execute test plan via horde-test."""

        # Invoke horde-test skill
        result = await self.skills.invoke(
            skill="horde-test",
            action="execute",
            parameters={
                "plan": plan.to_dict(),
                "options": {
                    "parallel": True,
                    "fail_fast": False,
                    "coverage": True
                }
            }
        )

        return TestExecutionResult.from_dict(result)
```

### 4.2 Interface Contract

```python
# Interface between horde-implement and horde-test

@dataclass
class TestRequirements:
    """Testing requirements passed from horde-implement."""
    unit_tests: bool = True
    integration_tests: bool = True
    e2e_tests: bool = False
    security_tests: bool = True
    performance_tests: bool = False
    coverage_targets: CoverageTargets = field(default_factory=CoverageTargets)
    test_environment: str = "staging"
    max_test_duration: int = 1800  # 30 minutes


@dataclass
class ImplementationResult:
    """Implementation result passed to horde-test."""
    task_id: str
    service_name: str
    code_changes: List[CodeChange]
    deployment_url: str
    has_api_changes: bool
    security_relevant: bool
    performance_relevant: bool
    dependencies: List[str]


@dataclass
class TestingPhaseResult:
    """Result returned to horde-implement."""
    passed: bool
    test_results: TestExecutionResult
    coverage: CoverageReport
    issues: List[TestIssue]
    recommendations: List[str]
    retry_recommended: bool
    quality_score: float  # 0.0 - 1.0
```

---

## 5. Output Format Specification

### 5.1 Test Execution Result

```json
{
  "execution_id": "exec-uuid",
  "plan_id": "plan-uuid",
  "status": "completed",
  "started_at": "2026-02-05T10:00:00Z",
  "completed_at": "2026-02-05T10:15:30Z",
  "duration_seconds": 930,
  "summary": {
    "total_tests": 150,
    "passed": 142,
    "failed": 5,
    "skipped": 2,
    "error": 1,
    "success_rate": 0.947
  },
  "by_type": {
    "unit": { "total": 100, "passed": 98, "failed": 2 },
    "integration": { "total": 40, "passed": 38, "failed": 2 },
    "security": { "total": 10, "passed": 6, "failed": 1, "error": 1 }
  },
  "by_suite": [
    {
      "suite_id": "auth-tests",
      "suite_name": "Authentication Tests",
      "status": "passed",
      "tests": 20,
      "passed": 20,
      "failed": 0,
      "duration_seconds": 45
    }
  ],
  "failures": [
    {
      "test_id": "auth-003",
      "test_name": "Token refresh flow",
      "suite": "auth-tests",
      "type": "integration",
      "status": "failed",
      "duration_seconds": 2.5,
      "error": {
        "type": "AssertionError",
        "message": "Expected status 200, got 401",
        "stack_trace": "..."
      },
      "output": {
        "stdout": "...",
        "stderr": "...",
        "logs": "..."
      },
      "artifacts": [
        {
          "type": "screenshot",
          "path": "s3://.../auth-003-failure.png"
        },
        {
          "type": "har",
          "path": "s3://.../auth-003-network.har"
        }
      ]
    }
  ],
  "coverage": {
    "line_coverage": {
      "percentage": 87.5,
      "covered": 875,
      "total": 1000,
      "required": 80,
      "status": "passed"
    },
    "branch_coverage": {
      "percentage": 82.3,
      "covered": 423,
      "total": 514,
      "required": 70,
      "status": "passed"
    },
    "function_coverage": {
      "percentage": 94.2,
      "covered": 98,
      "total": 104,
      "required": 90,
      "status": "passed"
    },
    "uncovered_lines": [
      {
        "file": "src/auth/service.py",
        "lines": [45, 46, 78, 79, 80],
        "function": "refresh_token"
      }
    ]
  },
  "performance": {
    "tests": [
      {
        "test_id": "perf-001",
        "metrics": {
          "p50_response_time_ms": 45,
          "p95_response_time_ms": 120,
          "p99_response_time_ms": 250,
          "requests_per_second": 850,
          "error_rate": 0.001
        },
        "thresholds": {
          "p95_response_time_ms": {
            "expected": 200,
            "actual": 120,
            "status": "passed"
          }
        }
      }
    ]
  },
  "security": {
    "scanners": [
      {
        "tool": "owasp-zap",
        "findings": [
          {
            "severity": "medium",
            "title": "X-Content-Type-Options header missing",
            "description": "...",
            "url": "https://api.example.com/v2/users",
            "remediation": "Add X-Content-Type-Options: nosniff header"
          }
        ]
      }
    ]
  },
  "insights": {
    "trends": [
      {
        "type": "improvement",
        "metric": "test_execution_time",
        "change": "-15%",
        "description": "Test execution time improved by 15% compared to last run"
      }
    ],
    "recommendations": [
      {
        "priority": "high",
        "category": "coverage",
        "message": "Increase branch coverage for auth/service.py:refresh_token",
        "action": "Add tests for token expiration edge cases"
      },
      {
        "priority": "medium",
        "category": "performance",
        "message": "Consider caching for user profile endpoint",
        "action": "Implement Redis caching for /users/{id}/profile"
      }
    ],
    "risk_assessment": {
      "level": "low",
      "factors": [
        "Core authentication tests passing",
        "Security scan shows only low-severity issues",
        "Performance within acceptable thresholds"
      ]
    }
  }
}
```

### 5.2 Report Generation

```python
class ReportGenerator:
    """Generates test reports in various formats."""

    def generate(
        self,
        result: TestExecutionResult,
        format_type: str,
        options: ReportOptions
    ) -> Report:
        """Generate report in specified format."""

        generators = {
            "json": self._generate_json,
            "html": self._generate_html,
            "junit": self._generate_junit,
            "markdown": self._generate_markdown,
            "pdf": self._generate_pdf
        }

        generator = generators.get(format_type)
        if not generator:
            raise ValueError(f"Unsupported format: {format_type}")

        return generator(result, options)

    def _generate_html(self, result: TestExecutionResult, options: ReportOptions) -> Report:
        """Generate interactive HTML report."""

        template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Report - {{ result.plan_id }}</title>
            <style>
                :root {
                    --color-success: #28a745;
                    --color-failure: #dc3545;
                    --color-warning: #ffc107;
                    --color-info: #17a2b8;
                }
                .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
                .metric-card { padding: 1rem; border-radius: 8px; text-align: center; }
                .metric-card.success { background: var(--color-success); color: white; }
                .metric-card.failure { background: var(--color-failure); color: white; }
                .test-list { margin-top: 2rem; }
                .test-item { padding: 1rem; border-bottom: 1px solid #eee; }
                .test-item.failed { border-left: 4px solid var(--color-failure); }
                .test-item.passed { border-left: 4px solid var(--color-success); }
                .coverage-bar { height: 20px; background: #eee; border-radius: 10px; }
                .coverage-fill { height: 100%; border-radius: 10px; }
                .coverage-fill.passed { background: var(--color-success); }
                .coverage-fill.failed { background: var(--color-failure); }
            </style>
        </head>
        <body>
            <header>
                <h1>Test Execution Report</h1>
                <p>Plan: {{ result.plan_id }}</p>
                <p>Executed: {{ result.started_at }}</p>
            </header>

            <section class="summary">
                <div class="metric-card {{ 'success' if result.summary.success_rate >= 0.9 else 'failure' }}">
                    <h2>{{ "%.1f"|format(result.summary.success_rate * 100) }}%</h2>
                    <p>Success Rate</p>
                </div>
                <div class="metric-card success">
                    <h2>{{ result.summary.passed }}</h2>
                    <p>Passed</p>
                </div>
                <div class="metric-card {{ 'failure' if result.summary.failed > 0 else 'success' }}">
                    <h2>{{ result.summary.failed }}</h2>
                    <p>Failed</p>
                </div>
                <div class="metric-card info">
                    <h2>{{ result.duration_seconds // 60 }}m {{ result.duration_seconds % 60 }}s</h2>
                    <p>Duration</p>
                </div>
            </section>

            <section class="coverage">
                <h2>Coverage</h2>
                {% for type, cov in result.coverage.items() %}
                <div class="coverage-item">
                    <label>{{ type.replace('_', ' ').title() }}: {{ cov.percentage }}%</label>
                    <div class="coverage-bar">
                        <div class="coverage-fill {{ 'passed' if cov.status == 'passed' else 'failed' }}"
                             style="width: {{ cov.percentage }}%"></div>
                    </div>
                </div>
                {% endfor %}
            </section>

            <section class="test-list">
                <h2>Test Results</h2>
                {% for suite in result.by_suite %}
                <div class="suite">
                    <h3>{{ suite.suite_name }}</h3>
                    {% for test in suite.tests %}
                    <div class="test-item {{ test.status }}">
                        <span class="status-icon">{{ '✓' if test.status == 'passed' else '✗' }}</span>
                        <span class="test-name">{{ test.test_name }}</span>
                        <span class="duration">{{ test.duration_seconds }}s</span>
                        {% if test.status == 'failed' %}
                        <div class="error-details">
                            <pre>{{ test.error.message }}</pre>
                        </div>
                        {% endif %}
                    </div>
                    {% endfor %}
                </div>
                {% endfor %}
            </section>

            <section class="recommendations">
                <h2>Recommendations</h2>
                <ul>
                    {% for rec in result.insights.recommendations %}
                    <li class="priority-{{ rec.priority }}">
                        <strong>[{{ rec.priority.upper() }}]</strong> {{ rec.message }}
                    </li>
                    {% endfor %}
                </ul>
            </section>
        </body>
        </html>
        """

        return Report(
            format="html",
            content=Template(template).render(result=result),
            content_type="text/html"
        )
```

---

## 6. Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1)

- [ ] Test Plan Parser implementation
- [ ] Dependency Analyzer implementation
- [ ] Basic Test Scheduler
- [ ] horde-swarm integration layer

### Phase 2: Subagent Development (Week 2)

- [ ] `testing:unit-tester` subagent
- [ ] `testing:integration-tester` subagent
- [ ] `testing:e2e-tester` subagent
- [ ] `testing:performance-engineer` subagent

### Phase 3: Advanced Testing (Week 3)

- [ ] `security-auditor` integration
- [ ] `testing:contract-validator` subagent
- [ ] `testing:chaos-engineer` subagent
- [ ] Result Aggregator implementation

### Phase 4: Integration & Reporting (Week 4)

- [ ] horde-implement Phase 6 integration
- [ ] Report generation (HTML, JSON, JUnit)
- [ ] Coverage analysis integration
- [ ] Notification system

### Phase 5: Optimization (Week 5)

- [ ] Intelligent test parallelization
- [ ] Test result caching
- [ ] Incremental test execution
- [ ] Performance optimization

---

## 7. Usage Examples

### Example 1: Basic Test Execution

```python
# Invoke horde-test skill
result = await skills.invoke(
    skill="horde-test",
    action="execute",
    parameters={
        "plan": {
            "target": {
                "type": "api",
                "url": "https://api.example.com"
            },
            "test_suites": [
                {
                    "type": "integration",
                    "tests": [
                        {"name": "Health check", "endpoint": "/health"}
                    ]
                }
            ]
        }
    }
)
```

### Example 2: Integration with horde-implement

```python
# Inside horde-implement Phase 6
testing_result = await skills.invoke(
    skill="horde-test",
    action="validate_implementation",
    parameters={
        "implementation": implementation_result,
        "requirements": {
            "unit_tests": True,
            "integration_tests": True,
            "coverage_targets": {"line": 80, "branch": 70}
        }
    }
)

if not testing_result["passed"]:
    return ImplementationStatus.NEEDS_FIX,
           testing_result["recommendations"]
```

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Test Execution Time | -50% vs sequential | Compare parallel vs sequential |
| Coverage Accuracy | >95% | Compare reported vs actual coverage |
| False Positive Rate | <5% | Manual review of failed tests |
| horde-implement Integration | <30s overhead | Time to generate and execute test plan |
| Report Generation | <5s | Time to generate all formats |

---

## 9. Related Documents

- [horde-swarm architecture](./horde-swarm-ultimate-vision.md)
- [swarm-orchestrator proposal](./swarm-orchestrator-proposal.md)
- [swarm-synthesizer proposal](../swarm-synthesizer-proposal.md)
- [kurultai_0.2.md](./kurultai_0.2.md) - Capability acquisition
- [neo4j.md](./neo4j.md) - Operational memory

---

*Document Version: 1.0.0*
*Date: 2026-02-05*
*Author: Backend System Architect*
