#!/usr/bin/env python3
"""
Central registry of all script filenames in the Kurultai system.

This prevents filename mismatch bugs (e.g., task-report-hook.py vs task_report_hook.py)
by providing a single source of truth for all script references.

Usage:
    from scripts.script_paths import SCRIPTS
    hook_path = Path(__file__).parent / SCRIPTS["task_report_hook"]
"""

from pathlib import Path
from typing import Dict

# All script filenames - use underscores for Python modules, hyphens for CLI tools
SCRIPTS: Dict[str, str] = {
    # Task processing
    "task_watcher": "task-watcher.py",
    "task_report_hook": "task_report_hook.py",
    "task_report_aggregator": "task_report_aggregator.py",
    "task_intake": "task_intake.py",
    "task_utils": "task_utils.py",
    "task_retry_api": "task_retry_api.py",
    "task_retry_service": "task_retry_service.py",
    "task_verification": "task_verification.py",
    "task_completion_standard": "task_completion_standard.py",
    
    # Voting & proposals
    "kurultai_voting": "kurultai_voting.py",
    "voting_manager": "voting_manager.py",
    "proposal_generator": "proposal_generator.py",
    "proposal_audit": "proposal_audit.py",
    "proposal_rollback": "proposal_rollback.py",
    
    # Reflection & review
    "meta_reflection": "meta_reflection.py",
    "review_with_fallback": "review-with-fallback.py",
    "reflection_anomaly_scanner": "reflection_anomaly_scanner.py",
    "reflection_model_check": "reflection_model_check.py",
    "reflection_proposal_tracker": "reflection_proposal_tracker.py",
    "generate_hourly_report": "generate_hourly_report.py",
    "report_analyzer": "report_analyzer.py",
    
    # Routing
    "routing_engine": "routing_engine.py",
    "routing_analytics": "routing_analytics.py",
    "routing_anomaly_detector": "routing_anomaly_detector.py",
    "route_quality_tracker": "route_quality_tracker.py",
    "routing_audit_action": "routing_audit_action.py",
    
    # Neo4j & memory
    "neo4j_utils": "neo4j_utils.py",
    "neo4j_schema_init": "neo4j_schema_init.py",
    "neo4j_schema_integration": "neo4j_schema_integration.py",
    "neo4j_atomic_transitions": "neo4j_atomic_transitions.py",
    "neo4j_backfill_filesystem": "neo4j-backfill-filesystem.py",
    "neo4j_fix_data_integrity": "neo4j-fix-data-integrity.py",
    "memory_audit": "memory_audit.py",
    "memory_pruner": "memory_pruner.py",
    "memory_rules_lifecycle": "memory_rules_lifecycle.py",
    
    # Agents & orchestration
    "kublai_actions": "kublai-actions.py",
    "kublai_initiative": "kublai-initiative.py",
    "kublai_task_report": "kublai_task_report.py",
    "agent_task_handler": "agent-task-handler.py",
    
    # Monitoring & health
    "ogedei_watchdog": "ogedei-watchdog.py",
    "watchdog_gather": "watchdog-gather.sh",
    "kurultai_monitor": "kurultai-monitor.py",
    "credential_health_monitor": "credential-health-monitor.py",
    
    # Skills & evaluation
    "score_skills": "score_skills.py",
    "update_skill_stats": "update_skill_stats.py",
    "action_scorer": "action_scorer.py",
    "evaluation_engine": "evaluation_engine.py",
    "hypothesis_generator": "hypothesis_generator.py",
    
    # Experiments
    "experiment_tracker": "experiment_tracker.py",
    "experiment_pool": "experiment-pool.py",
    "experiment_pool_status": "experiment-pool-status.py",
    "experiment_health_monitor": "experiment_health_monitor.py",
    
    # Rules & compliance
    "cross_agent_rules": "cross_agent_rules.py",
    "parse_rule_compliance": "parse_rule_compliance.py",
    "rule_lifecycle_audit": "rule_lifecycle_audit.py",
    
    # Model & session
    "session_model_drift_detector": "session_model_drift_detector.py",
    "get_model": "get_model.py",
    "model_drift_detector": "model_drift_detector.py",
    "subprocess_health_check": "subprocess_health_check.py",
    "subprocess_manager": "subprocess_manager.py",
    
    # Gate & ledger
    "gate_timeouts": "gate_timeouts.py",
    "gate_timeout_watchdog": "gate-timeout-watchdog.py",
    
    # Privacy & conversation
    "conversation_privacy": "conversation_privacy.py",
    "conversation_logger": "conversation_logger.py",
    "conversation_search": "conversation_search.py",
    "conversation_api": "conversation_api.py",
    "privacy_request_processor": "privacy_request_processor.py",
    
    # X/Twitter
    "x_client": "x_client.py",
    "x_queue": "x_queue.py",
    
    # Misc utilities
    "metrics": "metrics.py",
    "load_monitor": "load_monitor.py",
    "time_utils": "time_utils.py",
    "retry_utils": "retry_utils.py",
    "thread_safe_state": "thread_safe_state.py",
    "json_registry": "json_registry.py",
    "file_locking": "file_locking.py",
    "dashboard_utils": "dashboard_utils.py",
    "monitoring_utils": "monitoring_utils.py",
    "pre_submit_check": "pre_submit_check.py",
    "validate_completion_report": "validate_completion_report.py",
    "validate_mongke_routing": "validate_mongke_routing.py",
    "validate_fallback_chain": "validate-fallback-chain.sh",
    "jochi_verify": "jochi-verify.py",
    "cleanup_task_extensions": "cleanup_task_extensions.py",
    "clear_neo4j_session_key": "clear_neo4j_session_key.py",
    "fix_missing_resolutions": "fix-missing-resolutions.py",
    "audit_missing_resolutions": "audit_missing_resolutions.py",
    "fix_cron_model": "fix-cron-model.py",
    "rollback_manager": "rollback-manager.py",
    "git_branch_manager": "git_branch_manager.py",
    "git_operation_monitor": "git-operation-monitor.py",
    
    # Shell scripts
    "hourly_reflection": "hourly_reflection.sh",
    "run_brainstorm": "run_brainstorm.sh",
    "run_kurultai_reflect": "run_kurultai_reflect.sh",
    "backup_kurultai": "backup-kurultai.sh",
    "test_fastapi_server": "test_fastapi_server.sh",
}


def get_script_path(script_name: str, base_dir: Path = None) -> Path:
    """
    Get the full path to a script by name.
    
    Args:
        script_name: Key from SCRIPTS dict (e.g., "task_report_hook")
        base_dir: Base directory (defaults to scripts/ directory)
    
    Returns:
        Full Path to the script
    
    Raises:
        KeyError: If script_name not in SCRIPTS
    """
    if base_dir is None:
        base_dir = Path(__file__).parent
    
    if script_name not in SCRIPTS:
        raise KeyError(f"Unknown script: {script_name}. Available: {list(SCRIPTS.keys())}")
    
    return base_dir / SCRIPTS[script_name]


def validate_all_scripts_exist(base_dir: Path = None) -> list:
    """
    Check that all scripts in SCRIPTS dict actually exist.
    
    Returns:
        List of missing script paths (empty if all exist)
    """
    if base_dir is None:
        base_dir = Path(__file__).parent
    
    missing = []
    for name, filename in SCRIPTS.items():
        path = base_dir / filename
        if not path.exists():
            missing.append(str(path))
    
    return missing


if __name__ == "__main__":
    # Self-test: validate all scripts exist
    missing = validate_all_scripts_exist()
    if missing:
        print("MISSING SCRIPTS:")
        for path in missing:
            print(f"  - {path}")
        exit(1)
    else:
        print(f"All {len(SCRIPTS)} scripts found ✓")
        exit(0)
