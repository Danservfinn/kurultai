# Routing CLI Guide

**Date:** 2026-03-11
**Tool:** `test_routing.py`
**Location:** `/Users/kublai/.openclaw/agents/main/scripts/test_routing.py`

---

## Overview

The Routing CLI provides comprehensive testing and validation for the Kurultai task routing system. It validates that tasks are routed to the correct agents based on keywords, skill hints, and disambiguation rules.

**Key Features:**
- Single task routing validation
- Batch testing from markdown test cases
- Agent candidate comparison with scoring
- Comprehensive routing audit with queue depths
- JSON/JSONL output formats

---

## Installation

No installation required. The CLI imports directly from `task_intake.py`:

```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 test_routing.py --help
```

---

## Modes

### 1. Single Test Mode

Test routing for a single task title.

```bash
python3 test_routing.py --title "Fix the login bug" --expected jochi
```

**Output:**
```json
{
  "input": "Fix the login bug",
  "routed_to": "jochi",
  "expected": "jochi",
  "match": true,
  "skill_hint": "/code-reviewer",
  "domain": "analysis",
  "timestamp": "2026-03-11T06:21:05Z"
}
```

**Exit codes:** `0` if match, `1` if mismatch

---

### 2. Batch Mode

Parse `routing-test-prompts.md` and run all test cases.

```bash
python3 test_routing.py --batch-file docs/routing-test-prompts.md
```

**Output:** JSON with summary and detailed results

```json
{
  "summary": {
    "total": 12,
    "passed": 9,
    "failed": 3,
    "pass_rate": 75.0,
    "failures_by_agent": {
      "ogedei": [5],
      "Decompose": [10],
      "kublai": [12]
    }
  },
  "results": [...]
}
```

**Exit codes:** `0` if all pass, `1` if any failures

---

### 3. Compare Mode

Show top 3 agent candidates with keyword match scores.

```bash
python3 test_routing.py --compare "Research competitors and design API"
```

**Output:**
```json
{
  "input": "Research competitors and design API",
  "routed_to": "temujin",
  "top_candidates": [
    {"agent": "temujin", "score": 3, "matched_keywords": ["design", "api", "build"]},
    {"agent": "mongke", "score": 1, "matched_keywords": ["research"]},
    {"agent": "jochi", "score": 1, "matched_keywords": ["test"]}
  ],
  "disambiguation": "Rule: research + design -> temujin"
}
```

---

### 4. Audit Mode

Comprehensive routing audit with queue depths.

```bash
python3 test_routing.py --audit
```

**Output:**
```json
{
  "timestamp": "2026-03-11T06:21:05Z",
  "routing_version": "keyword_router",
  "valid_agents": ["chagatai", "jochi", "kublai", "mongke", "ogedei", "temujin", "tolui"],
  "queue_depths": {
    "jochi": 3,
    "temujin": 5,
    "mongke": 2
  },
  "test_results": {
    "summary": {...},
    "details": [...]
  }
}
```

---

## Arguments

| Argument | Short | Description | Mode |
|----------|-------|-------------|------|
| `--title` | `-t` | Task title to route | Single |
| `--expected` | `-e` | Expected agent (for validation) | Single |
| `--batch-file` | `-b` | Path to routing-test-prompts.md | Batch |
| `--compare` | `-c` | Show top 3 candidates for this title | Compare |
| `--audit` | `-a` | Run comprehensive audit | Audit |
| `--output` | `-o` | Output file path (JSON format) | All |
| `--jsonl` | | Output JSONL format (batch mode only) | Batch |

---

## Output Formats

### JSON (default)

Structured JSON with full details. Use with `--output` to save to file.

```bash
python3 test_routing.py --title "Test task" --output results.json
```

### JSONL (batch mode)

One JSON object per line for streaming processing.

```bash
python3 test_routing.py --batch-file docs/routing-test-prompts.md --jsonl > results.jsonl
```

---

## Integration with Cron Jobs

### Example Cron Entry

Run routing tests every hour and log results:

```cron
0 * * * * cd /Users/kublai/.openclaw/agents/main/scripts && python3 test_routing.py --batch-file ../docs/routing-test-prompts.md --output ../logs/routing-test-$(date +\%Y\%m\%d\%H\%M).json >> ../logs/routing-test.log 2>&1
```

### Example: Alert on Failure

```bash
#!/bin/bash
# routing-test-cron.sh
cd /Users/kublai/.openclaw/agents/main/scripts

RESULT=$(python3 test_routing.py --batch-file ../docs/routing-test-prompts.md 2>&1)
if echo "$RESULT" | grep -q "failed.*[1-9]"; then
    echo "$RESULT" | mail -s "Routing test failed" admin@example.com
fi
```

---

## Integration with Jochi

The `jochi_routing_check.py` script now integrates with the CLI:

```bash
# Run jochi routing check with routing tests
python3 ~/.openclaw/agents/jochi/workspace/jochi_routing_check.py --with-routing-tests
```

This provides:
- Git commit analysis for routing changes
- skill_hint flow validation
- AGENTS.md alignment checks
- Routing test execution via CLI

---

## Test Case Format

Batch mode parses markdown files in this format:

```markdown
### 1. temujin (BUILD)
> Build a REST API endpoint for user authentication with JWT tokens

**Expected:** temujin | **Skill hint:** none

### 2. mongke (RESEARCH)
> Research competitor pricing models for AI-powered media analysis platforms

**Expected:** mongke | **Skill hint:** /horde-learn
```

---

## Troubleshooting

### Import Error

If you see `ImportError: No module named 'task_intake'`, ensure you're running from the scripts directory:

```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 test_routing.py --help
```

### Empty Test Cases

If batch mode reports "No test cases found", check your markdown format matches the expected pattern above.

### Expected Failures

Some test failures are expected edge cases:
- **Test #5 (ogedei):** "Redis service is down" - keyword router picks dominant keyword
- **Test #10 (Decompose):** Multi-domain tasks require LLM-based decomposition
- **Test #12 (kublai):** Coordination tasks require kublai-level routing

These are documented in `docs/routing-test-prompts.md` under "Results".

---

## Source of Truth

All routing logic is in `task_intake.py`. The CLI imports and tests:

- `route_by_text()` - Core routing function
- `detect_skill_hint()` - Skill hint auto-detection
- `classify_task_domain()` - Domain classification
- `AGENT_KEYWORDS` - Keyword routing table
- `_DISAMBIGUATION` - Conflict resolution rules

No routing logic is duplicated in the CLI.

---

## Related Documentation

- `docs/routing-test-prompts.md` - Test case definitions and results
- `scripts/task_intake.py` - Core routing implementation
- `agents/jochi/workspace/jochi_routing_check.py` - Proactive routing audit
