"""
Jochi Backend Issue Identification Protocol (Phase 4.6)

This module implements Jochi's backend issue identification and analysis protocol
for the multi-agent system. Jochi analyzes performance metrics, identifies backend
issues, and collaborates with Temüjin on code-level investigations.
"""

import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

# Configure logging
logger = logging.getLogger(__name__)


class BackendAnalysisProtocol:
    """Jochi's backend issue identification and analysis protocol.

    This class implements the Phase 4.6 protocol for identifying backend issues,
    analyzing performance metrics, and managing Analysis nodes in Neo4j.
    Collaborates with Temüjin (developer) for code-level investigations.

    Attributes:
        memory: OperationalMemory instance for Neo4j interactions
        agent_id: Jochi's agent identifier
    """

    # Issue severity levels
    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"

    # Analysis types
    TYPE_PERFORMANCE = "performance"
    TYPE_ERROR = "error"
    TYPE_SECURITY = "security"
    TYPE_CAPACITY = "capacity"
    TYPE_BACKEND_ISSUE = "backend_issue"

    # Analysis status values
    STATUS_OPEN = "open"
    STATUS_INVESTIGATING = "investigating"
    STATUS_RESOLVED = "resolved"
    STATUS_IDENTIFIED = "identified"

    # Issue categories for backend analysis
    CATEGORY_CONNECTION_POOL = "connection_pool"
    CATEGORY_RESILIENCE = "resilience"
    CATEGORY_DATA_INTEGRITY = "data_integrity"
    CATEGORY_PERFORMANCE = "performance"
    CATEGORY_SECURITY = "security"

    # Performance thresholds (from Jochi SOUL)
    THRESHOLDS = {
        "response_time_warning": 500,  # ms
        "response_time_critical": 1000,  # ms
        "response_time_emergency": 2000,  # ms
        "error_rate_warning": 0.01,  # 1%
        "error_rate_critical": 0.05,  # 5%
        "error_rate_emergency": 0.10,  # 10%
        "cpu_warning": 70,  # %
        "cpu_critical": 85,  # %
        "cpu_emergency": 95,  # %
        "memory_warning": 80,  # %
        "memory_critical": 90,  # %
        "memory_emergency": 95,  # %
        "disk_warning": 80,  # %
        "disk_critical": 90,  # %
        "disk_emergency": 95,  # %
    }

    def __init__(self, memory: Any) -> None:
        """Initialize with operational memory.

        Args:
            memory: OperationalMemory instance for Neo4j interactions
        """
        self.memory = memory
        self.agent_id = "jochi"
        logger.info("[BackendAnalysisProtocol] Initialized for agent: %s", self.agent_id)

    def _execute_query(self, query: str, parameters: Dict[str, Any]) -> List[Dict]:
        """Execute a Cypher query with proper error handling.

        Args:
            query: Parameterized Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries

        Raises:
            RuntimeError: If query execution fails
        """
        if not self.memory or getattr(self.memory, "fallback_mode", False):
            logger.warning("[BackendAnalysisProtocol] Cannot execute query: memory unavailable or in fallback mode")
            return []

        try:
            with self.memory._session() as session:
                result = session.run(query, **parameters)
                return [record.data() for record in result]
        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Query execution failed: %s", e)
            raise RuntimeError(f"Neo4j query failed: {e}") from e

    def analyze_performance(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance metrics and identify issues.

        Analyzes:
        1. Response time trends
        2. Error rate spikes
        3. Resource utilization
        4. Throughput patterns

        Args:
            metrics: Dictionary containing performance metrics
                Expected keys: response_time_ms, error_rate, cpu_percent,
                              memory_percent, disk_percent, throughput_rps

        Returns:
            Dict with findings and recommendations
        """
        findings = []
        recommendations = []
        overall_severity = self.SEVERITY_LOW

        # Analyze response time
        response_time = metrics.get("response_time_ms", 0)
        if response_time > self.THRESHOLDS["response_time_emergency"]:
            findings.append({
                "category": "performance",
                "issue": f"Critical response time: {response_time}ms exceeds emergency threshold",
                "severity": self.SEVERITY_CRITICAL,
                "evidence": f"Current: {response_time}ms, Threshold: {self.THRESHOLDS['response_time_emergency']}ms",
                "metric": "response_time"
            })
            recommendations.append("Implement caching layer or optimize database queries")
            overall_severity = self.SEVERITY_CRITICAL
        elif response_time > self.THRESHOLDS["response_time_critical"]:
            findings.append({
                "category": "performance",
                "issue": f"High response time: {response_time}ms exceeds critical threshold",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {response_time}ms, Threshold: {self.THRESHOLDS['response_time_critical']}ms",
                "metric": "response_time"
            })
            recommendations.append("Profile slow endpoints and optimize hot paths")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)
        elif response_time > self.THRESHOLDS["response_time_warning"]:
            findings.append({
                "category": "performance",
                "issue": f"Elevated response time: {response_time}ms",
                "severity": self.SEVERITY_MEDIUM,
                "evidence": f"Current: {response_time}ms, Threshold: {self.THRESHOLDS['response_time_warning']}ms",
                "metric": "response_time"
            })
            recommendations.append("Monitor for sustained elevation")
            overall_severity = max(overall_severity, self.SEVERITY_MEDIUM)

        # Analyze error rate
        error_rate = metrics.get("error_rate", 0)
        if error_rate > self.THRESHOLDS["error_rate_emergency"]:
            findings.append({
                "category": "reliability",
                "issue": f"Emergency error rate: {error_rate:.2%}",
                "severity": self.SEVERITY_CRITICAL,
                "evidence": f"Current: {error_rate:.2%}, Threshold: {self.THRESHOLDS['error_rate_emergency']:.2%}",
                "metric": "error_rate"
            })
            recommendations.append("Immediately review error logs and implement circuit breaker")
            overall_severity = self.SEVERITY_CRITICAL
        elif error_rate > self.THRESHOLDS["error_rate_critical"]:
            findings.append({
                "category": "reliability",
                "issue": f"Critical error rate: {error_rate:.2%}",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {error_rate:.2%}, Threshold: {self.THRESHOLDS['error_rate_critical']:.2%}",
                "metric": "error_rate"
            })
            recommendations.append("Investigate error patterns and add retry logic")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)
        elif error_rate > self.THRESHOLDS["error_rate_warning"]:
            findings.append({
                "category": "reliability",
                "issue": f"Elevated error rate: {error_rate:.2%}",
                "severity": self.SEVERITY_MEDIUM,
                "evidence": f"Current: {error_rate:.2%}, Threshold: {self.THRESHOLDS['error_rate_warning']:.2%}",
                "metric": "error_rate"
            })
            recommendations.append("Review recent deployments for regression")
            overall_severity = max(overall_severity, self.SEVERITY_MEDIUM)

        # Analyze CPU utilization
        cpu = metrics.get("cpu_percent", 0)
        if cpu > self.THRESHOLDS["cpu_emergency"]:
            findings.append({
                "category": "capacity",
                "issue": f"Emergency CPU usage: {cpu}%",
                "severity": self.SEVERITY_CRITICAL,
                "evidence": f"Current: {cpu}%, Threshold: {self.THRESHOLDS['cpu_emergency']}%",
                "metric": "cpu_percent"
            })
            recommendations.append("Scale horizontally immediately or investigate CPU-intensive processes")
            overall_severity = self.SEVERITY_CRITICAL
        elif cpu > self.THRESHOLDS["cpu_critical"]:
            findings.append({
                "category": "capacity",
                "issue": f"Critical CPU usage: {cpu}%",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {cpu}%, Threshold: {self.THRESHOLDS['cpu_critical']}%",
                "metric": "cpu_percent"
            })
            recommendations.append("Plan capacity increase within 24 hours")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)
        elif cpu > self.THRESHOLDS["cpu_warning"]:
            findings.append({
                "category": "capacity",
                "issue": f"High CPU usage: {cpu}%",
                "severity": self.SEVERITY_MEDIUM,
                "evidence": f"Current: {cpu}%, Threshold: {self.THRESHOLDS['cpu_warning']}%",
                "metric": "cpu_percent"
            })
            recommendations.append("Monitor for sustained high usage")
            overall_severity = max(overall_severity, self.SEVERITY_MEDIUM)

        # Analyze memory utilization
        memory = metrics.get("memory_percent", 0)
        if memory > self.THRESHOLDS["memory_emergency"]:
            findings.append({
                "category": "capacity",
                "issue": f"Emergency memory usage: {memory}%",
                "severity": self.SEVERITY_CRITICAL,
                "evidence": f"Current: {memory}%, Threshold: {self.THRESHOLDS['memory_emergency']}%",
                "metric": "memory_percent"
            })
            recommendations.append("Check for memory leaks and restart services if necessary")
            overall_severity = self.SEVERITY_CRITICAL
        elif memory > self.THRESHOLDS["memory_critical"]:
            findings.append({
                "category": "capacity",
                "issue": f"Critical memory usage: {memory}%",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {memory}%, Threshold: {self.THRESHOLDS['memory_critical']}%",
                "metric": "memory_percent"
            })
            recommendations.append("Investigate memory usage patterns and optimize")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)
        elif memory > self.THRESHOLDS["memory_warning"]:
            findings.append({
                "category": "capacity",
                "issue": f"High memory usage: {memory}%",
                "severity": self.SEVERITY_MEDIUM,
                "evidence": f"Current: {memory}%, Threshold: {self.THRESHOLDS['memory_warning']}%",
                "metric": "memory_percent"
            })
            recommendations.append("Monitor for memory growth trends")
            overall_severity = max(overall_severity, self.SEVERITY_MEDIUM)

        # Analyze disk utilization
        disk = metrics.get("disk_percent", 0)
        if disk > self.THRESHOLDS["disk_emergency"]:
            findings.append({
                "category": "capacity",
                "issue": f"Emergency disk usage: {disk}%",
                "severity": self.SEVERITY_CRITICAL,
                "evidence": f"Current: {disk}%, Threshold: {self.THRESHOLDS['disk_emergency']}%",
                "metric": "disk_percent"
            })
            recommendations.append("Free disk space immediately or expand storage")
            overall_severity = self.SEVERITY_CRITICAL
        elif disk > self.THRESHOLDS["disk_critical"]:
            findings.append({
                "category": "capacity",
                "issue": f"Critical disk usage: {disk}%",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {disk}%, Threshold: {self.THRESHOLDS['disk_critical']}%",
                "metric": "disk_percent"
            })
            recommendations.append("Plan storage expansion within 48 hours")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)

        # Analyze throughput patterns
        throughput = metrics.get("throughput_rps", 0)
        throughput_baseline = metrics.get("throughput_baseline_rps", 0)
        if throughput_baseline and throughput < throughput_baseline * 0.5:
            findings.append({
                "category": "performance",
                "issue": f"Significant throughput drop: {throughput} RPS vs baseline {throughput_baseline} RPS",
                "severity": self.SEVERITY_HIGH,
                "evidence": f"Current: {throughput} RPS, Baseline: {throughput_baseline} RPS",
                "metric": "throughput_rps"
            })
            recommendations.append("Investigate bottlenecks causing throughput degradation")
            overall_severity = max(overall_severity, self.SEVERITY_HIGH)

        result = {
            "findings": findings,
            "recommendations": list(set(recommendations)),  # Deduplicate
            "severity": overall_severity,
            "metrics_summary": {
                "response_time_ms": response_time,
                "error_rate": error_rate,
                "cpu_percent": cpu,
                "memory_percent": memory,
                "disk_percent": disk,
                "throughput_rps": throughput
            },
            "analyzed_at": datetime.now().isoformat()
        }

        logger.info("[BackendAnalysisProtocol] Performance analysis complete: %d findings, severity=%s",
                    len(findings), overall_severity)

        return result

    def create_analysis(self, analysis_type: str, target: str,
                       findings: List[Dict], severity: str) -> str:
        """Create an Analysis node in Neo4j.

        Creates Analysis node with:
        - id
        - analysis_type (performance, error, security, capacity)
        - target (service/component analyzed)
        - findings (JSON array)
        - severity (critical, high, medium, low)
        - recommendations
        - status (open, investigating, resolved)
        - created_at

        Args:
            analysis_type: Type of analysis (performance, error, security, capacity)
            target: Service or component being analyzed
            findings: List of finding dictionaries
            severity: Overall severity level

        Returns:
            Analysis ID as string
        """
        analysis_id = str(uuid4())

        # Extract recommendations from findings
        recommendations = []
        for finding in findings:
            if "recommendation" in finding:
                recommendations.append(finding["recommendation"])
            elif "recommendations" in finding:
                if isinstance(finding["recommendations"], list):
                    recommendations.extend(finding["recommendations"])
                else:
                    recommendations.append(finding["recommendations"])

        query = """
        CREATE (a:Analysis {
            id: $analysis_id,
            analysis_type: $analysis_type,
            target: $target,
            findings: $findings_json,
            severity: $severity,
            recommendations: $recommendations,
            status: $status,
            created_at: datetime(),
            closed_at: null,
            resolution: null,
            correlated_security_audit: null,
            created_by: $created_by
        })
        RETURN a.id as id
        """

        parameters = {
            "analysis_id": analysis_id,
            "analysis_type": analysis_type,
            "target": target,
            "findings_json": json.dumps(findings),
            "severity": severity,
            "recommendations": json.dumps(recommendations),
            "status": self.STATUS_OPEN,
            "created_by": self.agent_id
        }

        try:
            result = self._execute_query(query, parameters)
            if result:
                logger.info("[BackendAnalysisProtocol] Created analysis %s for target=%s, type=%s",
                            analysis_id, target, analysis_type)
                return analysis_id
            else:
                raise RuntimeError("Failed to create analysis node")
        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to create analysis: %s", e)
            raise

    def identify_backend_issues(self, logs: List[str],
                               metrics: Dict[str, Any]) -> List[Dict]:
        """Identify backend issues from logs and metrics.

        Detects:
        - Database connection issues
        - Memory leaks
        - Slow queries
        - Error patterns
        - Capacity issues

        Args:
            logs: List of log lines to analyze
            metrics: Performance metrics dictionary

        Returns:
            List of identified issues as dictionaries
        """
        issues = []

        # Pattern definitions for issue detection
        patterns = {
            "database_connection": {
                "patterns": [
                    r"Connection.*refused",
                    r"database.*unavailable",
                    r"Failed to connect to.*database",
                    r"Connection pool exhausted",
                    r"Too many connections",
                    r"Neo4j.*ServiceUnavailable",
                    r"ConnectionTimeout",
                    r"Database.*locked"
                ],
                "category": self.CATEGORY_CONNECTION_POOL,
                "severity": self.SEVERITY_CRITICAL,
                "description": "Database connection issue detected"
            },
            "memory_leak": {
                "patterns": [
                    r"OutOfMemory",
                    r"MemoryError",
                    r"Java heap space",
                    r"GC overhead limit exceeded",
                    r"memory.*growing.*unbounded",
                    r"leak detected"
                ],
                "category": self.CATEGORY_PERFORMANCE,
                "severity": self.SEVERITY_HIGH,
                "description": "Potential memory leak detected"
            },
            "slow_query": {
                "patterns": [
                    r"Query.*took.*\d{4,}ms",
                    r"Slow query",
                    r"query.*timeout",
                    r"execution.*time.*exceeded",
                    r"QueryPerformance"
                ],
                "category": self.CATEGORY_PERFORMANCE,
                "severity": self.SEVERITY_MEDIUM,
                "description": "Slow query detected"
            },
            "resilience_issue": {
                "patterns": [
                    r"No retry logic",
                    r"Circuit breaker.*open",
                    r"Fallback.*failed",
                    r"No fallback",
                    r"Cascading failure"
                ],
                "category": self.CATEGORY_RESILIENCE,
                "severity": self.SEVERITY_HIGH,
                "description": "Resilience pattern issue detected"
            },
            "data_integrity": {
                "patterns": [
                    r"Unparameterized query",
                    r"SQL injection",
                    r"Cypher injection",
                    r"Missing transaction",
                    r"Data corruption"
                ],
                "category": self.CATEGORY_DATA_INTEGRITY,
                "severity": self.SEVERITY_CRITICAL,
                "description": "Data integrity issue detected"
            },
            "security_issue": {
                "patterns": [
                    r"Secret.*exposed",
                    r"Password.*in.*log",
                    r"Token.*exposed",
                    r"Unauthorized access",
                    r"Authentication failed",
                    r"Permission denied"
                ],
                "category": self.CATEGORY_SECURITY,
                "severity": self.SEVERITY_CRITICAL,
                "description": "Security issue detected"
            }
        }

        # Analyze logs for patterns
        for log_line in logs:
            for issue_type, config in patterns.items():
                for pattern in config["patterns"]:
                    if re.search(pattern, log_line, re.IGNORECASE):
                        issue = {
                            "type": issue_type,
                            "category": config["category"],
                            "severity": config["severity"],
                            "description": config["description"],
                            "evidence": log_line[:200],  # Truncate long lines
                            "pattern_matched": pattern
                        }
                        issues.append(issue)
                        logger.debug("[BackendAnalysisProtocol] Detected %s issue: %s",
                                     issue_type, log_line[:100])
                        break  # Avoid duplicate issues from same log line

        # Analyze metrics for capacity issues
        if metrics.get("memory_percent", 0) > self.THRESHOLDS["memory_critical"]:
            # Check for sustained high memory (potential leak)
            memory_history = metrics.get("memory_history", [])
            if len(memory_history) >= 3:
                trending_up = all(
                    memory_history[i] < memory_history[i + 1]
                    for i in range(len(memory_history) - 1)
                )
                if trending_up:
                    issues.append({
                        "type": "memory_leak_suspected",
                        "category": self.CATEGORY_PERFORMANCE,
                        "severity": self.SEVERITY_HIGH,
                        "description": "Memory usage trending upward - possible leak",
                        "evidence": f"Memory history: {memory_history[-5:]}",
                        "recommendation": "Profile memory usage and check for unclosed resources"
                    })

        # Check for connection pool exhaustion
        if metrics.get("connection_pool_usage", 0) > 90:
            issues.append({
                "type": "connection_pool_exhaustion",
                "category": self.CATEGORY_CONNECTION_POOL,
                "severity": self.SEVERITY_CRITICAL,
                "description": "Connection pool near exhaustion",
                "evidence": f"Pool usage: {metrics.get('connection_pool_usage')}%",
                "recommendation": "Increase pool size or implement connection pooling"
            })

        # Check for error rate spikes
        error_rate = metrics.get("error_rate", 0)
        error_rate_history = metrics.get("error_rate_history", [])
        if error_rate_history and len(error_rate_history) >= 2:
            avg_previous = sum(error_rate_history[:-1]) / len(error_rate_history[:-1])
            if error_rate > avg_previous * 3 and error_rate > 0.01:  # 3x spike and > 1%
                issues.append({
                    "type": "error_rate_spike",
                    "category": self.CATEGORY_RESILIENCE,
                    "severity": self.SEVERITY_HIGH,
                    "description": "Sudden error rate spike detected",
                    "evidence": f"Current: {error_rate:.2%}, Average: {avg_previous:.2%}",
                    "recommendation": "Check recent deployments and error logs"
                })

        logger.info("[BackendAnalysisProtocol] Identified %d backend issues from logs and metrics",
                    len(issues))

        return issues

    def correlate_with_security(self, analysis_id: str) -> Optional[Dict]:
        """Correlate analysis with security audits (collaboration with Temüjin).

        Args:
            analysis_id: ID of the analysis to correlate

        Returns:
            Dictionary with correlation results or None if no correlation found
        """
        # First, get the analysis details
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            logger.warning("[BackendAnalysisProtocol] Analysis %s not found for correlation", analysis_id)
            return None

        # Query for related security audits
        query = """
        MATCH (a:Analysis {id: $analysis_id})
        MATCH (sa:SecurityAudit)
        WHERE sa.target = a.target
        AND sa.created_at > datetime() - duration('P7D')
        AND (sa.status = 'open' OR sa.status = 'in_progress')
        RETURN sa.id as security_audit_id,
               sa.audit_type as audit_type,
               sa.severity as severity,
               sa.findings as findings,
               sa.created_at as created_at
        ORDER BY sa.created_at DESC
        LIMIT 5
        """

        try:
            results = self._execute_query(query, {"analysis_id": analysis_id})

            if not results:
                logger.info("[BackendAnalysisProtocol] No security audits found for analysis %s", analysis_id)
                return None

            # Update the analysis with correlation
            update_query = """
            MATCH (a:Analysis {id: $analysis_id})
            SET a.correlated_security_audit = $security_audit_id
            RETURN a.id as id
            """

            correlated_audits = []
            for result in results:
                security_audit_id = result.get("security_audit_id")
                self._execute_query(update_query, {
                    "analysis_id": analysis_id,
                    "security_audit_id": security_audit_id
                })
                correlated_audits.append({
                    "security_audit_id": security_audit_id,
                    "audit_type": result.get("audit_type"),
                    "severity": result.get("severity"),
                    "findings": json.loads(result.get("findings", "[]"))
                })

            correlation_result = {
                "analysis_id": analysis_id,
                "target": analysis.get("target"),
                "correlated_audits": correlated_audits,
                "correlation_count": len(correlated_audits),
                "correlated_at": datetime.now().isoformat()
            }

            logger.info("[BackendAnalysisProtocol] Correlated analysis %s with %d security audits",
                        analysis_id, len(correlated_audits))

            return correlation_result

        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to correlate with security: %s", e)
            return None

    def get_analysis(self, analysis_id: str) -> Optional[Dict]:
        """Get analysis by ID.

        Args:
            analysis_id: ID of the analysis to retrieve

        Returns:
            Analysis dictionary or None if not found
        """
        query = """
        MATCH (a:Analysis {id: $analysis_id})
        RETURN a.id as id,
               a.analysis_type as analysis_type,
               a.target as target,
               a.findings as findings,
               a.severity as severity,
               a.recommendations as recommendations,
               a.status as status,
               a.created_at as created_at,
               a.closed_at as closed_at,
               a.resolution as resolution,
               a.correlated_security_audit as correlated_security_audit,
               a.created_by as created_by
        """

        try:
            results = self._execute_query(query, {"analysis_id": analysis_id})
            if not results:
                return None

            result = results[0]

            # Parse JSON fields
            try:
                result["findings"] = json.loads(result.get("findings", "[]"))
            except (json.JSONDecodeError, TypeError):
                result["findings"] = []

            try:
                result["recommendations"] = json.loads(result.get("recommendations", "[]"))
            except (json.JSONDecodeError, TypeError):
                result["recommendations"] = []

            return result

        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to get analysis %s: %s", analysis_id, e)
            return None

    def list_open_analyses(self) -> List[Dict]:
        """List all open analyses.

        Returns:
            List of open analysis dictionaries
        """
        query = """
        MATCH (a:Analysis)
        WHERE a.status = 'open' OR a.status = 'investigating'
        RETURN a.id as id,
               a.analysis_type as analysis_type,
               a.target as target,
               a.findings as findings,
               a.severity as severity,
               a.recommendations as recommendations,
               a.status as status,
               a.created_at as created_at,
               a.created_by as created_by
        ORDER BY CASE a.severity
            WHEN 'critical' THEN 1
            WHEN 'high' THEN 2
            WHEN 'medium' THEN 3
            WHEN 'low' THEN 4
            ELSE 5
        END, a.created_at DESC
        """

        try:
            results = self._execute_query(query, {})

            analyses = []
            for result in results:
                try:
                    result["findings"] = json.loads(result.get("findings", "[]"))
                except (json.JSONDecodeError, TypeError):
                    result["findings"] = []

                try:
                    result["recommendations"] = json.loads(result.get("recommendations", "[]"))
                except (json.JSONDecodeError, TypeError):
                    result["recommendations"] = []

                analyses.append(result)

            logger.info("[BackendAnalysisProtocol] Listed %d open analyses", len(analyses))
            return analyses

        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to list open analyses: %s", e)
            return []

    def close_analysis(self, analysis_id: str, resolution: str) -> bool:
        """Mark analysis as resolved.

        Args:
            analysis_id: ID of the analysis to close
            resolution: Resolution description

        Returns:
            True if successful, False otherwise
        """
        query = """
        MATCH (a:Analysis {id: $analysis_id})
        SET a.status = $status,
            a.resolution = $resolution,
            a.closed_at = datetime()
        RETURN a.id as id
        """

        parameters = {
            "analysis_id": analysis_id,
            "status": self.STATUS_RESOLVED,
            "resolution": resolution
        }

        try:
            results = self._execute_query(query, parameters)
            if results:
                logger.info("[BackendAnalysisProtocol] Closed analysis %s with resolution: %s",
                            analysis_id, resolution[:100])
                return True
            else:
                logger.warning("[BackendAnalysisProtocol] Analysis %s not found for closing", analysis_id)
                return False
        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to close analysis %s: %s", analysis_id, e)
            return False

    def escalate_to_developer(self, analysis_id: str, reason: str) -> bool:
        """Escalate to Temüjin for code-level investigation.

        Args:
            analysis_id: ID of the analysis to escalate
            reason: Reason for escalation

        Returns:
            True if escalation was successful, False otherwise
        """
        # Get analysis details
        analysis = self.get_analysis(analysis_id)
        if not analysis:
            logger.warning("[BackendAnalysisProtocol] Cannot escalate: analysis %s not found", analysis_id)
            return False

        # Update analysis status to investigating
        query = """
        MATCH (a:Analysis {id: $analysis_id})
        SET a.status = $status,
            a.escalated_to = $escalated_to,
            a.escalation_reason = $reason,
            a.escalated_at = datetime()
        RETURN a.id as id
        """

        parameters = {
            "analysis_id": analysis_id,
            "status": self.STATUS_INVESTIGATING,
            "escalated_to": "temujin",
            "reason": reason
        }

        try:
            results = self._execute_query(query, parameters)
            if not results:
                return False

            # Create escalation notification/task for Temüjin
            escalation_query = """
            MATCH (a:Analysis {id: $analysis_id})
            CREATE (t:Task {
                id: $task_id,
                task_type: 'backend_implementation',
                description: $description,
                assigned_to: 'temujin',
                delegated_by: $delegated_by,
                status: 'pending',
                priority: $priority,
                related_analysis_id: $analysis_id,
                created_at: datetime()
            })
            CREATE (a)-[:REQUIRES_IMPLEMENTATION]->(t)
            RETURN t.id as task_id
            """

            # Determine priority based on severity
            severity = analysis.get("severity", self.SEVERITY_MEDIUM)
            priority = "urgent" if severity == self.SEVERITY_CRITICAL else (
                "high" if severity == self.SEVERITY_HIGH else "normal"
            )

            task_params = {
                "analysis_id": analysis_id,
                "task_id": str(uuid4()),
                "description": f"Backend issue investigation: {analysis.get('target', 'Unknown')} - {reason[:200]}",
                "delegated_by": self.agent_id,
                "priority": priority
            }

            self._execute_query(escalation_query, task_params)

            logger.info("[BackendAnalysisProtocol] Escalated analysis %s to Temüjin: %s",
                        analysis_id, reason[:100])

            return True

        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to escalate analysis %s: %s", analysis_id, e)
            return False

    def create_backend_issue_analysis(self, category: str, target: str,
                                      findings: str, location: str,
                                      recommended_fix: str,
                                      severity: str = SEVERITY_HIGH) -> str:
        """Create a backend issue analysis node (Phase 4.6 specific).

        This is a convenience method for creating backend issue analyses
        as specified in the Phase 4.6 protocol.

        Args:
            category: Issue category (connection_pool, resilience, data_integrity, performance, security)
            target: The service or component affected
            findings: Detailed description of the issue
            location: File and line number (e.g., "file.py:42")
            recommended_fix: Specific implementation approach
            severity: Issue severity level

        Returns:
            Analysis ID as string
        """
        analysis_id = str(uuid4())

        query = """
        CREATE (a:Analysis {
            id: $analysis_id,
            analysis_type: 'backend_issue',
            category: $category,
            target: $target,
            findings: $findings,
            location: $location,
            severity: $severity,
            recommended_fix: $recommended_fix,
            status: 'identified',
            identified_by: $identified_by,
            requires_implementation_by: 'temujin',
            created_at: datetime(),
            closed_at: null,
            resolution: null,
            correlated_security_audit: null
        })
        RETURN a.id as id
        """

        parameters = {
            "analysis_id": analysis_id,
            "category": category,
            "target": target,
            "findings": findings,
            "location": location,
            "severity": severity,
            "recommended_fix": recommended_fix,
            "identified_by": self.agent_id
        }

        try:
            result = self._execute_query(query, parameters)
            if result:
                logger.info("[BackendAnalysisProtocol] Created backend issue analysis %s "
                            "for target=%s, category=%s",
                            analysis_id, target, category)
                return analysis_id
            else:
                raise RuntimeError("Failed to create backend issue analysis")
        except Exception as e:
            logger.error("[BackendAnalysisProtocol] Failed to create backend issue analysis: %s", e)
            raise
