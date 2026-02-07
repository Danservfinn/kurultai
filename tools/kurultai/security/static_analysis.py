"""Static analysis scanner for Kurultai v0.2 multi-agent orchestration.

Regex-based detection of dangerous code patterns in Python source strings.
This module does NOT use the AST -- AST-based analysis lives in a separate
module. Regex scanning is fast and suitable for pre-commit hooks, agent
output validation, and CI pipelines.

OWASP A03:2021 - Injection prevention.
OWASP A05:2021 - Security Misconfiguration (hardcoded secrets).

Detection categories:
    - code_execution: eval(), exec(), compile() -- severity HIGH
    - command_injection: os.system(), subprocess shell=True, os.popen() -- severity CRITICAL
    - hardcoded_secrets: password/key/token/secret string assignments -- severity MEDIUM
    - sql_injection: string concatenation in SQL queries -- severity HIGH

Usage:
    scanner = StaticAnalysis()
    findings = scanner.analyze(source_code)
    for f in findings:
        print(f"{f['severity'].upper()} [{f['category']}] line {f['line']}: {f['pattern']}")
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("kurultai.security.static_analysis")


# --- Detection rules ---
# Each rule: (pattern_name, compiled_regex, category, severity, description)
# Patterns operate on individual lines unless otherwise noted.

_SINGLE_LINE_RULES: List[Tuple[str, re.Pattern, str, str, str]] = [
    # -------------------------------------------------------------------------
    # Category: code_execution (severity: high)
    # -------------------------------------------------------------------------
    (
        "eval_call",
        re.compile(r"\beval\s*\(", re.IGNORECASE),
        "code_execution",
        "high",
        "eval() executes arbitrary expressions -- use ast.literal_eval() for data parsing",
    ),
    (
        "exec_call",
        re.compile(r"\bexec\s*\(", re.IGNORECASE),
        "code_execution",
        "high",
        "exec() executes arbitrary code -- avoid in production",
    ),
    (
        "compile_call",
        re.compile(r"\bcompile\s*\("),
        "code_execution",
        "high",
        "compile() can prepare arbitrary code for execution",
    ),
    (
        "__import__call",
        re.compile(r"__import__\s*\("),
        "code_execution",
        "high",
        "__import__() can dynamically load arbitrary modules",
    ),
    (
        "getattr_builtin",
        re.compile(r"getattr\s*\(\s*__builtins__"),
        "code_execution",
        "high",
        "getattr on __builtins__ can access dangerous functions dynamically",
    ),

    # -------------------------------------------------------------------------
    # Category: command_injection (severity: critical)
    # -------------------------------------------------------------------------
    (
        "os_system",
        re.compile(r"\bos\.system\s*\("),
        "command_injection",
        "critical",
        "os.system() executes shell commands -- use subprocess with shell=False",
    ),
    (
        "os_popen",
        re.compile(r"\bos\.popen\s*\("),
        "command_injection",
        "critical",
        "os.popen() executes shell commands -- use subprocess with shell=False",
    ),
    (
        "subprocess_shell_true",
        re.compile(r"subprocess\.\w+\s*\([^)]*shell\s*=\s*True"),
        "command_injection",
        "critical",
        "subprocess with shell=True enables shell injection attacks",
    ),
    (
        "os_exec_family",
        re.compile(r"\bos\.exec[lv]p?e?\s*\("),
        "command_injection",
        "critical",
        "os.exec*() replaces the current process with an arbitrary command",
    ),
    (
        "os_spawn",
        re.compile(r"\bos\.spawn[lv]p?e?\s*\("),
        "command_injection",
        "critical",
        "os.spawn*() spawns an arbitrary process",
    ),
    (
        "commands_module",
        re.compile(r"\bcommands\.(getoutput|getstatusoutput)\s*\("),
        "command_injection",
        "critical",
        "commands module executes shell commands (deprecated but still dangerous)",
    ),

    # -------------------------------------------------------------------------
    # Category: hardcoded_secrets (severity: medium)
    # -------------------------------------------------------------------------
    (
        "password_assignment",
        re.compile(
            r"""(?:password|passwd|pwd)\s*=\s*['"][^'"]{3,}['"]""",
            re.IGNORECASE,
        ),
        "hardcoded_secrets",
        "medium",
        "Hardcoded password detected -- use environment variables or a secret manager",
    ),
    (
        "api_key_assignment",
        re.compile(
            r"""(?:api_?key|apikey)\s*=\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        ),
        "hardcoded_secrets",
        "medium",
        "Hardcoded API key detected -- use environment variables or a secret manager",
    ),
    (
        "secret_assignment",
        re.compile(
            r"""(?:secret|secret_?key|client_?secret)\s*=\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        ),
        "hardcoded_secrets",
        "medium",
        "Hardcoded secret detected -- use environment variables or a secret manager",
    ),
    (
        "token_assignment",
        re.compile(
            r"""(?:token|access_?token|auth_?token|bearer_?token)\s*=\s*['"][^'"]{8,}['"]""",
            re.IGNORECASE,
        ),
        "hardcoded_secrets",
        "medium",
        "Hardcoded token detected -- use environment variables or a secret manager",
    ),
    (
        "private_key_inline",
        re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
        "hardcoded_secrets",
        "medium",
        "Inline private key detected -- load from file or secret manager",
    ),
    (
        "connection_string_password",
        re.compile(
            r"""(?:mysql|postgres|postgresql|mongodb|redis)://[^:]+:[^@]+@""",
            re.IGNORECASE,
        ),
        "hardcoded_secrets",
        "medium",
        "Connection string with embedded credentials detected",
    ),

    # -------------------------------------------------------------------------
    # Category: sql_injection (severity: high)
    # -------------------------------------------------------------------------
    (
        "sql_string_concat",
        re.compile(
            r"""(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+.{0,80}"""
            r"""(?:\+\s*[\w.]+|\%\s*[\w.]+|\.format\s*\()""",
            re.IGNORECASE,
        ),
        "sql_injection",
        "high",
        "SQL query with string concatenation/formatting -- use parameterized queries",
    ),
    (
        "sql_fstring",
        re.compile(
            r"""f['"].*(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+.*\{""",
            re.IGNORECASE,
        ),
        "sql_injection",
        "high",
        "SQL query in f-string -- use parameterized queries instead",
    ),
    (
        "sql_percent_format",
        re.compile(
            r"""['"].*(?:SELECT|INSERT|UPDATE|DELETE)\s+.*%s""",
            re.IGNORECASE,
        ),
        "sql_injection",
        "high",
        "SQL query with %-formatting -- use parameterized queries instead",
    ),
    (
        "cursor_execute_concat",
        re.compile(
            r"""\.execute\s*\(\s*['"].*(?:SELECT|INSERT|UPDATE|DELETE).*['"]\s*\+""",
            re.IGNORECASE,
        ),
        "sql_injection",
        "high",
        "cursor.execute() with string concatenation -- use parameterized queries",
    ),
    (
        "raw_sql_user_input",
        re.compile(
            r"""\.execute\s*\(\s*f['"]""",
            re.IGNORECASE,
        ),
        "sql_injection",
        "high",
        "cursor.execute() with f-string -- use parameterized queries",
    ),
]

# Comment and string literal patterns used to reduce false positives
_COMMENT_PATTERN = re.compile(r"^\s*#")
_DOCSTRING_TRIPLE_SINGLE = re.compile(r"^\s*'''")
_DOCSTRING_TRIPLE_DOUBLE = re.compile(r'^\s*"""')


class StaticAnalysis:
    """Regex-based static analysis scanner for Python source code.

    Scans source code strings line-by-line for dangerous patterns.
    Skips comment lines to reduce false positives. Does NOT parse
    Python AST -- that capability lives in a separate module.

    Attributes:
        skip_comments: Whether to skip lines that are pure comments.
    """

    def __init__(self, skip_comments: bool = True) -> None:
        """Initialize the scanner.

        Args:
            skip_comments: If True, lines starting with # are skipped.
                Defaults to True to reduce false positives in documentation.
        """
        self.skip_comments = skip_comments

    def analyze(self, code: str) -> List[Dict]:
        """Scan Python source code for dangerous patterns.

        Args:
            code: Python source code as a string.

        Returns:
            List of finding dicts. Each dict contains:
                - pattern (str): The rule name that triggered.
                - category (str): Detection category.
                - severity (str): "critical", "high", or "medium".
                - line (int): 1-based line number where the finding occurs.
                - match (str): The matched text snippet.
                - description (str): Human-readable explanation and remediation.
        """
        if not code or not isinstance(code, str):
            return []

        findings: List[Dict] = []
        lines = code.splitlines()
        in_docstring = False
        docstring_char: Optional[str] = None

        for line_num_zero, line in enumerate(lines):
            line_num = line_num_zero + 1

            # --- Docstring tracking (skip contents of docstrings) ---
            stripped = line.strip()
            if not in_docstring:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    docstring_char = stripped[:3]
                    # Check if docstring opens and closes on the same line
                    if stripped.count(docstring_char) >= 2 and len(stripped) > 3:
                        continue  # Single-line docstring, skip it
                    in_docstring = True
                    continue
            else:
                if docstring_char and docstring_char in stripped:
                    in_docstring = False
                continue

            # --- Skip pure comment lines ---
            if self.skip_comments and _COMMENT_PATTERN.match(line):
                continue

            # --- Apply each rule ---
            for pattern_name, compiled, category, severity, description in _SINGLE_LINE_RULES:
                match = compiled.search(line)
                if match:
                    matched_text = match.group().strip()
                    # Truncate long matches to keep output readable
                    if len(matched_text) > 120:
                        matched_text = matched_text[:117] + "..."

                    finding = {
                        "pattern": pattern_name,
                        "category": category,
                        "severity": severity,
                        "line": line_num,
                        "match": matched_text,
                        "description": description,
                    }
                    findings.append(finding)
                    logger.debug(
                        "Finding: %s [%s/%s] at line %d",
                        pattern_name, category, severity, line_num,
                    )

        return findings

    def analyze_file(self, file_path: str) -> List[Dict]:
        """Convenience method to analyze a file by path.

        Args:
            file_path: Absolute path to a Python file.

        Returns:
            List of finding dicts (same format as analyze()).

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If the file cannot be read.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        findings = self.analyze(code)
        # Attach file_path to each finding for multi-file reports
        for finding in findings:
            finding["file"] = file_path
        return findings

    def summarize(self, findings: List[Dict]) -> Dict:
        """Produce a summary of findings grouped by severity and category.

        Args:
            findings: List of finding dicts from analyze().

        Returns:
            Dict with keys:
                - total (int): Total number of findings.
                - by_severity (dict): Count per severity level.
                - by_category (dict): Count per category.
                - critical_findings (list): Only the critical-severity findings.
        """
        by_severity: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        critical_findings = []

        for finding in findings:
            sev = finding.get("severity", "unknown")
            cat = finding.get("category", "unknown")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[cat] = by_category.get(cat, 0) + 1
            if sev == "critical":
                critical_findings.append(finding)

        return {
            "total": len(findings),
            "by_severity": by_severity,
            "by_category": by_category,
            "critical_findings": critical_findings,
        }
