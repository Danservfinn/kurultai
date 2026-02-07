"""
AST-based static analysis for Python code security validation.

This module provides lightweight security scanning using Python's built-in
ast module to detect common vulnerabilities in learned capabilities.
"""

import ast
import re
from typing import Dict, List, Optional


class ASTParser:
    """
    Analyzes Python code for security vulnerabilities using AST parsing.

    Detects:
    - Code execution risks (eval, exec, compile)
    - Command injection vulnerabilities (os.system, subprocess with shell=True)
    - Hardcoded secrets (passwords, API keys, tokens)
    - SQL injection patterns (string concatenation with SQL keywords)
    """

    # Security-sensitive function names
    CODE_EXEC_FUNCS = {"eval", "exec", "compile", "__import__"}
    COMMAND_EXEC_FUNCS = {"system", "popen", "spawn", "spawnl", "spawnle"}
    SUBPROCESS_FUNCS = {"call", "run", "Popen", "check_call", "check_output"}

    # Secret-related variable name patterns
    SECRET_PATTERNS = [
        r"password",
        r"passwd",
        r"pwd",
        r"secret",
        r"api[_-]?key",
        r"access[_-]?token",
        r"auth[_-]?token",
        r"private[_-]?key",
        r"credential",
    ]

    # SQL keywords for injection detection
    SQL_KEYWORDS = {
        "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
        "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "UNION"
    }

    def __init__(self):
        """Initialize the AST parser."""
        self.findings: List[Dict[str, any]] = []
        self.secret_regex = re.compile(
            r"|".join(self.SECRET_PATTERNS),
            re.IGNORECASE
        )

    def analyze_code(self, code: str) -> List[Dict[str, any]]:
        """
        Analyze Python code for security vulnerabilities.

        Args:
            code: Python source code to analyze

        Returns:
            List of findings, each containing:
            - category: vulnerability category
            - severity: critical/high/medium/low
            - line: line number in source
            - description: human-readable description
            - node_type: AST node type

        Raises:
            SyntaxError: If code cannot be parsed
        """
        self.findings = []

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return [{
                "category": "syntax_error",
                "severity": "critical",
                "line": e.lineno or 0,
                "description": f"Syntax error: {e.msg}",
                "node_type": "SyntaxError"
            }]

        # Visit all nodes in the AST
        self._analyze_node(tree)

        # Sort findings by severity and line number
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        self.findings.sort(
            key=lambda f: (severity_order.get(f["severity"], 4), f["line"])
        )

        return self.findings

    def _analyze_node(self, node: ast.AST) -> None:
        """Recursively analyze AST nodes."""
        # Check for code execution vulnerabilities
        if isinstance(node, ast.Call):
            self._check_code_execution(node)
            self._check_command_injection(node)

        # Check for hardcoded secrets
        elif isinstance(node, ast.Assign):
            self._check_hardcoded_secrets(node)

        # Check for SQL injection patterns
        elif isinstance(node, (ast.BinOp, ast.JoinedStr)):
            self._check_sql_injection(node)

        # Recurse to child nodes
        for child in ast.iter_child_nodes(node):
            self._analyze_node(child)

    def _check_code_execution(self, node: ast.Call) -> None:
        """Detect dangerous code execution functions."""
        func_name = self._get_function_name(node.func)

        if func_name in self.CODE_EXEC_FUNCS:
            self.findings.append({
                "category": "code_execution",
                "severity": "high",
                "line": node.lineno,
                "description": (
                    f"Dangerous code execution: {func_name}() can execute "
                    f"arbitrary code and should be avoided"
                ),
                "node_type": "ast.Call"
            })

    def _check_command_injection(self, node: ast.Call) -> None:
        """Detect command injection vulnerabilities."""
        func_name = self._get_function_name(node.func)

        # Check os.system, os.popen, etc.
        if isinstance(node.func, ast.Attribute):
            if (isinstance(node.func.value, ast.Name) and
                node.func.value.id == "os" and
                func_name in self.COMMAND_EXEC_FUNCS):
                self.findings.append({
                    "category": "command_injection",
                    "severity": "critical",
                    "line": node.lineno,
                    "description": (
                        f"Command injection risk: os.{func_name}() executes "
                        f"shell commands directly. Use subprocess with shell=False"
                    ),
                    "node_type": "ast.Call"
                })

        # Check subprocess.call/run/Popen with shell=True
        if func_name in self.SUBPROCESS_FUNCS:
            has_shell_true = any(
                kw.arg == "shell" and
                isinstance(kw.value, ast.Constant) and
                kw.value.value is True
                for kw in node.keywords
            )

            if has_shell_true:
                self.findings.append({
                    "category": "command_injection",
                    "severity": "critical",
                    "line": node.lineno,
                    "description": (
                        f"Command injection risk: subprocess.{func_name}() "
                        f"with shell=True enables shell injection attacks"
                    ),
                    "node_type": "ast.Call"
                })

    def _check_hardcoded_secrets(self, node: ast.Assign) -> None:
        """Detect hardcoded secrets in variable assignments."""
        for target in node.targets:
            var_name = self._get_variable_name(target)

            if var_name and self.secret_regex.search(var_name):
                # Check if the assigned value is a string literal
                if isinstance(node.value, ast.Constant):
                    if isinstance(node.value.value, str):
                        value_preview = node.value.value[:20]
                        if len(node.value.value) > 20:
                            value_preview += "..."

                        self.findings.append({
                            "category": "hardcoded_secrets",
                            "severity": "medium",
                            "line": node.lineno,
                            "description": (
                                f"Hardcoded secret detected: variable '{var_name}' "
                                f"contains a string literal. Use environment variables "
                                f"or secure credential storage"
                            ),
                            "node_type": "ast.Assign"
                        })

    def _check_sql_injection(self, node: ast.AST) -> None:
        """Detect SQL injection patterns via string concatenation."""
        # Check binary operations (+ operator)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            if self._contains_sql_keyword(node):
                self.findings.append({
                    "category": "sql_injection",
                    "severity": "high",
                    "line": node.lineno,
                    "description": (
                        "SQL injection risk: SQL query construction via "
                        "string concatenation. Use parameterized queries"
                    ),
                    "node_type": "ast.BinOp"
                })

        # Check f-strings (JoinedStr)
        elif isinstance(node, ast.JoinedStr):
            if self._contains_sql_keyword_in_fstring(node):
                self.findings.append({
                    "category": "sql_injection",
                    "severity": "high",
                    "line": node.lineno,
                    "description": (
                        "SQL injection risk: SQL query construction via "
                        "f-string interpolation. Use parameterized queries"
                    ),
                    "node_type": "ast.JoinedStr"
                })

    def _get_function_name(self, func: ast.AST) -> Optional[str]:
        """Extract function name from Call node."""
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            return func.attr
        return None

    def _get_variable_name(self, target: ast.AST) -> Optional[str]:
        """Extract variable name from assignment target."""
        if isinstance(target, ast.Name):
            return target.id
        elif isinstance(target, ast.Attribute):
            return target.attr
        return None

    def _contains_sql_keyword(self, node: ast.BinOp) -> bool:
        """Check if binary operation contains SQL keywords."""
        return (
            self._node_contains_sql_keyword(node.left) or
            self._node_contains_sql_keyword(node.right)
        )

    def _node_contains_sql_keyword(self, node: ast.AST) -> bool:
        """Check if a node contains SQL keywords."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return any(
                keyword in node.value.upper()
                for keyword in self.SQL_KEYWORDS
            )
        elif isinstance(node, ast.BinOp):
            return self._contains_sql_keyword(node)
        return False

    def _contains_sql_keyword_in_fstring(self, node: ast.JoinedStr) -> bool:
        """Check if f-string contains SQL keywords."""
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if any(
                    keyword in value.value.upper()
                    for keyword in self.SQL_KEYWORDS
                ):
                    return True
        return False
