"""
Molt Tools Package

This package provides tools for agent integration with the operational memory system.

Modules:
    memory_tools: Tool functions that wrap OperationalMemory methods
    agent_integration: Helper class for agents to integrate with memory system
    file_consistency: FileConsistencyChecker for monitoring and conflict detection
    background_synthesis: BackgroundTaskManager for idle-time synthesis tasks
    reflection_memory: AgentReflectionMemory for recording agent mistakes
    meta_learning: MetaLearningEngine for generating MetaRules from reflections

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

    # Using reflection memory
    from tools.reflection_memory import AgentReflectionMemory
    reflection_memory = AgentReflectionMemory(memory)
    reflection_id = reflection_memory.record_mistake(
        agent="developer",
        mistake_type="security",
        context="Implementing authentication",
        expected_behavior="Password should be hashed",
        actual_behavior="Password stored in plaintext",
        root_cause="Forgot to call hash function",
        lesson="Always use hash_password() before storage"
    )

    # Using meta learning engine
    from tools.meta_learning import MetaLearningEngine
    meta_engine = MetaLearningEngine(memory, reflection_memory)
    rule_id = meta_engine.create_metarule(
        rule_content="NEVER store passwords in plaintext",
        rule_type="absolute",
        source_reflections=[reflection_id]
    )
    meta_engine.approve_metarule(rule_id, approved_by="main")
"""

__version__ = "1.0.0"
__all__ = [
    "memory_tools",
    "agent_integration",
    "file_consistency",
    "background_synthesis",
    "reflection_memory",
    "meta_learning",
]

# Import main classes for convenience
from . import memory_tools
from . import agent_integration
from . import file_consistency
from . import background_synthesis
from . import reflection_memory
from . import meta_learning
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
from .reflection_memory import (
    AgentReflectionMemory,
    ReflectionNotFoundError,
    ReflectionError,
    create_reflection_memory,
    record_agent_mistake,
)
from .meta_learning import (
    MetaLearningEngine,
    MetaRuleNotFoundError,
    MetaRuleError,
    create_meta_learning_engine,
    generate_and_create_metarule,
)
