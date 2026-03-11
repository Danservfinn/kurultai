# Routing Idle Agent Bypass — Diagnostic Guide

**Created:** 2026-03-09
**Agent:** chagatai
**Severity:** FLEW-WIDE — Multiple agents idle but not receiving tasks

---

## Symptom

The routing system detects idle agents (chagatai, mongke) but consistently routes to agents with higher queue depths. Every routing decision shows:

```json
{
  "idle_agents": ["chagatai", "mongke"],
  "would_overflow": true
}
```

Yet tasks continue routing to busy agents (ogedei, kublai, temujin).

---

## Root Causes

### 1. Domain Compatibility Guard (Most Common)

The `DOMAIN_AGENT_COMPATIBILITY` matrix restricts which agents can receive tasks by domain:

```python
DOMAIN_AGENT_COMPATIBILITY = {
    "research": ["mongke", "jochi", "tolui"],
    "implementation": ["temujin", "ogedei", "jochi", "tolui"],
    "ops": ["ogedei", "temujin", "jochi", "tolui"],
    "documentation": ["chagatai", "mongke", "tolui"],  # ← chagatai ONLY here
    "strategy": ["temujin", "kublai", "ogedei"],
    "analysis": ["jochi", "mongke", "kublai", "tolui"],
}
```

**Impact:** If current tasks are ops/implementation/analysis domains, chagatai will NEVER be routed to them, regardless of queue depth.

### 2. Skill-Locked Routing

Tasks with skill hints (e.g., `/kurultai-health`, `/horde-implement`) are locked to specific agents:

```python
_SKILL_AGENT_MAP = {
    "/kurultai-health": "ogedei",  # Always goes to ogedei
    "/horde-implement": "temujin",  # Always goes to temujin
    ...
}
```

**Impact:** Even when ogedei/temujin are overloaded, skill-locked tasks bypass load balancing.

### 3. Task Flow Imbalance

When the system generates mostly system-generated tasks (escalations, health checks, watchdog alerts), there are few tasks with documentation keywords:

```python
"chagatai": ["write", "document", "blog", "content", "changelog", "copy", "article",
             "social", "twitter", "marketing", "announcement", "readme", "presence",
             "draft", "summarize", "summary", "guide", "tutorial", "outline", ...]
```

**Impact:** If no tasks contain these keywords, chagatai scores 0 on keyword matching and is never selected.

---

## Diagnosis Commands

### Check Current Task Domains

```bash
jq -r '.domain' /Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl | tail -50 | sort | uniq -c
```

**Expected output:** Should show variety across domains. If dominated by ops/implementation, that's the issue.

### Check idle Agent Detection

```bash
jq -r '.idle_agents' /Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl | tail -20 | sort | uniq -c
```

**Expected output:** Should consistently show idle agents. If not, the idle detection is broken.

### Check Skill-Locked Task Ratio

```bash
jq -r 'select(.skill_hint != null) | .skill_hint' /Users/kublai/.openclaw/agents/main/logs/routing-decisions.jsonl | tail -50 | sort | uniq -c
```

**Expected output:** If >80% are skill-locked, load balancing has limited effect.

---

## Solutions

### Option A: Expand Domain Compatibility (Architecture Change)

**File:** `scripts/task_intake.py`
**Risk:** MEDIUM — Cross-domain tasks may misroute

Add chagatai to additional domains where it has relevant skills:

```python
DOMAIN_AGENT_COMPATIBILITY = {
    "documentation": ["chagatai", "mongke", "tolui"],
    "analysis": ["jochi", "mongke", "kublai", "tolui", "chagatai"],  # ← add chagatai
    "strategy": ["temujin", "kublai", "ogedei", "chagatai"],       # ← add chagatai
}
```

**Trade-off:** Chagatai may receive tasks that aren't pure documentation. Monitor for misroutes.

### Option B: Enable Skill Overflow (Quick Fix)

**File:** `scripts/task_intake.py`
**Risk:** LOW — Skill overflow already implemented

Ensure skill overflow bypass is enabled:

```python
# In find_best_idle_agent(), verify skill_overflow_bypass logic exists
# around line 2500-2530. The _SKILL_CAPABLE_ALTERNATES map should include
# entries for common skills.
```

### Option C: Generate Documentation Tasks (Self-Service)

**File:** Create tasks in `~/.openclaw/agents/chagatai/tasks/`
**Risk:** NONE — chagatai works on own domain

Create proactive documentation tasks based on system changes:

```bash
# Example: Document recent routing changes
echo "Document routing-idle-agent-bypass-diagnostic.md changes" > \
  ~/.openclaw/agents/chagatai/tasks/write-routing-diagnostic-$(date +%s).md
```

---

## Monitoring

### Health Check

```bash
# Run hourly to detect stuck agents
for agent in chagatai mongke jochi; do
  depth=$(jq -r --arg a "$agent" '.queue[$a]' \
    ~/.openclaw/agents/main/logs/routing-decisions.jsonl | tail -1)
  if [ "$depth" = "0" ]; then
    echo "ALERT: $agent has zero tasks — check task flow"
  fi
done
```

### Alert Thresholds

- **Critical:** Agent idle >2 hours with 0 tasks while system has >10 total tasks
- **Warning:** would_overflow=true >80% of routing decisions
- **Info:** Domain imbalance (>70% of tasks in 1 domain)

---

## References

- **Routing Logic:** `scripts/task_intake.py` lines 1606-1800
- **Domain Matrix:** `scripts/task_intake.py` lines 84-94
- **Capability Matrix:** `scripts/task_intake.py` lines 625-670
- **Routing Audit:** `scripts/routing_audit.py`

---

## Changelog

| Date | Change | Agent |
|------|--------|-------|
| 2026-03-09 | Initial diagnostic guide created | chagatai |
