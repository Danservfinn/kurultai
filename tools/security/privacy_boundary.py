"""
Privacy Boundary Framework for Neo4j Operational Memory.

Defines data classification, storage locations, and enforcement rules
to ensure sensitive data never enters shared Neo4j storage inappropriately.

OWASP References:
- A01:2021-Broken Access Control
- A02:2021-Cryptographic Failures
- A05:2021-Security Misconfiguration
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)


class DataClassification(Enum):
    """
    Privacy classification for operational memory data.
    Determines storage location and protection level.
    """
    PUBLIC = "public"           # General knowledge, code patterns
    OPERATIONAL = "operational" # Task metadata, non-sensitive work products
    SENSITIVE = "sensitive"     # Business ideas, health, finance (anonymized)
    PRIVATE = "private"         # PII, personal relationships - NEVER to Neo4j


class StorageLocation(Enum):
    """Where data is stored based on classification."""
    NEO4J_SHARED = "neo4j"      # Shared operational memory
    FILE_KUBLAI = "kublai_file" # Kublai's personal memory only
    ENCRYPTED_VAULT = "vault"   # Encrypted storage with strict access


@dataclass
class PrivacyBoundary:
    """Defines privacy rules for a data type."""
    classification: DataClassification
    storage: StorageLocation
    encryption_required: bool
    anonymization_required: bool
    retention_days: int
    audit_level: str  # "none", "standard", "full"


# ============================================================================
# PRIVACY BOUNDARY DEFINITIONS
# ============================================================================

PRIVACY_BOUNDARIES: Dict[str, PrivacyBoundary] = {
    # Task metadata - safe for Neo4j with sanitization
    "task_metadata": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,  # Sanitize description
        retention_days=90,
        audit_level="standard"
    ),

    # Research findings - anonymize before storage
    "research_findings": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,
        retention_days=365,
        audit_level="standard"
    ),

    # Code patterns - generally safe
    "code_patterns": PrivacyBoundary(
        classification=DataClassification.PUBLIC,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=False,
        retention_days=730,
        audit_level="none"
    ),

    # Business ideas - sensitive
    "business_ideas": PrivacyBoundary(
        classification=DataClassification.SENSITIVE,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=True,
        anonymization_required=True,
        retention_days=365,
        audit_level="full"
    ),

    # Personal relationships - NEVER to Neo4j
    "personal_relationships": PrivacyBoundary(
        classification=DataClassification.PRIVATE,
        storage=StorageLocation.FILE_KUBLAI,
        encryption_required=True,
        anonymization_required=False,
        retention_days=365,
        audit_level="full"
    ),

    # Financial information - sensitive
    "financial_data": PrivacyBoundary(
        classification=DataClassification.SENSITIVE,
        storage=StorageLocation.ENCRYPTED_VAULT,
        encryption_required=True,
        anonymization_required=True,
        retention_days=2555,  # 7 years for compliance
        audit_level="full"
    ),

    # Analysis results - operational
    "analysis_results": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,
        retention_days=180,
        audit_level="standard"
    ),

    # Content drafts - operational
    "content_drafts": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,
        retention_days=90,
        audit_level="standard"
    ),

    # Security audit results - sensitive
    "security_audits": PrivacyBoundary(
        classification=DataClassification.SENSITIVE,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=True,
        anonymization_required=True,
        retention_days=730,
        audit_level="full"
    ),

    # Process updates - operational
    "process_updates": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=False,
        retention_days=365,
        audit_level="standard"
    ),

    # Workflow improvements - operational
    "workflow_improvements": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=False,
        retention_days=730,
        audit_level="standard"
    ),

    # Agent reflections - operational
    "agent_reflections": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,
        retention_days=365,
        audit_level="standard"
    ),

    # Synthesis insights - operational
    "synthesis_insights": PrivacyBoundary(
        classification=DataClassification.OPERATIONAL,
        storage=StorageLocation.NEO4J_SHARED,
        encryption_required=False,
        anonymization_required=True,
        retention_days=365,
        audit_level="standard"
    ),
}


# ============================================================================
# PROHIBITED DATA CATEGORIES
# ============================================================================

# Data categories that must NEVER be stored in shared Neo4j
NEVER_STORE_IN_NEO4J = {
    # Personal Identifiers
    "raw_phone_numbers": "Store HMAC hash only",
    "email_addresses": "Tokenize or hash",
    "physical_addresses": "Never store",
    "government_ids": "SSN, passport, driver's license - NEVER",
    "biometric_data": "Fingerprints, facial recognition data",

    # Personal Relationships
    "family_names": "Names of family members",
    "friend_names": "Names of friends",
    "colleague_names": "Names of specific colleagues",
    "relationship_details": "Personal relationship information",

    # Authentication Secrets
    "passwords": "Never store in any form",
    "api_keys": "Store in dedicated vault only",
    "private_keys": "Hardware security module only",
    "session_tokens": "Ephemeral, never persist",

    # Financial Data
    "bank_account_numbers": "Tokenize in separate vault",
    "credit_card_numbers": "Use PCI-compliant vault",
    "crypto_private_keys": "Hardware wallet only",
    "transaction_details": "Anonymize before storage",

    # Health Information
    "medical_conditions": "HIPAA-protected",
    "medications": "HIPAA-protected",
    "mental_health_details": "HIPAA-protected",
    "disability_status": "Protected class information",

    # Location Data
    "precise_geolocation": "GPS coordinates",
    "home_address": "Never store",
    "work_address": "Never store",
    "frequent_locations": "Pattern of life data",

    # Communication Content
    "private_messages": "Content of private conversations",
    "email_content": "Full email bodies",
    "call_records": "Metadata only, not content",

    # Behavioral Data
    "browsing_history": "Never store",
    "search_queries": "Anonymize or don't store",
    "app_usage_patterns": "Aggregated only",
}


# ============================================================================
# PRE-STORAGE CHECKLIST
# ============================================================================

PRE_NEO4J_CHECKLIST = """
PRE-NEO4J STORAGE CHECKLIST (MANDATORY)

Before any data enters Neo4j, verify:

[ ] No raw phone numbers (use HMAC-SHA256 hash)
[ ] No email addresses (tokenize or use hash)
[ ] No personal names of friends/family/colleagues
[ ] No specific addresses (home, work, frequent locations)
[ ] No API keys, passwords, or authentication tokens
[ ] No credit card or bank account numbers
[ ] No SSN, passport, or government ID numbers
[ ] No health conditions or medical details
[ ] No precise geolocation data
[ ] Business ideas anonymized (no specific company names)
[ ] Financial amounts generalized ("thousands" not "$5,247.33")
[ ] Descriptions reviewed for embedded PII
[ ] sender_hash field populated for sender isolation
[ ] Data classification determined and logged
"""


# ============================================================================
# EXCEPTIONS AND ERRORS
# ============================================================================

class PrivacyBlockedError(Exception):
    """
    Raised when data cannot be stored in Neo4j due to privacy classification.

    This exception indicates that the data should be stored in Kublai's
    file-based memory instead, or not stored at all.
    """
    pass


class ClassificationError(Exception):
    """Raised when data classification cannot be determined."""
    pass


# ============================================================================
# PRIVACY BOUNDARY ENFORCEMENT
# ============================================================================

async def apply_privacy_boundary(
    data: Dict[str, Any],
    data_type: str,
    sender_hash: str,
    privacy_processor=None  # HybridPrivacyProcessor instance
) -> Dict[str, Any]:
    """
    Apply privacy boundary framework to data before Neo4j storage.

    Args:
        data: Data to store
        data_type: Type of data (key in PRIVACY_BOUNDARIES)
        sender_hash: Sender identifier (HMAC-SHA256 hash)
        privacy_processor: Privacy processor instance for anonymization

    Returns:
        Data safe for Neo4j storage with privacy metadata

    Raises:
        PrivacyBlockedError: If data cannot be stored in Neo4j
        ClassificationError: If data type is unknown
    """
    # Step 1: Validate data type
    boundary = PRIVACY_BOUNDARIES.get(data_type)
    if not boundary:
        raise ClassificationError(
            f"Unknown data type: {data_type}. "
            f"Must be one of: {list(PRIVACY_BOUNDARIES.keys())}"
        )

    # Step 2: Check storage location
    if boundary.storage == StorageLocation.FILE_KUBLAI:
        raise PrivacyBlockedError(
            f"Data type '{data_type}' classified as PRIVATE. "
            f"Must be stored in Kublai's file-based memory only. "
            f"Content: {str(data)[:100]}..."
        )

    if boundary.storage == StorageLocation.ENCRYPTED_VAULT:
        raise PrivacyBlockedError(
            f"Data type '{data_type}' requires encrypted vault storage. "
            f"Not suitable for Neo4j. Use dedicated vault service."
        )

    # Step 3: Process data through privacy pipeline if processor available
    processed = data.copy()
    metadata = {
        "original_classification": boundary.classification.value,
        "processing_steps": [],
        "pii_detected": [],
        "processed_at": datetime.utcnow().isoformat(),
    }

    if privacy_processor:
        try:
            import asyncio
            processed, proc_metadata = await privacy_processor.process_for_neo4j(
                data, data_type
            )
            metadata["processing_steps"] = proc_metadata.get("processing_steps", [])
            metadata["pii_detected"] = proc_metadata.get("pii_detected", [])
            metadata["token_map"] = proc_metadata.get("token_map", {})
        except Exception as e:
            logger.error(f"Privacy processing failed: {e}")
            # Fall back to basic sanitization
            processed = _basic_sanitize(data)
            metadata["processing_steps"].append("basic_sanitization_fallback")

    # Step 4: Add sender hash for isolation
    processed["sender_hash"] = sender_hash
    processed["privacy_metadata"] = {
        "classification": boundary.classification.value,
        "storage": boundary.storage.value,
        "processed_at": metadata["processed_at"],
        "retention_days": boundary.retention_days,
    }

    # Step 5: Log audit record
    audit_log = {
        "event": "privacy_boundary_applied",
        "data_type": data_type,
        "classification": boundary.classification.value,
        "sender_hash": sender_hash,
        "pii_detected_count": len(metadata.get("pii_detected", [])),
        "timestamp": metadata["processed_at"],
    }

    if boundary.audit_level in ("standard", "full"):
        logger.info("Privacy boundary applied", extra=audit_log)

    if boundary.audit_level == "full":
        # Full audit includes more detail for sensitive data
        audit_log["processing_steps"] = metadata["processing_steps"]
        logger.info("Full privacy audit", extra=audit_log)

    return processed


def _basic_sanitize(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Basic sanitization when full privacy processor unavailable.

    Applies simple regex-based PII removal.
    """
    import re

    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Remove common PII patterns
            sanitized = value

            # Email addresses
            sanitized = re.sub(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
                '[EMAIL_REDACTED]',
                sanitized
            )

            # Phone numbers
            sanitized = re.sub(
                r'\b(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
                '[PHONE_REDACTED]',
                sanitized
            )

            # SSN
            sanitized = re.sub(
                r'\b\d{3}-\d{2}-\d{4}\b',
                '[SSN_REDACTED]',
                sanitized
            )

            # API keys
            sanitized = re.sub(
                r'\b(sk-|pk-|Bearer\s)[a-zA-Z0-9_-]{20,}\b',
                '[API_KEY_REDACTED]',
                sanitized
            )

            result[key] = sanitized
        else:
            result[key] = value

    return result


def check_prohibited_content(data: Dict[str, Any]) -> list:
    """
    Check data for prohibited content categories.

    Returns:
        List of prohibited categories found
    """
    found = []
    data_str = str(data).lower()

    for category, description in NEVER_STORE_IN_NEO4J.items():
        # Simple keyword check - production should use more sophisticated detection
        keywords = category.replace("_", " ").split()
        if any(kw in data_str for kw in keywords):
            found.append({
                "category": category,
                "description": description
            })

    return found


def get_retention_policy(data_type: str) -> Optional[int]:
    """
    Get retention period in days for a data type.

    Args:
        data_type: Type of data

    Returns:
        Retention period in days, or None if unknown
    """
    boundary = PRIVACY_BOUNDARIES.get(data_type)
    if boundary:
        return boundary.retention_days
    return None


def requires_encryption(data_type: str) -> bool:
    """Check if data type requires encryption."""
    boundary = PRIVACY_BOUNDARIES.get(data_type)
    if boundary:
        return boundary.encryption_required
    return False


def requires_anonymization(data_type: str) -> bool:
    """Check if data type requires anonymization."""
    boundary = PRIVACY_BOUNDARIES.get(data_type)
    if boundary:
        return boundary.anonymization_required
    return False
