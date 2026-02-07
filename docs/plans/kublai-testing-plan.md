# Kublai Testing Plan - Comprehensive Multi-Agent System Test Coverage

## Overview

This prompt is designed to be executed with a **subagent swarm** to design and implement a comprehensive testing plan for the Kublai multi-agent orchestrator system. The testing plan must cover all intended functionalities and architecture specified in:
- `docs/plans/neo4j.md` - 6-agent OpenClaw system with Neo4j operational memory
- `docs/plans/kurultai_0.1.md` - Task Dependency Engine with DAG orchestration

## Prompt for Subagent Swarm

---

**You are a Senior Test Architect tasked with designing a comprehensive testing plan for the Kublai multi-agent orchestrator system.**

### Context

Kublai is the **main orchestrator agent** in a 6-agent OpenClaw system with Neo4j-backed operational memory:

**Agent Architecture:**
1. **Kublai (main)** - Central orchestrator, receives all user messages, delegates to specialists
2. **Möngke (researcher)** - Research and investigation tasks
3. **Chagatai (writer)** - Writing and content creation
4. **Temüjin (developer)** - Code, development, security audits
5. **Jochi (analyst)** - Analysis, metrics, patterns
6. **Ögedei (ops)** - Operations, deployment, emergency failover for Kublai

**Core Systems:**
- **OperationalMemory** (`openclaw_memory.py`) - Neo4j-backed task lifecycle, notifications, rate limiting, agent heartbeat
- **DelegationProtocol** (`tools/delegation_protocol.py`) - Agent routing, privacy sanitization, task delegation
- **Multi-Goal Orchestration** (`tools/multi_goal_orchestration.py`) - DAG-based task dependency engine with relationship detection
- **FailoverMonitor** (`tools/failover_monitor.py`) - Kublai health monitoring with Ögedei failover

### Your Task

Design a **comprehensive testing plan** using **Tasks (TodoWrite)** and a **subagent swarm approach**. The plan should:

1. **Map all testable functionalities** from both neo4j.md and kurultai_0.1.md
2. **Organize tests by type** (unit, integration, E2E, performance, security)
3. **Assign test suites to specialized subagents** based on expertise
4. **Define test dependencies** using Tasks with `blocks` relationships
5. **Specify test coverage targets** and acceptance criteria

### Requirements

#### 1. Test Coverage Matrix

Create a test coverage matrix that maps:
- **Phases from neo4j.md** (Phases 1-11) to test suites
- **Components from kurultai_0.1.md** (DAG, dependency detection, Notion sync) to test scenarios

Key areas to cover:
- Agent routing and delegation logic
- Privacy sanitization (PII patterns)
- Neo4j operations (CRUD, transactions, fallback mode)
- Failover and recovery
- DAG construction and validation
- Relationship detection (semantic similarity, keyword-based)
- Priority command handling
- Intent window buffering
- Notion integration
- Rate limiting
- Session isolation
- agentToAgent messaging

#### 2. Subagent Swarm Architecture

Define subagent specializations:
- **Unit Test Agent** - Component isolation tests
- **Integration Test Agent** - Cross-component workflow tests
- **Contract Test Agent** - API/interface compatibility tests
- **Performance Test Agent** - Load, latency, scalability tests
- **Security Test Agent** - PII sanitization, auth, injection tests
- **Chaos Test Agent** - Failure injection, recovery tests

#### 3. Task-Based Organization

Use TodoWrite Tasks to create a hierarchical test plan:
- Parent task: "Comprehensive Kublai Testing Suite"
- Child tasks for each test suite
- `blocks` relationships for dependencies (e.g., "Integration tests" blocked by "Unit tests pass")
- Metadata tags for test type, component, priority

#### 4. Test Implementation Patterns

Specify test patterns for:
- **Mocking Neo4j** - Use in-memory Neo4j or mocks for unit tests
- **Agent Simulation** - Simulate agent responses for delegation tests
- **DAG Fixtures** - Create reusable test DAGs for orchestration tests
- **Privacy Test Data** - PII samples for sanitization validation
- **Failure Scenarios** - Network failures, Neo4j downtime, agent crashes

#### 5. Existing Test Analysis

Build upon existing tests in:
- `tests/test_delegation_protocol.py` - 934 lines, comprehensive delegation tests
- `tests/test_pre_flight.py` - Environment, Neo4j, auth, agent checks
- `tests/test_failover_monitor.py` - Failover and heartbeat tests

Identify gaps in current coverage and extend accordingly.

#### 6. kurultai_0.1.md Specific Tests

Design tests for the Task Dependency Engine:
- Intent window buffering (30-60 second windows)
- Semantic similarity thresholds (0.75 high, 0.55 medium)
- Relationship type detection (blocks, feeds_into, parallel_ok, synergistic)
- Topological sorting with priority handling
- Unified vs streaming delivery modes
- Notion sync with safe reconciliation
- Natural language priority commands

#### 7. Neo4j Schema Validation

Tests must validate the complete Neo4j schema:
- Node types: Agent, Task, Research, Content, Application, Analysis, ProcessUpdate, Notification, SessionContext, SignalSession, SyncEvent, FailoverEvent, RateLimit, UserConfig, AgentResponseRoute, AgentHeartbeat
- Relationship types: CREATED, ASSIGNED_TO, RESPONDS_VIA, DEPENDS_ON, PART_OF, ROUTES_TO, BLOCKS, FEEDS_INTO, PARALLEL_OK, MERGED_INTO
- Indexes and constraints
- Cypher query correctness

#### 8. Output Format

Your response should include:

**Section 1: Test Coverage Matrix**
- Table mapping functionalities to test types
- Coverage percentage targets

**Section 2: Subagent Task Definitions**
- TodoWrite Task definitions for each test suite
- Dependencies (blocks relationships)
- Assignments to subagent types

**Section 3: Test Suite Specifications**
For each test suite:
- Test class name and file location
- Test methods with descriptions
- Fixtures required
- Expected assertions
- Edge cases covered

**Section 4: Integration Test Scenarios**
- End-to-end workflow descriptions
- Multi-agent interaction sequences
- State transitions to validate

**Section 5: Performance Test Specifications**
- Load patterns (concurrent users, message rates)
- Latency thresholds (P50, P95, P99)
- Scalability targets

**Section 6: Security Test Specifications**
- PII patterns to test
- Injection attempts (Cypher, command)
- Authentication/authorization scenarios

**Section 7: Test Infrastructure Requirements**
- Test Neo4j instance configuration
- Mock agents setup
- Test data fixtures
- CI/CD integration approach

### Deliverables

1. **A complete test plan** that can be executed by a subagent swarm
2. **TodoWrite Task definitions** for organizing test execution
3. **pytest test file specifications** with test methods and assertions
4. **Test data fixtures** for privacy, DAGs, and agent scenarios
5. **Coverage targets** and success criteria

### Important Notes

- Tests should be **deterministic** and **isolated**
- Use **pytest** with **fixtures** for reusable components
- Mock external dependencies (Neo4j, Signal, Notion API)
- Follow existing test patterns in `tests/test_*.py`
- Include both **happy path** and **error case** tests
- Test **fallback mode** behavior when Neo4j is unavailable
- Validate **thread safety** for concurrent operations
- Include **property-based tests** where applicable (e.g., sanitization)

---

## Execution Instructions for Subagent Swarm

When executing this prompt:

1. **Spawn parallel subagents** for each test suite type
2. Each subagent should:
   - Read the relevant source code files
   - Design comprehensive tests for their area
   - Output pytest-compatible test files
   - Create TodoWrite Tasks for their test suite
3. **Coordinator agent** should:
   - Resolve dependencies between test suites
   - Ensure no duplicate test coverage
   - Generate final test execution plan
   - Provide coverage report

## Key Files to Analyze

- `tools/delegation_protocol.py` (1244 lines)
- `openclaw_memory.py` (OperationalMemory class)
- `tools/multi_goal_orchestration.py` (1875 lines)
- `tools/failover_monitor.py`
- `docs/plans/neo4j.md` (all phases and appendices)
- `docs/plans/kurultai_0.1.md` (Task Dependency Engine specs)
- `tests/test_*.py` (existing test patterns)
