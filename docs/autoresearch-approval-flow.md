# Autoresearch Approval Flow

## Overview

The autoresearch approval flow provides human-in-the-loop control for autonomous agent research operations. This system ensures that no autonomous agent can merge changes to protected branches without explicit Kublai approval.

## Security Model

**Core Principle:** Mongke security assessment requires Kublai coordination for all autonomous merges. No autonomous agent should merge without Kublai's explicit blessing.

## Workflow

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐     ┌─────────────┐
│  1. PROPOSE │ ──> │ 2. KUBLAI    │ ──> │ 3. QUARANTINE │ ──> │ 4. SUBMIT    │ ──> │ 5. MERGE    │
│  Agent      │     │ REVIEW       │     │ EXECUTE       │     │ FOR REVIEW   │     │ (Human)     │
│  creates    │     │ Kublai       │     │ Agent works   │     │ PR created  │     │ Kublai      │
│  task       │     │ approves/    │     │ in isolated   │     │ for human   │     │ merges after│
│             │     │ rejects      │     │ branch        │     │ review      │     │ review      │
└─────────────┘     └──────────────┘     └───────────────┘     └──────────────┘     └─────────────┘
```

## Components

### 1. Configuration (`config/autoresearch-policy.json`)

```json
{
  "enabled_agents": ["mongke", "jochi", "chagatai"],
  "require_human_approval_for": ["main", "master", "prod/*"],
  "auto_approve_safe_paths": ["workspace/**", "memory/*.md"],
  "max_parallel_autonomous_tasks": 3,
  "completion_gate": {
    "block_branches": ["main", "master"],
    "require_pr_review": true
  },
  "signal_notifications": {
    "enabled": true,
    "events": ["autonomous_task_started", "pr_created", "approval_granted"]
  }
}
```

### 2. Approval Script (`scripts/autoresearch-approval.py`)

Manages the approval workflow:

- `propose()` - Create approval request, notify Kublai via Signal
- `approve()` - Grant approval (Kublai only)
- `reject()` - Deny approval (Kublai only)
- `start_quarantine()` - Create isolated branch for work
- `create_pr()` - Create pull request after work complete

### 3. Task Intake Integration (`scripts/task_intake.py`)

- New `autoresearch` domain added to VALID_DOMAINS
- Autoresearch tasks automatically routed through approval flow
- Approval request created before task execution

### 4. Completion Gate (`scripts/autoresearch-completion-gate.py`)

Blocks autonomous commits to protected branches:

- Checks approval status before allowing commits
- Sends Signal alerts for violations
- Records all commit attempts to audit log

### 5. Completion Gate Audit Integration

Modified `scripts/completion-gate-audit.py` to:
- Check autoresearch approval status during task completion audit
- Block tasks awaiting approval
- Create follow-up tasks for approval requests

## Usage

### For Agents

When creating an autoresearch task:

```python
from task_intake import create_task

task_id = create_task(
    title="Research competitor pricing",
    body="Analyze competitor pricing tiers...",
    priority="high",
    source="reflection",
    agent="mongke",  # Will be classified as autoresearch domain
    skill_hint="/horde-learn"
)
```

The task intake system will:
1. Classify as `autoresearch` domain
2. Create approval request via `AutoresearchApproval.propose()`
3. Send Signal notification to Kublai
4. Wait for approval before execution

### For Kublai (Human Approval)

Approve or reject via CLI:

```bash
# Check pending requests
python3 scripts/autoresearch-approval.py status --request-id ar-task-123-abc

# Approve
python3 scripts/autoresearch-approval.py approve --request-id ar-task-123-abc --approver kublai

# Reject
python3 scripts/autoresearch-approval.py reject --request-id ar-task-123-abc --approver kublai --reason "Scope too broad"
```

### Signal Notifications

Kublai receives Signal messages for:

| Event | Emoji | Description |
|-------|-------|-------------|
| Task Proposed | 📋 | New autoresearch task created |
| Approval Requested | ⏳ | Action required - review needed |
| Approval Granted | ✅ | Kublai approved the task |
| Approval Denied | ❌ | Kublai rejected the task |
| Quarantine Started | 🔒 | Agent started work in isolated branch |
| PR Created | 🔗 | Pull request created for review |
| PR Merged | 🎉 | Human merged the PR |
| Quarantine Violation | ⚠️ | Agent attempted unauthorized action |
| Escalation Triggered | 🚨 | Request pending > 2 hours |

## Protected Branches

By default, autonomous commits are blocked to:
- `main`
- `master`
- Any branch matching patterns in `require_human_approval_for`

## Safe Paths

Files in these paths are auto-approved (no human review needed):
- `workspace/**`
- `memory/*.md`
- `logs/**`
- `data/**`
- `research/**`

## Configuration Options

### enabled_agents

List of agents allowed to perform autoresearch:

```json
"enabled_agents": ["mongke", "jochi", "chagatai"]
```

### require_human_approval_for

Branch and file patterns requiring human approval:

```json
"require_human_approval_for": [
  "main",
  "master",
  "**/config/*.json",
  "**/scripts/*.py"
]
```

### max_parallel_autonomous_tasks

Maximum concurrent autoresearch tasks per agent:

```json
"max_parallel_autonomous_tasks": 3
```

### approval_timeout_minutes

Time before approval request expires:

```json
"approval_timeout_minutes": 60
```

### escalation

Auto-escalate pending requests after timeout:

```json
"escalation": {
  "enabled": true,
  "timeout_minutes": 120,
  "escalate_to": "kublai"
}
```

## Audit Logging

All autoresearch events are logged to:
- `~/.openclaw/logs/autoresearch-gate/YYYY-MM-DD.jsonl`
- `~/.openclaw/logs/gate-audits/{task_id}.json`

## Security Events

The system logs security events for:
- Prompt injection attempts in approval requests
- Quarantine violations
- Unauthorized commit attempts
- Approval bypass attempts

## Error Handling

### Agent Not Enabled

If an agent not in `enabled_agents` attempts autoresearch:
```
AUTORESEARCH BLOCKED: Agent {agent} not enabled for autoresearch
```

### Max Parallel Tasks Exceeded

If agent has too many active tasks:
```
AUTORESEARCH BLOCKED: Agent {agent} has {count} active tasks (max: {max})
```

### Approval Timeout

If approval not granted within timeout:
- Request marked as EXPIRED
- Escalation task created for Kublai
- Signal notification sent

## Testing

Test the approval flow:

```bash
# Test approval request creation
python3 scripts/autoresearch-approval.py propose \
  --task-id test-123 \
  --agent mongke \
  --title "Test autoresearch" \
  --target-branch main

# Test approval
python3 scripts/autoresearch-approval.py approve \
  --request-id ar-test-123-abc \
  --approver kublai

# Test completion gate
python3 scripts/autoresearch-completion-gate.py check \
  --agent mongke \
  --branch main \
  --files research/output.md \
  --task-id test-123
```

## Related Documentation

- [Completion Gate Design](../mongke/workspace/completion-gate-design-2026-03-08.md)
- [Approval Workflow](./approval_workflow.py)
- [Protected Branches Config](../../config/protected_branches.yaml)
