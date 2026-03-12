# Agent Meta-Reflection: Task & Spawning System Evaluation

**Agent:** {AGENT_NAME}  
**Role:** {AGENT_ROLE}  
**Reflection Period:** Last {HOURS} hours  
**Timestamp:** {TIMESTAMP}  
**Last Updated:** 2026-03-11 (aligned with Neo4j reflection pipeline)

---

## Your Role in the System

As **{AGENT_NAME}** ({AGENT_ROLE}), you are both a **participant** and **observer** in the task/spawning system. Your unique perspective matters.

---

## Critical Evaluation Questions

### 1. System Performance (Your Experience)

**Reflect on your own tasks:**
- How many tasks did you complete this period?
- What was your success rate?
- Did you experience any failures or retries? Why?
- Were tasks clearly defined or ambiguous?
- Did you have the right tools/context to succeed?

**Your metrics:**
- Tasks completed: {TASKS_COMPLETED}
- Success rate: {SUCCESS_RATE}
- Retries: {RETRIES}
- Avg duration: {AVG_DURATION}

---

### 2. System Bottlenecks

**From your perspective, what's broken or slow?**

Consider:
- Task classification accuracy (are you getting the right tasks?)
- Spawn latency (how long from task creation to execution?)
- Queue backlog (are tasks waiting too long?)
- Resource constraints (model limits, timeouts, etc.)
- Coordination gaps (missing handoffs between agents?)

**Your observations:**
```
[Your honest assessment here]
```

---

### 3. Improvement Ideas

**What would make the system better?**

Think about:
- New features or capabilities
- Process improvements
- Better routing/classification
- Monitoring or alerting
- Automation opportunities

**Your proposals:**
```
[Your ideas here - be specific and actionable]
```

---

### 4. Agent-to-Agent Feedback

**What do you observe about OTHER agents?**

- Who's overloaded? Who's underutilized?
- Any coordination issues between agents?
- Tasks that should be rerouted to different agents?
- Collaboration opportunities?

**Your observations:**
```
[Your feedback on other agents]
```

---

### 5. Strategic Recommendations

**Big-picture thinking:**

If you could change ONE thing about the task/spawning system to make it 10x better, what would it be?

**Your recommendation:**
```
[Your boldest idea]
```

---

## Submission to Kublai

**Priority Level:**
- [ ] CRITICAL (system broken, needs immediate fix)
- [ ] HIGH (significant improvement, implement soon)
- [ ] MEDIUM (nice to have, schedule when possible)
- [ ] LOW (minor optimization, backlog)

**Proposal Summary:**
```
[1-2 sentence summary of your main recommendation]
```

**Specific Tasks to Implement:**
```
[If applicable, list specific tasks that should be created]
Example:
- Create auto-retry with exponential backoff (assign to: temujin)
- Add task priority aging system (assign to: temujin)
- Implement load balancing across agents (assign to: ogedei)
```

---

## Notes for Kublai

**Why this matters:**
[Explain the impact of implementing your ideas]

**Estimated effort:**
[Low/Medium/High]

**Expected benefit:**
[Quantify if possible: faster spawn time, higher success rate, etc.]

---

*Submit this reflection to Kublai via Neo4j (AgentFeedback node) or direct message.*
