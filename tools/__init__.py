"""
Molt Tools Package

This package provides tools for agent integration with the operational memory system.

Modules:
    memory_tools: Tool functions that wrap OperationalMemory methods
    agent_integration: Helper class for agents to integrate with memory system

Example Usage:
    # Using tools directly
    from tools.memory_tools import create_task, claim_task, complete_task
    task_id = create_task(
        delegated_by="main",
        assigned_to="developer",
        task_type="code_review",
        description="Review authentication module",
        priority="high"
    )

    # Using integration helper
    from tools.agent_integration import AgentMemoryIntegration
    memory = AgentMemoryIntegration("developer")
    task = memory.claim_next_task()
    if task:
        # Do work...
        memory.complete_and_notify(task['id'], {"approved": True})
"""

__version__ = "1.0.0"
__all__ = [
    "memory_tools",
    "agent_integration",
]

# Import main classes for convenience
from . import memory_tools
from . import agent_integration
from .agent_integration import AgentMemoryIntegration
