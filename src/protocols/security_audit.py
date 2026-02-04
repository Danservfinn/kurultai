"""
Temüjin Security Audit Protocol - Phase 4.1 Implementation

This module implements the security audit protocol for the multi-agent system,
integrating with Neo4j operational memory for audit tracking and findings storage.

Security Audit Procedures:
    - Phase 1: Scope Definition
    - Phase 2: Discovery (static analysis, dependency check)
    - Phase 3: Vulnerability Assessment
    - Phase 4: Reporting and Storage in Neo4j

Reference: /Users/kurultai/molt/data/workspace/souls/developer/SOUL.md
"""

import json
import logging
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from neo4j.exceptions import Neo4jError, ServiceUnavailable

# Configure logging
logger = logging.getLogger(__name__)

# Import OperationalMemory - handle both possible locations
try:
    from openclaw_memory import OperationalMemory
except ImportError:
    try:
        from ..memory.openclaw_memory import OperationalMemory
    except ImportError:
        from molt.openclaw_memory import OperationalMemory


class SecurityAuditError(Exception):
    """Raised when a security audit operation fails."""
    pass


class AuditNotFoundError(Exception):
    """Raised when an audit is not found in the database."""
    pass


class SecurityAuditProtocol:
    """
    Temüjin's security audit protocol with Neo4j integration.

    This class implements comprehensive security auditing capabilities including:
    - Static code analysis for vulnerabilities
    - Dependency vulnerability scanning
    - Configuration security review
    - Secret detection in code
    - Neo4j-backed audit storage and retrieval

    All database operations use parameterized Cypher queries to prevent injection.

    Example:
        >>> from openclaw_memory import OperationalMemory
        >>> from protocols.security_audit import SecurityAuditProtocol
        >>>
        >>> memory = OperationalMemory()
        >>> protocol = SecurityAuditProtocol(memory)
        >>>
        >>> # Create and run an audit
        >>> audit_id = protocol.create_security_audit(
        ...     target="/path/to/code",
        ...     audit_type="code_review",
        ...     requested_by="kublai"
        ... )
        >>> results = protocol.run_audit(audit_id)
        >>>
        >>> # Check status
        >>> status = protocol.get_audit_status(audit_id)
    """

    # OWASP Top 10 categories for classification
    OWASP_CATEGORIES = [
        "A01:2021-Broken Access Control",
        "A02:2021-Cryptographic Failures",
        "A03:2021-Injection",
        "A04:2021-Insecure Design",
        "A05:2021-Security Misconfiguration",
        "A06:2021-Vulnerable and Outdated Components",
        "A07:2021-Identification and Authentication Failures",
        "A08:2021-Software and Data Integrity Failures",
        "A09:2021-Security Logging and Monitoring Failures",
        "A10:2021-Server-Side Request Forgery (SSRF)"
    ]

    # Severity definitions with response times
    SEVERITY_LEVELS = {
        "critical": {"response_time": "immediate", "score": 4},
        "high": {"response_time": "24 hours", "score": 3},
        "medium": {"response_time": "7 days", "score": 2},
        "low": {"response_time": "30 days", "score": 1}
    }

    # Patterns for secret detection
    SECRET_PATTERNS = {
        "api_key": re.compile(r'[a-zA-Z0-9_-]*(?:api[_-]?key|apikey)[\s]*[:=][\s]*["\']?[a-zA-Z0-9]{16,}["\']?', re.IGNORECASE),
        "password": re.compile(r'[a-zA-Z0-9_-]*(?:password|passwd|pwd)[\s]*[:=][\s]*["\'][^"\']{4,}["\']', re.IGNORECASE),
        "token": re.compile(r'[a-zA-Z0-9_-]*(?:token|secret)[\s]*[:=][\s]*["\']?[a-zA-Z0-9]{16,}["\']?', re.IGNORECASE),
        "private_key": re.compile(r'-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----', re.IGNORECASE),
        "aws_key": re.compile(r'AKIA[0-9A-Z]{16}'),
        "github_token": re.compile(r'gh[pousr]_[A-Za-z0-9_]{36}'),
        "slack_token": re.compile(r'xox[baprs]-[0-9]{10,13}-[0-9]{10,13}'),
    }

    # Patterns for injection vulnerabilities
    INJECTION_PATTERNS = {
        "sql_injection": re.compile(r'(?:execute|query|run)[\s]*\([\s]*["\'].*\{.*\}.*["\']', re.IGNORECASE),
        "command_injection": re.compile(r'(?:os\.system|subprocess\.call|subprocess\.run|exec|eval)\s*\(', re.IGNORECASE),
        "cypher_injection": re.compile(r'\.run\s*\([^,]*\+[^)]*\)', re.IGNORECASE),
    }

    def __init__(self, memory: OperationalMemory):
        """
        Initialize the security audit protocol with operational memory.

        Args:
            memory: OperationalMemory instance for Neo4j operations and notifications

        Raises:
            ValueError: If memory is None or not properly initialized
        """
        if memory is None:
            raise ValueError("OperationalMemory instance is required")

        self.memory = memory
        logger.info("SecurityAuditProtocol initialized")

    def _generate_id(self) -> str:
        """Generate a unique UUID for audit tracking."""
        return str(uuid.uuid4())

    def _now(self) -> datetime:
        """Get current UTC datetime."""
        return datetime.now(timezone.utc)

    def _get_session(self):
        """Get a Neo4j session from the operational memory."""
        return self.memory._session()

    def create_security_audit(
        self,
        target: str,
        audit_type: str,
        requested_by: str
    ) -> str:
        """
        Create a new security audit task.

        Creates a SecurityAudit node in Neo4j with initial status 'pending'.
        The audit can then be executed using run_audit().

        Args:
            target: What to audit (file path, URL, code module, or system name)
            audit_type: Type of audit - one of:
                - 'code_review': Static code analysis
                - 'dependency_scan': Check for vulnerable dependencies
                - 'config_audit': Configuration security review
                - 'secret_scan': Detect secrets in code
                - 'full_audit': Comprehensive audit (all types)
            requested_by: Agent or user requesting the audit

        Returns:
            audit_id: UUID of the created audit

        Raises:
            SecurityAuditError: If the audit cannot be created in Neo4j
            ValueError: If audit_type is not a valid type

        Example:
            >>> audit_id = protocol.create_security_audit(
            ...     target="/app/src/auth.py",
            ...     audit_type="code_review",
            ...     requested_by="kublai"
            ... )
        """
        valid_types = ['code_review', 'dependency_scan', 'config_audit', 'secret_scan', 'full_audit']
        if audit_type not in valid_types:
            raise ValueError(f"Invalid audit_type. Must be one of: {valid_types}")

        audit_id = self._generate_id()
        created_at = self._now()

        # Parameterized Cypher query - prevents injection
        cypher = """
        CREATE (sa:SecurityAudit {
            id: $audit_id,
            target: $target,
            audit_type: $audit_type,
            requested_by: $requested_by,
            findings: '[]',
            severity_summary: $severity_summary,
            recommendations: '[]',
            status: 'pending',
            created_at: $created_at,
            completed_at: null,
            claimed_by: null
        })
        RETURN sa.id as audit_id
        """

        severity_summary = json.dumps({
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        })

        with self._get_session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Security audit creation simulated for {target}")
                return audit_id

            try:
                result = session.run(
                    cypher,
                    audit_id=audit_id,
                    target=target,
                    audit_type=audit_type,
                    requested_by=requested_by,
                    severity_summary=severity_summary,
                    created_at=created_at
                )
                record = result.single()
                if record:
                    logger.info(f"Security audit created: {audit_id} for {target}")
                    return record["audit_id"]
                else:
                    raise SecurityAuditError("Audit creation failed: no record returned")
            except Neo4jError as e:
                logger.error(f"Failed to create security audit: {e}")
                raise SecurityAuditError(f"Neo4j error: {e}")

    def run_audit(self, audit_id: str) -> Dict[str, Any]:
        """
        Execute the security audit.

        Performs comprehensive security analysis based on the audit type:
        1. Static analysis of code (for code_review and full_audit)
        2. Dependency vulnerability check (for dependency_scan and full_audit)
        3. Configuration security review (for config_audit and full_audit)
        4. Secret detection (for secret_scan and full_audit)

        Args:
            audit_id: UUID of the audit to execute

        Returns:
            Dict containing:
                - audit_id: The audit UUID
                - target: Audited target
                - audit_type: Type of audit performed
                - findings: List of security findings
                - severity_summary: Counts by severity level
                - recommendations: Prioritized remediation steps
                - status: 'completed' or 'failed'
                - completed_at: ISO timestamp

        Raises:
            AuditNotFoundError: If the audit_id doesn't exist
            SecurityAuditError: If the audit execution fails

        Example:
            >>> results = protocol.run_audit(audit_id)
            >>> print(f"Found {results['severity_summary']['critical']} critical issues")
        """
        # Get audit details
        audit = self.get_audit_status(audit_id)
        if not audit:
            raise AuditNotFoundError(f"Audit {audit_id} not found")

        if audit.get("status") == "in_progress":
            raise SecurityAuditError(f"Audit {audit_id} is already in progress")

        # Mark as in_progress
        self._update_audit_status(audit_id, "in_progress", claimed_by="temüjin")

        try:
            target = audit["target"]
            audit_type = audit["audit_type"]

            all_findings: List[Dict[str, Any]] = []

            # Execute audit based on type
            if audit_type in ["code_review", "full_audit"]:
                all_findings.extend(self._run_code_review(target))

            if audit_type in ["dependency_scan", "full_audit"]:
                all_findings.extend(self._run_dependency_scan(target))

            if audit_type in ["config_audit", "full_audit"]:
                all_findings.extend(self._run_config_audit(target))

            if audit_type in ["secret_scan", "full_audit"]:
                all_findings.extend(self._run_secret_scan(target))

            # Calculate severity summary
            severity_summary = self._calculate_severity_summary(all_findings)

            # Generate recommendations
            recommendations = self._generate_recommendations(all_findings)

            # Store findings
            self.store_findings(audit_id, all_findings)

            # Mark as completed
            completed_at = self._now()
            self._update_audit_status(audit_id, "completed", completed_at=completed_at)

            # Check for critical findings that need escalation
            critical_findings = [f for f in all_findings if f.get("severity") == "critical"]
            if critical_findings:
                self.escalate_critical(audit_id, critical_findings)

            result = {
                "audit_id": audit_id,
                "target": target,
                "audit_type": audit_type,
                "findings": all_findings,
                "severity_summary": severity_summary,
                "recommendations": recommendations,
                "status": "completed",
                "completed_at": completed_at.isoformat()
            }

            logger.info(f"Security audit completed: {audit_id} - "
                       f"{severity_summary['critical']} critical, "
                       f"{severity_summary['high']} high, "
                       f"{severity_summary['medium']} medium, "
                       f"{severity_summary['low']} low")

            return result

        except Exception as e:
            self._update_audit_status(audit_id, "failed")
            logger.error(f"Security audit failed: {audit_id} - {e}")
            raise SecurityAuditError(f"Audit execution failed: {e}")

    def _run_code_review(self, target: str) -> List[Dict[str, Any]]:
        """
        Perform static code analysis for security vulnerabilities.

        Checks for:
        - Injection vulnerabilities (SQL, command, code)
        - Insecure function usage
        - Hardcoded credentials
        - Improper error handling

        Args:
            target: Path to code file or directory

        Returns:
            List of findings
        """
        findings = []
        target_path = Path(target)

        if not target_path.exists():
            findings.append({
                "severity": "high",
                "category": "A05:2021-Security Misconfiguration",
                "description": f"Target path does not exist: {target}",
                "location": target,
                "evidence": "Path not found",
                "remediation": "Verify the target path is correct and accessible",
                "effort": "immediate"
            })
            return findings

        # Determine files to scan
        files_to_scan = []
        if target_path.is_file():
            files_to_scan = [target_path]
        elif target_path.is_dir():
            files_to_scan = list(target_path.rglob("*.py")) + \
                          list(target_path.rglob("*.js")) + \
                          list(target_path.rglob("*.ts")) + \
                          list(target_path.rglob("*.jsx")) + \
                          list(target_path.rglob("*.tsx"))

        for file_path in files_to_scan:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')

                # Check for injection patterns
                for pattern_name, pattern in self.INJECTION_PATTERNS.items():
                    for match in pattern.finditer(content):
                        # Calculate line number
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                        severity = "critical" if pattern_name == "sql_injection" else "high"
                        category = "A03:2021-Injection" if "injection" in pattern_name else "A09:2021-Security Logging and Monitoring Failures"

                        findings.append({
                            "severity": severity,
                            "category": category,
                            "description": f"Potential {pattern_name.replace('_', ' ')} vulnerability detected",
                            "location": f"{file_path}:{line_num}",
                            "evidence": line_content.strip()[:200],
                            "remediation": "Use parameterized queries and avoid dynamic code execution",
                            "effort": "4-8 hours"
                        })

                # Check for hardcoded credentials (basic check)
                for pattern_name, pattern in self.SECRET_PATTERNS.items():
                    if pattern_name == "private_key":
                        continue  # Handled in secret scan

                    for match in pattern.finditer(content):
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                        findings.append({
                            "severity": "critical",
                            "category": "A07:2021-Identification and Authentication Failures",
                            "description": f"Potential hardcoded {pattern_name.replace('_', ' ')} detected",
                            "location": f"{file_path}:{line_num}",
                            "evidence": line_content.strip()[:100] + "...",
                            "remediation": "Move secrets to environment variables or secure vault",
                            "effort": "2-4 hours"
                        })

                # Check for insecure functions
                insecure_functions = [
                    (r'eval\s*\(', "eval() can execute arbitrary code"),
                    (r'exec\s*\(', "exec() can execute arbitrary code"),
                    (r'pickle\.loads?', "pickle can execute arbitrary code during deserialization"),
                    (r'yaml\.load\s*\([^)]*\)(?!.*Loader)', "yaml.load without Loader is unsafe"),
                    (r'input\s*\(', "input() is unsafe in Python 2"),
                ]

                for func_pattern, description in insecure_functions:
                    pattern = re.compile(func_pattern)
                    for match in pattern.finditer(content):
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                        findings.append({
                            "severity": "high",
                            "category": "A03:2021-Injection",
                            "description": description,
                            "location": f"{file_path}:{line_num}",
                            "evidence": line_content.strip()[:200],
                            "remediation": "Use safer alternatives (ast.literal_eval, yaml.safe_load, etc.)",
                            "effort": "2-4 hours"
                        })

            except Exception as e:
                logger.warning(f"Could not scan file {file_path}: {e}")

        return findings

    def _run_dependency_scan(self, target: str) -> List[Dict[str, Any]]:
        """
        Check for vulnerable dependencies.

        Args:
            target: Path to project directory or requirements file

        Returns:
            List of findings
        """
        findings = []
        target_path = Path(target)

        # Look for requirements files
        req_files = []
        if target_path.is_file() and target_path.name in ['requirements.txt', 'Pipfile', 'pyproject.toml']:
            req_files = [target_path]
        elif target_path.is_dir():
            req_files = list(target_path.rglob('requirements*.txt')) + \
                       list(target_path.rglob('Pipfile')) + \
                       list(target_path.rglob('pyproject.toml'))

        for req_file in req_files:
            try:
                # Run safety check if available
                result = subprocess.run(
                    ['safety', 'check', '--file', str(req_file), '--json'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0 and result.stdout:
                    vulnerabilities = json.loads(result.stdout)
                    for vuln in vulnerabilities:
                        findings.append({
                            "severity": vuln.get("severity", "high").lower(),
                            "category": "A06:2021-Vulnerable and Outdated Components",
                            "description": f"Vulnerable dependency: {vuln.get('package_name')} {vuln.get('vulnerable_spec')}",
                            "location": str(req_file),
                            "evidence": vuln.get("advisory", "No details available"),
                            "remediation": f"Upgrade to {vuln.get('analyzed_spec', 'latest version')}",
                            "effort": "1-2 hours"
                        })

            except FileNotFoundError:
                # safety not installed, do basic check
                logger.warning("safety package not installed, running basic dependency check")
                findings.extend(self._basic_dependency_check(req_file))
            except subprocess.TimeoutExpired:
                logger.warning(f"Dependency scan timed out for {req_file}")
            except Exception as e:
                logger.warning(f"Could not scan dependencies in {req_file}: {e}")

        return findings

    def _basic_dependency_check(self, req_file: Path) -> List[Dict[str, Any]]:
        """Basic dependency check without safety package."""
        findings = []

        # Known vulnerable package patterns (simplified)
        known_vulnerable = {
            'django': [('1.11', '2.2'), ('2.0', '2.2.13')],
            'flask': [('0.0', '1.0')],
            'requests': [('2.0', '2.20')],
            'urllib3': [('1.0', '1.24.2')],
        }

        try:
            with open(req_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    for pkg, vulnerable_ranges in known_vulnerable.items():
                        if pkg in line.lower():
                            findings.append({
                                "severity": "medium",
                                "category": "A06:2021-Vulnerable and Outdated Components",
                                "description": f"Potentially outdated dependency: {pkg}",
                                "location": str(req_file),
                                "evidence": line,
                                "remediation": f"Check {pkg} for latest security updates",
                                "effort": "1-2 hours"
                            })
        except Exception as e:
            logger.warning(f"Basic dependency check failed for {req_file}: {e}")

        return findings

    def _run_config_audit(self, target: str) -> List[Dict[str, Any]]:
        """
        Review configuration files for security issues.

        Args:
            target: Path to configuration file or directory

        Returns:
            List of findings
        """
        findings = []
        target_path = Path(target)

        # Configuration files to check
        config_patterns = ['*.conf', '*.config', '*.ini', '*.yaml', '*.yml', '*.json', '.env*']

        config_files = []
        if target_path.is_file():
            config_files = [target_path]
        elif target_path.is_dir():
            for pattern in config_patterns:
                config_files.extend(target_path.rglob(pattern))

        for config_file in config_files:
            try:
                with open(config_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')

                # Check for debug mode enabled
                debug_patterns = [
                    (r'debug\s*=\s*true', "Debug mode enabled"),
                    (r'DEBUG\s*=\s*True', "DEBUG mode enabled in Django/Flask"),
                    (r'APP_DEBUG\s*=\s*true', "Application debug mode enabled"),
                ]

                for pattern, description in debug_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        findings.append({
                            "severity": "high",
                            "category": "A05:2021-Security Misconfiguration",
                            "description": description,
                            "location": str(config_file),
                            "evidence": f"Pattern '{pattern}' found",
                            "remediation": "Disable debug mode in production",
                            "effort": "immediate"
                        })

                # Check for weak crypto settings
                weak_crypto_patterns = [
                    (r'ALLOWED_HOSTS\s*=\s*\[\s*\*\s*\]', "ALLOWED_HOSTS set to wildcard"),
                    (r'CORS_ALLOW_ALL_ORIGINS\s*=\s*True', "CORS allows all origins"),
                    (r'password.*md5', "Weak password hashing (MD5)"),
                    (r'password.*sha1', "Weak password hashing (SHA1)"),
                ]

                for pattern, description in weak_crypto_patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        severity = "critical" if "password" in description.lower() else "high"
                        findings.append({
                            "severity": severity,
                            "category": "A02:2021-Cryptographic Failures",
                            "description": description,
                            "location": str(config_file),
                            "evidence": f"Pattern '{pattern}' found",
                            "remediation": "Use strong cryptography and restrict access",
                            "effort": "2-4 hours"
                        })

                # Check for secrets in config files
                for pattern_name, pattern in self.SECRET_PATTERNS.items():
                    for match in pattern.finditer(content):
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                        findings.append({
                            "severity": "critical",
                            "category": "A07:2021-Identification and Authentication Failures",
                            "description": f"Secret ({pattern_name}) found in configuration file",
                            "location": f"{config_file}:{line_num}",
                            "evidence": line_content.strip()[:100] + "...",
                            "remediation": "Move secrets to environment variables or secure vault",
                            "effort": "1-2 hours"
                        })

            except Exception as e:
                logger.warning(f"Could not audit config file {config_file}: {e}")

        return findings

    def _run_secret_scan(self, target: str) -> List[Dict[str, Any]]:
        """
        Scan for secrets and credentials in code.

        Args:
            target: Path to file or directory

        Returns:
            List of findings
        """
        findings = []
        target_path = Path(target)

        files_to_scan = []
        if target_path.is_file():
            files_to_scan = [target_path]
        elif target_path.is_dir():
            # Scan all text files
            for ext in ['*.py', '*.js', '*.ts', '*.jsx', '*.tsx', '*.json', '*.yaml', '*.yml', '*.xml', '*.md', '*.txt', '*.sh', '*.bash']:
                files_to_scan.extend(target_path.rglob(ext))

        for file_path in files_to_scan:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')

                for pattern_name, pattern in self.SECRET_PATTERNS.items():
                    for match in pattern.finditer(content):
                        line_num = content[:match.start()].count('\n') + 1
                        line_content = lines[line_num - 1] if line_num <= len(lines) else ""

                        findings.append({
                            "severity": "critical",
                            "category": "A07:2021-Identification and Authentication Failures",
                            "description": f"Potential secret ({pattern_name}) exposed in code",
                            "location": f"{file_path}:{line_num}",
                            "evidence": line_content.strip()[:100] + "...",
                            "remediation": "Remove secret from code, rotate credentials, use environment variables",
                            "effort": "1-2 hours"
                        })

            except Exception as e:
                logger.warning(f"Could not scan file for secrets {file_path}: {e}")

        return findings

    def _calculate_severity_summary(self, findings: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calculate severity counts from findings."""
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for finding in findings:
            severity = finding.get("severity", "low").lower()
            if severity in summary:
                summary[severity] += 1

        return summary

    def _generate_recommendations(self, findings: List[Dict[str, Any]]) -> List[str]:
        """Generate prioritized recommendations from findings."""
        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(
            findings,
            key=lambda f: severity_order.get(f.get("severity", "low"), 4)
        )

        recommendations = []
        seen_remediations = set()

        for finding in sorted_findings:
            remediation = finding.get("remediation", "")
            if remediation and remediation not in seen_remediations:
                recommendations.append(remediation)
                seen_remediations.add(remediation)

        return recommendations

    def store_findings(self, audit_id: str, findings: List[Dict[str, Any]]) -> bool:
        """
        Store audit findings in Neo4j.

        Updates the SecurityAudit node with:
        - findings (JSON array)
        - severity_summary (counts by severity)
        - recommendations (JSON array)
        - completed_at timestamp

        Args:
            audit_id: UUID of the audit
            findings: List of finding dictionaries

        Returns:
            True if successful

        Raises:
            AuditNotFoundError: If the audit doesn't exist
            SecurityAuditError: If the update fails
        """
        severity_summary = self._calculate_severity_summary(findings)
        recommendations = self._generate_recommendations(findings)
        completed_at = self._now()

        # Parameterized Cypher query
        cypher = """
        MATCH (sa:SecurityAudit {id: $audit_id})
        SET sa.findings = $findings_json,
            sa.severity_summary = $severity_summary,
            sa.recommendations = $recommendations_json,
            sa.completed_at = $completed_at
        RETURN sa.id as audit_id
        """

        with self._get_session() as session:
            if session is None:
                logger.warning(f"Fallback mode: Findings storage simulated for {audit_id}")
                return True

            try:
                result = session.run(
                    cypher,
                    audit_id=audit_id,
                    findings_json=json.dumps(findings),
                    severity_summary=json.dumps(severity_summary),
                    recommendations_json=json.dumps(recommendations),
                    completed_at=completed_at
                )
                record = result.single()
                if record:
                    logger.info(f"Findings stored for audit: {audit_id}")
                    return True
                else:
                    raise AuditNotFoundError(f"Audit {audit_id} not found")
            except Neo4jError as e:
                logger.error(f"Failed to store findings: {e}")
                raise SecurityAuditError(f"Neo4j error: {e}")

    def _update_audit_status(
        self,
        audit_id: str,
        status: str,
        claimed_by: Optional[str] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """
        Update the status of an audit.

        Args:
            audit_id: UUID of the audit
            status: New status ('pending', 'in_progress', 'completed', 'failed')
            claimed_by: Agent claiming the audit (optional)
            completed_at: Completion timestamp (optional)

        Returns:
            True if successful
        """
        cypher = """
        MATCH (sa:SecurityAudit {id: $audit_id})
        SET sa.status = $status
        """

        params = {
            "audit_id": audit_id,
            "status": status
        }

        if claimed_by:
            cypher += ", sa.claimed_by = $claimed_by"
            params["claimed_by"] = claimed_by

        if completed_at:
            cypher += ", sa.completed_at = $completed_at"
            params["completed_at"] = completed_at

        cypher += " RETURN sa.id as audit_id"

        with self._get_session() as session:
            if session is None:
                return True

            try:
                result = session.run(cypher, **params)
                record = result.single()
                return record is not None
            except Neo4jError as e:
                logger.error(f"Failed to update audit status: {e}")
                return False

    def get_audit_status(self, audit_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of an audit.

        Args:
            audit_id: UUID of the audit

        Returns:
            Dict with audit details if found, None otherwise
        """
        cypher = """
        MATCH (sa:SecurityAudit {id: $audit_id})
        RETURN sa
        """

        with self._get_session() as session:
            if session is None:
                return None

            try:
                result = session.run(cypher, audit_id=audit_id)
                record = result.single()
                if record:
                    audit_data = dict(record["sa"])
                    # Parse JSON fields
                    if "findings" in audit_data and audit_data["findings"]:
                        try:
                            audit_data["findings"] = json.loads(audit_data["findings"])
                        except json.JSONDecodeError:
                            pass
                    if "severity_summary" in audit_data and audit_data["severity_summary"]:
                        try:
                            audit_data["severity_summary"] = json.loads(audit_data["severity_summary"])
                        except json.JSONDecodeError:
                            pass
                    if "recommendations" in audit_data and audit_data["recommendations"]:
                        try:
                            audit_data["recommendations"] = json.loads(audit_data["recommendations"])
                        except json.JSONDecodeError:
                            pass
                    return audit_data
                return None
            except Neo4jError as e:
                logger.error(f"Failed to get audit status: {e}")
                return None

    def list_pending_audits(self) -> List[Dict[str, Any]]:
        """
        List all pending security audits.

        Returns:
            List of audit dictionaries
        """
        cypher = """
        MATCH (sa:SecurityAudit)
        WHERE sa.status = 'pending'
        RETURN sa
        ORDER BY sa.created_at ASC
        """

        with self._get_session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher)
                audits = []
                for record in result:
                    audit_data = dict(record["sa"])
                    audits.append(audit_data)
                return audits
            except Neo4jError as e:
                logger.error(f"Failed to list pending audits: {e}")
                return []

    def escalate_critical(self, audit_id: str, findings: List[Dict[str, Any]]) -> bool:
        """
        Escalate critical findings to Kublai via notification.

        Creates a high-priority notification for Kublai (main) agent
        when critical security issues are discovered.

        Args:
            audit_id: UUID of the audit
            findings: List of critical findings to escalate

        Returns:
            True if escalation notification was created
        """
        if not findings:
            return False

        try:
            # Create summary of critical findings
            finding_summary = "; ".join([
                f"{f.get('category', 'Unknown')}: {f.get('description', 'No description')[:100]}"
                for f in findings[:3]  # Limit to first 3
            ])

            summary = (f"CRITICAL: Security audit {audit_id} found "
                      f"{len(findings)} critical issue(s). {finding_summary}")

            # Create notification for Kublai
            self.memory.create_notification(
                agent="kublai",
                type="security_alert",
                summary=summary,
                task_id=audit_id
            )

            # Also notify Ögedei for operational awareness
            self.memory.create_notification(
                agent="ögedei",
                type="security_notification",
                summary=f"Critical security findings in audit {audit_id}: {len(findings)} issue(s)",
                task_id=audit_id
            )

            logger.warning(f"Critical findings escalated for audit {audit_id}: {len(findings)} issues")
            return True

        except Exception as e:
            logger.error(f"Failed to escalate critical findings: {e}")
            return False

    def get_audit_history(self, target: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get historical audit results.

        Args:
            target: Filter by target (optional)
            limit: Maximum number of results to return

        Returns:
            List of audit dictionaries
        """
        if target:
            cypher = """
            MATCH (sa:SecurityAudit)
            WHERE sa.target = $target
            RETURN sa
            ORDER BY sa.created_at DESC
            LIMIT $limit
            """
            params = {"target": target, "limit": limit}
        else:
            cypher = """
            MATCH (sa:SecurityAudit)
            RETURN sa
            ORDER BY sa.created_at DESC
            LIMIT $limit
            """
            params = {"limit": limit}

        with self._get_session() as session:
            if session is None:
                return []

            try:
                result = session.run(cypher, **params)
                audits = []
                for record in result:
                    audit_data = dict(record["sa"])
                    # Parse JSON fields
                    for field in ["findings", "severity_summary", "recommendations"]:
                        if field in audit_data and audit_data[field]:
                            try:
                                audit_data[field] = json.loads(audit_data[field])
                            except json.JSONDecodeError:
                                pass
                    audits.append(audit_data)
                return audits
            except Neo4jError as e:
                logger.error(f"Failed to get audit history: {e}")
                return []

    def create_security_indexes(self) -> List[str]:
        """
        Create recommended indexes for SecurityAudit nodes.

        Returns:
            List of created index names
        """
        indexes = [
            ("CREATE INDEX security_audit_id_idx IF NOT EXISTS FOR (sa:SecurityAudit) ON (sa.id)", "security_audit_id_idx"),
            ("CREATE INDEX security_audit_status_idx IF NOT EXISTS FOR (sa:SecurityAudit) ON (sa.status)", "security_audit_status_idx"),
            ("CREATE INDEX security_audit_target_idx IF NOT EXISTS FOR (sa:SecurityAudit) ON (sa.target)", "security_audit_target_idx"),
            ("CREATE INDEX security_audit_created_idx IF NOT EXISTS FOR (sa:SecurityAudit) ON (sa.created_at)", "security_audit_created_idx"),
        ]

        created = []

        with self._get_session() as session:
            if session is None:
                logger.warning("Cannot create indexes: Neo4j unavailable")
                return created

            for cypher, name in indexes:
                try:
                    session.run(cypher)
                    created.append(name)
                    logger.info(f"Created index: {name}")
                except Neo4jError as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Failed to create index {name}: {e}")

        return created


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging for example
    logging.basicConfig(level=logging.INFO)

    # Example usage
    try:
        from openclaw_memory import OperationalMemory

        with OperationalMemory(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password",
            fallback_mode=True
        ) as memory:

            # Initialize security audit protocol
            protocol = SecurityAuditProtocol(memory)

            # Create security indexes
            indexes = protocol.create_security_indexes()
            print(f"Created indexes: {indexes}")

            # Create a security audit
            audit_id = protocol.create_security_audit(
                target="/path/to/code",
                audit_type="full_audit",
                requested_by="kublai"
            )
            print(f"Created security audit: {audit_id}")

            # List pending audits
            pending = protocol.list_pending_audits()
            print(f"Pending audits: {len(pending)}")

            # Get audit status
            status = protocol.get_audit_status(audit_id)
            print(f"Audit status: {status['status'] if status else 'Not found'}")

            # Note: To run the actual audit, you would call:
            # results = protocol.run_audit(audit_id)
            # print(f"Audit results: {results}")

    except ImportError:
        print("OperationalMemory not available for example")
    except Exception as e:
        print(f"Example error: {e}")
