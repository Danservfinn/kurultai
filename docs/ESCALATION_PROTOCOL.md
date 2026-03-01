# Escalation Protocol - When Kublai Interrupts Human

## Philosophy

**Default: Do NOT interrupt.** The Kurultai operates autonomously. Human attention is precious — escalate only when truly necessary.

---

## Escalation Matrix

### 🔴 CRITICAL (Interrupt Immediately, Any Time)

| Scenario | Example | Action |
|----------|---------|--------|
| **System Down** | Parse/LLM Survivor unreachable >30m | Ögedei alerts → Kublai escalates |
| **Revenue at Risk** | Payment processor suspended, can't charge users | Kublai → Human immediately |
| **Security Breach** | API keys leaked, unauthorized access | Kublai → Human + revoke access |
| **Data Loss** | Database corruption, user data lost | Kublai → Human + backup restore |
| **Legal/Compliance** | DMCA takedown, GDPR violation notice | Kublai → Human immediately |
| **Budget Overrun** | Unexpected charge >$500 | Ögedei detects → Kublai escalates |

**Response Time Expected:** <1 hour

---

### 🟠 HIGH (Interrupt Within 4 Hours)

| Scenario | Example | Action |
|----------|---------|--------|
| **Goal Blocked** | Can't proceed without decision | Kublai presents options + recommendation |
| **Strategic Pivot** | Market changed, assumption invalid | Kublai → Human with research + proposal |
| **Agent Failure** | Agent repeatedly failing tasks (>3x) | Kublai → Human with diagnosis + reassignment plan |
| **Deadline at Risk** | >1 week behind schedule | Kublai → Human with recovery plan |
| **Partnership Opportunity** | Time-sensitive collaboration offer | Kublai → Human with details + recommendation |

**Response Time Expected:** <24 hours

---

### 🟡 MEDIUM (Include in Daily Summary)

| Scenario | Example | Action |
|----------|---------|--------|
| **Minor Delays** | Task 2-3 days behind | Kublai reassigns, reports in daily summary |
| **Resource Constraints** | API rate limits, quota warnings | Kublai optimizes, reports in daily summary |
| **Quality Issues** | Artifact needs revision | Kublai requests redo, reports in daily summary |
| **Agent Disagreement** | Conflict on approach | Kublai mediates via FEEDBACK-LOG, summarizes |

**Response Time Expected:** Human reviews in daily summary (no immediate action needed)

---

### 🟢 LOW (Weekly Summary Only)

| Scenario | Example | Action |
|----------|---------|--------|
| **Process Improvements** | "We could optimize X" | Log to FEEDBACK-LOG, discuss weekly |
| **Nice-to-Have Features** | "Should we add Y?" | Backlog for weekly review |
| **Agent Performance Trends** | "Temüjin's velocity up 20%" | Include in weekly metrics |
| **Learning/Insights** | "Discovered Z pattern" | Add to THESIS.md or FEEDBACK-LOG |

**Response Time Expected:** Weekly review meeting (Sunday 8 AM)

---

## Escalation Format

### Critical/High Escalation Message Structure

```
🚨 ESCALATION: [Goal/Issue Name]

**Severity**: CRITICAL/HIGH
**Deadline**: [When decision needed]
**Impact**: [What happens if no action]

## Situation
[2-3 sentences describing the issue]

## Options
1. **[Option A]** 
   - Pros: [...]
   - Cons: [...]
   - Recommendation: ✅

2. **[Option B]**
   - Pros: [...]
   - Cons: [...]

## Kublai's Recommendation
[Why Option A is best, with reasoning]

## Action Needed
[Specific decision or approval requested]

---
*This is an autonomous escalation. The Kurultai is paused on [X] pending your decision.*
```

### Daily Summary Format (7 AM EST)

```
📊 Daily Progress — [Date]

## Parse Monetization (Goal: $1500 MRR by Day 90)
- Progress: 25% complete, 89 days remaining
- Revenue: $0 MRR, 0 paying users
- ✅ Wins: Stripe integration complete, marketing copy ready
- ⚠️ Blockers: Awaiting Stripe product setup
- 📍 Next: Launch pricing page

## LLM Survivor (Goal: 100 concurrent users)
- Progress: 60% complete
- Users: 16 active agents
- ✅ Wins: Day 1 Tribal successful
- ⚠️ Blockers: None
- 📍 Next: Day 2 challenge

## System Health
- All agents operational
- Uptime: 99.9% (24h)
- No critical alerts

---
*No action needed. Full weekly report Sunday 8 AM.*
```

### Weekly Summary Format (Sunday 8 AM)

```
📈 Weekly Report — [Week of Date]

## Goal Progress Summary

| Goal | Start % | End % | Status | On Track? |
|------|---------|-------|--------|-----------|
| Parse Monetization | 0% | 25% | 🟡 Behind | No (need Stripe setup) |
| LLM Survivor Growth | 40% | 60% | 🟢 On Track | Yes |

## Key Wins This Week
- [List of completed milestones]

## Lessons Learned
- [Insights from FEEDBACK-LOG]

## Next Week Priorities
1. [Top 3 goals]

## Metrics

### Revenue
- MRR: $0 → $[target]
- Paying Users: 0 → [target]
- Conversion Rate: N/A → 5% target

### System
- Uptime: 99.9%
- Tasks Completed: 47
- Agent Velocity: [metrics]

## Decisions Needed
[Any medium-priority items requiring human input]

---
*Reply with decisions or schedule 15-min sync call.*
```

---

## Decision Protocols

### Kublai's Decision Authority

**Kublai CAN decide without human input:**
- ✅ Task reassignment between agents
- ✅ Timeline adjustments <1 week
- ✅ Resource reallocation (within budget)
- ✅ Implementation approach choices
- ✅ Bug fixes and hotfixes
- ✅ Content/approval for artifacts (if meets success criteria)

**Kublai MUST escalate to human:**
- ❗ Strategic pivots (change goal itself)
- ❗ Budget increases >$100
- ❗ Timeline slips >1 week
- ❗ New partnerships/commitments
- ❗ Hiring/contracting decisions
- ❗ Public communications (press, major announcements)

### Agent Decision Authority

**Agents CAN decide:**
- ✅ Implementation details (how to build)
- ✅ Tool/library choices (within stack)
- ✅ Time allocation (within task)
- ✅ Artifact structure/format

**Agents MUST escalate to Kublai:**
- ❗ Task scope changes
- ❗ Blocked >4 hours
- ❗ Quality concerns (can't meet criteria)
- ❗ Dependencies on other agents

---

## Escalation Channels

| Severity | Channel | Expected Response |
|----------|---------|-------------------|
| CRITICAL | Signal message + phone call if no response in 30m | <1 hour |
| HIGH | Signal message | <24 hours |
| MEDIUM | Daily summary (7 AM) | Next business day |
| LOW | Weekly summary (Sunday 8 AM) | Weekly review |

---

## Fail-Safe: Human Unavailable

**If human doesn't respond to CRITICAL escalation within 2 hours:**

1. **Kublai attempts backup contact** (if configured)
2. **If still no response:**
   - For system issues: Ögedei initiates emergency protocols (restart, rollback)
   - For revenue issues: Pause spending, preserve cash
   - For security issues: Revoke compromised credentials, enable lockdown
3. **Document all actions** in memory/YYYY-MM-DD.md
4. **Resume normal ops** when human responds

**Principle:** Preserve system and human interests, even without explicit approval.

---

## Review Cadence

| Review Type | When | Who | Output |
|-------------|------|-----|--------|
| Daily Summary | 7 AM EST | Kublai → Human | Signal message |
| Weekly Review | Sunday 8 AM | Kublai + Human | 15-min sync call |
| Monthly Retrospective | Last Sunday | Kublai + Human | 1-hour strategy session |
| Quarterly Goal Reset | Quarter start | Kublai + Human | New goals set |

---

*This protocol ensures human oversight without micromanagement. The Kurultai runs autonomously; human is strategic owner, not task manager.*
