# Task Specification - Agent Harness Integration Completion

**Task ID:** TASK-002  
**Created:** 2026-03-03 00:20 EST  
**Assigned To:** Temüjin  
**Priority:** CRITICAL  
**Estimated Time:** 45 minutes  

---

## Overview

Complete the remaining 5% of Agent Harness implementation by integrating hooks into the workflow, updating all agents' AGENTS.md files, and running end-to-end tests.

**Current Status:** 95% Complete  
**Remaining:** Integration, AGENTS.md updates, testing

---

## What This Task Does

Completes the Agent Harness implementation by:
1. Integrating hooks into hourly_reflection.sh
2. Updating all 6 agents' AGENTS.md files
3. Running end-to-end tests to verify everything works

---

## Integration Points

- **Depends On:** Hook scripts (pre-commit.sh, pre-deploy.sh, post-task.sh)
- **Affects:** scripts/hourly_reflection.sh, all agents' AGENTS.md files
- **Integrates With:** Neo4j logging, git workflow

---

## Requirements

### Functional Requirements
- [ ] pre-commit.sh called before git commits in hourly_reflection.sh
- [ ] post-task.sh called after task completion in hourly_reflection.sh
- [ ] All 6 agents' AGENTS.md files reference hooks and specs
- [ ] End-to-end test passes (full workflow executes without errors)

### Non-Functional Requirements
- [ ] Performance: <2s overhead from hooks
- [ ] Security: No hardcoded secrets
- [ ] Reliability: Graceful failure handling (hooks missing = warning, not error)

---

## Edge Cases
- [ ] Hook scripts missing → Skip with warning (don't fail)
- [ ] Neo4j unavailable → Log to file instead
- [ ] Validation fails → Block with clear error message
- [ ] Permission denied on hooks → Auto-fix with chmod +x

---

## Acceptance Criteria
- [ ] hourly_reflection.sh calls pre-commit.sh before commits
- [ ] hourly_reflection.sh calls post-task.sh after tasks
- [ ] All 6 agents' AGENTS.md files updated with hooks documentation
- [ ] End-to-end test passes (full workflow executes)
- [ ] Neo4j logging verified working
- [ ] All hooks execute successfully

---

## Test Plan

### Unit Tests
- [ ] Test pre-commit.sh with valid files (should pass)
- [ ] Test pre-commit.sh with syntax errors (should fail)
- [ ] Test post-task.sh Neo4j logging (should log successfully)

### Integration Tests
- [ ] Run full hourly_reflection.sh workflow
- [ ] Verify hooks are called at correct points
- [ ] Verify Neo4j TaskCompletion nodes created
- [ ] Verify CHANGELOG.md updated

### Validation
```bash
# Test 1: Run hourly_reflection.sh with hooks
bash /Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh

# Test 2: Verify Neo4j logging
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
with driver.session() as session:
    result = session.run('MATCH (t:TaskCompletion) RETURN t ORDER BY t.completed_at DESC LIMIT 1')
    record = result.single()
    if record:
        print(f'✅ Neo4j logging working: {record[\"t\"][\"task_name\"]}')
    else:
        print('❌ Neo4j logging NOT working')
driver.close()
"

# Test 3: Verify CHANGELOG.md updated
grep "Agent Harness" /Users/kublai/.openclaw/agents/main/CHANGELOG.md
```

---

## Definition of Done
- [ ] All acceptance criteria met
- [ ] All tests passing
- [ ] Documentation updated (hooks/README.md)
- [ ] Code reviewed (self-review sufficient)
- [ ] No regressions introduced

---

## Implementation Steps

### Step 1: Integrate Hooks into hourly_reflection.sh (15 min)

**File:** `/Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh`

**Add pre-commit validation** (add after the "Check for git changes" section, before actual commit):

```bash
# ============================================================================
# PRE-COMMIT VALIDATION
# ============================================================================
if [ -f "$WORKSPACE/hooks/pre-commit.sh" ]; then
    echo "Running pre-commit validation..."
    if ! "$WORKSPACE/hooks/pre-commit.sh"; then
        echo "❌ Pre-commit validation FAILED"
        exit 1
    fi
    echo "✅ Pre-commit validation PASSED"
else
    echo "⚠️  pre-commit.sh not found (skipping validation)"
fi
```

**Add post-task logging** (add at the end of the script, before the final "Done" message):

```bash
# ============================================================================
# POST-TASK LOGGING
# ============================================================================
if [ -f "$WORKSPACE/hooks/post-task.sh" ]; then
    echo "Logging task completion..."
    "$WORKSPACE/hooks/post-task.sh" "Hourly Reflection" "Complete"
else
    echo "⚠️  post-task.sh not found (skipping logging)"
fi
```

**Testing:**
```bash
# Test the updated script
bash /Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh --dry-run 2>&1 | grep -E "(pre-commit|post-task|✅|❌)"
```

---

### Step 2: Update All Agents' AGENTS.md (20 min)

**Files:** All 6 agents' AGENTS.md files

**Add this section to EACH agent's AGENTS.md** (add after the "Model Configuration" section):

```markdown
## Agent Harness Tools

### Hooks
All agents should use the automated hooks:

- **pre-commit.sh**: Run before committing code
  ```bash
  ./hooks/pre-commit.sh
  ```
  Validates: Python/Bash syntax, hardcoded secrets, large files

- **pre-deploy.sh**: Run before deploying
  ```bash
  ./hooks/pre-deploy.sh
  ```
  Validates: Neo4j connectivity, environment variables, disk space

- **post-task.sh**: Run after completing tasks
  ```bash
  ./hooks/post-task.sh "Task Name" "Complete"
  ```
  Logs to: Neo4j (TaskCompletion nodes) + CHANGELOG.md

### Spec Templates
Use spec templates for all new work:

- **Task Spec**: `specs/task-spec-template.md`
- **Feature Spec**: `specs/feature-spec-template.md`
- **Bug Fix Spec**: `specs/bug-fix-spec-template.md`

### Examples
See `specs/examples/` for example specs.

### Documentation
Full documentation: `hooks/README.md`
```

**Files to Update:**
1. `/Users/kublai/.openclaw/agents/main/AGENTS.md` (Kublai)
2. `/Users/kublai/.openclaw/agents/mongke/AGENTS.md` (Möngke)
3. `/Users/kublai/.openclaw/agents/chagatai/AGENTS.md` (Chagatai)
4. `/Users/kublai/.openclaw/agents/temujin/AGENTS.md` (Temüjin)
5. `/Users/kublai/.openclaw/agents/jochi/AGENTS.md` (Jochi)
6. `/Users/kublai/.openclaw/agents/ogedei/AGENTS.md` (Ögedei)

**Verification:**
```bash
# Verify all 6 agents have hooks documentation
for agent in main mongke chagatai temujin jochi ogedei; do
    if grep -q "hooks/" /Users/kublai/.openclaw/agents/$agent/AGENTS.md; then
        echo "✅ $(basename $agent): Updated"
    else
        echo "❌ $(basename $agent): NOT updated"
    fi
done
```

---

### Step 3: End-to-End Testing (15 min)

**Test Full Workflow:**

```bash
cd /Users/kublai/.openclaw/agents/main

echo "=== END-TO-END TEST ==="
echo ""

# 1. Create a test task spec
echo "Creating test task spec..."
cp specs/examples/task-example.md specs/test-task-e2e.md

# 2. Make a code change
echo "Making code change..."
echo "# Test change for agent harness" >> TEST.md
git add TEST.md

# 3. Run pre-commit hook
echo "Running pre-commit hook..."
./hooks/pre-commit.sh
if [ $? -eq 0 ]; then
    echo "✅ Pre-commit PASSED"
else
    echo "❌ Pre-commit FAILED"
    exit 1
fi

# 4. Commit the change
echo "Committing change..."
git commit -m "Test: Agent harness E2E test"

# 5. Run post-task hook
echo "Running post-task hook..."
./hooks/post-task.sh "Agent Harness E2E Test" "Complete"

# 6. Verify Neo4j logging
echo "Verifying Neo4j logging..."
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
with driver.session() as session:
    result = session.run('MATCH (t:TaskCompletion) WHERE t.task_name CONTAINS \"E2E\" RETURN t ORDER BY t.completed_at DESC LIMIT 1')
    record = result.single()
    if record:
        print(f'✅ Neo4j logging working: {record[\"t\"][\"task_name\"]}')
    else:
        print('❌ Neo4j logging NOT working')
driver.close()
"

# 7. Verify CHANGELOG.md updated
echo "Verifying CHANGELOG.md..."
if grep -q "Agent Harness E2E" CHANGELOG.md; then
    echo "✅ CHANGELOG.md updated"
else
    echo "⚠️  CHANGELOG.md NOT updated"
fi

# Cleanup
rm TEST.md
git reset --hard HEAD~1
rm specs/test-task-e2e.md

echo ""
echo "=== E2E TEST COMPLETE ==="
```

**Acceptance Criteria:**
- [ ] Pre-commit hook executes and passes
- [ ] Git commit succeeds
- [ ] Post-task hook executes
- [ ] Neo4j TaskCompletion node created
- [ ] CHANGELOG.md updated
- [ ] Cleanup successful

---

## Timeline

| Step | Estimated Time | Priority |
|------|---------------|----------|
| Step 1: Integrate hooks | 15 min | CRITICAL |
| Step 2: Update AGENTS.md | 20 min | HIGH |
| Step 3: E2E testing | 15 min | CRITICAL |
| **TOTAL** | **50 minutes** | |

---

## Resources

- **Hook Scripts:** `/Users/kublai/.openclaw/agents/main/hooks/`
- **Spec Templates:** `/Users/kublai/.openclaw/agents/main/specs/`
- **Example Specs:** `/Users/kublai/.openclaw/agents/main/specs/examples/`
- **Documentation:** `/Users/kublai/.openclaw/agents/main/hooks/README.md`
- **Review Document:** `/Users/kublai/.openclaw/agents/main/shared-context/AGENT-HARNESS-REVIEW.md`
- **Task Spec:** `/Users/kublai/.openclaw/agents/main/specs/agent-harness-phase2-spec.md`

---

## Definition of Done

- [ ] All 3 steps complete
- [ ] All acceptance criteria met
- [ ] All tests passing
- [ ] All 6 agents' AGENTS.md updated
- [ ] End-to-end test passing
- [ ] Neo4j logging verified

---

**Assigned By:** Kublai  
**Assigned To:** Temüjin  
**Due Date:** 2026-03-03 (early morning)  
**Priority:** CRITICAL
