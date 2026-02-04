"""
Molt Tools Package

This package provides tools for agent integration with the operational memory system.

Modules:
    memory_tools: Tool functions that wrap OperationalMemory methods
    agent_integration: Helper class for agents to integrate with memory system
    file_consistency: FileConsistencyChecker for monitoring and conflict detection
    background_synthesis: BackgroundTaskManager for idle-time synthesis tasks

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

    # Using file consistency checker
    from tools.file_consistency import FileConsistencyChecker
    checker = FileConsistencyChecker(memory)
    checker.record_version("/path/to/file.md", "developer")
    conflicts = checker.detect_conflicts()

    # Using background synthesis
    from tools.background_synthesis import BackgroundTaskManager
    manager = BackgroundTaskManager(memory)
    manager.queue_task("graph_maintenance", priority="low")
    results = manager.run_synthesis_cycle()
"""

__version__ = "1.0.0"
__all__ = [
    "memory_tools",
    "agent_integration",
    "file_consistency",
    "background_synthesis",
]

# Import main classes for convenience
from . import memory_tools
from . import agent_integration
from . import file_consistency
from . import background_synthesis
from .agent_integration import AgentMemoryIntegration
from .file_consistency import (
    FileConsistencyChecker,
    FileConsistencyError,
    ConflictNotFoundError,
    create_file_consistency_checker,
    record_file_version,
    detect_and_escalate,
)
from .background_synthesis import (
    BackgroundTaskManager,
    BackgroundTaskError,
    TaskNotFoundError,
    create_background_task_manager,
    run_background_synthesis,
)
