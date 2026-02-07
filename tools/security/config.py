"""
Security Configuration for Neo4j Operational Memory.

Environment variables and configuration for the security module.
"""

import os
from typing import Optional


class SecurityConfig:
    """Security configuration loaded from environment variables."""

    # Encryption
    NEO4J_FIELD_ENCRYPTION_KEY: Optional[str] = None
    QUERY_HASH_SALT: Optional[str] = None

    # Anonymization
    ANONYMIZATION_SALT: Optional[str] = None

    # Tokenization
    TOKEN_VAULT_URL: Optional[str] = None
    TOKEN_VAULT_PASSWORD: Optional[str] = None
    TOKEN_TTL_DAYS: int = 90

    # Neo4j Security
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: Optional[str] = None
    NEO4J_VERIFY_MODE: str = "require"  # require, verify-ca, verify-full
    NEO4J_CA_CERT_PATH: Optional[str] = None

    # Audit
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_LOG_LEVEL: str = "INFO"

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Load configuration from environment variables."""
        config = cls()

        # Encryption
        config.NEO4J_FIELD_ENCRYPTION_KEY = os.getenv("NEO4J_FIELD_ENCRYPTION_KEY")
        config.QUERY_HASH_SALT = os.getenv("QUERY_HASH_SALT")

        # Anonymization
        config.ANONYMIZATION_SALT = os.getenv("ANONYMIZATION_SALT")

        # Tokenization
        config.TOKEN_VAULT_URL = os.getenv("TOKEN_VAULT_URL")
        config.TOKEN_VAULT_PASSWORD = os.getenv("TOKEN_VAULT_PASSWORD")
        config.TOKEN_TTL_DAYS = int(os.getenv("TOKEN_TTL_DAYS", "90"))

        # Neo4j
        config.NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        config.NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        config.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
        config.NEO4J_VERIFY_MODE = os.getenv("NEO4J_VERIFY_MODE", "require")
        config.NEO4J_CA_CERT_PATH = os.getenv("NEO4J_CA_CERT_PATH")

        # Audit
        config.AUDIT_LOG_ENABLED = os.getenv("AUDIT_LOG_ENABLED", "true").lower() == "true"
        config.AUDIT_LOG_LEVEL = os.getenv("AUDIT_LOG_LEVEL", "INFO")

        return config

    def validate(self) -> list:
        """Validate configuration and return list of issues."""
        issues = []

        # Check for default/placeholder values in production
        if not self.NEO4J_FIELD_ENCRYPTION_KEY:
            issues.append("WARNING: NEO4J_FIELD_ENCRYPTION_KEY not set")

        if not self.ANONYMIZATION_SALT:
            issues.append("WARNING: ANONYMIZATION_SALT not set")

        if not self.NEO4J_PASSWORD:
            issues.append("ERROR: NEO4J_PASSWORD not set")

        if not self.NEO4J_URI.startswith(("bolt+s://", "neo4j+s://")):
            issues.append("WARNING: Neo4j connection should use TLS")

        return issues
