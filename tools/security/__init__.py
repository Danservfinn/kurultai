"""
Security module for Neo4j-backed operational memory.

Provides privacy-preserving storage, access control, and audit logging
for the 6-agent OpenClaw system.
"""

from .privacy_boundary import (
    DataClassification,
    StorageLocation,
    PrivacyBoundary,
    PRIVACY_BOUNDARIES,
    apply_privacy_boundary,
    PrivacyBlockedError
)

from .anonymization import (
    AnonymizationEngine,
    LLMPrivacyReviewer,
    PIIEntity
)

from .encryption import (
    FieldEncryption,
    EncryptedPropertyManager
)

from .tokenization import (
    TokenizationService,
    HybridPrivacyProcessor
)

from .access_control import (
    Neo4jSecurityManager,
    SenderIsolationEnforcer,
    AGENT_ROLES
)

from .injection_prevention import (
    CypherInjectionPrevention,
    SecureQueryBuilder,
    CypherInjectionError
)

__all__ = [
    # Privacy boundary
    "DataClassification",
    "StorageLocation",
    "PrivacyBoundary",
    "PRIVACY_BOUNDARIES",
    "apply_privacy_boundary",
    "PrivacyBlockedError",

    # Anonymization
    "AnonymizationEngine",
    "LLMPrivacyReviewer",
    "PIIEntity",

    # Encryption
    "FieldEncryption",
    "EncryptedPropertyManager",

    # Tokenization
    "TokenizationService",
    "HybridPrivacyProcessor",

    # Access control
    "Neo4jSecurityManager",
    "SenderIsolationEnforcer",
    "AGENT_ROLES",

    # Injection prevention
    "CypherInjectionPrevention",
    "SecureQueryBuilder",
    "CypherInjectionError",
]
