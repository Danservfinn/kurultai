# horde-test Skill Design Document

## Executive Summary

The `horde-test` skill is a distributed testing orchestration system built on `horde-swarm` that executes comprehensive testing plans across multiple test types (unit, integration, e2e, performance, security, accessibility). It leverages parallel subagent dispatch with intelligent result aggregation and failure handling.

---

## 1. Test Type Patterns

### 1.1 Unit Tests

**Purpose**: Validate individual functions, classes, and modules in isolation.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `python-development:python-pro` | Core test implementation | 2-3 |
| `python-development:tdd-orchestrator` | Test strategy & coverage | 1 |
| `python-development:pytest-specialist` | Pytest configuration & fixtures | 1 |

**Task Dispatch Pattern**:
```python
# Parallel dispatch for unit test generation
unit_test_tasks = [
    Task(
        subagent_type="python-development:python-pro",
        prompt="""
        Generate comprehensive unit tests for module: {module_path}

        Focus:
        - Test all public functions and methods
        - Cover edge cases (empty inputs, None, boundary values)
        - Mock external dependencies
        - Use pytest with descriptive test names

        Output format:
        1. Test file content (Python code)
        2. Coverage report target: >90%
        3. List of tested functions
        4. Edge cases covered
        """,
        expected_output={
            "test_file_content": "str",
            "coverage_target": "float",
            "tested_functions": "List[str]",
            "edge_cases": "List[str]"
        }
    ),
    Task(
        subagent_type="python-development:tdd-orchestrator",
        prompt="""
        Design test strategy for: {module_path}

        Analyze:
        - Critical code paths requiring coverage
        - Dependency injection points for mocking
        - Test data requirements
        - Fixture design patterns

        Output:
        1. Test strategy document
        2. Recommended test structure
        3. Mock requirements
        4. Coverage priorities
        """,
        expected_output={
            "strategy": "dict",
            "test_structure": "str",
            "mock_requirements": "List[str]",
            "coverage_priorities": "List[str]"
        }
    )
]

# Execute in parallel
results = await horde_swarm.dispatch_parallel(unit_test_tasks)
```

**Expected Outputs**:
- Test files with pytest-compatible code
- Coverage reports (target: >90% for unit tests)
- Mock/stub configurations
- Test data fixtures

---

### 1.2 Integration Tests

**Purpose**: Validate interactions between components, APIs, and services.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `backend-development:backend-architect` | API contract validation | 1 |
| `backend-development:api-tester` | Endpoint testing | 2 |
| `database:db-specialist` | Database integration | 1 |
| `devops:container-specialist` | Service orchestration | 1 |

**Task Dispatch Pattern**:
```python
integration_tasks = [
    Task(
        subagent_type="backend-development:backend-architect",
        prompt="""
        Design integration test suite for service: {service_name}

        Components to test:
        - API endpoints and their interactions
        - Database layer integration
        - External service mocks
        - Event/message queue flows

        Deliver:
        1. Integration test plan
        2. Service dependency graph
        3. Test environment specification
        4. Contract validation tests
        """,
        expected_output={
            "test_plan": "dict",
            "dependency_graph": "mermaid",
            "environment_spec": "dict",
            "contract_tests": "List[dict]"
        }
    ),
    Task(
        subagent_type="backend-development:api-tester",
        prompt="""
        Implement API integration tests for: {api_endpoints}

        Test scenarios:
        - Happy path requests
        - Error handling (4xx, 5xx)
        - Authentication/authorization flows
        - Rate limiting behavior
        - Request/response schema validation

        Tools: pytest, requests/httpx, jsonschema

        Output:
        1. Test implementation
        2. Test data fixtures
        3. Expected response schemas
        """,
        expected_output={
            "test_code": "str",
            "fixtures": "dict",
            "schemas": "dict"
        }
    ),
    Task(
        subagent_type="database:db-specialist",
        prompt="""
        Create database integration tests for: {service_name}

        Coverage:
        - Migration tests
        - Transaction rollback behavior
        - Connection pooling
        - Query performance baselines
        - Data integrity constraints

        Output:
        1. DB test fixtures
        2. Migration test suite
        3. Performance benchmarks
        """,
        expected_output={
            "fixtures": "str",
            "migration_tests": "str",
            "benchmarks": "List[dict]"
        }
    )
]
```

**Expected Outputs**:
- API contract tests
- Database integration tests
- Service orchestration configs
- Docker Compose test environment

---

### 1.3 E2E Tests

**Purpose**: Validate complete user workflows from UI through backend.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `frontend-mobile-development:frontend-developer` | UI automation | 2 |
| `qa:automation-engineer` | Test flow design | 1 |
| `qa:test-strategist` | E2E strategy | 1 |

**Task Dispatch Pattern**:
```python
e2e_tasks = [
    Task(
        subagent_type="qa:test-strategist",
        prompt="""
        Design E2E test strategy for application: {app_name}

        Define:
        - Critical user journeys (CUJs)
        - Page object model structure
        - Browser/device matrix
        - Test data management approach
        - Environment requirements

        Output:
        1. CUJ documentation
        2. Page object hierarchy
        3. Browser support matrix
        4. Test environment spec
        """,
        expected_output={
            "cujs": "List[dict]",
            "page_objects": "dict",
            "browser_matrix": "dict",
            "environment": "dict"
        }
    ),
    Task(
        subagent_type="frontend-mobile-development:frontend-developer",
        prompt="""
        Implement E2E tests using Playwright for: {cuj_list}

        Requirements:
        - Page Object Model pattern
        - Visual regression checks
        - Network interception for API mocking
        - Screenshot on failure
        - Parallel execution support

        Output:
        1. Page object classes
        2. Test specifications
        3. Configuration files
        4. CI/CD integration scripts
        """,
        expected_output={
            "page_objects": "str",
            "tests": "str",
            "config": "dict",
            "ci_scripts": "str"
        }
    ),
    Task(
        subagent_type="qa:automation-engineer",
        prompt="""
        Build E2E test execution framework for: {app_name}

        Features:
        - Test data seeding/cleanup
        - Environment provisioning
        - Parallel test runner
        - Result aggregation
        - Video recording on failure

        Output:
        1. Test runner implementation
        2. Docker Compose for test env
        3. Reporting dashboard config
        """,
        expected_output={
            "runner": "str",
            "docker_compose": "str",
            "reporting": "dict"
        }
    )
]
```

**Expected Outputs**:
- Playwright/Cypress test suites
- Page Object Model implementations
- Test environment configurations
- Video recordings of test runs

---

### 1.4 Performance Tests

**Purpose**: Validate system performance under load and identify bottlenecks.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `python-development:python-pro` | Load test scripts | 1 |
| `devops:performance-engineer` | Performance analysis | 1 |
| `devops:sre` | Infrastructure monitoring | 1 |
| `backend-development:backend-architect` | Optimization recommendations | 1 |

**Task Dispatch Pattern**:
```python
performance_tasks = [
    Task(
        subagent_type="devops:performance-engineer",
        prompt="""
        Design performance test plan for: {service_name}

        Define:
        - Load patterns (steady, spike, ramp-up)
        - Performance SLAs (p50, p95, p99 latencies)
        - Throughput targets (RPS)
        - Resource utilization thresholds
        - Scenarios to test

        Output:
        1. Performance test plan
        2. Load pattern specifications
        3. SLA definitions
        4. Resource monitoring plan
        """,
        expected_output={
            "test_plan": "dict",
            "load_patterns": "List[dict]",
            "slas": "dict",
            "monitoring_plan": "dict"
        }
    ),
    Task(
        subagent_type="python-development:python-pro",
        prompt="""
        Implement Locust/k6 performance tests for: {endpoints}

        Test scenarios:
        - Baseline load (expected traffic)
        - Stress test (2x expected)
        - Spike test (10x for 1 minute)
        - Soak test (4 hours sustained)

        Include:
        - Realistic user behavior simulation
        - Parameterized test data
        - Custom metrics collection
        - Failure condition handling

        Output:
        1. Locustfile/k6 script
        2. Test data generators
        3. Custom metrics definitions
        """,
        expected_output={
            "script": "str",
            "test_data": "str",
            "metrics": "List[dict]"
        }
    ),
    Task(
        subagent_type="devops:sre",
        prompt="""
        Set up performance monitoring for test execution

        Configure:
        - Application metrics (CPU, memory, GC)
        - Database metrics (query time, connections)
        - Infrastructure metrics (network, disk)
        - Custom business metrics
        - Alert thresholds

        Output:
        1. Grafana dashboards
        2. Prometheus rules
        3. Alertmanager config
        4. Log aggregation queries
        """,
        expected_output={
            "dashboards": "List[dict]",
            "prometheus_rules": "str",
            "alerts": "str",
            "log_queries": "List[str]"
        }
    ),
    Task(
        subagent_type="backend-development:backend-architect",
        prompt="""
        Analyze performance results and provide optimization recommendations

        Review:
        - Bottleneck identification
        - Resource contention points
        - Algorithmic inefficiencies
        - Caching opportunities
        - Database query optimization

        Output:
        1. Bottleneck analysis report
        2. Prioritized optimization list
        3. Architecture recommendations
        4. Performance regression fixes
        """,
        expected_output={
            "bottlenecks": "List[dict]",
            "optimizations": "List[dict]",
            "architecture_changes": "List[str]",
            "fixes": "List[str]"
        }
    )
]
```

**Expected Outputs**:
- Load test scripts (Locust/k6)
- Performance baseline reports
- Bottleneck analysis
- Optimization recommendations
- Grafana dashboards

---

### 1.5 Security Tests

**Purpose**: Identify security vulnerabilities and validate security controls.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `security-auditor` | Vulnerability scanning | 1 |
| `security:penetration-tester` | Penetration testing | 1 |
| `security:code-reviewer` | Security code review | 1 |
| `backend-development:backend-architect` | Secure design review | 1 |

**Task Dispatch Pattern**:
```python
security_tasks = [
    Task(
        subagent_type="security-auditor",
        prompt="""
        Perform automated security scan for: {target_url}

        Scan types:
        - OWASP Top 10 vulnerabilities
        - API security (authentication, authorization)
        - Injection attacks (SQL, NoSQL, Command)
        - XSS and CSRF vulnerabilities
        - Security misconfigurations
        - Sensitive data exposure

        Tools: OWASP ZAP, nuclei, semgrep

        Output:
        1. Vulnerability scan report
        2. Risk severity classification
        3. CWE references
        4. Remediation guidance
        """,
        expected_output={
            "vulnerabilities": "List[dict]",
            "risk_matrix": "dict",
            "cwe_mappings": "dict",
            "remediation": "List[dict]"
        }
    ),
    Task(
        subagent_type="security:penetration-tester",
        prompt="""
        Conduct manual penetration testing for: {application_scope}

        Focus areas:
        - Authentication bypass attempts
        - Session management flaws
        - Privilege escalation paths
        - Business logic vulnerabilities
        - API endpoint abuse
        - File upload vulnerabilities

        Output:
        1. Penetration test report
        2. Exploitation evidence
        3. Attack chain documentation
        4. Remediation priorities
        """,
        expected_output={
            "findings": "List[dict]",
            "evidence": "List[str]",
            "attack_chains": "List[dict]",
            "priorities": "List[str]"
        }
    ),
    Task(
        subagent_type="security:code-reviewer",
        prompt="""
        Perform security-focused code review for: {codebase_path}

        Review for:
        - Hardcoded secrets/credentials
        - Insecure cryptographic practices
        - Input validation gaps
        - Insecure deserialization
        - Race conditions
        - Logging of sensitive data

        Output:
        1. Security code review report
        2. Critical findings with line numbers
        3. Secure coding recommendations
        4. Security unit test suggestions
        """,
        expected_output={
            "findings": "List[dict]",
            "critical_issues": "List[dict]",
            "recommendations": "List[str]",
            "test_suggestions": "List[str]"
        }
    ),
    Task(
        subagent_type="backend-development:backend-architect",
        prompt="""
        Review security architecture for: {application_name}

        Evaluate:
        - Authentication architecture
        - Authorization model (RBAC/ABAC)
        - Data encryption (at rest, in transit)
        - Secrets management
        - Network segmentation
        - Audit logging

        Output:
        1. Architecture security assessment
        2. Design flaw identification
        3. Security control gaps
        4. Compliance mapping (SOC2, ISO27001)
        """,
        expected_output={
            "assessment": "dict",
            "design_flaws": "List[dict]",
            "control_gaps": "List[dict]",
            "compliance_mapping": "dict"
        }
    )
]
```

**Expected Outputs**:
- Vulnerability scan reports
- Penetration test findings
- Security code review results
- Risk severity classifications
- Remediation guidance

---

### 1.6 Accessibility Tests

**Purpose**: Ensure application accessibility for users with disabilities.

**Subagent Types Dispatched**:
| Agent Type | Role | Count |
|------------|------|-------|
| `web-accessibility-checker` | Automated a11y scanning | 1 |
| `ux:accessibility-specialist` | Manual WCAG review | 1 |
| `frontend-mobile-development:frontend-developer` | A11y fixes | 1 |

**Task Dispatch Pattern**:
```python
accessibility_tasks = [
    Task(
        subagent_type="web-accessibility-checker",
        prompt="""
        Run automated accessibility audit for: {urls}

        Standards: WCAG 2.1 Level AA

        Check:
        - Color contrast ratios
        - Keyboard navigation
        - Screen reader compatibility
        - Focus management
        - ARIA usage
        - Form labels and error handling
        - Image alt text
        - Heading hierarchy

        Tools: axe-core, Lighthouse, pa11y

        Output:
        1. Accessibility scan results
        2. Violations by severity
        3. WCAG success criteria mapping
        4. Automated fix suggestions
        """,
        expected_output={
            "violations": "List[dict]",
            "severity_breakdown": "dict",
            "wcag_mapping": "dict",
            "fix_suggestions": "List[dict]"
        }
    ),
    Task(
        subagent_type="ux:accessibility-specialist",
        prompt="""
        Perform manual accessibility review for: {application_name}

        Manual checks:
        - Screen reader flow (NVDA, JAWS, VoiceOver)
        - Keyboard-only navigation
        - Zoom and reflow (200%, 400%)
        - Cognitive accessibility
        - Motion sensitivity
        - Alternative text quality
        - Error identification and recovery

        Output:
        1. Manual audit report
        2. User experience issues
        3. Assistive technology compatibility
        4. Remediation recommendations
        """,
        expected_output={
            "audit_report": "dict",
            "ux_issues": "List[dict]",
            "compatibility_matrix": "dict",
            "recommendations": "List[str]"
        }
    ),
    Task(
        subagent_type="frontend-mobile-development:frontend-developer",
        prompt="""
        Implement accessibility improvements for: {component_list}

        Fixes:
        - ARIA attributes and roles
        - Keyboard event handlers
        - Focus indicators
        - Skip links
        - Live regions
        - Error announcements

        Output:
        1. Updated component code
        2. Accessibility test cases
        3. Documentation updates
        4. Before/after comparison
        """,
        expected_output={
            "code_changes": "List[dict]",
            "test_cases": "str",
            "documentation": "str",
            "comparison": "dict"
        }
    )
]
```

**Expected Outputs**:
- WCAG compliance reports
- Automated and manual audit results
- Accessibility remediation code
- Screen reader compatibility matrix

---

## 2. Swarm Compositions by Test Type

### 2.1 Composition Matrix

```python
TEST_TYPE_COMPOSITIONS = {
    "unit": {
        "agents": [
            {"type": "python-development:python-pro", "count": 3, "role": "test_implementer"},
            {"type": "python-development:tdd-orchestrator", "count": 1, "role": "strategy_lead"},
            {"type": "python-development:pytest-specialist", "count": 1, "role": "fixture_expert"}
        ],
        "execution_pattern": "parallel",
        "synthesis_strategy": "merge_coverage"
    },

    "integration": {
        "agents": [
            {"type": "backend-development:backend-architect", "count": 1, "role": "design_lead"},
            {"type": "backend-development:api-tester", "count": 2, "role": "endpoint_tester"},
            {"type": "database:db-specialist", "count": 1, "role": "db_tester"},
            {"type": "devops:container-specialist", "count": 1, "role": "env_manager"}
        ],
        "execution_pattern": "sequential_with_parallel_subtasks",
        "synthesis_strategy": "dependency_aware_merge"
    },

    "e2e": {
        "agents": [
            {"type": "qa:test-strategist", "count": 1, "role": "strategy_lead"},
            {"type": "frontend-mobile-development:frontend-developer", "count": 2, "role": "test_implementer"},
            {"type": "qa:automation-engineer", "count": 1, "role": "framework_builder"}
        ],
        "execution_pattern": "parallel_with_coordination",
        "synthesis_strategy": "cuj_coverage_merge"
    },

    "performance": {
        "agents": [
            {"type": "devops:performance-engineer", "count": 1, "role": "test_designer"},
            {"type": "python-development:python-pro", "count": 1, "role": "script_developer"},
            {"type": "devops:sre", "count": 1, "role": "monitoring_lead"},
            {"type": "backend-development:backend-architect", "count": 1, "role": "optimization_advisor"}
        ],
        "execution_pattern": "sequential_phases",
        "synthesis_strategy": "metric_aggregation"
    },

    "security": {
        "agents": [
            {"type": "security-auditor", "count": 1, "role": "scanner_operator"},
            {"type": "security:penetration-tester", "count": 1, "role": "manual_tester"},
            {"type": "security:code-reviewer", "count": 1, "role": "code_analyst"},
            {"type": "backend-development:backend-architect", "count": 1, "role": "design_reviewer"}
        ],
        "execution_pattern": "parallel_with_cross_validation",
        "synthesis_strategy": "risk_based_consolidation"
    },

    "accessibility": {
        "agents": [
            {"type": "web-accessibility-checker", "count": 1, "role": "automated_scanner"},
            {"type": "ux:accessibility-specialist", "count": 1, "role": "manual_reviewer"},
            {"type": "frontend-mobile-development:frontend-developer", "count": 1, "role": "fix_implementer"}
        ],
        "execution_pattern": "sequential",
        "synthesis_strategy": "wcag_compliance_merge"
    }
}
```

### 2.2 Dynamic Composition Logic

```python
class TestSwarmComposer:
    """
    Dynamically composes agent teams based on test requirements.
    """

    def compose_for_test_type(
        self,
        test_type: str,
        codebase_context: CodebaseContext,
        constraints: TestConstraints
    ) -> AgentTeam:
        """
        Compose optimal agent team for test type.
        """
        base_composition = TEST_TYPE_COMPOSITIONS[test_type]

        # Adjust based on codebase characteristics
        if codebase_context.language == "python":
            base_composition = self._adjust_for_python(base_composition)
        elif codebase_context.language == "javascript":
            base_composition = self._adjust_for_javascript(base_composition)

        # Scale based on codebase size
        if codebase_context.lines_of_code > 100000:
            base_composition = self._scale_up(base_composition, factor=1.5)

        # Add specialized agents for detected frameworks
        for framework in codebase_context.frameworks:
            base_composition = self._add_framework_specialist(
                base_composition, framework
            )

        return AgentTeam(
            agents=self._instantiate_agents(base_composition),
            execution_pattern=base_composition["execution_pattern"],
            synthesis_strategy=base_composition["synthesis_strategy"]
        )

    def _adjust_for_python(self, composition: dict) -> dict:
        """Adjust composition for Python-specific testing."""
        composition["agents"].append({
            "type": "python-development:pytest-specialist",
            "count": 1,
            "role": "pytest_expert"
        })
        return composition

    def _add_framework_specialist(
        self,
        composition: dict,
        framework: str
    ) -> dict:
        """Add framework-specific testing specialist."""
        framework_agents = {
            "django": "python-development:django-tester",
            "fastapi": "python-development:fastapi-tester",
            "react": "frontend-mobile-development:react-tester",
            "vue": "frontend-mobile-development:vue-tester"
        }

        if framework in framework_agents:
            composition["agents"].append({
                "type": framework_agents[framework],
                "count": 1,
                "role": f"{framework}_specialist"
            })

        return composition
```

---

## 3. Test Result Aggregation

### 3.1 Result Collection Architecture

```python
@dataclass
class TestResult:
    """Unified test result structure."""
    test_type: str
    agent_id: str
    status: TestStatus  # PASSED, FAILED, SKIPPED, ERROR
    duration_ms: int
    coverage: Optional[CoverageReport]
    failures: List[FailureDetail]
    metadata: Dict[str, Any]


class ResultAggregator:
    """
    Aggregates test results from multiple agents into unified report.
    """

    async def aggregate_results(
        self,
        results: List[TestResult],
        aggregation_strategy: str
    ) -> AggregatedTestReport:
        """
        Aggregate results using specified strategy.
        """
        strategies = {
            "merge_coverage": self._merge_coverage_results,
            "dependency_aware_merge": self._dependency_aware_merge,
            "cuj_coverage_merge": self._cuj_coverage_merge,
            "metric_aggregation": self._metric_aggregation,
            "risk_based_consolidation": self._risk_based_consolidation,
            "wcag_compliance_merge": self._wcag_compliance_merge
        }

        strategy_fn = strategies.get(
            aggregation_strategy,
            self._default_aggregation
        )

        return await strategy_fn(results)

    def _merge_coverage_results(
        self,
        results: List[TestResult]
    ) -> AggregatedTestReport:
        """
        Merge coverage results from multiple unit test agents.
        """
        # Combine coverage data
        combined_coverage = CoverageReport()
        all_failures = []
        total_duration = 0

        for result in results:
            if result.coverage:
                combined_coverage.merge(result.coverage)
            all_failures.extend(result.failures)
            total_duration += result.duration_ms

        # Calculate overall metrics
        line_coverage = combined_coverage.line_rate
        branch_coverage = combined_coverage.branch_rate

        # Deduplicate failures
        unique_failures = self._deduplicate_failures(all_failures)

        return AggregatedTestReport(
            test_type="unit",
            overall_status="PASSED" if not unique_failures else "FAILED",
            line_coverage=line_coverage,
            branch_coverage=branch_coverage,
            total_tests=combined_coverage.total_statements,
            passed_tests=combined_coverage.covered_statements,
            failed_tests=len(unique_failures),
            duration_ms=total_duration,
            failures=unique_failures,
            coverage_report=combined_coverage
        )

    def _metric_aggregation(
        self,
        results: List[TestResult]
    ) -> AggregatedTestReport:
        """
        Aggregate performance metrics from load tests.
        """
        metrics = {
            "latency_p50": [],
            "latency_p95": [],
            "latency_p99": [],
            "throughput_rps": [],
            "error_rate": [],
            "cpu_usage": [],
            "memory_usage": []
        }

        for result in results:
            for metric_name in metrics:
                if metric_name in result.metadata:
                    metrics[metric_name].append(result.metadata[metric_name])

        # Calculate aggregates
        aggregated = {}
        for metric_name, values in metrics.items():
            if values:
                aggregated[metric_name] = {
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.mean(values),
                    "median": statistics.median(values)
                }

        # Check SLA compliance
        sla_violations = self._check_sla_compliance(aggregated)

        return AggregatedTestReport(
            test_type="performance",
            overall_status="PASSED" if not sla_violations else "FAILED",
            metrics=aggregated,
            sla_violations=sla_violations,
            duration_ms=sum(r.duration_ms for r in results)
        )

    def _risk_based_consolidation(
        self,
        results: List[TestResult]
    ) -> AggregatedTestReport:
        """
        Consolidate security findings by risk level.
        """
        all_findings = []

        for result in results:
            if "findings" in result.metadata:
                all_findings.extend(result.metadata["findings"])

        # Group by severity
        by_severity = defaultdict(list)
        for finding in all_findings:
            by_severity[finding["severity"]].append(finding)

        # Deduplicate similar findings
        unique_findings = self._deduplicate_security_findings(all_findings)

        # Calculate risk score
        risk_weights = {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 2, "LOW": 1}
        risk_score = sum(
            risk_weights.get(f["severity"], 0)
            for f in unique_findings
        )

        return AggregatedTestReport(
            test_type="security",
            overall_status="FAILED" if by_severity.get("CRITICAL") else "PASSED",
            risk_score=risk_score,
            findings_by_severity=dict(by_severity),
            total_findings=len(unique_findings),
            critical_count=len(by_severity.get("CRITICAL", [])),
            high_count=len(by_severity.get("HIGH", [])),
            findings=unique_findings
        )
```

### 3.2 Coverage Calculation

```python
class CoverageCalculator:
    """
    Calculate overall test coverage across all test types.
    """

    def calculate_overall_coverage(
        self,
        test_results: Dict[str, AggregatedTestReport]
    ) -> OverallCoverage:
        """
        Calculate weighted overall coverage.
        """
        coverage_dimensions = {
            "code_coverage": self._calculate_code_coverage(test_results),
            "api_coverage": self._calculate_api_coverage(test_results),
            "flow_coverage": self._calculate_flow_coverage(test_results),
            "scenario_coverage": self._calculate_scenario_coverage(test_results),
            "risk_coverage": self._calculate_risk_coverage(test_results),
            "compliance_coverage": self._calculate_compliance_coverage(test_results)
        }

        # Weight by test type importance
        weights = {
            "unit": 0.25,
            "integration": 0.25,
            "e2e": 0.20,
            "performance": 0.15,
            "security": 0.10,
            "accessibility": 0.05
        }

        weighted_score = sum(
            coverage_dimensions[dim] * weight
            for dim, weight in weights.items()
        )

        return OverallCoverage(
            overall_score=weighted_score,
            dimensions=coverage_dimensions,
            gaps=self._identify_coverage_gaps(coverage_dimensions),
            recommendations=self._generate_recommendations(coverage_dimensions)
        )

    def _calculate_code_coverage(
        self,
        results: Dict[str, AggregatedTestReport]
    ) -> float:
        """Calculate code coverage from unit and integration tests."""
        unit_coverage = results.get("unit", {}).coverage_report.line_rate or 0
        integration_coverage = results.get("integration", {}).coverage_report.line_rate or 0

        # Weight unit tests higher for code coverage
        return unit_coverage * 0.7 + integration_coverage * 0.3

    def _calculate_api_coverage(
        self,
        results: Dict[str, AggregatedTestReport]
    ) -> float:
        """Calculate API endpoint coverage."""
        integration_results = results.get("integration")
        if not integration_results:
            return 0.0

        tested_endpoints = integration_results.metadata.get("tested_endpoints", [])
        total_endpoints = integration_results.metadata.get("total_endpoints", 1)

        return len(tested_endpoints) / total_endpoints
```

### 3.3 Failure Prioritization

```python
class FailurePrioritizer:
    """
    Prioritize test failures for remediation.
    """

    def prioritize_failures(
        self,
        failures: List[FailureDetail],
        codebase_context: CodebaseContext
    ) -> List[PrioritizedFailure]:
        """
        Prioritize failures based on multiple factors.
        """
        prioritized = []

        for failure in failures:
            score = self._calculate_priority_score(failure, codebase_context)
            prioritized.append(PrioritizedFailure(
                failure=failure,
                priority_score=score,
                category=self._categorize_failure(failure)
            ))

        # Sort by priority score (descending)
        prioritized.sort(key=lambda x: x.priority_score, reverse=True)

        return prioritized

    def _calculate_priority_score(
        self,
        failure: FailureDetail,
        context: CodebaseContext
    ) -> float:
        """
        Calculate priority score (0-100).
        """
        score = 0.0

        # Base severity weight
        severity_weights = {
            "CRITICAL": 40,
            "HIGH": 30,
            "MEDIUM": 20,
            "LOW": 10
        }
        score += severity_weights.get(failure.severity, 10)

        # Impact on critical paths
        if failure.affects_critical_path:
            score += 25

        # Frequency of occurrence (flaky tests lower priority)
        if failure.is_flaky:
            score -= 15

        # Code ownership (prefer failures in core modules)
        if failure.module in context.core_modules:
            score += 15

        # Security test failures get bonus
        if failure.test_type == "security":
            score += 10

        # Performance regression magnitude
        if failure.test_type == "performance":
            score += min(failure.regression_percentage / 2, 20)

        return max(0, min(100, score))

    def _categorize_failure(self, failure: FailureDetail) -> str:
        """Categorize failure type."""
        if "assertion" in failure.error_type.lower():
            return "ASSERTION_FAILURE"
        elif "timeout" in failure.error_type.lower():
            return "TIMEOUT"
        elif "exception" in failure.error_type.lower():
            return "EXCEPTION"
        elif "vulnerability" in failure.error_type.lower():
            return "SECURITY_VULNERABILITY"
        else:
            return "UNKNOWN"
```

---

## 4. Failure Handling

### 4.1 Failure Detection and Response

```python
class FailureHandler:
    """
    Handles test failures with intelligent debugging and retry logic.
    """

    async def handle_failures(
        self,
        failures: List[FailureDetail],
        test_context: TestContext
    ) -> FailureResolution:
        """
        Handle test failures with appropriate response strategy.
        """
        resolutions = []

        for failure in failures:
            # Determine failure type
            failure_type = self._classify_failure(failure)

            # Select response strategy
            if failure_type == "FLAKY":
                resolution = await self._handle_flaky_test(failure, test_context)
            elif failure_type == "REGRESSION":
                resolution = await self._handle_regression(failure, test_context)
            elif failure_type == "ENVIRONMENT":
                resolution = await self._handle_environment_failure(failure, test_context)
            elif failure_type == "CODE_DEFECT":
                resolution = await self._handle_code_defect(failure, test_context)
            else:
                resolution = await self._handle_unknown_failure(failure, test_context)

            resolutions.append(resolution)

        return FailureResolution(
            resolutions=resolutions,
            retry_plan=self._build_retry_plan(resolutions),
            requires_human_attention=self._needs_escalation(resolutions)
        )

    def _classify_failure(self, failure: FailureDetail) -> str:
        """Classify failure type based on patterns."""
        # Check for flaky test patterns
        if self._is_flaky_pattern(failure):
            return "FLAKY"

        # Check for regression patterns
        if failure.previous_pass and failure.current_fail:
            return "REGRESSION"

        # Check for environment issues
        if any(pattern in failure.error_message for pattern in [
            "Connection refused",
            "Timeout",
            "Network error",
            "Service unavailable"
        ]):
            return "ENVIRONMENT"

        # Check for code defects
        if any(pattern in failure.error_message for pattern in [
            "AssertionError",
            "ValueError",
            "TypeError",
            "KeyError"
        ]):
            return "CODE_DEFECT"

        return "UNKNOWN"
```

### 4.2 Debugging Agent Dispatch

```python
class DebuggingOrchestrator:
    """
    Dispatches debugging agents for failed tests.
    """

    async def dispatch_debugging_agents(
        self,
        failure: FailureDetail,
        test_context: TestContext
    ) -> DebugResult:
        """
        Dispatch appropriate debugging agents based on failure type.
        """
        debug_tasks = []

        # Root cause analysis agent
        debug_tasks.append(Task(
            subagent_type="debugging:root-cause-analyzer",
            prompt=f"""
            Analyze root cause for test failure:

            Test: {failure.test_name}
            Error: {failure.error_message}
            Stack trace: {failure.stack_trace}

            Perform:
            1. Stack trace analysis
            2. Code path reconstruction
            3. State change identification
            4. Hypothesis generation

            Output:
            - Root cause hypothesis (ranked by likelihood)
            - Supporting evidence
            - Recommended fix approach
            """,
            expected_output={"root_cause": "dict", "confidence": "float"}
        ))

        # Code fix agent (if code defect suspected)
        if failure.failure_type == "CODE_DEFECT":
            debug_tasks.append(Task(
                subagent_type="python-development:python-pro",
                prompt=f"""
                Propose fix for failing test:

                Test: {failure.test_name}
                Error: {failure.error_message}
                Failing code: {failure.failing_code}

                Provide:
                1. Fix implementation
                2. Explanation of the fix
                3. Potential side effects
                4. Additional test cases needed
                """,
                expected_output={"fix": "str", "explanation": "str"}
            ))

        # Environment diagnostic agent
        if failure.failure_type == "ENVIRONMENT":
            debug_tasks.append(Task(
                subagent_type="devops:sre",
                prompt=f"""
                Diagnose environment issue:

                Test: {failure.test_name}
                Error: {failure.error_message}
                Environment: {test_context.environment}

                Check:
                1. Service health status
                2. Network connectivity
                3. Resource availability
                4. Configuration correctness

                Output:
                - Environment diagnostic report
                - Recommended remediation
                - Prevention measures
                """,
                expected_output={"diagnostic": "dict", "remediation": "str"}
            ))

        # Execute debugging agents in parallel
        debug_results = await horde_swarm.dispatch_parallel(debug_tasks)

        return DebugResult(
            root_cause=debug_results[0].root_cause,
            proposed_fix=debug_results[1].fix if len(debug_results) > 1 else None,
            environment_fix=debug_results[2].remediation if len(debug_results) > 2 else None
        )
```

### 4.3 Flaky Test Handling

```python
class FlakyTestHandler:
    """
    Detects and handles flaky tests with retry strategies.
    """

    async def handle_flaky_test(
        self,
        failure: FailureDetail,
        test_context: TestContext
    ) -> FlakyTestResolution:
        """
        Handle potentially flaky test with retry and analysis.
        """
        # Retry with exponential backoff
        retry_results = []
        for attempt in range(1, 4):
            result = await self._retry_test(failure, test_context)
            retry_results.append(result)

            if result.status == "PASSED":
                # Test passed on retry - confirm flakiness
                flakiness_score = self._calculate_flakiness_score(retry_results)

                return FlakyTestResolution(
                    status="CONFIRMED_FLAKEY",
                    flakiness_score=flakiness_score,
                    retry_count=attempt,
                    recommendation=self._generate_flaky_recommendation(
                        failure, flakiness_score
                    )
                )

            await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # All retries failed - likely not flaky
        return FlakyTestResolution(
            status="NOT_FLAKEY",
            recommendation="Treat as genuine failure"
        )

    def _calculate_flakiness_score(
        self,
        retry_results: List[TestResult]
    ) -> float:
        """
        Calculate flakiness score based on retry results.
        """
        passes = sum(1 for r in retry_results if r.status == "PASSED")
        total = len(retry_results)

        # Score based on pass rate variance
        pass_rate = passes / total

        # Higher variance = more flaky
        variance = pass_rate * (1 - pass_rate)

        # Scale to 0-100
        return variance * 100

    def _generate_flaky_recommendation(
        self,
        failure: FailureDetail,
        flakiness_score: float
    ) -> str:
        """Generate recommendation for handling flaky test."""
        if flakiness_score > 70:
            return (
                f"HIGH FLAKINESS ({flakiness_score:.1f}): "
                "Quarantine test and prioritize fix. "
                "Consider: async timing issues, shared state, external dependencies."
            )
        elif flakiness_score > 40:
            return (
                f"MODERATE FLAKINESS ({flakiness_score:.1f}): "
                "Add retry logic and investigate root cause."
            )
        else:
            return (
                f"LOW FLAKINESS ({flakiness_score:.1f}): "
                "Monitor for pattern. May be environmental."
            )
```

### 4.4 Retry Strategies

```python
class RetryStrategyEngine:
    """
    Implements intelligent retry strategies for different failure types.
    """

    RETRY_STRATEGIES = {
        "FLAKY": {
            "max_attempts": 3,
            "backoff": "exponential",
            "base_delay": 2,
            "jitter": True
        },
        "ENVIRONMENT": {
            "max_attempts": 5,
            "backoff": "linear",
            "base_delay": 5,
            "jitter": False
        },
        "TIMEOUT": {
            "max_attempts": 2,
            "backoff": "fixed",
            "base_delay": 10,
            "jitter": False
        },
        "REGRESSION": {
            "max_attempts": 1,  # Don't retry regressions
            "backoff": "none",
            "base_delay": 0,
            "jitter": False
        }
    }

    async def execute_with_retry(
        self,
        test: TestCase,
        failure_type: str
    ) -> RetryResult:
        """
        Execute test with appropriate retry strategy.
        """
        strategy = self.RETRY_STRATEGIES.get(
            failure_type,
            self.RETRY_STRATEGIES["FLAKY"]
        )

        for attempt in range(1, strategy["max_attempts"] + 1):
            try:
                result = await self._execute_test(test)

                if result.status == "PASSED":
                    return RetryResult(
                        status="PASSED",
                        attempts=attempt,
                        was_flaky=(attempt > 1)
                    )

            except Exception as e:
                result = TestResult(status="ERROR", error=e)

            # Calculate delay
            if attempt < strategy["max_attempts"]:
                delay = self._calculate_delay(strategy, attempt)
                await asyncio.sleep(delay)

        return RetryResult(
            status="FAILED",
            attempts=strategy["max_attempts"],
            final_error=result.error
        )

    def _calculate_delay(self, strategy: dict, attempt: int) -> float:
        """Calculate retry delay based on strategy."""
        base = strategy["base_delay"]

        if strategy["backoff"] == "exponential":
            delay = base * (2 ** (attempt - 1))
        elif strategy["backoff"] == "linear":
            delay = base * attempt
        else:
            delay = base

        if strategy["jitter"]:
            delay *= random.uniform(0.8, 1.2)

        return delay
```

---

## 5. Complete Example: horde-test Skill Implementation

```python
# /skills/horde-test/skill.py

from horde_swarm import Task, Swarm
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import asyncio


@dataclass
class TestPlan:
    """Test plan specification."""
    test_types: List[str]
    target_paths: List[str]
    coverage_target: float
    timeout_minutes: int
    parallel_agents: int


@dataclass
class TestExecutionResult:
    """Complete test execution result."""
    test_plan: TestPlan
    overall_status: str
    coverage: OverallCoverage
    results_by_type: Dict[str, AggregatedTestReport]
    failures: List[PrioritizedFailure]
    duration_ms: int
    recommendations: List[str]


class HordeTestSkill:
    """
    horde-test skill for distributed testing using horde-swarm.
    """

    SKILL_NAME = "horde-test"
    SKILL_VERSION = "1.0.0"

    def __init__(self):
        self.swarm = Swarm()
        self.composer = TestSwarmComposer()
        self.aggregator = ResultAggregator()
        self.coverage_calculator = CoverageCalculator()
        self.failure_handler = FailureHandler()

    async def execute(self, test_plan: TestPlan) -> TestExecutionResult:
        """
        Execute comprehensive test plan using horde-swarm.
        """
        start_time = asyncio.get_event_loop().time()

        # Phase 1: Compose agent teams for each test type
        teams = {}
        for test_type in test_plan.test_types:
            teams[test_type] = self.composer.compose_for_test_type(
                test_type=test_type,
                codebase_context=self._analyze_codebase(test_plan.target_paths),
                constraints=TestConstraints(
                    max_agents=test_plan.parallel_agents,
                    timeout_minutes=test_plan.timeout_minutes
                )
            )

        # Phase 2: Dispatch test agents in parallel
        all_results = {}
        for test_type, team in teams.items():
            tasks = self._create_test_tasks(test_type, team, test_plan)
            results = await self.swarm.dispatch_parallel(tasks)
            all_results[test_type] = results

        # Phase 3: Aggregate results by test type
        aggregated = {}
        for test_type, results in all_results.items():
            strategy = TEST_TYPE_COMPOSITIONS[test_type]["synthesis_strategy"]
            aggregated[test_type] = await self.aggregator.aggregate_results(
                results, strategy
            )

        # Phase 4: Calculate overall coverage
        coverage = self.coverage_calculator.calculate_overall_coverage(aggregated)

        # Phase 5: Collect and prioritize failures
        all_failures = []
        for test_type, report in aggregated.items():
            all_failures.extend(report.failures)

        prioritizer = FailurePrioritizer()
        prioritized_failures = prioritizer.prioritize_failures(
            all_failures,
            self._analyze_codebase(test_plan.target_paths)
        )

        # Phase 6: Handle failures
        if prioritized_failures:
            resolution = await self.failure_handler.handle_failures(
                prioritized_failures,
                TestContext(test_plan=test_plan, results=aggregated)
            )

            # Execute retry plan if applicable
            if resolution.retry_plan:
                retry_results = await self._execute_retry_plan(resolution.retry_plan)
                # Merge retry results
                aggregated = self._merge_retry_results(aggregated, retry_results)

        # Phase 7: Generate recommendations
        recommendations = self._generate_recommendations(coverage, prioritized_failures)

        duration_ms = int(
            (asyncio.get_event_loop().time() - start_time) * 1000
        )

        return TestExecutionResult(
            test_plan=test_plan,
            overall_status="PASSED" if not prioritized_failures else "FAILED",
            coverage=coverage,
            results_by_type=aggregated,
            failures=prioritized_failures,
            duration_ms=duration_ms,
            recommendations=recommendations
        )

    def _create_test_tasks(
        self,
        test_type: str,
        team: AgentTeam,
        test_plan: TestPlan
    ) -> List[Task]:
        """Create test tasks based on test type."""
        task_creators = {
            "unit": self._create_unit_test_tasks,
            "integration": self._create_integration_test_tasks,
            "e2e": self._create_e2e_test_tasks,
            "performance": self._create_performance_test_tasks,
            "security": self._create_security_test_tasks,
            "accessibility": self._create_accessibility_test_tasks
        }

        creator = task_creators.get(test_type)
        if not creator:
            raise ValueError(f"Unknown test type: {test_type}")

        return creator(team, test_plan)

    def _create_unit_test_tasks(self, team: AgentTeam, plan: TestPlan) -> List[Task]:
        """Create unit test tasks."""
        tasks = []

        # Distribute modules across python-pro agents
        modules = self._discover_modules(plan.target_paths)
        agents = [a for a in team.agents if a.role == "test_implementer"]

        for i, module in enumerate(modules):
            agent = agents[i % len(agents)]
            tasks.append(Task(
                subagent_type=agent.type,
                prompt=f"""
                Generate unit tests for module: {module}
                Coverage target: {plan.coverage_target}%

                Requirements:
                - Use pytest
                - Mock external dependencies
                - Test edge cases
                - Follow AAA pattern (Arrange-Act-Assert)
                """,
                expected_output={
                    "test_file": "str",
                    "coverage": "float",
                    "tests_count": "int"
                }
            ))

        return tasks

    def _generate_recommendations(
        self,
        coverage: OverallCoverage,
        failures: List[PrioritizedFailure]
    ) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []

        # Coverage-based recommendations
        for dimension, score in coverage.dimensions.items():
            if score < 0.5:
                recommendations.append(
                    f"CRITICAL: {dimension} coverage is {score:.1%}. "
                    f"Prioritize adding {dimension} tests."
                )
            elif score < 0.8:
                recommendations.append(
                    f"IMPROVE: {dimension} coverage is {score:.1%}. "
                    f"Consider expanding {dimension} test suite."
                )

        # Failure-based recommendations
        if failures:
            critical_failures = [f for f in failures if f.priority_score > 80]
            if critical_failures:
                recommendations.append(
                    f"URGENT: {len(critical_failures)} critical failures detected. "
                    f"Address top priority: {critical_failures[0].failure.test_name}"
                )

        return recommendations


# Skill registration
SKILL = HordeTestSkill
```

---

## 6. Integration with Kurultai Skills Marketplace

```yaml
# /skills/horde-test/skill.yaml
name: horde-test
version: 1.0.0
description: Distributed testing orchestration using horde-swarm
author: Kurultai Team
category: testing

inputs:
  - name: test_types
    type: array
    description: List of test types to run
    enum: [unit, integration, e2e, performance, security, accessibility]
    required: true

  - name: target_paths
    type: array
    description: Paths to test
    required: true

  - name: coverage_target
    type: number
    description: Target coverage percentage
    default: 80

  - name: timeout_minutes
    type: number
    description: Maximum execution time
    default: 60

  - name: parallel_agents
    type: number
    description: Maximum parallel agents
    default: 10

outputs:
  - name: overall_status
    type: string
    enum: [PASSED, FAILED]

  - name: coverage
    type: object
    description: Overall coverage metrics

  - name: results_by_type
    type: object
    description: Detailed results per test type

  - name: failures
    type: array
    description: Prioritized list of failures

  - name: recommendations
    type: array
    description: Improvement recommendations

pricing:
  base_cost: 0.10
  per_agent_minute: 0.05

required_agents:
  - python-development:python-pro
  - python-development:tdd-orchestrator
  - backend-development:backend-architect
  - qa:test-strategist
  - devops:performance-engineer
  - security-auditor
  - web-accessibility-checker
```

---

## 7. Summary

The `horde-test` skill provides a comprehensive distributed testing solution:

1. **Test Type Patterns**: Each test type has specialized agent compositions with specific roles and prompts
2. **Swarm Compositions**: Dynamic team composition based on test requirements and codebase characteristics
3. **Result Aggregation**: Intelligent merging of results with coverage calculation and failure prioritization
4. **Failure Handling**: Automated debugging agent dispatch, flaky test detection, and intelligent retry strategies

The skill integrates seamlessly with the Kurultai skills marketplace and leverages the full power of horde-swarm for parallel test execution.
