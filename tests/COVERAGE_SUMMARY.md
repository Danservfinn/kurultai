# Kublai Testing Suite - Coverage Report

Generated: 2026-02-04

## Overall Coverage

| Metric | Value |
|--------|-------|
| **Overall Coverage** | **49.9%** |
| Total Lines | 9,492 |
| Lines Executed | 4,737 |
| Lines Missing | 4,755 |

## Coverage by Module

### Core Modules

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| openclaw_memory | `openclaw_memory.py` | 1,402 | 568 | 834 | 40.5% |
| tools/__init__ | `tools/__init__.py` | 21 | 21 | 0 | 100.0% |

### Agent Tools

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| agent_integration | `tools/agent_integration.py` | 167 | 33 | 134 | 19.8% |
| backend_collaboration | `tools/backend_collaboration.py` | 325 | 289 | 36 | 88.9% |
| background_synthesis | `tools/background_synthesis.py` | 398 | 277 | 121 | 69.6% |
| delegation_protocol | `tools/delegation_protocol.py` | 322 | 276 | 46 | 85.7% |
| error_recovery | `tools/error_recovery.py` | 595 | 428 | 167 | 71.9% |
| failover_monitor | `tools/failover_monitor.py` | 294 | 254 | 40 | 86.4% |
| file_consistency | `tools/file_consistency.py` | 358 | 299 | 59 | 83.5% |
| memory_tools | `tools/memory_tools.py` | 179 | 80 | 99 | 44.7% |
| meta_learning | `tools/meta_learning.py` | 371 | 282 | 89 | 76.0% |
| monitoring | `tools/monitoring.py` | 609 | 492 | 117 | 80.8% |
| notion_integration | `tools/notion_integration.py` | 609 | 492 | 117 | 80.8% |
| reflection_memory | `tools/reflection_memory.py` | 230 | 194 | 36 | 84.3% |

### Kurultai Modules

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| kurultai/__init__ | `tools/kurultai/__init__.py` | 7 | 7 | 0 | 100.0% |
| dependency_analyzer | `tools/kurultai/dependency_analyzer.py` | 84 | 58 | 26 | 69.0% |
| intent_buffer | `tools/kurultai/intent_buffer.py` | 84 | 79 | 5 | 94.0% |
| priority_override | `tools/kurultai/priority_override.py` | 170 | 129 | 41 | 75.9% |
| topological_executor | `tools/kurultai/topological_executor.py` | 103 | 84 | 19 | 81.6% |
| types | `tools/kurultai/types.py` | 87 | 83 | 4 | 95.4% |

### Orchestration

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| multi_goal_orchestration | `tools/multi_goal_orchestration.py` | 733 | 312 | 421 | 42.6% |

### Notion/Parse Integration

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| notion_sync | `tools/notion_sync.py` | 494 | 0 | 494 | 0.0% |
| parse_api_client | `tools/parse_api_client.py` | 241 | 0 | 241 | 0.0% |

### Security Modules

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| security/__init__ | `tools/security/__init__.py` | 7 | 0 | 7 | 0.0% |
| access_control | `tools/security/access_control.py` | 112 | 0 | 112 | 0.0% |
| anonymization | `tools/security/anonymization.py` | 174 | 0 | 174 | 0.0% |
| config | `tools/security/config.py` | 44 | 0 | 44 | 0.0% |
| encryption | `tools/security/encryption.py` | 125 | 0 | 125 | 0.0% |
| example_usage | `tools/security/example_usage.py` | 100 | 0 | 100 | 0.0% |
| injection_prevention | `tools/security/injection_prevention.py` | 196 | 0 | 196 | 0.0% |
| privacy_boundary | `tools/security/privacy_boundary.py` | 97 | 0 | 97 | 0.0% |
| test_security | `tools/security/test_security.py` | 191 | 0 | 191 | 0.0% |
| tokenization | `tools/security/tokenization.py` | 157 | 0 | 157 | 0.0% |

### Test Files (in tools/)

| Module | File | Lines | Executed | Missing | Coverage |
|--------|------|-------|----------|---------|----------|
| test_multi_goal_orchestration | `tools/test_multi_goal_orchestration.py` | 326 | 0 | 326 | 0.0% |
| test_parse_client | `tools/test_parse_client.py` | 80 | 0 | 80 | 0.0% |

## Files with <80% Coverage

The following files need additional test coverage:

### Critical Priority (<50% coverage)

| File | Coverage | Missing Lines |
|------|----------|---------------|
| `tools/notion_sync.py` | 0.0% | 494 lines |
| `tools/parse_api_client.py` | 0.0% | 241 lines |
| `tools/security/__init__.py` | 0.0% | 7 lines |
| `tools/security/access_control.py` | 0.0% | 112 lines |
| `tools/security/anonymization.py` | 0.0% | 174 lines |
| `tools/security/config.py` | 0.0% | 44 lines |
| `tools/security/encryption.py` | 0.0% | 125 lines |
| `tools/security/example_usage.py` | 0.0% | 100 lines |
| `tools/security/injection_prevention.py` | 0.0% | 196 lines |
| `tools/security/privacy_boundary.py` | 0.0% | 97 lines |
| `tools/security/test_security.py` | 0.0% | 191 lines |
| `tools/security/tokenization.py` | 0.0% | 157 lines |
| `tools/test_multi_goal_orchestration.py` | 0.0% | 326 lines |
| `tools/test_parse_client.py` | 0.0% | 80 lines |
| `openclaw_memory.py` | 40.5% | 834 lines |
| `tools/multi_goal_orchestration.py` | 42.6% | 421 lines |
| `tools/memory_tools.py` | 44.7% | 99 lines |
| `tools/agent_integration.py` | 19.8% | 134 lines |

### High Priority (50-79% coverage)

| File | Coverage | Missing Lines |
|------|----------|---------------|
| `tools/background_synthesis.py` | 69.6% | 121 lines |
| `tools/kurultai/dependency_analyzer.py` | 69.0% | 26 lines |
| `tools/error_recovery.py` | 71.9% | 167 lines |
| `tools/kurultai/priority_override.py` | 75.9% | 41 lines |
| `tools/meta_learning.py` | 76.0% | 89 lines |

### Medium Priority (80-89% coverage)

| File | Coverage | Missing Lines |
|------|----------|---------------|
| `tools/delegation_protocol.py` | 85.7% | 46 lines |
| `tools/failover_monitor.py` | 86.4% | 40 lines |
| `tools/file_consistency.py` | 83.5% | 59 lines |
| `tools/reflection_memory.py` | 84.3% | 36 lines |
| `tools/backend_collaboration.py` | 88.9% | 36 lines |
| `tools/kurultai/topological_executor.py` | 81.6% | 19 lines |

### Good Coverage (>=90%)

| File | Coverage |
|------|----------|
| `tools/__init__.py` | 100.0% |
| `tools/kurultai/__init__.py` | 100.0% |
| `tools/kurultai/intent_buffer.py` | 94.0% |
| `tools/kurultai/types.py` | 95.4% |

## Recommendations for Improving Coverage

### Immediate Actions

1. **Security Module Tests**: All security modules have 0% coverage. Priority should be given to:
   - `tools/security/injection_prevention.py` (196 lines)
   - `tools/security/anonymization.py` (174 lines)
   - `tools/security/tokenization.py` (157 lines)
   - `tools/security/encryption.py` (125 lines)

2. **Core Memory Tests**: `openclaw_memory.py` at 40.5% is critical infrastructure that needs comprehensive testing.

3. **Integration Tests**: `notion_sync.py` and `parse_api_client.py` need integration test coverage.

### Short-term Goals

1. **Target 80% coverage** for:
   - `tools/multi_goal_orchestration.py` (currently 42.6%)
   - `tools/memory_tools.py` (currently 44.7%)
   - `tools/agent_integration.py` (currently 19.8%)

2. **Target 90% coverage** for:
   - `tools/background_synthesis.py` (currently 69.6%)
   - `tools/error_recovery.py` (currently 71.9%)
   - `tools/meta_learning.py` (currently 76.0%)

### Test Infrastructure

1. **Move test files**: `tools/test_multi_goal_orchestration.py` and `tools/test_parse_client.py` should be moved to the `tests/` directory.

2. **Mock external dependencies**: Neo4j, Notion API, and Parse API calls should be properly mocked for unit tests.

3. **Separate integration tests**: Ensure integration tests are isolated and don't run during unit test coverage collection.

## Test Results Summary

| Metric | Value |
|--------|-------|
| Tests Passed | 953 |
| Tests Failed | 102 |
| Test Errors | 11 |
| **Total Tests** | **1,066** |

## HTML Coverage Report

A detailed HTML coverage report has been generated at:
`htmlcov/index.html`

Open this file in a browser to see line-by-line coverage details.

## JSON Coverage Data

Raw coverage data is available at:
`coverage.json`
