# Heartbeat-Driven Task Progress System

**Current State:** Heartbeats are passive check-ins (status reporting only)

**Opportunity:** Transform heartbeats into active task progression engines

---

## Current Heartbeat Function

```
Every 30 minutes:
  1. Agent checks in
  2. Reports status
  3. Does self-reflection
  4. Returns HEARTBEAT_OK
```

**Limitation:** No task progression, no accountability, no momentum

---

## Proposed: Heartbeat-Driven Task Progression

### Core Concept

Each heartbeat becomes a **micro-commitment cycle**:

```
Every 30 minutes:
  1. Review assigned tasks
  2. Report progress (% complete)
  3. Identify blockers
  4. Commit to next 30-min action
  5. Execute immediately
```

---

## Mechanism 1: Task Progress Tracking

### Heartbeat Task Report

```markdown
## Task Progress (Last 30 min)

| Task | Progress | Status | Next Action |
|------|----------|--------|-------------|
| Research longevity supplements | 75% | 🟢 On Track | Write summary (15 min) |
| Write Twitter thread | 30% | 🟡 Behind | Draft intro (30 min) |
| Deploy analytics endpoint | 0% | 🔴 Blocked | Waiting for API key |

### Blockers Identified:
- ❌ Deploy task blocked: Missing API key (needs Kublai)

### Next 30-Min Commitment:
- Complete Twitter thread draft (Chagatai)
- Escalate API key blocker to Kublai (Ögedei)
```

### Implementation

```python
def heartbeat_task_report(agent_name):
    """
    Generate task progress report for heartbeat.
    """
    tasks = get_agent_tasks(agent_name)
    
    report = {
        'agent': agent_name,
        'timestamp': datetime.now(),
        'tasks': []
    }
    
    for task in tasks:
        progress = calculate_progress(task)
        status = determine_status(progress, task.deadline)
        
        report['tasks'].append({
            'id': task.id,
            'description': task.description,
            'progress': progress,
            'status': status,
            'next_action': task.next_action,
            'eta': task.eta
        })
    
    return report
```

---

## Mechanism 2: Automatic Task Escalation

### Escalation Rules

| Heartbeat Count | Status | Action |
|-----------------|--------|--------|
| **1 heartbeat** (30 min) | 🟢 Normal | Continue working |
| **2 heartbeats** (60 min) | 🟡 Check-in | Report progress to Kublai |
| **3 heartbeats** (90 min) | 🟠 Warning | Request assistance |
| **4+ heartbeats** (120+ min) | 🔴 Critical | Auto-reassign task |

### Implementation

```python
def check_task_escalation(task_id, agent_name):
    """
    Check if task needs escalation based on heartbeat count.
    """
    task = get_task(task_id)
    heartbeats_without_progress = count_stagnant_heartbeats(task_id)
    
    if heartbeats_without_progress >= 4:
        # Auto-reassign task
        new_agent = find_available_agent(task.skills_required)
        reassign_task(task_id, agent_name, new_agent)
        notify_kublai(f"Task {task_id} reassigned from {agent_name} to {new_agent}")
        
    elif heartbeats_without_progress >= 3:
        # Request assistance
        request_assistance(task_id, agent_name)
        notify_kublai(f"Task {task_id} blocked for 90 minutes")
        
    elif heartbeats_without_progress >= 2:
        # Just check in
        request_progress_report(task_id, agent_name)
```

---

## Mechanism 3: Dependency Resolution

### Heartbeat Dependency Check

```python
def check_dependencies_at_heartbeat(agent_name):
    """
    Check if any blocked tasks are now unblocked.
    """
    blocked_tasks = get_blocked_tasks(agent_name)
    
    for task in blocked_tasks:
        dependencies = get_task_dependencies(task.id)
        
        for dep in dependencies:
            if is_dependency_complete(dep):
                # Dependency is complete, unblock task
                unblock_task(task.id)
                notify_agent(agent_name, f"Task {task.id} unblocked: {dep.name} complete")
```

### Example Flow

```
Heartbeat #1 (Ögedei):
  "Deploy task blocked: Waiting for API key from Kublai"
  ↓
Kublai receives notification
  ↓
Kublai provides API key (15 min later)
  ↓
Heartbeat #2 (Ögedei):
  "Checking dependencies... API key received ✓"
  "Deploy task UNBLOCKED - starting execution"
```

---

## Mechanism 4: Priority Escalation

### Dynamic Priority System

```python
def calculate_dynamic_priority(task, heartbeat_count):
    """
    Increase task priority with each heartbeat without progress.
    """
    base_priority = task.base_priority  # 1-10
    
    # Increase priority by 1 for each heartbeat without progress
    priority_boost = heartbeat_count
    
    # Cap at maximum priority
    dynamic_priority = min(base_priority + priority_boost, 10)
    
    return dynamic_priority
```

### Priority Queue at Each Heartbeat

```
Before Heartbeat:
[Task A (P=5), Task B (P=3), Task C (P=7)]

After 2 Heartbeats (no progress on Task B):
[Task C (P=7), Task B (P=5), Task A (P=5)]
  ↑ Task B escalated from P=3 to P=5
```

---

## Mechanism 5: Momentum Commitments

### 30-Minute Commitment System

```python
def make_heartbeat_commitment(agent_name, task_id, commitment):
    """
    Agent commits to specific action in next 30 minutes.
    """
    commitment = {
        'agent': agent_name,
        'task': task_id,
        'action': commitment,
        'deadline': datetime.now() + timedelta(minutes=30),
        'status': 'committed'
    }
    
    save_commitment(commitment)
    
    # Check at next heartbeat
    schedule_commitment_check(commitment)
```

### Commitment Tracking

```
Heartbeat #1 (Chagatai):
  "Commitment: Write Twitter thread intro (30 min)"
  
Heartbeat #2 (Chagatai):
  "Commitment Status: COMPLETE ✓"
  "New Commitment: Draft 7 tweets (30 min)"
  
Heartbeat #3 (Chagatai):
  "Commitment Status: COMPLETE ✓"
  "New Commitment: Review and finalize (30 min)"
```

---

## Mechanism 6: Cross-Agent Coordination

### Heartbeat Sync Points

```python
def heartbeat_cross_agent_sync():
    """
    At each heartbeat, check for cross-agent dependencies.
    """
    # Find tasks waiting on other agents
    waiting_tasks = get_tasks_waiting_on_agents()
    
    for task in waiting_tasks:
        blocking_agent = task.blocked_by_agent
        
        if is_agent_available(blocking_agent):
            # Notify blocking agent
            notify_agent(blocking_agent, f"Task {task.id} waiting on you")
```

### Example Coordination

```
Heartbeat Check:
  Möngke: "Research complete, waiting on Chagatai"
  Chagatai: "Starting content creation now"
  
Next Heartbeat:
  Möngke: "Available for new tasks"
  Chagatai: "Content 50% complete, need Möngke fact-check"
  Möngke: "Starting fact-check (30 min)"
```

---

## Mechanism 7: Progress Visualization

### Heartbeat Dashboard

```
┌─────────────────────────────────────────────────────────┐
│              KURULTAI TASK DASHBOARD                    │
│              (Updated: 19:42 EST)                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Agent     │ Tasks │ Progress | Blockers | Next        │
│───────────┼───────┼──────────┼──────────┼─────────────│
│ Kublai    │   3   │   67% 🟢 |    0     │ Summary (15m)│
│ Möngke    │   5   │   40% 🟡 |    1     │ Research (30m)│
│ Chagatai  │   4   │   80% 🟢 |    0     │ Review (15m) │
│ Temüjin   │   6   │   25% 🔴 |    2     │ Deploy (60m) │
│ Jochi     │   3   │   50% 🟢 |    0     │ Analysis (30m)│
│ Ögedei    │   2   │   90% 🟢 |    0     │ Monitor (15m)│
│                                                         │
│ Total: 23 tasks │ 52% complete │ 3 blockers            │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Task Progress Tracking (Day 1)

```python
# Add to hourly_reflection.sh
def heartbeat_task_progress():
    """
    Report task progress at each heartbeat.
    """
    tasks = get_agent_tasks(agent_name)
    report = generate_progress_report(tasks)
    log_to_neo4j(report)
```

### Phase 2: Escalation System (Day 2)

```python
# Add escalation logic
def heartbeat_escalation_check():
    """
    Check if tasks need escalation.
    """
    stagnant_tasks = find_stagnant_tasks(agent_name)
    
    for task in stagnant_tasks:
        escalate_if_needed(task)
```

### Phase 3: Dependency Resolution (Day 3)

```python
# Add dependency checking
def heartbeat_dependency_check():
    """
    Check if blocked tasks are now unblocked.
    """
    blocked_tasks = get_blocked_tasks(agent_name)
    
    for task in blocked_tasks:
        if dependencies_complete(task):
            unblock_task(task)
```

### Phase 4: Commitment System (Day 4)

```python
# Add commitment tracking
def heartbeat_commitment():
    """
    Make and track 30-minute commitments.
    """
    check_previous_commitments()
    make_new_commitments()
```

### Phase 5: Dashboard (Day 5)

```python
# Create progress dashboard
def generate_heartbeat_dashboard():
    """
    Generate real-time task dashboard.
    """
    dashboard = aggregate_all_agent_progress()
    publish_to_channel(dashboard)
```

---

## Example: Full Heartbeat Flow

### Before (Current)

```
19:30 Heartbeat (Chagatai):
  "All systems operational. HEARTBEAT_OK"
  
19:00 Heartbeat (Chagatai):
  "All systems operational. HEARTBEAT_OK"
  
18:30 Heartbeat (Chagatai):
  "All systems operational. HEARTBEAT_OK"
```

**Result:** No task visibility, no accountability, no momentum

### After (Proposed)

```
19:30 Heartbeat (Chagatai):
  ────────────────────────────────────────
  Task Progress (Last 30 min):
  
  ✅ Twitter thread draft (COMPLETE)
  🔄 Age-reversal post (75% - Final review)
  ⏳ Bio options (0% - Blocked, waiting on user feedback)
  
  Blockers:
  ❌ Bio selection needs user input
  
  Next 30-Min Commitment:
  → Finalize age-reversal post (publish)
  → Start X profile research (30 min)
  ────────────────────────────────────────
  
19:00 Heartbeat (Chagatai):
  ────────────────────────────────────────
  Task Progress (Last 30 min):
  
  ✅ Research competitors (COMPLETE)
  🔄 Twitter thread draft (80% - 6/8 tweets)
  ⏳ Bio options (0% - Waiting)
  
  Next 30-Min Commitment:
  → Complete Twitter thread (30 min)
  ────────────────────────────────────────
```

**Result:** Full visibility, clear accountability, measurable momentum

---

## Metrics to Track

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Task Velocity** | Unknown | 5+ tasks/agent/day | Tasks completed / day |
| **Blocker Resolution** | Unknown | <2 hours avg | Time from block to unblock |
| **Commitment Keep Rate** | N/A | >90% | Commitments kept / total |
| **Escalation Rate** | N/A | <10% | Tasks escalated / total |
| **Cross-Agent Handoffs** | N/A | 3+ per day | Tasks handed between agents |

---

## Benefits

### For Agents:
- ✅ Clear task visibility
- ✅ Automatic blocker resolution
- ✅ Accountability without micromanagement
- ✅ Momentum building through commitments

### For Kublai:
- ✅ Real-time task dashboard
- ✅ Automatic escalation alerts
- ✅ No need to poll agents for status
- ✅ Clear bottleneck identification

### For Users:
- ✅ Faster task completion (parallel execution)
- ✅ Transparent progress tracking
- ✅ Clear ETAs on deliverables
- ✅ Automatic escalation on blockers

---

## Recommended Implementation Order

1. **Day 1:** Task progress tracking (foundational)
2. **Day 2:** Escalation system (accountability)
3. **Day 3:** Dependency resolution (unblocking)
4. **Day 4:** Commitment system (momentum)
5. **Day 5:** Dashboard (visibility)

**Total Implementation:** 5 days

**Expected Impact:** 3-5x task throughput, 50% reduction in blocker time

---

## Next Steps

**Ready to implement Phase 1?**

I can add task progress tracking to the hourly reflection script immediately. This will:
1. Track task progress at each heartbeat
2. Log to Neo4j for dashboard generation
3. Provide baseline metrics for optimization

**Shall I start implementation?**
