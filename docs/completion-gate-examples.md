# Completion Gate Examples

> **Version:** 1.0
> **Last Updated:** 2026-03-08

This document provides realistic examples of how the Completion Gate works in practice.

---

## Example 1: Immediate Pass (100% Complete)

### Task
```
# Task: Fix typo in homepage hero text

Change "Build the fueture" → "Build the future" in homepage hero section.
```

### Agent Work
Temujin fixes the typo, verifies the change, and marks task done.

### Audit Result
```json
{
  "completion_percentage": 100,
  "can_complete": true,
  "missing_components": [],
  "quality_issues": [],
  "required_followups": [],
  "optional_improvements": [],
  "blockers": []
}
```

### Outcome
Task → `fix-typo-hero.completed.done.md` (immediate pass)

---

## Example 2: Follow-ups Created (75% Complete)

### Task
```
# Task: Implement Stripe checkout flow

Create Stripe checkout endpoint that:
- Accepts credit card payment
- Creates subscription
- Returns success/error

Project: Parse platform at /Users/kublai/projects/parse-github
```

### Agent Work
Temujin creates the checkout endpoint and marks task done.

### Audit Result
```json
{
  "completion_percentage": 75,
  "can_complete": false,
  "missing_components": [
    "Credit pack display bug ($500 → $5)",
    "Stripe webhook handler for subscription events"
  ],
  "quality_issues": [
    "No tests written for checkout endpoint",
    "Error handling incomplete for declined cards"
  ],
  "required_followups": [
    {
      "title": "Fix credit pack display bug ($500 → $5)",
      "agent": "temujin",
      "priority": "high",
      "reason": "Critical UX bug blocking launch"
    },
    {
      "title": "Add Stripe webhook handler",
      "agent": "temujin",
      "priority": "high",
      "reason": "Required for subscription status updates"
    }
  ],
  "optional_improvements": [
    {
      "title": "Write tests for checkout endpoint",
      "agent": "jochi",
      "priority": "normal",
      "reason": "Quality assurance"
    }
  ],
  "blockers": []
}
```

### Outcome
Original Task → `stripe-checkout.pending-gate.md`

Follow-up tasks created:
- `temujin/tasks/high-gate-stripe-checkout-1234-fix-display.md`
- `temujin/tasks/high-gate-stripe-checkout-5678-webhook.md`
- `jochi/tasks/normal-gate-stripe-checkout-9012-tests.md`

When follow-ups complete → gate resolves → `stripe-checkout.gate-passed.done.md`

---

## Example 3: Blocked by External Issue

### Task
```
# Task: Configure Stripe production keys

Update Railway deployment with production Stripe API keys.
```

### Agent Work
Temujin checks Railway variables but can't find production keys.

### Audit Result
```json
{
  "completion_percentage": 0,
  "can_complete": false,
  "missing_components": ["Stripe production keys not available"],
  "quality_issues": [],
  "required_followups": [],
  "blockers": [
    "Stripe production API keys required from human",
    "Keys must be retrieved from Stripe dashboard"
  ]
}
```

### Outcome
Task → `stripe-keys.gate-blocked.md`

**Resolution:** Human provides keys via Railway dashboard. Then:
1. New task created: "Apply Stripe keys to Railway"
2. Original task bypassed (wasn't started)
3. New task completes successfully

---

## Example 4: Trivial Fix (Opt-out)

### Task
```
# Task: Update README contact email

Change contact email in README from old@example.com to new@example.com
---
completion_gate_optout: true
---
```

### Agent Work
Chagatai updates the email and marks task done.

### Outcome
Task → `update-readme-email.completed.done.md` (no audit run)

**Note:** This is appropriate use of opt-out. For substantive README changes (restructuring, adding sections), the gate should apply.

---

## Example 5: Follow-up Creates Its Own Follow-ups

### Original Task
`stripe-checkout.pending-gate.md` (from Example 2)

### First Follow-up
```
# Task: Fix credit pack display bug ($500 → $5)

Audit: Credit packs showing $500 instead of $5 in UI.
```

Temujin fixes the pricing bug but doesn't verify all pack sizes.

### First Follow-up Audit
```json
{
  "completion_percentage": 80,
  "can_complete": false,
  "missing_components": ["$10 pack not verified"],
  "required_followups": [
    {
      "title": "Verify $10 credit pack displays correctly",
      "agent": "temujin",
      "priority": "high",
      "reason": "Missing verification"
    }
  ],
  "blockers": []
}
```

### Outcome
`fix-credit-pack-display.pending-gate.md` → creates second-level follow-up

Second-level follow-up completes → first follow-up gate passes → original task gate checked → still waiting for webhook handler → continues waiting

---

## Example 6: Optional Improvements Only (92% Complete)

### Task
```
# Task: Add user profile API endpoint

Create GET /api/profile endpoint returning user profile data.
```

### Agent Work
Temujin implements the endpoint with basic auth check.

### Audit Result
```json
{
  "completion_percentage": 92,
  "can_complete": true,
  "missing_components": [],
  "quality_issues": ["Rate limiting not implemented"],
  "required_followups": [],
  "optional_improvements": [
    {
      "title": "Add rate limiting to profile endpoint",
      "agent": "temujin",
      "priority": "low",
      "reason": "Production best practice"
    }
  ],
  "blockers": []
}
```

### Outcome
Task → `profile-api.completed.done.md` (passes gate)

Optional improvement task created:
- `temujin/tasks/low-gate-profile-api-rate-limit.md`

**Note:** Since original was ≥90%, it passed immediately. Optional improvements are created but don't block completion.

---

## Example 7: Multiple Audit Cycles

### Task
```
# Task: Implement password reset flow

Full password reset: email sending, token validation, password update.
```

### Cycle 1
Agent implements email sending and password update (90%).

Audit: Token validation missing → follow-up created.

### Cycle 2
Follow-up: "Add token validation"
Agent implements basic token check (85%).

Audit: Token expiration not checked → another follow-up.

### Cycle 3
Follow-up: "Add token expiration check"
Agent adds 24-hour expiration logic (100%).

Gate resolves → follow-up passes → original task re-audited → now 100% → original task passes.

### Outcome
- `password-reset.pending-gate.md` (waits through 2 cycles)
- `token-validation.pending-gate.md` → `.gate-passed.done.md`
- `token-expiry.gate-passed.done.md`
- `password-reset.gate-passed.done.md` (final resolution)

---

## Example 8: Emergency Bypass

### Task
```
# Task: Fix critical production bug

Users getting 500 errors on checkout. Fix immediately.
```

### Agent Work
Temujin fixes the bug (95%). Audit creates follow-up for tests.

But production is down, need to deploy NOW.

### Bypass Command
```bash
python3 ~/.openclaw/agents/main/scripts/completion-gate-bypass.py \
  --task checkout-bug-fix \
  --reason "Production emergency - deploying hotfix, tests to follow"
```

### Outcome
Task → `checkout-bug-fix.gate-bypassed.done.md`

Follow-up for tests still created and completed later.

**Note:** Bypass is logged and reviewed. Use only for genuine emergencies.

---

## Audit JSON Example

Full audit output file (`~/.openclaw/agents/main/logs/gate-audits/high-12345.json`):

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "audit_id": "audit-high-12345-20260308-123456",
  "original_task": "high-12345",
  "audit_timestamp": "2026-03-08T12:34:56.789012",
  "audit_version": "1.0",
  "agent": "temujin",
  "task_title": "Implement Stripe checkout flow",
  "completion_percentage": 75,
  "can_complete": false,
  "requirements_analysis": {
    "total_requirements": 4,
    "met_requirements": 3,
    "missing_requirements": 1
  },
  "missing_components": [
    "Credit pack display bug ($500 → $5)",
    "Stripe webhook handler for subscription events"
  ],
  "quality_issues": [
    "No tests written for checkout endpoint",
    "Error handling incomplete for declined cards"
  ],
  "required_followups": [
    {
      "title": "Fix credit pack display bug ($500 → $5)",
      "agent": "temujin",
      "priority": "high",
      "reason": "Critical UX bug blocking launch",
      "domain": "implementation"
    },
    {
      "title": "Add Stripe webhook handler",
      "agent": "temujin",
      "priority": "high",
      "reason": "Required for subscription status updates",
      "domain": "implementation"
    }
  ],
  "optional_improvements": [
    {
      "title": "Write tests for checkout endpoint",
      "agent": "jochi",
      "priority": "normal",
      "reason": "Quality assurance",
      "domain": "testing"
    }
  ],
  "blockers": [],
  "audit_model": "claude-opus-4-6",
  "gate_cycle": 1
}
```

---

## Follow-up Task Template Example

```markdown
---
agent: temujin
priority: high
created: 2026-03-08T12:34:56.789012
source: completion-gate
depth: 1
task_id: gate-stripe-checkout-1234-abcd5678
parent_task: high-stripe-checkout-main
completion_gate: true
gate_audit_ref: ~/.openclaw/agents/main/logs/gate-audits/high-stripe-checkout-main.json
gate_required: true
bucket: TODAY
domain: implementation
timeout: 3600
skill_hint: null
---

# Task: Fix credit pack display bug ($500 → $5)

This is a **completion gate follow-up task** for parent: `high-stripe-checkout-main`

## Parent Context

The parent task "Implement Stripe checkout flow" identified that credit packs
are displaying $500 instead of $5. This is a critical UX bug that must be
fixed before the feature can be considered production-ready.

## What to Do

1. Locate the credit pack pricing display component
2. Fix the display bug ($500 → $5)
3. Verify the fix works in the UI
4. Test with different pack sizes ($5, $10, $25, $50)

## Audit Reason

> Critical UX bug blocking launch

## Success Criteria

- [ ] Credit packs display correct prices
- [ ] All pack sizes verified ($5, $10, $25, $50)
- [ ] No regression in other price displays

---
_Generated by completion-gate-audit at 2026-03-08T12:34:56_
```
