#!/usr/bin/env python3
"""
Kublai Task Report - Comprehensive data collection for reflections and system improvement.

Extends Neo4j schema with detailed task execution metrics, agent state, error analysis,
code/content changes, resource usage, quality signals, and context chain tracking.

Usage:
    from kublai_task_report import TaskReporter
    reporter = TaskReporter()
    reporter.record_task_execution(task_id, agent, execution_data)
    reporter.record_agent_state(agent, state_data)
    reporter.generate_task_report(task_id)
"""

import hashlib
import json
import os
import re
import sys
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_tracker, get_driver
from kurultai_paths import TASK_LEDGER, AGENTS_DIR
from kurultai_ledger import append_ledger


# ============================================================
# Extended Neo4j Schema Properties
# ============================================================

TASK_EXECUTION_PROPERTIES = {
    # Token usage
    "input_tokens": "integer",
    "output_tokens": "integer",
    "total_tokens": "integer",
    "token_cost_usd": "float",

    # Model settings
    "model_temperature": "float",
    "model_effort": "string",  # low, medium, high

    # Timing
    "retry_count": "integer",
    "timeout_threshold": "integer",  # seconds
    "actual_duration_seconds": "float",
    "estimated_duration_seconds": "float",

    # Skills and tools
    "skills_invoked": "list",
    "tools_used": "object",  # {tool_name: count}
}

AGENT_STATE_PROPERTIES = {
    # Context and memory
    "context_window_percent": "float",
    "memory_state_before": "string",  # hash of memory file
    "memory_state_after": "string",  # hash of memory file

    # Workload
    "queue_depth_at_start": "integer",
    "concurrent_tasks": "integer",

    # Health
    "health_flags": "list",  # ["stressed", "normal", "idle"]
}

ERROR_ANALYSIS_PROPERTIES = {
    # Categorization
    "error_category": "string",  # timeout, auth, model, network, verification, unknown
    "error_message_hash": "string",  # SHA256 for clustering
    "error_message_truncated": "string",  # First 500 chars

    # Recovery
    "recovery_attempts": "integer",
    "fallback_models_tried": "list",
    "recovery_success": "boolean",
}

CODE_CONTENT_PROPERTIES = {
    # Changes
    "lines_added": "integer",
    "lines_removed": "integer",
    "files_modified": "list",
    "files_created": "list",
    "files_deleted": "list",

    # By file type
    "code_lines_added": "integer",  # .py, .js, .ts, etc.
    "doc_lines_added": "integer",  # .md, .txt, etc.
    "test_lines_added": "integer",  # test_*.py, *.test.js, etc.

    # Coverage
    "test_coverage_before": "float",
    "test_coverage_after": "float",

    # Complexity
    "cyclomatic_complexity_delta": "integer",
    "function_count_delta": "integer",
}

RESOURCE_USAGE_PROPERTIES = {
    # System
    "cpu_time_seconds": "float",
    "cpu_peak_percent": "float",
    "memory_peak_mb": "float",
    "memory_avg_mb": "float",

    # API/Network
    "api_calls_count": "integer",
    "api_calls_by_service": "object",  # {service: count}
    "network_bytes_in": "integer",
    "network_bytes_out": "integer",

    # Disk
    "disk_read_mb": "float",
    "disk_write_mb": "float",
}

QUALITY_SIGNALS_PROPERTIES = {
    # Verification
    "verification_checks_passed": "integer",
    "verification_checks_failed": "integer",
    "verification_score": "float",  # 0-100

    # Rework
    "rework_required": "boolean",
    "followup_tasks_created": "list",  # task_ids
    "rework_reason": "string",
}

CONTEXT_CHAIN_PROPERTIES = {
    # Upstream
    "parent_task_id": "string",
    "triggered_by_event": "string",
    "root_cause_task_id": "string",

    # Downstream
    "downstream_tasks": "list",  # task_ids created by this task

    # Related
    "related_task_ids": "list",  # by keyword/graph similarity
    "task_graph_depth": "integer",
}


class TaskReporter:
    """Comprehensive task data collection and reporting."""

    def __init__(self):
        self.driver = get_driver()
        self.agents_dir = str(AGENTS_DIR)

    def close(self):
        """Close database connection."""
        self.driver.close()

    # ============================================================
    # Schema Initialization
    # ============================================================

    def ensure_schema(self):
        """Ensure all extended properties exist in Neo4j schema."""
        with self.driver.session() as session:
            # Create constraints for Task nodes
            session.run("""
                CREATE CONSTRAINT task_id_unique IF NOT EXISTS
                FOR (t:Task) REQUIRE t.task_id IS UNIQUE
            """)

            # Create indexes for common queries
            session.run("""
                CREATE INDEX task_agent_idx IF NOT EXISTS
                FOR (t:Task) ON (t.agent)
            """)
            session.run("""
                CREATE INDEX task_status_idx IF NOT EXISTS
                FOR (t:Task) ON (t.status)
            """)
            session.run("""
                CREATE INDEX task_created_idx IF NOT EXISTS
                FOR (t:Task) ON (t.created)
            """)
            session.run("""
                CREATE INDEX task_error_category_idx IF NOT EXISTS
                FOR (t:Task) ON (t.error_category)
            """)
            session.run("""
                CREATE INDEX task_parent_idx IF NOT EXISTS
                FOR (t:Task) ON (t.parent_task_id)
            """)

            # Create AgentState index
            session.run("""
                CREATE INDEX agent_state_ts_idx IF NOT EXISTS
                FOR (a:AgentState) ON (a.timestamp)
            """)

            # Create TaskReport index
            session.run("""
                CREATE INDEX task_report_idx IF NOT EXISTS
                FOR (r:TaskReport) ON (r.task_id)
            """)

    # ============================================================
    # Task Execution Recording
    # ============================================================

    def record_task_execution(self, task_id: str, agent: str, data: Dict[str, Any]):
        """Record task execution metrics.

        Args:
            task_id: The task ID
            agent: Agent name
            data: Dict with execution metrics:
                - input_tokens, output_tokens, total_tokens
                - model_temperature, model_effort
                - retry_count, timeout_threshold
                - actual_duration_seconds, estimated_duration_seconds
                - skills_invoked, tools_used
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.input_tokens = coalesce($input_tokens, t.input_tokens),
                    t.output_tokens = coalesce($output_tokens, t.output_tokens),
                    t.total_tokens = coalesce($total_tokens, t.total_tokens),
                    t.token_cost_usd = coalesce($token_cost_usd, t.token_cost_usd),
                    t.model_temperature = coalesce($model_temperature, t.model_temperature),
                    t.model_effort = coalesce($model_effort, t.model_effort),
                    t.retry_count = coalesce($retry_count, t.retry_count),
                    t.timeout_threshold = coalesce($timeout_threshold, t.timeout_threshold),
                    t.actual_duration_seconds = coalesce($actual_duration_seconds, t.actual_duration_seconds),
                    t.estimated_duration_seconds = coalesce($estimated_duration_seconds, t.estimated_duration_seconds),
                    t.skills_invoked = coalesce($skills_invoked, t.skills_invoked),
                    t.tools_used = coalesce($tools_used, t.tools_used),
                    t.execution_recorded = datetime()
            """,
            task_id=task_id,
            input_tokens=data.get("input_tokens"),
            output_tokens=data.get("output_tokens"),
            total_tokens=data.get("total_tokens"),
            token_cost_usd=data.get("token_cost_usd"),
            model_temperature=data.get("model_temperature"),
            model_effort=data.get("model_effort"),
            retry_count=data.get("retry_count"),
            timeout_threshold=data.get("timeout_threshold"),
            actual_duration_seconds=data.get("actual_duration_seconds"),
            estimated_duration_seconds=data.get("estimated_duration_seconds"),
            skills_invoked=data.get("skills_invoked"),
            tools_used=json.dumps(data.get("tools_used", {})) if data.get("tools_used") else None,
            )

    # ============================================================
    # Agent State Recording
    # ============================================================

    def record_agent_state(self, agent: str, data: Dict[str, Any], task_id: Optional[str] = None):
        """Record agent state snapshot.

        Args:
            agent: Agent name
            data: Dict with state metrics:
                - context_window_percent
                - memory_state_before, memory_state_after
                - queue_depth_at_start, concurrent_tasks
                - health_flags
            task_id: Optional associated task ID
        """
        state_id = f"{agent}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with self.driver.session() as session:
            # Create AgentState node
            session.run("""
                CREATE (a:AgentState {
                    state_id: $state_id,
                    agent: $agent,
                    context_window_percent: $context_window_percent,
                    memory_state_before: $memory_state_before,
                    memory_state_after: $memory_state_after,
                    queue_depth_at_start: $queue_depth_at_start,
                    concurrent_tasks: $concurrent_tasks,
                    health_flags: $health_flags,
                    task_id: $task_id,
                    timestamp: datetime()
                })
            """,
            state_id=state_id,
            agent=agent,
            context_window_percent=data.get("context_window_percent"),
            memory_state_before=data.get("memory_state_before"),
            memory_state_after=data.get("memory_state_after"),
            queue_depth_at_start=data.get("queue_depth_at_start"),
            concurrent_tasks=data.get("concurrent_tasks"),
            health_flags=data.get("health_flags"),
            task_id=task_id,
            )

    # ============================================================
    # Error Analysis Recording
    # ============================================================

    def record_error(self, task_id: str, data: Dict[str, Any]):
        """Record error analysis for failed task.

        Args:
            task_id: The task ID
            data: Dict with error data:
                - error_category (timeout, auth, model, network, verification, unknown)
                - error_message
                - recovery_attempts, fallback_models_tried, recovery_success
        """
        error_msg = data.get("error_message", "")
        error_hash = hashlib.sha256(error_msg.encode()).hexdigest()[:16]

        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.error_category = $error_category,
                    t.error_message_hash = $error_hash,
                    t.error_message_truncated = $error_message_truncated,
                    t.recovery_attempts = $recovery_attempts,
                    t.fallback_models_tried = $fallback_models_tried,
                    t.recovery_success = $recovery_success,
                    t.error_analyzed = datetime()
            """,
            task_id=task_id,
            error_category=data.get("error_category", "unknown"),
            error_hash=error_hash,
            error_message_truncated=error_msg[:500] if error_msg else None,
            recovery_attempts=data.get("recovery_attempts", 0),
            fallback_models_tried=data.get("fallback_models_tried", []),
            recovery_success=data.get("recovery_success", False),
            )

    # ============================================================
    # Code/Content Change Recording
    # ============================================================

    def record_code_changes(self, task_id: str, data: Dict[str, Any]):
        """Record code/content changes from task execution.

        Args:
            task_id: The task ID
            data: Dict with change data:
                - lines_added, lines_removed
                - files_modified, files_created, files_deleted
                - code_lines_added, doc_lines_added, test_lines_added
                - test_coverage_before, test_coverage_after
                - cyclomatic_complexity_delta, function_count_delta
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.lines_added = coalesce($lines_added, t.lines_added),
                    t.lines_removed = coalesce($lines_removed, t.lines_removed),
                    t.files_modified = coalesce($files_modified, t.files_modified),
                    t.files_created = coalesce($files_created, t.files_created),
                    t.files_deleted = coalesce($files_deleted, t.files_deleted),
                    t.code_lines_added = coalesce($code_lines_added, t.code_lines_added),
                    t.doc_lines_added = coalesce($doc_lines_added, t.doc_lines_added),
                    t.test_lines_added = coalesce($test_lines_added, t.test_lines_added),
                    t.test_coverage_before = coalesce($test_coverage_before, t.test_coverage_before),
                    t.test_coverage_after = coalesce($test_coverage_after, t.test_coverage_after),
                    t.cyclomatic_complexity_delta = coalesce($complexity_delta, t.complexity_delta),
                    t.function_count_delta = coalesce($function_delta, t.function_delta),
                    t.code_changes_recorded = datetime()
            """,
            task_id=task_id,
            lines_added=data.get("lines_added"),
            lines_removed=data.get("lines_removed"),
            files_modified=data.get("files_modified"),
            files_created=data.get("files_created"),
            files_deleted=data.get("files_deleted"),
            code_lines_added=data.get("code_lines_added"),
            doc_lines_added=data.get("doc_lines_added"),
            test_lines_added=data.get("test_lines_added"),
            test_coverage_before=data.get("test_coverage_before"),
            test_coverage_after=data.get("test_coverage_after"),
            complexity_delta=data.get("cyclomatic_complexity_delta"),
            function_delta=data.get("function_count_delta"),
            )

    # ============================================================
    # Resource Usage Recording
    # ============================================================

    def record_resource_usage(self, task_id: str, data: Dict[str, Any]):
        """Record resource usage from task execution.

        Args:
            task_id: The task ID
            data: Dict with resource data:
                - cpu_time_seconds, cpu_peak_percent
                - memory_peak_mb, memory_avg_mb
                - api_calls_count, api_calls_by_service
                - network_bytes_in, network_bytes_out
                - disk_read_mb, disk_write_mb
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.cpu_time_seconds = coalesce($cpu_time_seconds, t.cpu_time_seconds),
                    t.cpu_peak_percent = coalesce($cpu_peak_percent, t.cpu_peak_percent),
                    t.memory_peak_mb = coalesce($memory_peak_mb, t.memory_peak_mb),
                    t.memory_avg_mb = coalesce($memory_avg_mb, t.memory_avg_mb),
                    t.api_calls_count = coalesce($api_calls_count, t.api_calls_count),
                    t.api_calls_by_service = coalesce($api_calls_by_service, t.api_calls_by_service),
                    t.network_bytes_in = coalesce($network_bytes_in, t.network_bytes_in),
                    t.network_bytes_out = coalesce($network_bytes_out, t.network_bytes_out),
                    t.disk_read_mb = coalesce($disk_read_mb, t.disk_read_mb),
                    t.disk_write_mb = coalesce($disk_write_mb, t.disk_write_mb),
                    t.resources_recorded = datetime()
            """,
            task_id=task_id,
            cpu_time_seconds=data.get("cpu_time_seconds"),
            cpu_peak_percent=data.get("cpu_peak_percent"),
            memory_peak_mb=data.get("memory_peak_mb"),
            memory_avg_mb=data.get("memory_avg_mb"),
            api_calls_count=data.get("api_calls_count"),
            api_calls_by_service=json.dumps(data.get("api_calls_by_service", {})) if data.get("api_calls_by_service") else None,
            network_bytes_in=data.get("network_bytes_in"),
            network_bytes_out=data.get("network_bytes_out"),
            disk_read_mb=data.get("disk_read_mb"),
            disk_write_mb=data.get("disk_write_mb"),
            )

    # ============================================================
    # Quality Signals Recording
    # ============================================================

    def record_quality_signals(self, task_id: str, data: Dict[str, Any]):
        """Record quality signals from task execution.

        Args:
            task_id: The task ID
            data: Dict with quality data:
                - verification_checks_passed, verification_checks_failed
                - verification_score (0-100)
                - rework_required, followup_tasks_created, rework_reason
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.verification_checks_passed = coalesce($passed, t.passed),
                    t.verification_checks_failed = coalesce($failed, t.failed),
                    t.verification_score = coalesce($score, t.score),
                    t.rework_required = coalesce($rework_required, t.rework_required),
                    t.followup_tasks_created = coalesce($followups, t.followups),
                    t.rework_reason = coalesce($rework_reason, t.rework_reason),
                    t.quality_recorded = datetime()
            """,
            task_id=task_id,
            passed=data.get("verification_checks_passed"),
            failed=data.get("verification_checks_failed"),
            score=data.get("verification_score"),
            rework_required=data.get("rework_required"),
            followups=data.get("followup_tasks_created"),
            rework_reason=data.get("rework_reason"),
            )

    # ============================================================
    # Context Chain Recording
    # ============================================================

    def record_context_chain(self, task_id: str, data: Dict[str, Any]):
        """Record context chain relationships.

        Args:
            task_id: The task ID
            data: Dict with context data:
                - parent_task_id, triggered_by_event, root_cause_task_id
                - downstream_tasks
                - related_task_ids, task_graph_depth
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {task_id: $task_id})
                SET t.parent_task_id = coalesce($parent_task_id, t.parent_task_id),
                    t.triggered_by_event = coalesce($triggered_by_event, t.triggered_by_event),
                    t.root_cause_task_id = coalesce($root_cause_task_id, t.root_cause_task_id),
                    t.downstream_tasks = coalesce($downstream_tasks, t.downstream_tasks),
                    t.related_task_ids = coalesce($related_task_ids, t.related_task_ids),
                    t.task_graph_depth = coalesce($graph_depth, t.graph_depth),
                    t.context_recorded = datetime()
            """,
            task_id=task_id,
            parent_task_id=data.get("parent_task_id"),
            triggered_by_event=data.get("triggered_by_event"),
            root_cause_task_id=data.get("root_cause_task_id"),
            downstream_tasks=data.get("downstream_tasks"),
            related_task_ids=data.get("related_task_ids"),
            graph_depth=data.get("task_graph_depth"),
            )

            # Create relationships
            if data.get("parent_task_id"):
                session.run("""
                    MATCH (child:Task {task_id: $task_id})
                    MATCH (parent:Task {task_id: $parent_id})
                    MERGE (child)-[:CHILD_OF]->(parent)
                """, task_id=task_id, parent_id=data["parent_task_id"])

            if data.get("downstream_tasks"):
                for downstream_id in data["downstream_tasks"]:
                    session.run("""
                        MATCH (parent:Task {task_id: $task_id})
                        MATCH (child:Task {task_id: $child_id})
                        MERGE (parent)-[:CREATED]->(child)
                    """, task_id=task_id, child_id=downstream_id)

    # ============================================================
    # Task Report Generation
    # ============================================================

    def generate_task_report(self, task_id: str) -> Dict[str, Any]:
        """Generate comprehensive task report from Neo4j data.

        Returns dict with all collected metrics.
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task {task_id: $task_id})
                RETURN t
            """, task_id=task_id)

            record = result.single()
            if not record:
                return {"error": f"Task {task_id} not found"}

            task = record["t"]

            # Build report
            report = {
                "task_id": task_id,
                "report_generated": datetime.now().isoformat(),

                # Basic info
                "agent": task.get("agent"),
                "title": task.get("title"),
                "status": task.get("status"),
                "priority": task.get("priority"),
                "skill_hint": task.get("skill_hint"),

                # Execution metrics
                "execution": {
                    "input_tokens": task.get("input_tokens"),
                    "output_tokens": task.get("output_tokens"),
                    "total_tokens": task.get("total_tokens"),
                    "token_cost_usd": task.get("token_cost_usd"),
                    "model_temperature": task.get("model_temperature"),
                    "model_effort": task.get("model_effort"),
                    "retry_count": task.get("retry_count", 0),
                    "timeout_threshold": task.get("timeout_threshold"),
                    "actual_duration_seconds": task.get("actual_duration_seconds"),
                    "estimated_duration_seconds": task.get("estimated_duration_seconds"),
                    "skills_invoked": task.get("skills_invoked", []),
                    "tools_used": json.loads(task.get("tools_used", "{}") or "{}"),
                },

                # Error analysis (if failed)
                "error_analysis": {
                    "error_category": task.get("error_category"),
                    "error_message_hash": task.get("error_message_hash"),
                    "error_message": task.get("error_message_truncated"),
                    "recovery_attempts": task.get("recovery_attempts", 0),
                    "fallback_models_tried": task.get("fallback_models_tried", []),
                    "recovery_success": task.get("recovery_success"),
                } if task.get("status") == "FAILED" else None,

                # Code/content changes
                "code_changes": {
                    "lines_added": task.get("lines_added"),
                    "lines_removed": task.get("lines_removed"),
                    "files_modified": task.get("files_modified"),
                    "files_created": task.get("files_created"),
                    "files_deleted": task.get("files_deleted"),
                    "code_lines_added": task.get("code_lines_added"),
                    "doc_lines_added": task.get("doc_lines_added"),
                    "test_lines_added": task.get("test_lines_added"),
                    "test_coverage_delta": (task.get("test_coverage_after") or 0) - (task.get("test_coverage_before") or 0),
                    "complexity_delta": task.get("cyclomatic_complexity_delta"),
                    "function_delta": task.get("function_count_delta"),
                },

                # Resource usage
                "resources": {
                    "cpu_time_seconds": task.get("cpu_time_seconds"),
                    "cpu_peak_percent": task.get("cpu_peak_percent"),
                    "memory_peak_mb": task.get("memory_peak_mb"),
                    "memory_avg_mb": task.get("memory_avg_mb"),
                    "api_calls_count": task.get("api_calls_count"),
                    "network_bytes_in": task.get("network_bytes_in"),
                    "network_bytes_out": task.get("network_bytes_out"),
                    "disk_read_mb": task.get("disk_read_mb"),
                    "disk_write_mb": task.get("disk_write_mb"),
                },

                # Quality signals
                "quality": {
                    "verification_checks_passed": task.get("verification_checks_passed", 0),
                    "verification_checks_failed": task.get("verification_checks_failed", 0),
                    "verification_score": task.get("verification_score"),
                    "rework_required": task.get("rework_required", False),
                    "followup_tasks_created": task.get("followup_tasks_created", []),
                    "rework_reason": task.get("rework_reason"),
                },

                # Context chain
                "context_chain": {
                    "parent_task_id": task.get("parent_task_id"),
                    "triggered_by_event": task.get("triggered_by_event"),
                    "root_cause_task_id": task.get("root_cause_task_id"),
                    "downstream_tasks": task.get("downstream_tasks", []),
                    "related_task_ids": task.get("related_task_ids", []),
                    "task_graph_depth": task.get("task_graph_depth", 0),
                },
            }

            # Log TASK_REPORT_GENERATED event
            append_ledger({
                "task_id": task_id,
                "event": "TASK_REPORT_GENERATED",
                "ts": datetime.now().isoformat(),
                "agent": task.get("agent"),
                "report_summary": self._summarize_report(report),
            })

            # Create TaskReport node for aggregation
            session.run("""
                CREATE (r:TaskReport {
                    report_id: $report_id,
                    task_id: $task_id,
                    agent: $agent,
                    status: $status,
                    total_tokens: $total_tokens,
                    actual_duration: $actual_duration,
                    verification_score: $verification_score,
                    error_category: $error_category,
                    lines_changed: $lines_changed,
                    created: datetime()
                })
            """,
            report_id=f"report-{task_id}-{int(datetime.now().timestamp())}",
            task_id=task_id,
            agent=report["agent"],
            status=report["status"],
            total_tokens=report["execution"]["total_tokens"],
            actual_duration=report["execution"]["actual_duration_seconds"],
            verification_score=report["quality"]["verification_score"],
            error_category=report["error_analysis"]["error_category"] if report["error_analysis"] else None,
            lines_changed=(report["code_changes"]["lines_added"] or 0) + (report["code_changes"]["lines_removed"] or 0),
            )

            return report

    def _summarize_report(self, report: Dict) -> Dict:
        """Create compact summary for ledger."""
        return {
            "agent": report["agent"],
            "status": report["status"],
            "total_tokens": report["execution"]["total_tokens"],
            "duration_s": report["execution"]["actual_duration_seconds"],
            "verification_score": report["quality"]["verification_score"],
            "error_category": report["error_analysis"]["error_category"] if report["error_analysis"] else None,
        }

    # ============================================================
    # Aggregation Queries
    # ============================================================

    def aggregate_by_agent(self, hours: int = 24) -> List[Dict]:
        """Aggregate task metrics by agent."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                RETURN
                    t.agent AS agent,
                    count(t) AS total_tasks,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    sum(t.total_tokens) AS total_tokens,
                    sum(t.lines_added) AS total_lines_added,
                    avg(t.verification_score) AS avg_verification_score
                ORDER BY total_tasks DESC
            """, hours=hours)
            return [dict(r) for r in result]

    def aggregate_by_error_category(self, hours: int = 168) -> List[Dict]:
        """Aggregate failures by error category (7 days default)."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'FAILED'
                  AND t.created > datetime() - duration({hours: $hours})
                  AND t.error_category IS NOT NULL
                RETURN
                    t.error_category AS category,
                    count(t) AS failures,
                    count(DISTINCT t.error_message_hash) AS unique_errors,
                    avg(t.recovery_attempts) AS avg_recovery_attempts,
                    sum(CASE WHEN t.recovery_success THEN 1 ELSE 0 END) AS successful_recoveries
                ORDER BY failures DESC
            """, hours=hours)
            return [dict(r) for r in result]

    def aggregate_by_skill(self, hours: int = 168) -> List[Dict]:
        """Aggregate task metrics by skill hint."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.skill_hint IS NOT NULL
                  AND t.created > datetime() - duration({hours: $hours})
                RETURN
                    t.skill_hint AS skill,
                    count(t) AS invocations,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    avg(t.total_tokens) AS avg_tokens,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) AS failed
                ORDER BY invocations DESC
            """, hours=hours)
            return [dict(r) for r in result]

    def get_error_clusters(self, hours: int = 168, min_size: int = 2) -> List[Dict]:
        """Find recurring error patterns by message hash."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'FAILED'
                  AND t.error_message_hash IS NOT NULL
                  AND t.created > datetime() - duration({hours: $hours})
                WITH
                    t.error_message_hash AS error_hash,
                    t.error_message_truncated AS error_msg,
                    t.error_category AS category,
                    count(t) AS occurrences,
                    collect(DISTINCT t.agent) AS affected_agents
                WHERE occurrences >= $min_size
                RETURN
                    error_hash,
                    error_msg,
                    category,
                    occurrences,
                    affected_agents
                ORDER BY occurrences DESC
            """, hours=hours, min_size=min_size)
            return [dict(r) for r in result]

    def get_task_chain(self, task_id: str) -> Dict:
        """Get full context chain for a task."""
        with self.driver.session() as session:
            # Get ancestors
            ancestors = session.run("""
                MATCH (t:Task {task_id: $task_id})
                OPTIONAL MATCH path = (t)-[:CHILD_OF*]->(root:Task)
                RETURN
                    [node IN nodes(path) | node.task_id] AS ancestor_chain,
                    root.task_id AS root_task_id
            """, task_id=task_id).single()

            # Get descendants
            descendants = session.run("""
                MATCH (t:Task {task_id: $task_id})
                OPTIONAL MATCH path = (t)-[:CREATED*]->(descendant:Task)
                RETURN
                    collect(DISTINCT descendant.task_id) AS created_tasks
            """, task_id=task_id).single()

            return {
                "task_id": task_id,
                "ancestor_chain": ancestors["ancestor_chain"] if ancestors else [],
                "root_task_id": ancestors["root_task_id"] if ancestors else None,
                "created_tasks": descendants["created_tasks"] if descendants else [],
            }

    def get_reflection_summary(self, hours: int = 24) -> Dict:
        """Generate summary for hourly reflection."""
        with self.driver.session() as session:
            # Overall metrics
            overall = session.run("""
                MATCH (t:Task)
                WHERE t.created > datetime() - duration({hours: $hours})
                RETURN
                    count(t) AS total_tasks,
                    sum(CASE WHEN t.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    sum(CASE WHEN t.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                    avg(t.total_tokens) AS avg_tokens,
                    avg(t.actual_duration_seconds) AS avg_duration,
                    avg(t.verification_score) AS avg_quality
            """, hours=hours).single()

            # Top error categories
            errors = session.run("""
                MATCH (t:Task)
                WHERE t.status = 'FAILED'
                  AND t.created > datetime() - duration({hours: $hours})
                RETURN t.error_category AS category, count(t) AS count
                ORDER BY count DESC
                LIMIT 5
            """, hours=hours)

            # Most invoked skills
            skills = session.run("""
                MATCH (t:Task)
                WHERE t.skill_hint IS NOT NULL
                  AND t.created > datetime() - duration({hours: $hours})
                RETURN t.skill_hint AS skill, count(t) AS invocations
                ORDER BY invocations DESC
                LIMIT 5
            """, hours=hours)

            return {
                "period_hours": hours,
                "generated": datetime.now().isoformat(),
                "overall": dict(overall) if overall else {},
                "top_errors": [dict(r) for r in errors],
                "top_skills": [dict(r) for r in skills],
            }


# ============================================================
# Helper Functions
# ============================================================

def hash_memory_file(filepath: str) -> Optional[str]:
    """Compute SHA256 hash of memory file contents."""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except FileNotFoundError:
        return None


def count_queue_depth(agent: str) -> int:
    """Count pending tasks in agent queue."""
    agents_dir = str(AGENTS_DIR)
    queue_dir = f"{agents_dir}/{agent}/tasks"
    if not os.path.isdir(queue_dir):
        return 0

    count = 0
    for pattern in ['*.md', '*.executing.md']:
        for f in glob.glob(f"{queue_dir}/{pattern}"):
            if not f.endswith('.done.md'):
                count += 1
    return count


def estimate_token_cost(total_tokens: int, model: str = "claude-opus-4-6") -> float:
    """Estimate token cost in USD based on model pricing."""
    # Approximate pricing (per 1M tokens)
    pricing = {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    }

    rates = pricing.get(model, pricing["claude-opus-4-6"])
    # Rough estimate: 50% input, 50% output split
    return (total_tokens / 1_000_000) * ((rates["input"] + rates["output"]) / 2)


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Kublai Task Report - Comprehensive data collection")
    parser.add_argument("--task-id", help="Generate report for specific task ID")
    parser.add_argument("--agent", help="Generate aggregation for specific agent")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back (default: 24)")
    parser.add_argument("--errors", action="store_true", help="Show error category aggregation")
    parser.add_argument("--skills", action="store_true", help="Show skill hint aggregation")
    parser.add_argument("--clusters", action="store_true", help="Show error clusters")
    parser.add_argument("--reflection", action="store_true", help="Generate reflection summary")

    args = parser.parse_args()

    reporter = TaskReporter()

    try:
        if args.task_id:
            report = reporter.generate_task_report(args.task_id)
            print(json.dumps(report, indent=2, default=str))

        elif args.agent:
            agg = reporter.aggregate_by_agent(args.hours)
            print(json.dumps(agg, indent=2, default=str))

        elif args.errors:
            agg = reporter.aggregate_by_error_category(args.hours)
            print(json.dumps(agg, indent=2, default=str))

        elif args.skills:
            agg = reporter.aggregate_by_skill(args.hours)
            print(json.dumps(agg, indent=2, default=str))

        elif args.clusters:
            clusters = reporter.get_error_clusters(args.hours)
            print(json.dumps(clusters, indent=2, default=str))

        elif args.reflection:
            summary = reporter.get_reflection_summary(args.hours)
            print(json.dumps(summary, indent=2, default=str))

        else:
            # Default: show reflection summary
            summary = reporter.get_reflection_summary(args.hours)
            print(json.dumps(summary, indent=2, default=str))

    finally:
        reporter.close()
