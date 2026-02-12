# Code Review: Discord Context & Notion Task Execution Issues

**Review Date:** 2026-02-12
**Scope:** Discord bot_natural.py, Notion integration, Agent task execution
**Severity:** HIGH - Core functionality broken

---

## Issue 1: Discord Agents Can't Read Context / Say Irrelevant Nonsense

### 🔴 CRITICAL FINDINGS

#### 1.1 Hardcoded Template Responses (Line 350-550 in bot_natural.py)
**Problem:** Agents generate responses using `random.choice()` from predefined static templates that have ZERO connection to the actual message content.

```python
# Current broken implementation:
def _synthesis_addition(self) -> str: 
    return random.choice([
        "we're seeing convergence across multiple workstreams.",
        "this aligns with the broader strategic direction.",  # GENERIC
        "the pattern fits what we've been tracking.",  # NO ACTUAL PATTERN
    ])

# Response is just template + template + template:
responses = [
    f"@{trigger_message.author.split()[0]} raises a crucial point. {self._synthesis_addition()}",
]
```

**Impact:** Agents say things like "@Möngke raises a crucial point. we're seeing convergence across multiple workstreams" regardless of what Möngke actually said.

#### 1.2 No LLM/AI Integration for Response Generation
**Problem:** The bot NEVER calls any LLM to:
- Understand the message content
- Generate contextual responses
- Reference previous conversation
- Access agent knowledge

**Current Flow:**
```
Message Received → Keyword Match → Random Template → Send
```

**Required Flow:**
```
Message Received → Query Memories → LLM Context Build → Generate Response → Send
```

#### 1.3 Neo4j Memory Completely Disconnected
**Problem:** Despite having `neo4j_agent_memory.py` with full memory system, `bot_natural.py` NEVER queries it.

**Missing Integration:**
```python
# This NEVER happens in bot_natural.py:
from tools.kurultai.neo4j_agent_memory import get_task_context

# Get agent's relevant memories for this conversation
memories = get_task_context(agent_name, conversation_topic)
```

#### 1.4 Context Window Too Small & Not Used
**Problem:** `get_context()` returns last 5 messages truncated to 100 chars, but the templates don't actually use this context to generate meaningful responses.

#### 1.5 Value Scorer Over-Blocking
**Problem:** The 0.6 threshold in Value-First Protocol may be blocking legitimate conversations. The scorer doesn't understand context - it just keyword-matches.

---

## Issue 2: Notion Tasks Don't Lead to Actions

### 🔴 CRITICAL FINDINGS

#### 2.1 No Task Execution Router
**Problem:** `NotionIntegration` class creates tasks in Neo4j but NEVER routes them to agents for execution.

```python
# In notion_integration.py - Creates task but doesn't execute:
def create_neo4j_task_from_notion(self, notion_task):
    task_id = self.memory.create_task(...)  # Created!
    # ... but no code to actually DO the task
```

#### 2.2 Missing Agent Spawning Integration
**Problem:** There's no connection between Notion tasks and `sessions_spawn()` or any agent execution mechanism.

**File:** `tools/kurultai/agent_tasks.py` has background tasks but NO task-from-notion execution.

#### 2.3 Callbacks Defined But Never Connected
**Problem:** In `notion_integration.py`:
```python
self._on_new_task_callback: Optional[Callable] = None  # Never set!
self._on_status_change_callback: Optional[Callable] = None  # Never set!
```

These callbacks are never connected to an execution system.

#### 2.4 No Task-to-Agent Mapping Logic
**Problem:** While there's `ERROR_CLASSIFICATION` mapping errors to agents, there's NO mapping for task types to agents.

**Missing:**
```python
TASK_AGENT_MAPPING = {
    "research": "Möngke",
    "build": "Temüjin",
    "document": "Chagatai",
    "analyze": "Jochi",
    "ops": "Ögedei",
    "orchestrate": "Kublai",
}
```

#### 2.5 Polling Without Execution Loop
**Problem:** The polling mechanism finds tasks but doesn't have an execution loop:

```python
def poll_new_tasks(self) -> List[NotionTask]:
    # Finds new tasks
    new_tasks = [...]
    # Creates Neo4j tasks
    for task in new_tasks:
        self.create_neo4j_task_from_notion(task)
    # ... then what? Nothing executes them!
```

---

## Root Cause Diagram

```
DISCORD ISSUE:
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Message Received│────▶│ Keyword Matching │────▶│ Random Template │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                                               │
         ▼                                               ▼
┌─────────────────┐                           ┌──────────────────┐
│ Neo4j Memories  │◄───────────┬───────────────│ Generic Response │
│ (Not Queried)   │            │               └──────────────────┘
└─────────────────┘            │
                               │
┌─────────────────┐            │
│ LLM Context     │◄───────────┘ (Never Called)
│ (Not Generated) │
└─────────────────┘

NOTION ISSUE:
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Notion Task     │────▶│ Create Neo4j Task│────▶│ ???             │
│ Detected        │     │                  │     │ (No Execution)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                    ┌─────────────────────┐              │
                    │ Agent Should Execute│◄─────────────┘ (Never Happens)
                    │ (Not Implemented)   │
                    └─────────────────────┘
```

---

## Proposed Fix Architecture

### Fix 1.1: LLM-Powered Discord Responses
Replace template system with LLM context building:

```python
async def _generate_llm_response(self, agent: AgentRole, message: DiscordMessage) -> str:
    # 1. Query agent's memories from Neo4j
    memories = get_relevant_memories(agent.value, message.content)
    
    # 2. Build conversation context
    conversation_history = self.active_thread.get_context()
    
    # 3. Call LLM to generate contextual response
    prompt = f"""
    You are {AGENT_PERSONALITIES[agent].name}, {AGENT_PERSONALITIES[agent].voice_style}.
    
    CONVERSATION HISTORY:
    {conversation_history}
    
    YOUR RELEVANT MEMORIES:
    {memories}
    
    NEW MESSAGE FROM {message.author}: {message.content}
    
    Respond naturally, referencing specific points from the message and your memories.
    """
    
    response = await call_llm(prompt)
    return response
```

### Fix 1.2: Connect Neo4j Memory System
Integrate `neo4j_agent_memory.py` into `bot_natural.py`:

```python
from tools.kurultai.neo4j_agent_memory import Neo4jAgentMemory

class NaturalConversationBot:
    def __init__(self, ...):
        self.memory = Neo4jAgentMemory()
        
    async def _decide_response(self, message, ...):
        # Get agent's contextual memories
        context = self.memory.get_agent_context_for_task(agent_name, message.content)
        # Use context to inform response
```

### Fix 2.1: Task Execution Router
Create `tools/kurultai/task_executor.py`:

```python
class TaskExecutor:
    def __init__(self):
        self.agent_mapping = {
            "research": "Möngke",
            "build": "Temüjin",
            # ... etc
        }
    
    async def execute_task(self, task_id: str, task_type: str, description: str):
        agent = self.agent_mapping.get(task_type, "Kublai")
        
        # Spawn agent session via OpenClaw
        result = await sessions_spawn(
            agent_id=agent.lower(),
            task=f"Execute task {task_id}: {description}",
            label=f"notion-task-{task_id}"
        )
        
        # Update task status
        update_task_status(task_id, "in_progress")
        return result
```

### Fix 2.2: Connect Notion to Executor
Update `notion_integration.py`:

```python
def __init__(self, ...):
    from task_executor import TaskExecutor
    self.executor = TaskExecutor()
    self._on_new_task_callback = self._execute_new_task

def _execute_new_task(self, notion_task: NotionTask):
    # Auto-execute tasks based on type
    task_type = self._classify_task_type(notion_task.title)
    self.executor.execute_task(
        task_id=notion_task.neo4j_task_id,
        task_type=task_type,
        description=notion_task.title
    )
```

---

## Files Requiring Changes

| File | Changes Needed |
|------|----------------|
| `bot_natural.py` | Replace templates with LLM calls, add Neo4j memory queries |
| `neo4j_agent_memory.py` | Add conversation context method |
| `deliberation_client.py` | Add LLM client integration |
| `notion_integration.py` | Connect callbacks to executor |
| **NEW** `task_executor.py` | Create task routing & agent spawning |
| `agent_tasks.py` | Add task-from-notion execution |

---

## Priority Order

1. **P0:** Create TaskExecutor to make Notion tasks actually execute
2. **P0:** Integrate LLM into Discord bot for contextual responses
3. **P1:** Connect Neo4j memory to Discord bot
4. **P1:** Tune Value Scorer thresholds
5. **P2:** Add task classification to Notion integration

---

*Quid testa? Testa frangitur.*
