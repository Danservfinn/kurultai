# TaskExecutor Design for Notion→Agent Execution

## Problem
Notion tasks are created in Neo4j but never routed to agents for actual execution. The `NotionIntegration` class has `_on_new_task_callback` defined but never connected.

## Solution: TaskExecutor Class

```python
# tools/kurultai/task_executor.py

import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("kurultai.task_executor")


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskAssignment:
    task_id: str
    task_type: str
    description: str
    assigned_agent: str
    priority: str
    created_at: datetime
    notion_page_id: Optional[str] = None


class TaskExecutor:
    """
    Routes Notion/Neo4j tasks to appropriate agents for execution.
    
    Maps task types to specialist agents:
    - research → Möngke
    - build/implementation → Temüjin  
    - documentation → Chagatai
    - analysis/security → Jochi
    - operations → Ögedei
    - orchestration → Kublai
    """
    
    # Task type → Agent mapping
    TASK_AGENT_MAPPING = {
        "research": "Möngke",
        "analyze": "Möngke",
        "investigate": "Möngke",
        "build": "Temüjin",
        "implement": "Temüjin",
        "code": "Temüjin",
        "develop": "Temüjin",
        "document": "Chagatai",
        "write": "Chagatai",
        "capture": "Chagatai",
        "audit": "Jochi",
        "security": "Jochi",
        "test": "Jochi",
        "validate": "Jochi",
        "ops": "Ögedei",
        "monitor": "Ögedei",
        "health": "Ögedei",
        "sync": "Ögedei",
        "orchestrate": "Kublai",
        "coordinate": "Kublai",
        "synthesize": "Kublai",
        "route": "Kublai",
    }
    
    # Agent ID mapping for sessions_spawn
    AGENT_ID_MAPPING = {
        "Möngke": "main",      # Use main session as Möngke
        "Chagatai": "main",
        "Temüjin": "main",
        "Jochi": "main",
        "Ögedei": "main",
        "Kublai": "main",      # Router uses main
    }
    
    def __init__(self, memory=None, notion_integration=None):
        self.memory = memory
        self.notion = notion_integration
        self.active_tasks: Dict[str, TaskAssignment] = {}
        self._status_callbacks: List[Callable] = []
        
    def classify_task(self, description: str) -> str:
        """
        Classify task description to determine agent assignment.
        
        Returns agent name (e.g., "Möngke", "Temüjin")
        """
        desc_lower = description.lower()
        
        # Score each agent type based on keyword matches
        scores = {agent: 0 for agent in set(self.TASK_AGENT_MAPPING.values())}
        
        for keyword, agent in self.TASK_AGENT_MAPPING.items():
            if keyword in desc_lower:
                scores[agent] += 1
                
        # Return highest scoring agent, default to Kublai
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return "Kublai"
    
    async def execute_task(self, task_id: str, description: str, 
                          priority: str = "normal",
                          notion_page_id: Optional[str] = None) -> str:
        """
        Execute a task by spawning the appropriate agent.
        
        Args:
            task_id: Neo4j task ID
            description: Task description
            priority: Task priority (critical, high, normal, low)
            notion_page_id: Optional Notion page ID for status updates
            
        Returns:
            assigned_agent: Name of agent assigned to task
        """
        # Classify task to determine agent
        agent_name = self.classify_task(description)
        task_type = self._extract_task_type(description)
        
        assignment = TaskAssignment(
            task_id=task_id,
            task_type=task_type,
            description=description,
            assigned_agent=agent_name,
            priority=priority,
            created_at=datetime.utcnow(),
            notion_page_id=notion_page_id
        )
        
        self.active_tasks[task_id] = assignment
        
        logger.info(f"🎯 Task {task_id} assigned to {agent_name}: {description[:60]}...")
        
        # Update status to "In Progress"
        await self._update_task_status(task_id, TaskStatus.ASSIGNED)
        
        # Spawn agent to execute task
        asyncio.create_task(self._spawn_agent_execution(assignment))
        
        return agent_name
    
    def _extract_task_type(self, description: str) -> str:
        """Extract task type from description."""
        desc_lower = description.lower()
        for keyword in self.TASK_AGENT_MAPPING.keys():
            if keyword in desc_lower:
                return keyword
        return "general"
    
    async def _spawn_agent_execution(self, assignment: TaskAssignment):
        """
        Spawn an agent session to execute the task.
        """
        try:
            # Import here to avoid circular dependencies
            from tools.openclaw_gateway import sessions_spawn
            
            # Build task prompt with context
            task_prompt = self._build_task_prompt(assignment)
            
            # Spawn agent session
            agent_id = self.AGENT_ID_MAPPING.get(assignment.assigned_agent, "main")
            
            logger.info(f"🚀 Spawning {assignment.assigned_agent} for task {assignment.task_id}")
            
            # Use sessions_spawn to execute task
            # Note: sessions_spawn is synchronous, run in executor
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: sessions_spawn(
                    task=task_prompt,
                    agent_id=agent_id,
                    label=f"task-{assignment.task_id}",
                    timeout_seconds=300  # 5 minute timeout
                )
            )
            
            # Handle completion
            await self._handle_task_completion(assignment, result)
            
        except Exception as e:
            logger.error(f"❌ Task execution failed for {assignment.task_id}: {e}")
            await self._handle_task_failure(assignment, str(e))
    
    def _build_task_prompt(self, assignment: TaskAssignment) -> str:
        """Build the task prompt for the agent."""
        persona = self._get_agent_persona(assignment.assigned_agent)
        
        prompt = f"""You are {assignment.assigned_agent}, {persona['role']}.

YOUR MISSION: {assignment.description}

Task ID: {assignment.task_id}
Priority: {assignment.priority}
Task Type: {assignment.task_type}

{persona['instructions']}

INSTRUCTIONS:
1. Execute the task completely
2. Report your findings/actions
3. Mark the task as complete when done
4. If you need help, ask Kublai

BEGIN TASK EXECUTION:"""
        
        return prompt
    
    def _get_agent_persona(self, agent_name: str) -> Dict:
        """Get persona instructions for agent."""
        personas = {
            "Möngke": {
                "role": "the Council's researcher and pattern analyst",
                "instructions": "Research thoroughly. Find patterns others miss. Document your findings clearly."
            },
            "Temüjin": {
                "role": "the Council's builder and implementer", 
                "instructions": "Build working solutions. Test your code. Document how to use what you create."
            },
            "Chagatai": {
                "role": "the Council's chronicler and documentarian",
                "instructions": "Write clearly and comprehensively. Capture insights for future agents."
            },
            "Jochi": {
                "role": "the Council's security analyst",
                "instructions": "Validate thoroughly. Test edge cases. Report risks and vulnerabilities."
            },
            "Ögedei": {
                "role": "the Council's operations monitor",
                "instructions": "Monitor systems. Fix issues proactively. Keep operations smooth."
            },
            "Kublai": {
                "role": "the Council's orchestrator",
                "instructions": "Coordinate effectively. Route to specialists when needed. Synthesize findings."
            },
        }
        return personas.get(agent_name, {
            "role": "a member of the Kurultai Council",
            "instructions": "Execute the task competently. Report your results."
        })
    
    async def _handle_task_completion(self, assignment: TaskAssignment, result: Dict):
        """Handle successful task completion."""
        logger.info(f"✅ Task {assignment.task_id} completed by {assignment.assigned_agent}")
        
        # Update Neo4j status
        await self._update_task_status(assignment.task_id, TaskStatus.COMPLETED)
        
        # Update Notion if linked
        if assignment.notion_page_id and self.notion:
            await self._update_notion_status(assignment.notion_page_id, "Done")
        
        # Record completion memory
        if self.memory:
            await self._record_task_memory(assignment, result, success=True)
        
        # Notify callbacks
        for callback in self._status_callbacks:
            try:
                callback(assignment.task_id, "completed", assignment.assigned_agent)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
        
        # Clean up
        del self.active_tasks[assignment.task_id]
    
    async def _handle_task_failure(self, assignment: TaskAssignment, error: str):
        """Handle task failure."""
        logger.error(f"❌ Task {assignment.task_id} failed: {error}")
        
        # Update status
        await self._update_task_status(assignment.task_id, TaskStatus.FAILED)
        
        # Update Notion
        if assignment.notion_page_id and self.notion:
            await self._update_notion_status(assignment.notion_page_id, "Blocked")
        
        # Record failure memory
        if self.memory:
            await self._record_task_memory(assignment, {"error": error}, success=False)
        
        # Notify
        for callback in self._status_callbacks:
            try:
                callback(assignment.task_id, "failed", assignment.assigned_agent, error)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
        
        del self.active_tasks[assignment.task_id]
    
    async def _update_task_status(self, task_id: str, status: TaskStatus):
        """Update task status in Neo4j."""
        if not self.memory:
            return
        try:
            self.memory.update_task_status(task_id, status.value)
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
    
    async def _update_notion_status(self, page_id: str, status: str):
        """Update Notion task status."""
        if not self.notion:
            return
        try:
            self.notion.update_notion_task_status(page_id, status)
        except Exception as e:
            logger.error(f"Failed to update Notion status: {e}")
    
    async def _record_task_memory(self, assignment: TaskAssignment, 
                                  result: Dict, success: bool):
        """Record task completion in agent memory."""
        try:
            from tools.kurultai.neo4j_agent_memory import AgentMemoryEntry
            
            memory_type = "learning" if success else "observation"
            content = f"Task {assignment.task_id} ({assignment.task_type}): {assignment.description[:100]}... "
            content += f"Result: {'Success' if success else 'Failed'}"
            if not success and 'error' in result:
                content += f" - Error: {result['error'][:100]}"
            
            entry = AgentMemoryEntry(
                id=f"{assignment.assigned_agent.lower()}-task-{assignment.task_id}",
                agent_name=assignment.assigned_agent,
                memory_type=memory_type,
                content=content,
                source_task_id=assignment.task_id,
                importance=0.7 if success else 0.8,
                tags=[assignment.task_type, "notion" if assignment.notion_page_id else "internal"]
            )
            
            # Use memory system to store
            if hasattr(self.memory, 'record_agent_memory'):
                self.memory.record_agent_memory(entry)
                
        except Exception as e:
            logger.error(f"Failed to record task memory: {e}")
    
    def on_status_change(self, callback: Callable):
        """Register a callback for task status changes."""
        self._status_callbacks.append(callback)
    
    def get_active_tasks(self) -> List[TaskAssignment]:
        """Get list of currently active tasks."""
        return list(self.active_tasks.values())
    
    async def retry_failed_task(self, task_id: str) -> bool:
        """Retry a previously failed task."""
        # Get task from Neo4j
        if not self.memory:
            return False
            
        try:
            task = self.memory.get_task(task_id)
            if not task:
                return False
                
            return await self.execute_task(
                task_id=task_id,
                description=task.get('description', ''),
                priority=task.get('priority', 'normal'),
                notion_page_id=task.get('notion_page_id')
            )
        except Exception as e:
            logger.error(f"Failed to retry task {task_id}: {e}")
            return False


# ============================================================================
# Integration with NotionIntegration
# ============================================================================

def connect_executor_to_notion(notion_integration, task_executor):
    """
    Connect TaskExecutor to NotionIntegration callbacks.
    
    Usage:
        notion = NotionIntegration(memory)
        executor = TaskExecutor(memory, notion)
        connect_executor_to_notion(notion, executor)
        notion.start_polling()
    """
    
    def on_new_task(notion_task):
        """Callback when new Notion task detected."""
        asyncio.create_task(task_executor.execute_task(
            task_id=notion_task.neo4j_task_id,
            description=notion_task.title,
            priority=notion_task.priority,
            notion_page_id=notion_task.id
        ))
    
    def on_status_change(task_id, old_status, new_status):
        """Callback when task status changes."""
        logger.info(f"Task {task_id} status: {old_status} -> {new_status}")
    
    # Connect callbacks
    notion_integration._on_new_task_callback = on_new_task
    notion_integration._on_status_change_callback = on_status_change
    task_executor.on_status_change(on_status_change)
    
    logger.info("✅ TaskExecutor connected to NotionIntegration")


# ============================================================================
# Example Usage
# ============================================================================

async def example():
    """Example of using TaskExecutor."""
    from tools.kurultai.neo4j_memory import OperationalMemory
    from tools.notion_integration import NotionIntegration
    
    # Initialize systems
    memory = OperationalMemory()
    notion = NotionIntegration(memory)
    executor = TaskExecutor(memory, notion)
    
    # Connect them
    connect_executor_to_notion(notion, executor)
    
    # Start polling (this will auto-execute new tasks)
    notion.start_polling()
    
    # Or manually execute a task
    await executor.execute_task(
        task_id="task-123",
        description="Research the Clawnch ecosystem and document findings",
        priority="high",
        notion_page_id="page-456"
    )


if __name__ == "__main__":
    asyncio.run(example())
```

## Integration Points

### 1. NotionIntegration Changes

```python
# In notion_integration.py, update __init__:

def __init__(self, memory, ...):
    # ... existing code ...
    
    # Initialize task executor if available
    try:
        from tools.kurultai.task_executor import TaskExecutor, connect_executor_to_notion
        self.task_executor = TaskExecutor(memory, self)
        connect_executor_to_notion(self, self.task_executor)
    except ImportError:
        self.task_executor = None
        logger.warning("TaskExecutor not available")
```

### 2. Environment Configuration

```bash
# .env
KURULTAI_AUTO_EXECUTE_TASKS=true
KURULTAI_TASK_TIMEOUT_SECONDS=300
KURULTAI_MAX_CONCURRENT_TASKS=3
```

## Task Execution Flow

```
Notion Task Created
    ↓
NotionIntegration.poll_new_tasks()
    ↓
NotionIntegration.create_neo4j_task_from_notion()
    ↓
Callback: _on_new_task_callback
    ↓
TaskExecutor.execute_task()
    ↓
TaskExecutor.classify_task() → determines agent
    ↓
TaskExecutor._spawn_agent_execution()
    ↓
sessions_spawn() → spawns agent
    ↓
Agent executes task
    ↓
Task completion/failure
    ↓
Update Neo4j + Notion status
    ↓
Record memory of completion
```

## Key Features

1. **Automatic Classification**: Tasks classified by keywords (research→Möngke, build→Temüjin, etc.)
2. **Agent Spawning**: Uses `sessions_spawn()` to execute tasks in isolated sessions
3. **Status Tracking**: Updates both Neo4j and Notion as tasks progress
4. **Memory Recording**: Records task completion as agent memories
5. **Failure Handling**: Retries, error logging, status updates
6. **Callbacks**: Status change notifications for external systems

## Files Modified

| File | Changes |
|------|---------|
| `tools/kurultai/task_executor.py` | New file - TaskExecutor class |
| `tools/notion_integration.py` | Connect executor in `__init__` |

## Dependencies

- `sessions_spawn` from OpenClaw gateway
- Neo4j memory system
- Notion integration (optional)
