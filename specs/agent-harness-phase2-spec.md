# Agent Harness Implementation Plan - Phase 2 (Integration)

**Assigned To:** Temüjin (Development Specialist)  
**Created:** 2026-03-02 21:45 EST  
**Priority:** CRITICAL  
**Estimated Time:** 2-3 hours  

---

## Overview

The Agent Harness Phase 1 (files) is 100% complete. However, Phase 2 (integration) is 0% complete. This plan guides you through integrating the hooks and templates into the actual workflow.

**Current Status:**
- ✅ Phase 1 (Files): 36/36 files created
- ❌ Phase 2 (Integration): 0% complete
- ❌ Phase 3 (Adoption): 0% complete

---

## Success Criteria

- [ ] Hooks are called by hourly_reflection.sh
- [ ] All 3 hooks tested and working
- [ ] hooks/README.md created with usage instructions
- [ ] Example specs created for all 3 templates
- [ ] Agents trained on new workflow (AGENTS.md updated)
- [ ] Integration tested end-to-end

---

## Implementation Steps

### Step 1: Integrate Hooks into hourly_reflection.sh (30 min)

**File:** `/Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh`

**Task:** Add hook calls at appropriate points in the reflection workflow.

**Changes Required:**

1. **Add pre-commit validation** (before git commit):
```bash
# Validate before committing
if [ -f "$WORKSPACE/hooks/pre-commit.sh" ]; then
    echo "Running pre-commit validation..."
    "$WORKSPACE/hooks/pre-commit.sh" || {
        echo "❌ Pre-commit validation FAILED"
        exit 1
    }
    echo "✅ Pre-commit validation PASSED"
fi
```

2. **Add post-task logging** (after task completion):
```bash
# Log task completion
if [ -f "$WORKSPACE/hooks/post-task.sh" ]; then
    echo "Logging task completion..."
    "$WORKSPACE/hooks/post-task.sh" "Hourly Reflection" "Complete"
fi
```

3. **Add spec template reference** (when creating new tasks):
```bash
# Reference spec template
echo "For new tasks, use spec template: $WORKSPACE/specs/task-spec-template.md"
```

**Testing:**
```bash
# Test the updated script
bash /Users/kublai/.openclaw/agents/main/scripts/hourly_reflection.sh --dry-run
```

**Acceptance Criteria:**
- [ ] hourly_reflection.sh calls pre-commit.sh before commits
- [ ] hourly_reflection.sh calls post-task.sh after tasks
- [ ] Script references spec templates
- [ ] Script runs without errors
- [ ] All hooks execute successfully

---

### Step 2: Test All Hooks (30 min)

**Files to Test:**
- `hooks/pre-commit.sh`
- `hooks/pre-deploy.sh`
- `hooks/post-task.sh`

**Test pre-commit.sh:**
```bash
cd /Users/kublai/.openclaw/agents/main

# Create test file with syntax error
echo "def broken(" > /tmp/test.py
bash hooks/pre-commit.sh
# Should fail with syntax error

# Create valid test file
echo "def working(): pass" > /tmp/test.py
bash hooks/pre-commit.sh
# Should pass
```

**Test pre-deploy.sh:**
```bash
cd /Users/kublai/.openclaw/agents/main

# Run pre-deploy validation
bash hooks/pre-deploy.sh

# Should check:
# - Neo4j connectivity
# - Environment variables
# - Disk space
# - Uncommitted changes
```

**Test post-task.sh:**
```bash
cd /Users/kublai/.openclaw/agents/main

# Run post-task hook
bash hooks/post-task.sh "Test Task" "Complete"

# Verify Neo4j logging
python3 -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'neo4j'))
with driver.session() as session:
    result = session.run('MATCH (t:TaskCompletion) RETURN t LIMIT 1')
    print(result.single())
driver.close()
"
```

**Acceptance Criteria:**
- [ ] pre-commit.sh detects syntax errors
- [ ] pre-commit.sh passes for valid files
- [ ] pre-deploy.sh checks Neo4j connectivity
- [ ] post-task.sh logs to Neo4j
- [ ] All hooks return correct exit codes

---

### Step 3: Create hooks/README.md (20 min)

**File:** `/Users/kublai/.openclaw/agents/main/hooks/README.md`

**Content:**
```markdown
# Agent Hooks

Automated validation hooks for the Kurultai agent workflow.

## Available Hooks

### pre-commit.sh
Validates code before committing.

**Checks:**
- Python syntax errors
- Bash syntax errors
- Hardcoded secrets
- Large files
- TODO/FIXME comments

**Usage:**
```bash
./hooks/pre-commit.sh
```

**Exit Codes:**
- `0` - Validation passed
- `1` - Validation failed

### pre-deploy.sh
Validates before deployment.

**Checks:**
- Tests pass
- Neo4j connectivity
- Environment variables
- Disk space
- Uncommitted changes

**Usage:**
```bash
./hooks/pre-deploy.sh
```

### post-task.sh
Logs task completion to Neo4j and updates Change Log.

**Usage:**
```bash
./hooks/post-task.sh "Task Name" "Complete"
```

**Arguments:**
1. Task name
2. Status (Complete/Failed/Partial)

## Integration

Hooks are automatically called by:
- `scripts/hourly_reflection.sh` (pre-commit, post-task)
- Deployment pipeline (pre-deploy)

## Troubleshooting

### Hook fails with permission denied
```bash
chmod +x hooks/*.sh
```

### Neo4j connection fails
```bash
# Check Neo4j is running
# Check credentials in .env
```

### Python syntax check fails
```bash
python3 -m py_compile your_file.py
```
```

**Acceptance Criteria:**
- [ ] README.md created in hooks/ directory
- [ ] All 3 hooks documented
- [ ] Usage examples provided
- [ ] Troubleshooting section included

---

### Step 4: Create Example Specs (30 min)

**Files to Create:**
- `specs/examples/task-example.md`
- `specs/examples/feature-example.md`
- `specs/examples/bug-fix-example.md`

**Task Example:**
```bash
mkdir -p /Users/kublai/.openclaw/agents/main/specs/examples

cat > /Users/kublai/.openclaw/agents/main/specs/examples/task-example.md << 'EOF'
# Task Specification - Example

## Overview
- **Task ID:** TASK-001
- **Created:** 2026-03-02
- **Assigned To:** Temüjin
- **Priority:** 8

## What This Task Does
Integrates agent hooks into the hourly reflection workflow.

## Integration Points
- **Depends On:** Hook scripts (pre-commit.sh, pre-deploy.sh, post-task.sh)
- **Affects:** scripts/hourly_reflection.sh
- **Integrates With:** Neo4j logging

## Requirements
### Functional Requirements
- [ ] pre-commit.sh called before git commits
- [ ] post-task.sh called after task completion
- [ ] Spec templates referenced in workflow

### Non-Functional Requirements
- [ ] Performance: <1s validation time
- [ ] Security: No hardcoded secrets
- [ ] Reliability: Graceful failure handling

## Edge Cases
- [ ] Hook scripts missing → Skip validation with warning
- [ ] Neo4j unavailable → Log to file instead
- [ ] Validation fails → Block commit with clear error

## Acceptance Criteria
- [ ] Hooks integrated into hourly_reflection.sh
- [ ] All hooks tested and working
- [ ] Documentation created (hooks/README.md)
- [ ] Example specs created

## Test Plan
### Unit Tests
- [ ] Test pre-commit.sh with valid files
- [ ] Test pre-commit.sh with invalid files
- [ ] Test post-task.sh Neo4j logging

### Integration Tests
- [ ] Test full hourly_reflection.sh workflow
- [ ] Test end-to-end hook execution

## Definition of Done
- [ ] All acceptance criteria met
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Code reviewed
EOF
```

**Feature Example:**
```bash
cat > /Users/kublai/.openclaw/agents/main/specs/examples/feature-example.md << 'EOF'
# Feature Specification - Example

## Feature Overview
- **Feature Name:** Agent Hook Integration
- **Version:** 1.0
- **Created:** 2026-03-02
- **Owner:** Temüjin

## Problem Statement
Agent hooks were created but not integrated into the workflow, resulting in 0% adoption.

## Proposed Solution
Integrate hooks into hourly_reflection.sh and document usage.

## Technical Design

### Architecture
```
hourly_reflection.sh
    ↓
pre-commit.sh (validation)
    ↓
[git commit]
    ↓
post-task.sh (logging)
    ↓
Neo4j + Change Log
```

### Components
| Component | Responsibility | Technology |
|-----------|---------------|------------|
| pre-commit.sh | Validate before commit | Bash, Python |
| pre-deploy.sh | Validate before deploy | Bash, Python, Neo4j |
| post-task.sh | Log after task | Bash, Python, Neo4j |

## Integration Points
### Existing Systems
- [ ] hourly_reflection.sh integration
- [ ] Neo4j logging integration

### External Dependencies
- [ ] Python 3.9+
- [ ] Neo4j connectivity
- [ ] Git availability

## Implementation Plan

### Phase 1: Integration
- [ ] Integrate pre-commit.sh
- [ ] Integrate post-task.sh
- **Milestone:** Hooks integrated

### Phase 2: Documentation
- [ ] Create hooks/README.md
- [ ] Create example specs
- **Milestone:** Documentation complete

### Phase 3: Testing
- [ ] Test all hooks
- [ ] Test end-to-end workflow
- **Milestone:** All tests passing

## Acceptance Criteria
- [ ] Hooks called by hourly_reflection.sh
- [ ] All hooks tested and working
- [ ] Documentation complete
- [ ] Examples created

## Testing Strategy
### Unit Tests
- [ ] Individual hook tests
- [ ] Validation logic tests

### Integration Tests
- [ ] End-to-end workflow test
- [ ] Neo4j logging test

## Success Metrics
| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Hook Adoption | 0% | 100% | % of commits using hooks |
| Validation Pass Rate | N/A | >95% | % of validations passing |
| Documentation Coverage | 0% | 100% | % of hooks documented |

## Timeline
- **Start Date:** 2026-03-02
- **Phase 1 Complete:** 2026-03-02 (2 hours)
- **Launch Date:** 2026-03-02
EOF
```

**Bug Fix Example:**
```bash
cat > /Users/kublai/.openclaw/agents/main/specs/examples/bug-fix-example.md << 'EOF'
# Bug Fix Specification - Example

## Bug Overview
- **Bug ID:** BUG-001
- **Reported:** 2026-03-02
- **Reported By:** Kublai
- **Severity:** High
- **Assigned To:** Temüjin

## Bug Description
Agent hooks are not being called by hourly_reflection.sh, resulting in 0% adoption.

## Reproduction Steps
1. Run hourly_reflection.sh
2. Observe that hooks are not called
3. **Expected:** Hooks should be called
4. **Actual:** Hooks are not called

## Root Cause Analysis
### Investigation
Reviewed hourly_reflection.sh - no hook calls present.

### Root Cause
Hooks were created as separate files but never integrated into the workflow.

### Contributing Factors
- No integration plan created
- No testing of integration
- No documentation of usage

## Proposed Fix
### Solution
Integrate hooks into hourly_reflection.sh at appropriate points.

### Implementation Details
```bash
# Add to hourly_reflection.sh:

# Pre-commit validation
if [ -f "$WORKSPACE/hooks/pre-commit.sh" ]; then
    "$WORKSPACE/hooks/pre-commit.sh" || exit 1
fi

# Post-task logging
if [ -f "$WORKSPACE/hooks/post-task.sh" ]; then
    "$WORKSPACE/hooks/post-task.sh" "Task" "Complete"
fi
```

### Affected Components
- [x] scripts/hourly_reflection.sh
- [x] hooks/README.md (documentation)

## Testing Plan
### Reproduction Test
- [x] Can reproduce bug (hooks not called)
- [ ] Bug is fixed with new code

### Regression Tests
- [ ] hourly_reflection.sh runs without errors
- [ ] Hooks execute successfully

### Edge Cases
- [ ] Hook scripts missing → Skip with warning
- [ ] Hook fails → Block with clear error

## Acceptance Criteria
- [x] Hooks integrated into hourly_reflection.sh
- [ ] All hooks tested and working
- [ ] Documentation created
- [ ] No regressions introduced

## Rollback Plan
Revert hourly_reflection.sh to previous version if hooks cause issues.

## Prevention
### How to Prevent Recurrence
- [x] Add integration testing to workflow
- [x] Document hook usage in README
- [x] Add hook calls to reflection template

### Lessons Learned
Creating tools is not enough - must integrate them into the workflow.

## Sign-Off
- [ ] Code reviewed by: Kublai
- [ ] Tests reviewed by: Jochi
- [ ] Approved for deployment: Kublai
EOF
```

**Acceptance Criteria:**
- [ ] All 3 example specs created
- [ ] Examples follow template structure
- [ ] Examples are realistic and useful
- [ ] Examples stored in specs/examples/ directory

---

### Step 5: Update AGENTS.md (20 min)

**File:** `/Users/kublai/.openclaw/agents/main/AGENTS.md` (and all agent-specific AGENTS.md files)

**Changes Required:**

Add new section to each agent's AGENTS.md:

```markdown
## Agent Harness Tools

### Hooks
All agents should use the automated hooks:

- **pre-commit.sh**: Run before committing code
  ```bash
  ./hooks/pre-commit.sh
  ```

- **pre-deploy.sh**: Run before deploying
  ```bash
  ./hooks/pre-deploy.sh
  ```

- **post-task.sh**: Run after completing tasks
  ```bash
  ./hooks/post-task.sh "Task Name" "Complete"
  ```

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

**Acceptance Criteria:**
- [ ] All 6 agents' AGENTS.md updated
- [ ] Hooks documented
- [ ] Spec templates referenced
- [ ] Examples referenced
- [ ] hooks/README.md referenced

---

### Step 6: End-to-End Testing (30 min)

**Test Full Workflow:**

```bash
cd /Users/kublai/.openclaw/agents/main

# 1. Create a test task spec
cp specs/examples/task-example.md specs/test-task.md

# 2. Make a code change
echo "# Test change" >> README.md

# 3. Run pre-commit hook
./hooks/pre-commit.sh

# 4. Commit the change
git add README.md
git commit -m "Test: Agent harness integration"

# 5. Run post-task hook
./hooks/post-task.sh "Agent Harness Integration" "Complete"

# 6. Verify Neo4j logging
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

# 7. Verify Change Log updated
grep "Agent Harness" CHANGELOG.md
```

**Acceptance Criteria:**
- [ ] Full workflow executes without errors
- [ ] Pre-commit validation works
- [ ] Post-task logging works
- [ ] Neo4j logging works
- [ ] Change Log updated
- [ ] All hooks execute successfully

---

## Timeline

| Step | Estimated Time | Priority |
|------|---------------|----------|
| Step 1: Integrate hooks | 30 min | CRITICAL |
| Step 2: Test all hooks | 30 min | CRITICAL |
| Step 3: Create README | 20 min | HIGH |
| Step 4: Create examples | 30 min | HIGH |
| Step 5: Update AGENTS.md | 20 min | MEDIUM |
| Step 6: End-to-end test | 30 min | CRITICAL |
| **TOTAL** | **2.5 hours** | |

---

## Definition of Done

- [ ] All 6 steps complete
- [ ] All acceptance criteria met
- [ ] All tests passing
- [ ] Documentation complete
- [ ] Examples created
- [ ] Agents trained (AGENTS.md updated)
- [ ] End-to-end test passing
- [ ] Code reviewed by Kublai

---

## Resources

- **Hook Scripts:** `/Users/kublai/.openclaw/agents/main/hooks/`
- **Spec Templates:** `/Users/kublai/.openclaw/agents/main/specs/`
- **Example Specs:** `/Users/kublai/.openclaw/agents/main/specs/examples/`
- **Documentation:** `/Users/kublai/.openclaw/agents/main/hooks/README.md`
- **Review Document:** `/Users/kublai/.openclaw/agents/main/shared-context/AGENT-HARNESS-REVIEW.md`

---

## Support

If you encounter issues:
1. Check `hooks/README.md` for troubleshooting
2. Review test scripts for examples
3. Consult AGENTS.md for workflow integration
4. Ask Kublai for review/approval

---

**Assigned By:** Kublai  
**Assigned To:** Temüjin  
**Due Date:** 2026-03-02 (tonight)  
**Priority:** CRITICAL
