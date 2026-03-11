# Implementation Plan: Test Routing Feature Enhancement

## Objective Statement

**Clarification**: The task "test routing: implement new feature" with source "test-cli" is interpreted as: **Implement a CLI tool for testing and validating the Kurultai task routing system**.

This tool will allow developers and operators to:
- Test routing decisions without creating actual tasks
- Validate routing rules and disambiguation logic
- Audit routing behavior for debugging
- Generate routing test reports

## Phase 1: Requirements Analysis and Design

### Task 1.1: Analyze existing routing infrastructure
**Description**: Document current routing behavior, edge cases, and validation points.

**Actions**:
- Review `/Users/kublai/.openclaw/agents/main/scripts/task_intake.py` routing logic
- Document `AGENT_KEYWORDS`, `_DISAMBIGUATION`, `SKILL_HINTS` tables
- Analyze `route_by_text()` function behavior
- Review existing routing test cases in `/Users/kublai/.openclaw/agents/main/scripts/tests/test_routing_benchmarks.py`

**Exit Criteria Phase 1**:
- [ ] Routing logic documented with key functions identified
- [ ] Edge cases catalogued (mention routing, disambiguation conflicts, load balancing)
- [ ] Test scenarios defined from `routing-test-prompts.md`

### Task 1.2: Define CLI interface specification
**Description**: Design the CLI commands and output format.

**Proposed CLI Structure**:
```bash
# Test routing for a specific task description
python3 test_routing.py --title "Fix the login bug" --agent expected-temujin

# Batch test from prompts file
python3 test_routing.py --batch-file routing-test-prompts.md

# Compare routing results across agents
python3 test_routing.py --compare --title "Research security vulnerabilities"

# Full routing audit with report
python3 test_routing.py --audit --output routing-audit-report.json

# Dry-run mode (no task creation)
python3 test_routing.py --dry-run --title "Deploy to production"
```

**Output Format**:
```json
{
  "input": "Fix the login bug",
  "routed_to": "temujin",
  "expected": "temujin",
  "match": true,
  "confidence": 0.95,
  "method": "keyword_match",
  "disambiguation_triggered": false,
  "overflow_applied": false,
  "skill_hint": "/systematic-debugging",
  "domain": "implementation",
  "timestamp": "2026-03-11T02:00:00Z"
}
```

**Exit Criteria Phase 1**:
- [ ] CLI interface specification finalized
- [ ] JSON output schema defined
- [ ] Test scenarios from `routing-test-prompts.md` mapped to expected outputs

---

## Phase 2: Core Implementation

### Task 2.1: Create test_routing.py CLI skeleton
**Description**: Set up the basic CLI structure with argparse.

**File**: `/Users/kublai/.openclaw/agents/main/scripts/test_routing.py`

**Key Components**:
```python
#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from task_intake import route_by_text, detect_skill_hint, classify_task_domain

def test_single_routing(title: str, expected_agent: str = None) -> dict:
    """Test routing for a single task title."""
    result = {
        "input": title,
        "routed_to": None,
        "expected": expected_agent,
        "match": False,
        "confidence": 0,
        "method": None,
        "disambiguation_triggered": False,
        "overflow_applied": False,
        "skill_hint": None,
        "domain": None,
        "timestamp": datetime.now().isoformat()
    }

    # Route the task
    agent = route_by_text(title)
    result["routed_to"] = agent

    # Get skill hint
    skill_hint = detect_skill_hint(agent, title)
    result["skill_hint"] = skill_hint

    # Classify domain
    domain = classify_task_domain(title)
    result["domain"] = domain

    # Check against expected
    if expected_agent:
        result["match"] = (agent == expected_agent)

    return result
```

**Exit Criteria Phase 2.1**:
- [ ] `test_routing.py` created with argparse CLI interface
- [ ] Single routing test functional
- [ ] JSON output format matches specification

### Task 2.2: Implement batch testing mode
**Description**: Add support for running multiple routing tests from a prompts file.

**Key Features**:
- Parse `routing-test-prompts.md` format
- Run all test cases
- Generate summary report with pass/fail counts
- Output JSONL for integration with monitoring

**Exit Criteria Phase 2.2**:
- [ ] Batch mode reads from `routing-test-prompts.md`
- [ ] All 12 test cases from existing prompts file execute
- [ ] Pass/fail summary generated
- [ ] JSONL output compatible with routing audit tools

### Task 2.3: Implement comparison mode
**Description**: Compare routing results when titles are ambiguous.

**Key Features**:
- Show top 3 routing candidates with scores
- Display which disambiguation rules fired
- Show keyword matches per agent
- Recommend routing improvements

**Exit Criteria Phase 2.3**:
- [ ] Comparison mode shows candidate scores
- [ ] Disambiguation rule tracing enabled
- [ ] Keyword match visualization implemented

### Task 2.4: Implement audit mode
**Description**: Full routing audit with queue depth consideration.

**Key Features**:
- Check current queue depths
- Simulate overflow routing
- Validate agent availability
- Generate comprehensive audit report

**Exit Criteria Phase 2.4**:
- [ ] Audit mode checks queue depths via `get_queue_depth()`
- [ ] Overflow simulation functional
- [ ] Audit report includes recommendations

---

## Phase 3: Integration and Testing

### Task 3.1: Integrate with existing routing tests
**Description**: Ensure compatibility with `test_routing_benchmarks.py`.

**Actions**:
- Import routing functions without duplicating logic
- Reuse `AGENT_KEYWORDS` and `_DISAMBIGUATION` tables
- Align with existing test patterns

**Exit Criteria Phase 3.1**:
- [ ] No code duplication with `task_intake.py`
- [ ] Existing tests still pass
- [ ] New CLI produces same results as existing benchmarks

### Task 3.2: Create validation test suite
**Description**: Test the test tool itself.

**File**: `/Users/kublai/.openclaw/agents/main/scripts/tests/test_routing_cli.py`

**Test Cases**:
- Test single routing with known inputs
- Test batch mode parsing
- Test comparison mode output
- Test audit mode accuracy
- Test JSON output schema validation

**Exit Criteria Phase 3.2**:
- [ ] Unit tests pass for all CLI modes
- [ ] Schema validation tests pass
- [ ] Edge cases handled (empty input, @mentions, unknown agents)

### Task 3.3: Update jochi routing check script
**Description**: Extend `jochi_routing_check.py` to use new CLI.

**Actions**:
- Add `test_routing.py` invocation to proactive audit
- Parse JSON output for violation detection
- Enhance violation reporting with CLI results

**Exit Criteria Phase 3.3**:
- [ ] `jochi_routing_check.py` calls `test_routing.py`
- [ ] Violation detection enhanced with CLI data
- [ ] Report format improved

---

## Phase 4: Documentation and Deployment

### Task 4.1: Create documentation
**Description**: Document CLI usage and integration points.

**Files**:
- `/Users/kublai/.openclaw/agents/main/docs/routing-cli-guide.md`
- Update `/Users/kublai/.openclaw/agents/main/docs/routing-test-prompts.md`

**Content**:
- CLI usage examples
- Integration with cron jobs
- Troubleshooting guide

**Exit Criteria Phase 4.1**:
- [ ] CLI guide created
- [ ] Examples cover all modes
- [ ] Integration documented

### Task 4.2: Add to system monitoring
**Description**: Integrate with kurultai-monitor for routing health.

**Actions**:
- Add routing audit to health checks
- Track routing accuracy metrics
- Alert on routing failures

**Exit Criteria Phase 4.2**:
- [ ] Routing metrics in kurultai-monitor
- [ ] Alert rules defined
- [ ] Health check includes routing status

### Task 4.3: Deploy and validate
**Description**: Deploy to production and verify operation.

**Actions**:
- Run full audit on production system
- Verify no regressions in routing behavior
- Update source="test-cli" to use new CLI

**Exit Criteria Phase 4.3**:
- [ ] Production audit passes
- [ ] Routing accuracy >= 95%
- [ ] No new routing errors introduced

---

## Dependencies

**Phase 1** depends on: None (can start immediately)

**Phase 2** depends on:
- Phase 1 complete (requirements known)
- Existing `task_intake.py` unchanged (API compatibility)

**Phase 3** depends on:
- Phase 2 complete (CLI implemented)

**Phase 4** depends on:
- Phase 3 complete (tested and validated)

---

## Success Criteria

1. **Functional**:
   - CLI correctly predicts routing for all 12 test cases in `routing-test-prompts.md`
   - Accuracy >= 95% on benchmark tests
   - Performance: < 100ms per routing decision

2. **Integration**:
   - Compatible with existing `task_intake.py` API
   - Output consumable by `jochi_routing_check.py`
   - No breaking changes to routing logic

3. **Quality**:
   - Test coverage > 80% for new code
   - Documentation complete
   - Zero regressions in existing routing behavior

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Routing logic changes may break existing behavior | Import from `task_intake.py` without modifying it |
| CLI performance issues | Cache agent keywords, use efficient data structures |
| Ambiguous test cases lead to false failures | Add confidence scores and manual review flag |
| Integration conflicts with jochi's audit tools | Coordinate with jochi agent, use standard JSON format |

---

### Critical Files for Implementation

- **/Users/kublai/.openclaw/agents/main/scripts/task_intake.py** - Core routing logic to import and reuse (AGENT_KEYWORDS, _DISAMBIGUATION, route_by_text, detect_skill_hint, classify_task_domain)
- **/Users/kublai/.openclaw/agents/main/scripts/tests/test_routing_benchmarks.py** - Existing test patterns to follow for consistency
- **/Users/kublai/.openclaw/agents/main/docs/routing-test-prompts.md** - Test cases to validate against (12 scenarios with expected routing)
- **/Users/kublai/.openclaw/agents/jochi/workspace/jochi_routing_check.py** - Integration point for proactive routing audits
- **/Users/kublai/.openclaw/agents/main/AGENTS.md** - Source of truth for routing rules and agent domains
