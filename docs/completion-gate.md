# Completion Gate System

> **Version:** 1.0
> **Status:** Active
> **Author:** Mongke (Research Agent)
> **Last Updated:** 2026-03-08

## Overview

The Completion Gate is a quality assurance mechanism that prevents tasks from being marked complete without first auditing what follow-up work is required. It ensures that when an agent marks a task done, the work is actually complete per requirements.

### Problem Solved

Previously, agents could mark tasks `.done.md` even when:
- Only 50-80% of requirements were met
- Critical dependencies were missed
- Related improvements were overlooked
- Tests or documentation were incomplete

The Completion Gate catches these gaps before the task is marked complete.

---

## How It Works

### The Gate Flow

```
Agent finishes work
         ↓
   Run completion audit
         ↓
    ┌────┴────┐
    │         │
   <90%      ≥90%
  Complete   Complete
    │         │
    ↓         ↓
Create    Mark .done.md
follow-ups   (existing path)
    │
    ↓
Task → .pending-gate.md
    │
    ↓
[Async: Gate Resolver monitors]
    │
    ↓
All follow-ups complete?
    │
  Yes ────► Re-audit → Pass if 100% → .gate-passed.done.md
```

### Task State Transitions

``                               ┌─────────────────────┐
                               │   .pending.md       │
                               │   (Task Created)    │
                               └──────────┬──────────┘
                                          │
                                          │ Agent starts work
                                          ▼
                               ┌─────────────────────┐
                               │  .executing.md      │
                               │  (Agent Working)    │
                               └──────────┬──────────┘
                                          │
                                          │ Agent marks done
                                          ▼
                              ┌───────────────────────────┐
                              │ completion_gate_optout?   │
                              └───────────┬───────────────┘
                                          │
                   ┌──────────────────────┼──────────────────────┐
                   │ YES                  │ NO                   │
                   ▼                      ▼                      │
         ┌──────────────────┐    ┌──────────────────────┐       │
         │   .done.md       │    │   Run Audit          │       │
         │   (No Gate)      │    │   Analyze:           │       │
         └──────────────────┘    │   - Requirements %   │       │
                                 │   - Missing items    │       │
                                 └──────────┬───────────┘       │
                                            │                   │
                                            ▼                   │
                                 ┌───────────────────────────┐   │
                                 │   completion_percentage   │   │
                                 └───────────┬───────────────┘   │
                                             │                   │
                     ┌───────────────────────┼───────────────────┤
                     │ ≥90% AND              │ <90% OR            │
                     │ no blockers           │ has blockers       │
                     ▼                       ▼                   │
           ┌──────────────────┐   ┌──────────────────────┐       │
           │  .done.md        │   │  .pending-gate.md    │       │
           │  (Gate Passed)   │   │  (Follow-ups needed) │       │
           └──────────────────┘   └──────────┬───────────┘       │
                                          │                   │
                                          │ Create follow-ups  │
                                          ▼                   │
                               ┌──────────────────────┐       │
                               │ Follow-up tasks      │◄──────┘
                               │ (parent_task set)    │
                               └──────────┬───────────┘
                                          │
                                          │ Agents work on follow-ups
                                          ▼
                               ┌──────────────────────┐
                               │ All follow-ups .done?│
                               └──────────┬───────────┘
                                          │
                     ┌─────────────────────┼─────────────────────┐
                     │ NO                  │ YES                 │
                     ▼                     ▼                     │
           ┌──────────────────┐   ┌──────────────────────┐       │
           │ Keep waiting     │   │ Re-audit             │       │
           │ (or blocked if   │   │ Verify: 100%         │       │
           │  any blocked)    │   └──────────┬───────────┘       │
           └──────────────────┘              │                   │
                                             │                   │
                         ┌───────────────────┼───────────────────┤
                         │ 100% complete     │ <100% OR blockers  │
                         ▼                   ▼                   │
               ┌──────────────────┐   ┌──────────────────────┐   │
               │ .gate-passed.    │   │ Create more          │   │
               │   done.md        │   │ follow-ups           │   │
               │ (Final Complete) │   │ (cycle continues)    │   │
               └──────────────────┘   └──────────┬───────────┘   │
                                                      │           │
                                                      └───────────┘

                          ┌─────────────────────────────────────────┐
                          │   EMERGENCY BYPASS (any state)          │
                          │   Requires:                             │
                          │   - Authorized approver                 │
                          │   - Specific reason (min 20 chars)      │
                          │   - Rate limit check                    │
                          │   - Multi-party for critical/high       │
                          └──────────────────────┬──────────────────┘
                                                 │
                                                 ▼
                                ┌──────────────────────────────┐
                                │  .gate-bypassed.done.md      │
                                │  (Bypassed - logged &        │
                                │   reviewed)                  │
                                └──────────────────────────────┘
```

**State Suffixes Reference:**

| Suffix | Meaning | Who Creates |
|--------|---------|-------------|
| `.pending.md` | New task, not started | Task handler |
| `.executing.md` | Agent actively working | Agent on start |
| `.done.md` | Complete (opt-out) | Agent (no audit) |
| `.pending-gate.md` | Waiting for follow-ups | Audit script |
| `.gate-passed.done.md` | Truly complete | Resolver |
| `.gate-bypassed.done.md` | Emergency bypass | Bypass script |
| `.gate-blocked.md` | External blocker needed | Resolver |

**Frontmatter Fields Added by Gate:**

| Field | Value Set By | Description |
|-------|--------------|-------------|
| `completion_gate` | Audit | `true` if gated |
| `gate_status` | Resolver | Current gate state |
| `gate_audit_ref` | Audit | Path to audit JSON |
| `completion_percentage` | Audit | 0-100 score |
| `parent_task` | Audit | Original task ID (for follow-ups) |
| `gate_required` | Audit | `true` if blocking |
| `gate_cycle` | Resolver | Number of audit cycles |

---

### What Gets Audited

The audit analyzes:
1. **Requirements Coverage** — What % of original requirements were met
2. **Missing Components** — Specific items not delivered
3. **Quality Issues** — Tests missing, docs incomplete, etc.
4. **Dependencies Needed** — Related work that should be created
5. **Blockers** — External items requiring human action

### Gate Thresholds

| Completion % | Can Complete? | Follow-ups Created? |
|--------------|---------------|---------------------|
| 90-100% | Yes (unless blockers) | Optional improvements only |
| 70-89% | No | Required follow-ups |
| < 70% | No | Required follow-ups + may require replan |
| Any % | No (if blockers) | No — task blocked, human action needed |

---

## For Agents

### What Changes for You

**Before:** You mark a task `.done.md` when you think it's done.

**After:** When you finish a task:
1. The system runs an automatic audit
2. If < 90% complete, follow-up tasks are created automatically
3. Your task waits in `.pending-gate.md` state
4. When follow-ups complete, gate resolves automatically
5. Task marked `.gate-passed.done.md` when truly complete

### Handling Follow-up Tasks

If you receive a follow-up task from the Completion Gate:
- It includes `parent_task` in frontmatter
- It includes `gate_audit_ref` pointing to the audit JSON
- It explains what was missing in the "Audit Reason" section
- Complete it like any other task

### When to Opt-Out

For trivial tasks that don't need a gate, add to frontmatter:

```yaml
---
completion_gate_optout: true
---
```

Use for:
- One-line fixes
- Typos
- Simple config changes
- Status checks

DO NOT use for:
- Feature implementation
- Bug fixes with multiple steps
- Tasks requiring tests
- Tasks requiring documentation

---

## Task File States

### New Suffixes

| Suffix | Meaning |
|--------|---------|
| `.pending-gate.md` | Task blocked by gate, waiting for follow-ups |
| `.gate-passed.done.md` | Gate passed, task truly complete |
| `.gate-bypassed.done.md` | Gate bypassed (emergency) |
| `.gate-blocked.md` | Gate blocked (human action required) |

### New Frontmatter Fields

```yaml
---
# Completion gate fields (auto-populated)
completion_gate: false          # Does this task require a gate?
gate_status: null               # Current gate state
gate_audit_ref: null            # Path to audit JSON
completion_percentage: null     # Set by audit (0-100)
parent_task: null               # For follow-up tasks
gate_required: false            # For follow-up tasks
gate_cycle: 0                   # Audit cycles this task had
---
```

---

## Installation and Setup

### Initial Setup

The Completion Gate system requires minimal setup:

```bash
# 1. Verify scripts exist
ls ~/.openclaw/agents/main/scripts/completion-gate-*.py

# 2. Create allowlist for bypass authorization (see below)
# 3. Set up cron job for automatic gate resolution (optional but recommended)
```

### Bypass Allowlist Configuration

The `completion-gate-bypass.py` script requires an allowlist config to authorize bypass operations. This prevents unauthorized agents from bypassing gates.

**Location:** `~/.openclaw/agents/main/config/gate-bypass-allowlist.json`

**Create the allowlist:**

```bash
mkdir -p ~/.openclaw/agents/main/config
cat > ~/.openclaw/agents/main/config/gate-bypass-allowlist.json << 'EOF'
{
  "version": "1.0",
  "last_updated": "2026-03-08T09:00:00Z",
  "description": "Authorized approvers for completion gate bypass",
  "approvers": {
    "kublai": {
      "name": "Kublai",
      "type": "agent_coordinator",
      "can_bypass_any_priority": true,
      "requires_second_approval": false,
      "added": "2026-03-08T09:00:00Z"
    },
    "your-name": {
      "name": "Your Name",
      "type": "human",
      "can_bypass_any_priority": true,
      "requires_second_approval": false,
      "added": "2026-03-08T09:00:00Z"
    }
  },
  "restricted_patterns": [
    "^temujin$", "^mongke$", "^jochi$", "^ogedei$", "^chagatai$",
    "^agent-", "-agent$", "^bot", "^automation"
  ],
  "multi_party_rules": {
    "enabled": true,
    "threshold_priorities": ["critical", "high"],
    "required_approvers": 2,
    "description": "Critical and high priority tasks require 2 separate approvers"
  },
  "rate_limits": {
    "max_per_day": 10,
    "max_per_hour": 3,
    "cooldown_seconds": 300
  },
  "audit": {
    "log_to_neo4j": true,
    "log_to_file": true,
    "signal_alert": true,
    "immutable": true
  }
}
EOF
```

**Allowlist Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `approvers` | object | Map of approver ID to config |
| `approvers.{id}.type` | string | Must be `human` or `agent_coordinator` (kublai only) |
| `restricted_patterns` | array | Regex patterns that are NEVER allowed (e.g., agent names) |
| `multi_party_rules.enabled` | boolean | Enable multi-party approval for high-priority tasks |
| `multi_party_rules.threshold_priorities` | array | Priorities requiring multiple approvers |
| `multi_party_rules.required_approvers` | number | How many approvers needed |
| `rate_limits.max_per_day` | number | Max bypasses per approver per day |
| `rate_limits.max_per_hour` | number | Max bypasses per approver per hour |

**Security Notes:**
- Agent names (temujin, mongke, etc.) are blocked via `restricted_patterns`
- Only humans and kublai (as coordinator) can authorize bypass
- All bypass attempts are logged immutably to Neo4j and file
- Rate limits prevent bypass abuse
- Multi-party approval required for critical/high priority tasks

### Cron Job Setup (Optional)

For automatic gate resolution, add a cron job:

```bash
# Edit crontab
crontab -e

# Add this line to check every 5 minutes
*/5 * * * * /usr/bin/python3 ~/.openclaw/agents/main/scripts/completion-gate-resolver.py --resolve-all >> ~/.openclaw/logs/gate-resolver.log 2>&1
```

---

## CLI Tools Reference

### completion-gate-audit.py

**Purpose:** Analyze task completion and generate follow-up requirements.

**Location:** `~/.openclaw/agents/main/scripts/completion-gate-audit.py`

**Usage:**
```bash
# Run audit on a task file
python3 completion-gate-audit.py --task /path/to/task.md --agent temujin

# Dry run (don't create follow-ups)
python3 completion-gate-audit.py --task /path/to/task.md --agent temujin --dry-run

# Save audit to specific path
python3 completion-gate-audit.py --task /path/to/task.md --agent temujin --output /path/to/audit.json

# Run demo audit
python3 completion-gate-audit.py --test
```

**Options:**
| Option | Description |
|--------|-------------|
| `--task PATH` | Path to task file (.md or .executing.md) |
| `--agent NAME` | Agent name (e.g., mongke, temujin, jochi) |
| `--dry-run` | Show audit without creating follow-ups |
| `--output PATH` | Save audit JSON to specific path |
| `--test` | Run demo audit on sample task |

**Security Features (v2.0):**
- Input sanitization against prompt injection
- Structured prompt boundaries with delimiters
- Output validation for suspicious patterns
- Automatic security logging for injection attempts

---

### completion-gate-resolver.py

**Purpose:** Monitor and resolve pending gates automatically. Runs via cron or task-watcher.

**Location:** `~/.openclaw/agents/main/scripts/completion-gate-resolver.py`

**Usage:**
```bash
# Resolve all pending gates
python3 completion-gate-resolver.py --resolve-all

# Show gate metrics
python3 completion-gate-resolver.py --metrics

# Check specific task
python3 completion-gate-resolver.py --task high-12345678

# Check specific task without resolving
python3 completion-gate-resolver.py --task high-12345678 --check-only

# Dry run (show what would happen)
python3 completion-gate-resolver.py --resolve-all --dry-run
```

**Options:**
| Option | Description |
|--------|-------------|
| `--resolve-all` | Check and resolve all pending gates |
| `--metrics` | Show aggregate gate metrics |
| `--task ID` | Check specific task by ID |
| `--check-only` | Show status without resolving |
| `--dry-run` | Show what would happen without changes |

**How It Works:**
1. Uses Neo4j-first gate discovery with filesystem fallback
2. For each pending gate:
   - Finds all follow-up tasks
   - Checks if all are complete
   - Re-audits to verify completion
   - Marks gate passed if 100% complete
   - Marks gate blocked if any follow-up is blocked

**Metrics Output:**
```
=== COMPLETION GATE METRICS ===

Pending Gates:       5
Blocked Gates:       1
Total Follow-ups:    12

Recent Audits (24h): 15
Passed Audits:       12
Pass Rate:           80.0%
Avg Completion:      87.5%
```

---

### task-gate-validator.py

**Purpose:** Debug stuck gates and inspect gate status interactively.

**Location:** `~/.openclaw/agents/main/scripts/task-gate-validator.py`

**Usage:**
```bash
# List all pending gates
python3 task-gate-validator.py --list-pending

# Show detailed status for a task
python3 task-gate-validator.py --task high-12345678

# List follow-ups for a task
python3 task-gate-validator.py --list-followups high-12345678

# Show full audit JSON
python3 task-gate-validator.py --audit-json high-12345678

# Check for circular dependencies
python3 task-gate-validator.py --check-cycles

# Check for stale gates (>24 hours)
python3 task-gate-validator.py --check-stale

# Check with custom stale threshold
python3 task-gate-validator.py --check-stale --stale-hours 48
```

**Options:**
| Option | Description |
|--------|-------------|
| `--task ID` | Show gate status for task ID |
| `--list-pending` | List all pending gates |
| `--list-followups ID` | List follow-ups for a task |
| `--audit-json ID` | Show full audit JSON |
| `--check-cycles` | Check for circular dependencies |
| `--check-stale` | Check for gates stuck >24 hours |
| `--stale-hours N` | Custom stale threshold (default: 24) |

**Status Output Example:**
```
=== GATE STATUS: high-12345678 ===

File: /Users/kublai/.openclaw/agents/temujin/tasks/high-12345678.pending-gate.md
Agent: temujin
Status: .pending-gate
Parent: N/A
Gate Required: true
Created: 2026-03-08T12:34:56

Audit Result:
  Completion: 75%
  Can Complete: false
  Required Follow-ups: 2
  Optional Improvements: 1
  Blockers: 0

Follow-up Tasks (2):
  → gate-high-12345678-abcd1234
     Agent: temujin, Status: executing
  ○ gate-high-12345678-efgh5678
     Agent: jochi, Status: pending

All follow-ups complete: false
```

---

### completion-gate-bypass.py

**Purpose:** Emergency override for blocked gates with security hardening.

**Location:** `~/.openclaw/agents/main/scripts/completion-gate-bypass.py`

**Usage:**
```bash
# Bypass a gate (requires allowlist setup)
python3 completion-gate-bypass.py \
  --task high-12345678 \
  --approver kublai \
  --reason "Production hotfix for critical security vulnerability - auth bypass allows data exfiltration"

# Dry run (test authorization)
python3 completion-gate-bypass.py \
  --task high-12345678 \
  --approver kublai \
  --reason "Testing bypass authorization" \
  --dry-run

# Show bypass log
python3 completion-gate-bypass.py --log

# Show last 50 log entries
python3 completion-gate-bypass.py --log --log-count 50

# Force bypass (skip rate limits - emergency only)
python3 completion-gate-bypass.py \
  --task high-12345678 \
  --approver kublai \
  --reason "CRITICAL: Production down, immediate deployment required" \
  --force
```

**Options:**
| Option | Description |
|--------|-------------|
| `--task ID` | Task ID to bypass |
| `--approver NAME` | Approver name (must be on allowlist) |
| `--reason TEXT` | Reason for bypass (min 20 chars, specific) |
| `--dry-run` | Show what would happen |
| `--force` | Skip rate limit checks (emergency) |
| `--log` | Show bypass log |
| `--log-count N` | Number of log entries (default: 20) |

**Security Requirements (v2.0):**
- `--approver` REQUIRED — must be on allowlist (agents NOT allowed)
- `--reason` REQUIRED — min 20 characters, specific (no generic words)
- Rate limiting — max 10/day, 3/hour per approver
- Multi-party approval — required for critical/high priority tasks
- Immutable logging — all bypasses logged to Neo4j + file
- Signal alerts — sent for all bypass events

**Generic Reasons That Will Be Rejected:**
- "needed", "required", "fix", "urgent", "asap"
- "do it", "just do", "bypass", "skip"
- "production hotfix", "emergency" (without context)
- "...", "test", "n/a"

**Good Reasons (specific, contextual):**
- "Production hotfix for critical security vulnerability - auth bypass allows data exfiltration"
- "Deploying urgent fix for checkout bug affecting 100% of users, tests will run in staging"
- "Database migration stuck in production, need to bypass to complete manual rollback"

---

## Operations

### Monitoring Gates

Check pending gates:

```bash
# Find all pending-gate tasks
find ~/.openclaw/agents/*/tasks -name "*.pending-gate.md"

# Check gate status via Neo4j
python3 ~/.openclaw/agents/main/scripts/task-gate-validator.py --list-pending
```

### Troubleshooting

#### Gate stuck for >24 hours?

Symptoms: Task remains in `.pending-gate.md` state despite follow-ups being complete.

```bash
# Check for stale gates
python3 ~/.openclaw/agents/main/scripts/task-gate-validator.py --check-stale

# Validate specific gate status
python3 ~/.openclaw/agents/main/scripts/task-gate-validator.py --task <task_id>

# Check follow-up completion status
python3 ~/.openclaw/agents/main/scripts/completion-gate-resolver.py --task <task_id> --check-only

# Manual resolution if all follow-ups are truly complete
python3 ~/.openclaw/agents/main/scripts/completion-gate-resolver.py --resolve-all
```

**Common causes:**
- Follow-up tasks renamed incorrectly (not `.done.md`)
- Neo4j cache stale (resolver needs --refresh)
- Follow-up task has `parent_task` mismatch

#### Follow-ups not being created?

Symptoms: Gate audit completes but no follow-up tasks appear.

```bash
# Check audit log
cat ~/.openclaw/agents/main/logs/gate-audits/<task_id>.json

# Verify required_followups array is populated
jq '.required_followups' ~/.openclaw/agents/main/logs/gate-audits/<task_id>.json

# Check if dry-run was used
# (dry-run shows audit but doesn't create tasks)
```

**Common causes:**
- Agent directory doesn't exist for target agent
- Disk space issue
- Permission issue on tasks directory

#### Gate creating incorrect follow-ups?

Symptoms: Audit generates wrong or unnecessary follow-up tasks.

```bash
# Review the audit JSON to understand what was detected
python3 ~/.openclaw/agents/main/scripts/task-gate-validator.py --audit-json <task_id>

# For incorrect follow-ups, bypass the original task
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task <task_id> \
  --approver kublai \
  --reason "Audit created incorrect follow-ups: <explain why they're wrong>"

# Report the audit failure for system improvement
# (helps train the audit LLM for next time)
```

#### Circular dependency detected?

Symptoms: Tasks waiting on each other in a loop.

```bash
# Check for circular dependencies
python3 ~/.openclaw/agents/main/scripts/task-gate-validator.py --check-cycles

# Example output:
# ⚠ Found 1 potential cycle:
#   task-a -> task-b -> task-c -> task-a
```

**Resolution:**
1. Identify the weakest link in the cycle
2. Bypass that task to break the cycle
3. Complete remaining tasks
4. Re-create bypassed task if needed

#### "Allowlist not found" error?

Symptoms: Bypass script fails with missing allowlist.

```bash
# Check allowlist exists
ls ~/.openclaw/agents/main/config/gate-bypass-allowlist.json

# If missing, create it (see Installation section above)
mkdir -p ~/.openclaw/agents/main/config
# ... (create allowlist JSON as shown in Installation section)
```

#### "Approver not on allowlist" error?

Symptoms: Bypass authorization fails even with correct name.

```bash
# Check allowlist contents
cat ~/.openclaw/agents/main/config/gate-bypass-allowlist.json | jq '.approvers'

# Verify exact name match (case-insensitive)
# Add your name if missing
```

#### Rate limit exceeded?

Symptoms: Bypass blocked due to too many recent bypasses.

```bash
# Check bypass log for recent activity
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py --log --log-count 10

# Wait for cooldown (default: 3/hour, 10/day)
# OR use --force for genuine emergency (document reason carefully)
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task <task_id> \
  --approver kublai \
  --reason "PRODUCTION EMERGENCY: <specific details>" \
  --force
```

#### Multi-party approval needed?

Symptoms: Critical/high priority task requires multiple approvals.

```bash
# First approval (records but doesn't bypass yet)
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task <task_id> \
  --approver kublai \
  --reason "<reason>"

# Second approval (completes bypass)
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task <task_id> \
  --approver human \
  --reason "<reason>"

# Check current approval count in bypass log
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py --log
```

#### Emergency Bypass

Use only when gate is blocking critical operations:

```bash
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task <task_id> \
  --approver kublai \
  --reason "Production hotfix for critical security vulnerability - auth bypass allows data exfiltration"
```

**When to use bypass:**
- Production down/losing revenue
- Critical security vulnerability being exploited
- Gate bug preventing completion (document the bug)

**When NOT to use bypass:**
- Task is genuinely incomplete
- Follow-ups are legitimate
- "Just want to move faster"

All bypasses are logged immutably and reviewed.

---

## Audit Output Schema

```json
{
  "original_task": "task-id",
  "audit_timestamp": "2026-03-08T12:34:56",
  "completion_percentage": 75,
  "can_complete": false,
  "missing_components": [
    "Credit pack display not fixed",
    "Webhook handler missing"
  ],
  "quality_issues": [
    "No tests written",
    "Error handling incomplete"
  ],
  "required_followups": [
    {
      "title": "Fix credit pack display",
      "agent": "temujin",
      "priority": "high",
      "reason": "Critical UX bug"
    }
  ],
  "optional_improvements": [
    {
      "title": "Add analytics",
      "agent": "mongke",
      "priority": "normal",
      "reason": "Track usage"
    }
  ],
  "blockers": []
}
```

---

## FAQ

### Q: Does the gate slow down task completion?

**A:** Minimally. The audit runs in parallel with your completion. For tasks passing the gate (≥90%), you see no difference. For tasks needing follow-ups, the async resolution means you're not blocked.

### Q: What if I disagree with the audit?

**A:** Complete the legitimate follow-ups. For incorrect ones, bypass with explanation. Report audit failures — the system improves with feedback.

### Q: Can I disable the gate entirely?

**A:** No. The gate is a system-wide quality mechanism. Use `completion_gate_optout: true` for specific trivial tasks.

### Q: What happens to opt-out tasks?

**A:** They follow the old path: `.executing.md` → `.done.md` with no audit.

### Q: How do I know if a task is a follow-up?

**A:** Check frontmatter for `parent_task` and `completion_gate: true`.

### Q: Can follow-up tasks create their own follow-ups?

**A:** Yes. The gate applies recursively. A follow-up at 80% creates its own follow-ups.

### Q: What if all follow-ups are done but the gate doesn't resolve?

**A:** Run the validator script. If it shows all complete but gate stuck, use bypass — this is a bug to report.

### Q: Where are audit logs stored?

**A:** `~/.openclaw/agents/main/logs/gate-audits/<task_id>.json`

### Q: Can I see what % complete I was before follow-ups?

**A:** Yes, check `completion_percentage` in the audit JSON or task frontmatter.

---

## Related Documentation

- **Design Document:** `~/.openclaw/agents/mongke/workspace/completion-gate-design-2026-03-08.md`
- **Examples:** `~/.openclaw/agents/main/docs/completion-gate-examples.md`
- **Scripts:** `~/.openclaw/agents/main/scripts/completion-gate-*.py`
