# Kurultai Process Improvement Protocol

## Overview

The Kurultai not only syncs on agent status but also **continuously improves its own processes** through structured reflection.

---

## Process Improvement Flow

```
Kurultai Sync (Hourly)
    ↓
Agents Reflect on Processes
    ↓
Kublai Distills Insights
    ↓
Log to Neo4j (ProcessImprovement node)
    ↓
Kublai Executes Improvements
    ↓
Track Implementation Status
    ↓
Review Effectiveness (Next Sync)
```

---

## Neo4j Schema

### ProcessImprovement Node

```cypher
CREATE (pi:ProcessImprovement {
  timestamp: datetime(),
  date: '2026-03-02',
  time: '11:00',
  
  // Reflection
  whats_working: ['Heartbeat reflections every 5min'],
  whats_not_working: ['Parse Analytics 404'],
  improvements_to_implement: ['Fix analytics deployment'],
  
  // Tracking
  implemented: false,
  implemented_at: null,
  effectiveness_review: null,
  
  // Link to sync
  sync_id: '...'
})
```

### Relationships

```
(KurultaiSync)-[:HAS_IMPROVEMENT]->(ProcessImprovement)
(KurultaiSync)-[:HAS_DECISION]->(KublaiDecision)
(KublaiDecision)-[:IMPLEMENTS]->(ProcessImprovement)
```

---

## Reflection Prompts

### What's Working Well

**Agents report:**
- Processes that are efficient
- Workflows that are smooth
- Tools that are effective
- Communication that is clear

**Examples:**
- "Heartbeat reflections every 5 minutes working well"
- "Neo4j logging provides good visibility"
- "Kurultai Sync helps identify blockers early"

---

### What's Not Working

**Agents report:**
- Bottlenecks or delays
- Tools that are broken
- Communication gaps
- Resource constraints

**Examples:**
- "Parse Analytics deployment stuck at 404"
- "Crontab commands hanging"
- "Waiting on human decisions"

---

### Process Improvements to Implement

**Kublai identifies:**
- Immediate actions (this hour)
- Deferred actions (schedule for later)
- Experiments to try
- Processes to retire

**Examples:**
- "Fix Parse Analytics deployment"
- "Use manual crontab edit instead of pipe"
- "Set up Slack alerts for 404s"

---

## Kublai's Workflow

### 1. Review Sync File

```bash
cat /Users/kublai/.openclaw/agents/main/shared-context/KURULTAI-SYNC-*.md | tail -100
```

### 2. Distill Learnings

**Read agent status and identify:**
- Patterns across agents
- Common blockers
- Dependencies between agents
- Synergies to enable

### 3. Log to Neo4j

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "neo4j"))

with driver.session() as session:
    # Update ProcessImprovement with distilled insights
    session.run("""
        MATCH (pi:ProcessImprovement)
        WHERE pi.date = $date AND pi.time = $time
        SET pi.whats_working = $working,
            pi.whats_not_working = $not_working,
            pi.improvements_to_implement = $improvements
    """, date=date, time=time, 
        working=['Heartbeat working'],
        not_working=['Analytics 404'],
        improvements=['Fix deployment'])
```

### 4. Execute Immediate Actions

**Kublai acts on improvements:**
- Unblock agents
- Fix broken tools
- Reallocate resources
- Adjust priorities

### 5. Archive Sync File

```bash
# After Kublai reviews and acts
mv KURULTAI-SYNC-*.md shared-context/archive/sync/
```

### 6. Track Implementation

**Next sync, review:**
- Were improvements implemented?
- Did they work?
- Should they be kept, adjusted, or retired?

---

## Query Examples

### Get Recent Improvements

```cypher
MATCH (pi:ProcessImprovement)
WHERE pi.timestamp > datetime() - duration('P7D')
RETURN pi.date, pi.time, pi.whats_not_working, pi.improvements_to_implement
ORDER BY pi.timestamp DESC
```

### Track Implementation Status

```cypher
MATCH (pi:ProcessImprovement)
WHERE pi.implemented = false
RETURN pi.date, pi.time, pi.improvements_to_implement
ORDER BY pi.timestamp DESC
```

### Review Effectiveness

```cypher
MATCH (pi:ProcessImprovement)
WHERE pi.implemented = true AND pi.effectiveness_review IS NOT NULL
RETURN pi.improvements_to_implement, pi.effectiveness_review
ORDER BY pi.timestamp DESC
LIMIT 10
```

### Count Improvements by Category

```cypher
MATCH (pi:ProcessImprovement)
WHERE pi.date = '2026-03-02'
UNWIND pi.whats_working AS working
RETURN 'Working' AS category, working AS item, count(*) AS count
UNION ALL
MATCH (pi:ProcessImprovement)
WHERE pi.date = '2026-03-02'
UNWIND pi.whats_not_working AS not_working
RETURN 'Not Working' AS category, not_working AS item, count(*) AS count
```

---

## Continuous Improvement Cycle

### Hourly (Kurultai Sync)

1. Collect agent status
2. Reflect on processes
3. Identify improvements
4. Kublai acts

### Daily (Review)

1. Review all improvements from day
2. Track implementation status
3. Identify patterns

### Weekly (Retrospective)

1. Review all improvements from week
2. Assess effectiveness
3. Decide: Keep / Adjust / Retire
4. Update protocols

---

## Example Flow

### 11:00 Sync

**Agents Report:**
- Temüjin: "Crontab command hanging"
- Kublai: "Parse Analytics 404"
- Ögedei: "Heartbeat working well"

**Kublai Distills:**
- Working: Heartbeat, Neo4j logging
- Not Working: Crontab, Analytics deployment
- Improvements: Manual crontab, fix deployment

**Kublai Acts:**
- Updates kurultai-sync.sh with manual crontab instructions
- Investigates Parse Analytics 404

**Logs to Neo4j:**
```cypher
CREATE (:ProcessImprovement {
  date: '2026-03-02',
  time: '11:00',
  whats_working: ['Heartbeat'],
  whats_not_working: ['Crontab', 'Analytics'],
  improvements_to_implement: ['Manual crontab', 'Fix deployment'],
  implemented: false
})
```

### 12:00 Sync (Review)

**Kublai Reports:**
- ✅ Manual crontab added to protocol
- ⏳ Parse Analytics still investigating

**Neo4j Updated:**
```cypher
MATCH (pi:ProcessImprovement)
WHERE pi.date = '2026-03-02' AND pi.time = '11:00'
SET pi.implemented = true,
    pi.implemented_at = datetime()
```

---

## Benefits

| Benefit | Impact |
|---------|--------|
| **Continuous Improvement** | Processes get better every hour |
| **Agent Voice** | Every agent can identify issues |
| **Kublai Accountability** | Actions are tracked in Neo4j |
| **Pattern Recognition** | Query Neo4j for recurring issues |
| **Institutional Memory** | Neo4j stores all improvements |

---

## Implementation Checklist

- [x] Kurultai Sync script updated
- [x] Neo4j schema defined
- [ ] Neo4j logging implemented in script
- [ ] Kublai review workflow documented
- [ ] Archive workflow implemented
- [ ] Query examples tested
- [ ] Daily review process established
- [ ] Weekly retrospective scheduled

---

*The Kurultai thinks as one. Through reflection, we improve. Through improvement, we excel.*
