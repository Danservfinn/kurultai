# Multi-Task Distribution System

**Problem:** Currently, multiple queued tasks are processed sequentially by Kublai (1-by-1).

**Solution:** Distribute tasks across all 6 agents based on specialization for parallel execution.

---

## Current State (Sequential)

```
Queue: [Task 1, Task 2, Task 3, Task 4, Task 5, Task 6]
                ↓
            Kublai processes Task 1 (10 min)
                ↓
            Kublai processes Task 2 (10 min)
                ↓
            Kublai processes Task 3 (10 min)
                ↓
            ... (60 minutes total for 6 tasks)
```

**Bottleneck:** Single agent (Kublai) processing all tasks

**Throughput:** ~6 tasks/hour

---

## Proposed State (Parallel Distribution)

```
Queue: [Task 1, Task 2, Task 3, Task 4, Task 5, Task 6]
         │        │        │        │        │        │
         ↓        ↓        ↓        ↓        ↓        ↓
      Kublai  Möngke  Chagatai  Temüjin   Jochi   Ögedei
         │        │        │        │        │        │
         └────────┴────────┴────────┴────────┴────────┘
                            ↓
                    Parallel Execution
                            ↓
                    ~10 minutes total
```

**Throughput:** ~36 tasks/hour (6x improvement)

---

## Task Classification & Routing

### Automatic Task Classification

| Task Type | Keywords | Assigned Agent |
|-----------|----------|----------------|
| **Research** | "research", "find", "analyze", "compare", "investigate" | Möngke |
| **Content** | "write", "post", "thread", "bio", "content", "create" | Chagatai |
| **Development** | "code", "deploy", "fix", "build", "implement", "script" | Temüjin |
| **Analysis** | "analyze", "compare", "evaluate", "review", "test" | Jochi |
| **Operations** | "monitor", "check", "status", "deploy", "restart", "health" | Ögedei |
| **Coordination** | "coordinate", "manage", "organize", "plan", "summary" | Kublai |

### Routing Algorithm

```python
def route_task(task_description):
    """
    Automatically route task to appropriate agent based on keywords.
    Returns: (agent_name, confidence_score)
    """
    
    keywords = {
        'mongke': ['research', 'find', 'search', 'analyze', 'compare', 'investigate', 'discover'],
        'chagatai': ['write', 'post', 'thread', 'bio', 'content', 'create', 'draft', 'compose'],
        'temujin': ['code', 'deploy', 'fix', 'build', 'implement', 'script', 'fix', 'debug'],
        'jochi': ['analyze', 'compare', 'evaluate', 'review', 'test', 'benchmark', 'measure'],
        'ogedei': ['monitor', 'check', 'status', 'deploy', 'restart', 'health', 'heartbeat'],
        'kublai': ['coordinate', 'manage', 'organize', 'plan', 'summary', 'report']
    }
    
    task_lower = task_description.lower()
    scores = {}
    
    for agent, agent_keywords in keywords.items():
        score = sum(1 for keyword in agent_keywords if keyword in task_lower)
        scores[agent] = score
    
    best_agent = max(scores, key=scores.get)
    confidence = scores[best_agent] / max(len(keywords) for keywords in keywords.values())
    
    return best_agent, confidence
```

---

## Implementation Options

### Option 1: OpenClaw Subagent Spawning (Recommended)

**Mechanism:** Use `sessions_spawn` to spawn parallel subagent sessions

**Pros:**
- ✅ True parallel execution
- ✅ Each agent has isolated context
- ✅ No context window contention
- ✅ Built-in OpenClaw support
- ✅ Results aggregated automatically

**Cons:**
- ⚠️ Higher token usage (6x contexts)
- ⚠️ Slightly more complex coordination

**Implementation:**
```python
# Kublai receives 6 tasks
tasks = [task1, task2, task3, task4, task5, task6]

# Classify and route
assignments = []
for task in tasks:
    agent, confidence = route_task(task.description)
    assignments.append((agent, task))

# Spawn parallel subagents
for agent, task in assignments:
    sessions_spawn(
        agent=agent,
        task=task.description,
        mode="run",
        runtime="subagent"
    )

# Wait for all to complete
# Aggregate results
# Return to user
```

---

### Option 2: Internal Task Queue with Worker Threads

**Mechanism:** Maintain internal task queue, spawn threads for each agent

**Pros:**
- ✅ Single context window
- ✅ Lower token overhead
- ✅ Simpler state management

**Cons:**
- ❌ Not truly parallel (Python GIL)
- ❌ Context switching overhead
- ❌ More complex error handling

**Implementation:**
```python
import threading
from queue import Queue

task_queue = Queue()
results = {}

def agent_worker(agent_name):
    while True:
        task = task_queue.get()
        if task is None:
            break
        result = execute_task(agent_name, task)
        results[task.id] = result
        task_queue.task_done()

# Start worker threads for each agent
threads = []
for agent in ['kublai', 'mongke', 'chagatai', 'temujin', 'jochi', 'ogedei']:
    t = threading.Thread(target=agent_worker, args=(agent,))
    t.start()
    threads.append(t)

# Queue tasks
for task in tasks:
    task_queue.put(task)

# Wait for completion
task_queue.join()
```

---

### Option 3: Hybrid Approach (Best of Both)

**Mechanism:** Use subagent spawning for large/complex tasks, internal queue for simple tasks

**Decision Matrix:**

| Task Complexity | Execution Method |
|-----------------|------------------|
| **Simple** (<5 min) | Internal queue |
| **Medium** (5-15 min) | Subagent spawn |
| **Complex** (>15 min) | Subagent spawn with dedicated context |

**Implementation:**
```python
def execute_task(task):
    if task.estimated_time < 5:  # minutes
        return execute_local(task)
    else:
        return spawn_subagent(task)
```

---

## Recommended Implementation: Option 1 (Subagent Spawning)

### Why This Is Best:

1. **True Parallelism:** All 6 agents work simultaneously
2. **Isolated Contexts:** No context window contention
3. **Scalable:** Can handle 6+ tasks simultaneously
4. **OpenClaw Native:** Uses built-in `sessions_spawn`
5. **Clean Separation:** Each agent has clear ownership

### Architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    KUBLAI (Main)                        │
│  - Receives all user tasks                              │
│  - Classifies tasks by type                             │
│  - Spawns subagents for parallel execution              │
│  - Aggregates results                                   │
│  - Returns consolidated response                        │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ↓                 ↓                 ↓
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   MÖNGKE      │ │  CHAGATAI     │ │   TEMÜJIN     │
│  (Research)   │ │  (Content)    │ │  (Dev)        │
│  Subagent     │ │  Subagent     │ │  Subagent     │
└───────────────┘ └───────────────┘ └───────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                          ↓
                  Results Aggregated
                          │
                          ↓
                  Return to User
```

---

## Implementation Steps

### Phase 1: Task Classification (Day 1)

```python
# Add to Kublai's session
def classify_and_route_tasks(tasks):
    """
    Classify multiple tasks and route to appropriate agents.
    """
    assignments = {
        'kublai': [],
        'mongke': [],
        'chagatai': [],
        'temujin': [],
        'jochi': [],
        'ogedei': []
    }
    
    for task in tasks:
        agent, confidence = route_task(task)
        assignments[agent].append(task)
    
    return assignments
```

### Phase 2: Parallel Execution (Day 1)

```python
def execute_parallel(assignments):
    """
    Spawn subagents for each agent's task queue.
    """
    results = {}
    
    for agent, tasks in assignments.items():
        if tasks:
            # Spawn subagent for this agent's tasks
            result = sessions_spawn(
                agent=agent,
                task=serialize_tasks(tasks),
                mode="run",
                runtime="subagent"
            )
            results[agent] = result
    
    return results
```

### Phase 3: Result Aggregation (Day 2)

```python
def aggregate_results(results):
    """
    Aggregate results from all subagents.
    """
    consolidated = []
    
    for agent, result in results.items():
        consolidated.append(f"### {agent.title()}'s Results:\n{result}")
    
    return "\n\n".join(consolidated)
```

### Phase 4: User Response (Day 2)

```python
def respond_to_user(original_tasks, aggregated_results):
    """
    Return consolidated results to user.
    """
    response = f"## Task Completion Summary\n\n"
    response += f"Processed {len(original_tasks)} tasks across 6 agents.\n\n"
    response += aggregated_results
    return response
```

---

## Example Workflow

### User Input:
```
I need you to:
1. Research the top 5 longevity supplements
2. Write a Twitter thread about the findings
3. Deploy the new analytics endpoint
4. Check if Parse is still running
5. Analyze the deployment logs for errors
6. Create a summary report
```

### Kublai's Classification:
```
Task 1 → Möngke (Research)
Task 2 → Chagatai (Content)
Task 3 → Temüjin (Development)
Task 4 → Ögedei (Operations)
Task 5 → Jochi (Analysis)
Task 6 → Kublai (Coordination)
```

### Parallel Execution:
```
[All 6 subagents spawn simultaneously]
[Each works on their assigned task]
[Results stream back to Kublai]
[Kublai aggregates and responds]
```

### Time Comparison:
- **Sequential:** ~60 minutes (10 min × 6 tasks)
- **Parallel:** ~10-15 minutes (all tasks simultaneous)
- **Speedup:** 4-6x faster

---

## Edge Cases & Handling

### Case 1: All Tasks Same Type
```
User: "Write 6 different Twitter threads"
→ All 6 tasks → Chagatai
→ Spawn 6 Chagatai subagents in parallel
```

### Case 2: Task Dependencies
```
Task 1: Research longevity supplements (Möngke)
Task 2: Write thread about findings (Chagatai) [DEPENDS ON Task 1]

Solution: 
- Execute Task 1 first
- Pass results to Task 2
- Chain dependent tasks
```

### Case 3: Agent Overload
```
Scenario: 20 tasks, all for Temüjin (development)

Solution:
- Spawn multiple Temüjin subagents
- Distribute tasks evenly
- Aggregate all results
```

---

## Metrics to Track

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Throughput** | 30+ tasks/hour | Tasks completed / hour |
| **Latency** | <15 min avg | Time from queue to response |
| **Agent Utilization** | >80% | % time agents are active |
| **Success Rate** | >95% | Tasks completed without error |
| **User Satisfaction** | >4.5/5 | User ratings/feedback |

---

## Implementation Priority

### Week 1:
- [ ] Task classification algorithm
- [ ] Subagent spawning logic
- [ ] Basic result aggregation

### Week 2:
- [ ] Dependency handling
- [ ] Error handling & retries
- [ ] User-facing progress updates

### Week 3:
- [ ] Metrics dashboard
- [ ] Performance optimization
- [ ] User feedback integration

---

## Recommended Next Steps

1. **Implement task classification** (30 min)
2. **Test with 6 sample tasks** (30 min)
3. **Measure parallel speedup** (15 min)
4. **Iterate based on results** (ongoing)

---

**Estimated Implementation Time:** 2-3 hours for basic version

**Expected Throughput Improvement:** 4-6x faster task completion

---

**Ready to implement?** I can start with Phase 1 (task classification) immediately.
