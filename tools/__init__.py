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
    backend_collaboration: BackendCodeReviewer for Jochi-Temüjin collaboration protocol
    failover_monitor: FailoverMonitor for Kublai failover to Ögedei
    notion_integration: NotionIntegration for bidirectional Notion sync
    monitoring: PrometheusMetrics and AlertManager for system monitoring

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

    # Using backend collaboration (Jochi-Temüjin protocol)
    from tools.backend_collaboration import BackendCodeReviewer
    reviewer = BackendCodeReviewer(memory)
    analysis_id = reviewer.create_backend_analysis(
        category="connection_pool",
        findings="Database connections not pooled",
        location="db.py:25",
        severity="critical",
        recommended_fix="Implement connection pooling"
    )

    # Using Notion integration
    from tools.notion_integration import NotionIntegration
    integration = NotionIntegration(memory)
    integration.start_polling()

    # Using monitoring
    from tools.monitoring import PrometheusMetrics, AlertManager, start_monitoring
    metrics, alert_manager = start_monitoring(port=9090)
    metrics.inc_task_created("main", "research")
    metrics.inc_task_completed("main", "research", duration=45.2)
    alerts = alert_manager.check_all(metrics)
    for alert in alerts:
        alert_manager.send_alert(alert)
"""

__version__ = "1.0.0"
__all__ = [
    "memory_tools",
    "agent_integration",
    "file_consistency",
    "background_synthesis",
    "reflection_memory",
    "meta_learning",
    "backend_collaboration",
    "failover_monitor",
    "notion_integration",
    "monitoring",
]

# Lazy imports to avoid numpy recursion issues during test collection
# The neo4j driver imports numpy which can cause RecursionError when pytest's -W error is enabled
_import_cache = {}


def __getattr__(name):
    """Lazy import modules and classes to avoid numpy recursion issues."""
    if name in _import_cache:
        return _import_cache[name]

    # Module imports
    if name == "memory_tools":
        from . import memory_tools as mod
        _import_cache[name] = mod
        return mod
    if name == "agent_integration":
        from . import agent_integration as mod
        _import_cache[name] = mod
        return mod
    if name == "file_consistency":
        from . import file_consistency as mod
        _import_cache[name] = mod
        return mod
    if name == "background_synthesis":
        from . import background_synthesis as mod
        _import_cache[name] = mod
        return mod
    if name == "reflection_memory":
        from . import reflection_memory as mod
        _import_cache[name] = mod
        return mod
    if name == "meta_learning":
        from . import meta_learning as mod
        _import_cache[name] = mod
        return mod
    if name == "backend_collaboration":
        from . import backend_collaboration as mod
        _import_cache[name] = mod
        return mod
    if name == "failover_monitor":
        from . import failover_monitor as mod
        _import_cache[name] = mod
        return mod
    if name == "notion_integration":
        from . import notion_integration as mod
        _import_cache[name] = mod
        return mod
    if name == "monitoring":
        from . import monitoring as mod
        _import_cache[name] = mod
        return mod

    # Class imports from agent_integration
    if name == "AgentMemoryIntegration":
        from .agent_integration import AgentMemoryIntegration as cls
        _import_cache[name] = cls
        return cls

    # Class imports from file_consistency
    if name == "FileConsistencyChecker":
        from .file_consistency import FileConsistencyChecker as cls
        _import_cache[name] = cls
        return cls
    if name == "FileConsistencyError":
        from .file_consistency import FileConsistencyError as cls
        _import_cache[name] = cls
        return cls
    if name == "ConflictNotFoundError":
        from .file_consistency import ConflictNotFoundError as cls
        _import_cache[name] = cls
        return cls
    if name == "create_file_consistency_checker":
        from .file_consistency import create_file_consistency_checker as fn
        _import_cache[name] = fn
        return fn
    if name == "record_file_version":
        from .file_consistency import record_file_version as fn
        _import_cache[name] = fn
        return fn
    if name == "detect_and_escalate":
        from .file_consistency import detect_and_escalate as fn
        _import_cache[name] = fn
        return fn

    # Class imports from background_synthesis
    if name == "BackgroundTaskManager":
        from .background_synthesis import BackgroundTaskManager as cls
        _import_cache[name] = cls
        return cls
    if name == "BackgroundTaskError":
        from .background_synthesis import BackgroundTaskError as cls
        _import_cache[name] = cls
        return cls
    if name == "TaskNotFoundError":
        from .background_synthesis import TaskNotFoundError as cls
        _import_cache[name] = cls
        return cls
    if name == "create_background_task_manager":
        from .background_synthesis import create_background_task_manager as fn
        _import_cache[name] = fn
        return fn
    if name == "run_background_synthesis":
        from .background_synthesis import run_background_synthesis as fn
        _import_cache[name] = fn
        return fn

    # Class imports from reflection_memory
    if name == "AgentReflectionMemory":
        from .reflection_memory import AgentReflectionMemory as cls
        _import_cache[name] = cls
        return cls
    if name == "ReflectionNotFoundError":
        from .reflection_memory import ReflectionNotFoundError as cls
        _import_cache[name] = cls
        return cls
    if name == "ReflectionError":
        from .reflection_memory import ReflectionError as cls
        _import_cache[name] = cls
        return cls
    if name == "create_reflection_memory":
        from .reflection_memory import create_reflection_memory as fn
        _import_cache[name] = fn
        return fn
    if name == "record_agent_mistake":
        from .reflection_memory import record_agent_mistake as fn
        _import_cache[name] = fn
        return fn

    # Class imports from meta_learning
    if name == "MetaLearningEngine":
        from .meta_learning import MetaLearningEngine as cls
        _import_cache[name] = cls
        return cls
    if name == "MetaRuleNotFoundError":
        from .meta_learning import MetaRuleNotFoundError as cls
        _import_cache[name] = cls
        return cls
    if name == "MetaRuleError":
        from .meta_learning import MetaRuleError as cls
        _import_cache[name] = cls
        return cls
    if name == "create_meta_learning_engine":
        from .meta_learning import create_meta_learning_engine as fn
        _import_cache[name] = fn
        return fn
    if name == "generate_and_create_metarule":
        from .meta_learning import generate_and_create_metarule as fn
        _import_cache[name] = fn
        return fn

    # Class imports from backend_collaboration
    if name == "BackendCodeReviewer":
        from .backend_collaboration import BackendCodeReviewer as cls
        _import_cache[name] = cls
        return cls

    # Class imports from failover_monitor
    if name == "FailoverMonitor":
        from .failover_monitor import FailoverMonitor as cls
        _import_cache[name] = cls
        return cls
    if name == "FailoverError":
        from .failover_monitor import FailoverError as cls
        _import_cache[name] = cls
        return cls
    if name == "create_failover_monitor":
        from .failover_monitor import create_failover_monitor as fn
        _import_cache[name] = fn
        return fn

    # Class imports from notion_integration
    if name == "NotionIntegration":
        from .notion_integration import NotionIntegration as cls
        _import_cache[name] = cls
        return cls
    if name == "NotionClient":
        from .notion_integration import NotionClient as cls
        _import_cache[name] = cls
        return cls
    if name == "NotionTask":
        from .notion_integration import NotionTask as cls
        _import_cache[name] = cls
        return cls
    if name == "Checkpoint":
        from .notion_integration import Checkpoint as cls
        _import_cache[name] = cls
        return cls
    if name == "create_notion_integration":
        from .notion_integration import create_notion_integration as fn
        _import_cache[name] = fn
        return fn

    # Class imports from monitoring
    if name == "PrometheusMetrics":
        from .monitoring import PrometheusMetrics as cls
        _import_cache[name] = cls
        return cls
    if name == "AlertManager":
        from .monitoring import AlertManager as cls
        _import_cache[name] = cls
        return cls
    if name == "Alert":
        from .monitoring import Alert as cls
        _import_cache[name] = cls
        return cls
    if name == "MetricsRegistry":
        from .monitoring import MetricsRegistry as cls
        _import_cache[name] = cls
        return cls
    if name == "get_registry":
        from .monitoring import get_registry as fn
        _import_cache[name] = fn
        return fn
    if name == "create_monitoring":
        from .monitoring import create_monitoring as fn
        _import_cache[name] = fn
        return fn
    if name == "start_monitoring":
        from .monitoring import start_monitoring as fn
        _import_cache[name] = fn
        return fn

    raise AttributeError(f"module 'tools' has no attribute '{name}'")
