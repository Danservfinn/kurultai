"""
Cypher Injection Prevention for Neo4j.

OWASP A03:2021 - Injection prevention for Neo4j Cypher queries.

Provides validation, sanitization, and secure query building to prevent
Cypher injection attacks.
"""

import re
import logging
from typing import Any, Dict, Set, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Dangerous Cypher keywords that should never come from user input
DANGEROUS_KEYWORDS = {
    "CALL", "LOAD", "CSV", "FROM", "YIELD",
    "CREATE", "DELETE", "REMOVE", "SET", "DROP",
    "INDEX", "CONSTRAINT", "DATABASE", "USER", "ROLE",
    "PASSWORD", "PRIVILEGE", "GRANT", "DENY", "REVOKE",
    "FOREACH", "APOC", "GDS",  # APOC and GDS procedures
}

# Pattern for detecting injection attempts
INJECTION_PATTERNS = [
    (r'\$\{[^}]+\}', "template_literal"),  # Template literal style: ${...}
    (r'`[^`]+`', "backtick_escape"),       # Backtick escaping
    (r'\/\/.*', "line_comment"),          # Comment injection
    (r'\/\*.*\*\/', "block_comment"),     # Block comment injection
    (r';\s*\w+', "statement_chaining"),   # Statement chaining
    (r'\bOR\s+\d+=\d+', "boolean_or"),    # Boolean OR injection
    (r'\bAND\s+\d+=\d+', "boolean_and"),  # Boolean AND injection
    (r'UNION\s+ALL', "union_injection"),  # UNION injection
]

# Allowed Cypher parameter types
ALLOWED_PARAM_TYPES = (str, int, float, bool, list, type(None))


class CypherInjectionError(Exception):
    """Raised when potential Cypher injection is detected."""
    pass


class ValidationError(Exception):
    """Raised when query validation fails."""
    pass


@dataclass
class ValidationResult:
    """Result of query validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]


class CypherInjectionPrevention:
    """
    Prevents Cypher injection attacks through validation and sanitization.

    OWASP A03:2021 - Injection prevention for Neo4j Cypher queries.

    Example:
        # Validate query before execution
        result = CypherInjectionPrevention.validate_query(
            query="MATCH (t:Task {id: $task_id}) RETURN t",
            allowed_params={"task_id"}
        )

        if not result.is_valid:
            raise CypherInjectionError(result.errors[0])

        # Sanitize parameters
        safe_value = CypherInjectionPrevention.sanitize_parameter(
            "description", user_input
        )
    """

    @classmethod
    def validate_query(
        cls,
        query: str,
        allowed_params: Optional[Set[str]] = None
    ) -> ValidationResult:
        """
        Validate Cypher query for injection attempts.

        Args:
            query: Cypher query string
            allowed_params: Set of allowed parameter names

        Returns:
            ValidationResult with is_valid, errors, and warnings
        """
        errors = []
        warnings = []

        if not query or not isinstance(query, str):
            return ValidationResult(
                is_valid=False,
                errors=["Query must be a non-empty string"],
                warnings=[]
            )

        # Check for direct value interpolation (anti-pattern)
        if cls._has_string_interpolation(query):
            errors.append(
                "Query contains potential string interpolation. "
                "Use parameterized queries only."
            )

        # Check for injection patterns
        for pattern, pattern_name in INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                errors.append(
                    f"Query contains suspicious pattern: {pattern_name}"
                )

        # Check for dangerous keywords in unexpected contexts
        keyword_issues = cls._check_dangerous_keywords(query)
        errors.extend(keyword_issues)

        # Validate parameter names
        if allowed_params is not None:
            param_issues = cls._validate_parameters(query, allowed_params)
            warnings.extend(param_issues)

        # Check for common mistakes
        if "MATCH" not in query.upper() and "CREATE" not in query.upper():
            warnings.append("Query lacks MATCH or CREATE clause")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    @classmethod
    def _has_string_interpolation(cls, query: str) -> bool:
        """Check for string interpolation patterns."""
        # Check for f-string style: f"...{var}..."
        if re.search(r'f["\'][^"\']*\{[^}]+\}[^"\']*["\']', query):
            return True

        # Check for .format() style
        if re.search(r'\.format\s*\(', query):
            return True

        # Check for % formatting
        if re.search(r'%\s*\(?\w+', query):
            return True

        # Check for $var outside of parameter context
        if re.search(r'["\'][^"\']*\$\w+[^"\']*["\']', query):
            return True

        return False

    @classmethod
    def _check_dangerous_keywords(cls, query: str) -> List[str]:
        """Check for dangerous keywords in query."""
        issues = []
        query_upper = query.upper()

        for keyword in DANGEROUS_KEYWORDS:
            # Check if keyword appears outside of comments/strings
            # This is a simplified check - production should use proper parsing
            pattern = rf'\b{keyword}\b'
            if re.search(pattern, query_upper):
                # Additional context check
                if keyword in ("CALL", "LOAD", "CSV"):
                    issues.append(
                        f"Query contains dangerous keyword: {keyword}. "
                        "Ensure this is intentional and safe."
                    )

        return issues

    @classmethod
    def _validate_parameters(
        cls,
        query: str,
        allowed_params: Set[str]
    ) -> List[str]:
        """Validate that query only uses allowed parameters."""
        warnings = []

        # Extract parameter names from query
        param_pattern = r'\$(\w+)'
        found_params = set(re.findall(param_pattern, query))

        # Check for unexpected parameters
        unexpected = found_params - allowed_params
        if unexpected:
            warnings.append(
                f"Query uses unexpected parameters: {unexpected}"
            )

        return warnings

    @classmethod
    def sanitize_parameter(
        cls,
        name: str,
        value: Any,
        allowed_types: tuple = ALLOWED_PARAM_TYPES
    ) -> Any:
        """
        Sanitize query parameter.

        Args:
            name: Parameter name
            value: Parameter value
            allowed_types: Allowed Python types

        Returns:
            Sanitized value

        Raises:
            CypherInjectionError: If value type is not allowed
        """
        if value is None:
            return None

        if not isinstance(value, allowed_types):
            raise CypherInjectionError(
                f"Parameter '{name}' has disallowed type: {type(value).__name__}. "
                f"Allowed types: {[t.__name__ for t in allowed_types]}"
            )

        # Additional sanitization for strings
        if isinstance(value, str):
            return cls._sanitize_string(value, name)

        # Sanitize list contents
        if isinstance(value, list):
            return [
                cls.sanitize_parameter(f"{name}[{i}]", item, allowed_types)
                for i, item in enumerate(value)
            ]

        return value

    @classmethod
    def _sanitize_string(cls, value: str, name: str) -> str:
        """Sanitize string parameter."""
        # Check for null bytes
        if '\x00' in value:
            raise CypherInjectionError(
                f"Parameter '{name}' contains null bytes"
            )

        # Check for control characters
        control_chars = [c for c in value if ord(c) < 32 and c not in '\t\n\r']
        if control_chars:
            logger.warning(
                f"Parameter '{name}' contains control characters"
            )
            # Remove control characters
            value = ''.join(c for c in value if ord(c) >= 32 or c in '\t\n\r')

        # Check for Cypher comment markers
        if '//' in value or '/*' in value or '*/' in value:
            logger.warning(
                f"Parameter '{name}' contains comment markers"
            )
            # Escape comment markers
            value = value.replace('//', r'\/\/')
            value = value.replace('/*', '/ *')
            value = value.replace('*/', '* /')

        # Check for backtick escaping
        if '`' in value:
            logger.warning(
                f"Parameter '{name}' contains backticks"
            )
            # Remove backticks
            value = value.replace('`', '')

        return value

    @classmethod
    def sanitize_label(cls, label: str) -> str:
        """
        Sanitize node/relationship label.

        Labels should be alphanumeric with underscores only.

        Args:
            label: Label to sanitize

        Returns:
            Sanitized label

        Raises:
            CypherInjectionError: If label contains dangerous characters
        """
        if not label:
            raise CypherInjectionError("Label cannot be empty")

        # Labels should match pattern: [A-Za-z_][A-Za-z0-9_]*
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', label):
            raise CypherInjectionError(
                f"Invalid label format: '{label}'. "
                "Labels must be alphanumeric with underscores only."
            )

        # Check against reserved keywords
        if label.upper() in DANGEROUS_KEYWORDS:
            raise CypherInjectionError(
                f"Label '{label}' is a reserved keyword"
            )

        return label

    @classmethod
    def sanitize_property_key(cls, key: str) -> str:
        """
        Sanitize property key.

        Property keys should be alphanumeric with underscores.

        Args:
            key: Property key to sanitize

        Returns:
            Sanitized key
        """
        if not key:
            raise CypherInjectionError("Property key cannot be empty")

        # Property keys can contain more characters than labels
        # but we restrict for safety
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            raise CypherInjectionError(
                f"Invalid property key format: '{key}'"
            )

        return key


class SecureQueryBuilder:
    """
    Builder pattern for constructing safe Cypher queries.

    Ensures all values are properly parameterized.

    Example:
        builder = SecureQueryBuilder()

        query, params = (builder
            .match("(t:Task)")
            .where("t.id = $task_id", task_id="123")
            .and_where("t.status = $status", status="pending")
            .return_("t")
            .build())

        # Execute with driver
        result = session.run(query, **params)
    """

    def __init__(self):
        self.clauses = []
        self.params = {}
        self.param_counter = 0

    def _add_param(self, name: str, value: Any) -> str:
        """Add parameter and return unique parameter name."""
        # Sanitize value
        safe_value = CypherInjectionPrevention.sanitize_parameter(name, value)

        # Generate unique parameter name
        unique_name = f"{name}_{self.param_counter}"
        self.param_counter += 1

        self.params[unique_name] = safe_value
        return f"${unique_name}"

    def match(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add MATCH clause."""
        self.clauses.append(("MATCH", pattern, params))
        return self

    def optional_match(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add OPTIONAL MATCH clause."""
        self.clauses.append(("OPTIONAL MATCH", pattern, params))
        return self

    def where(self, condition: str, **params) -> 'SecureQueryBuilder':
        """Add WHERE clause."""
        self.clauses.append(("WHERE", condition, params))
        return self

    def and_where(self, condition: str, **params) -> 'SecureQueryBuilder':
        """Add AND condition to WHERE."""
        self.clauses.append(("AND", condition, params))
        return self

    def or_where(self, condition: str, **params) -> 'SecureQueryBuilder':
        """Add OR condition to WHERE."""
        self.clauses.append(("OR", condition, params))
        return self

    def create(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add CREATE clause."""
        self.clauses.append(("CREATE", pattern, params))
        return self

    def merge(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add MERGE clause."""
        self.clauses.append(("MERGE", pattern, params))
        return self

    def set(self, assignment: str, **params) -> 'SecureQueryBuilder':
        """Add SET clause."""
        self.clauses.append(("SET", assignment, params))
        return self

    def delete(self, variable: str) -> 'SecureQueryBuilder':
        """Add DELETE clause."""
        self.clauses.append(("DELETE", variable, {}))
        return self

    def detach_delete(self, variable: str) -> 'SecureQueryBuilder':
        """Add DETACH DELETE clause."""
        self.clauses.append(("DETACH DELETE", variable, {}))
        return self

    def with_(self, expression: str, **params) -> 'SecureQueryBuilder':
        """Add WITH clause."""
        self.clauses.append(("WITH", expression, params))
        return self

    def return_(self, expression: str, **params) -> 'SecureQueryBuilder':
        """Add RETURN clause."""
        self.clauses.append(("RETURN", expression, params))
        return self

    def order_by(self, expression: str) -> 'SecureQueryBuilder':
        """Add ORDER BY clause."""
        self.clauses.append(("ORDER BY", expression, {}))
        return self

    def limit(self, count: int) -> 'SecureQueryBuilder':
        """Add LIMIT clause."""
        self.clauses.append(("LIMIT", str(count), {}))
        return self

    def skip(self, count: int) -> 'SecureQueryBuilder':
        """Add SKIP clause."""
        self.clauses.append(("SKIP", str(count), {}))
        return self

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """
        Build final query and parameters.

        Returns:
            Tuple of (query_string, parameters)
        """
        query_parts = []

        for clause_type, clause_content, clause_params in self.clauses:
            # Replace parameter placeholders
            content = clause_content
            for param_name, param_value in clause_params.items():
                placeholder = f"${param_name}"
                if placeholder in content:
                    unique_name = self._add_param(param_name, param_value)
                    content = content.replace(placeholder, unique_name)

            query_parts.append(f"{clause_type} {content}")

        query = "\n".join(query_parts)

        # Validate final query
        result = CypherInjectionPrevention.validate_query(query)
        if not result.is_valid:
            raise CypherInjectionError(
                f"Generated query failed validation: {result.errors}"
            )

        return query, self.params


class QueryWhitelist:
    """
    Whitelist-based query validation for high-security scenarios.

    Only allows pre-approved query patterns.
    """

    def __init__(self):
        self.allowed_patterns: List[str] = []

    def add_pattern(self, pattern: str):
        """Add allowed query pattern."""
        # Normalize pattern (remove extra whitespace)
        normalized = " ".join(pattern.split())
        self.allowed_patterns.append(normalized)

    def validate(self, query: str) -> bool:
        """
        Validate query against whitelist.

        Args:
            query: Query to validate

        Returns:
            True if query matches an allowed pattern
        """
        # Normalize query
        normalized = " ".join(query.split())

        for pattern in self.allowed_patterns:
            # Convert pattern to regex
            # Replace $param with regex for parameter values
            regex_pattern = re.escape(pattern)
            regex_pattern = regex_pattern.replace(r'\$\w+', r'\$\w+')

            if re.match(regex_pattern, normalized, re.IGNORECASE):
                return True

        return False
