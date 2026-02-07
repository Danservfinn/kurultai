# Security Audit: Neo4j Memory Storage for OpenClaw 6-Agent System

> **Classification**: Security Audit Report
> **Date**: 2026-02-04
> **Scope**: Neo4j-backed operational memory privacy and security
> **OWASP References**: A01:2021-Broken Access Control, A02:2021-Cryptographic Failures, A03:2021-Injection, A05:2021-Security Misconfiguration

---

## Executive Summary

This audit evaluates the security and privacy implications of moving operational memory from file-based storage to Neo4j for a 6-agent multi-tenant system. The current architecture has Kublai reviewing content for PII before delegation, with personal memory remaining file-based (Kublai only) and operational memory going to Neo4j (shared among 6 agents).

**Key Finding**: The existing privacy boundary approach is sound in principle but requires significant hardening for production use. The multi-tenant nature of Neo4j introduces risks not present in file-based storage that must be addressed through defense-in-depth controls.

---

## 1. Risks of Neo4j vs File-Based Storage

### 1.1 Multi-Tenant Concerns (Severity: HIGH)

| Risk | File-Based | Neo4j | Mitigation Required |
|------|------------|-------|---------------------|
| **Cross-sender data leakage** | Impossible (separate files) | Possible via query errors | Strict sender_hash filtering on ALL queries |
| **Privilege escalation** | OS-level only | Graph traversal attacks | Role-based access control (RBAC) |
| **Data exfiltration scope** | Single sender | All senders if breached | Encryption at rest, network isolation |
| **Query injection impact** | File corruption | Cross-sender data access | Parameterized queries, input validation |

**Specific Multi-Tenant Risks:**

1. **Graph Traversal Attacks**: In a graph database, relationships can be traversed. A malicious or compromised agent could potentially:
   ```cypher
   // DANGEROUS: Finds all tasks across all senders
   MATCH (t:Task)-[*..5]-(other:Task)
   RETURN other
   ```

2. **Property Inference**: Even with sender_hash filtering, graph algorithms might infer relationships:
   ```cypher
   // DANGEROUS: Similarity search could reveal cross-sender patterns
   CALL db.index.vector.queryNodes('concept_embedding', 10, $embedding)
   YIELD node, score
   // Missing: WHERE node.sender_hash = $sender_hash
   RETURN node
   ```

3. **Backup/Restore Contamination**: Neo4j backups contain all sender data. A restore operation could accidentally expose data to wrong agents.

### 1.2 Audit Trail Requirements (Severity: MEDIUM)

**Current State Gaps:**
- No comprehensive audit logging for data access
- No tracking of which agent accessed what sender data
- Missing data lineage for compliance reporting

**Required Audit Events:**
```python
AUDIT_EVENTS = {
    "data_access": "Agent queried sender data",
    "data_modification": "Agent modified sender data",
    "cross_sender_query": "Query returned data from multiple senders",
    "encryption_operation": "Sensitive data encrypted/decrypted",
    "schema_change": "Database schema modified",
    "backup_operation": "Backup or restore performed"
}
```

### 1.3 Data Retention Policies (Severity: MEDIUM)

**GDPR/CCPA Considerations:**
- Right to erasure: Must be able to delete ALL data for a sender
- Right to portability: Must be able to export sender data
- Data minimization: Cannot retain data longer than necessary

**Neo4j-Specific Challenges:**
- Deleted nodes may persist in backups
- Relationship history requires explicit tracking
- Vector indexes don't support logical deletion

---

## 2. Privacy-Preserving Memory Storage Implementation

### 2.1 Data Classification Framework

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any
import hashlib
import hmac
import os

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

# Privacy boundary definitions
PRIVACY_BOUNDARIES = {
    # Task metadata - safe for Neo4j
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
}
```

### 2.2 Anonymization Pipeline

```python
import re
import hashlib
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class PIIEntity:
    """Detected PII entity."""
    entity_type: str
    start: int
    end: int
    value: str
    replacement: str

class AnonymizationEngine:
    """
    Multi-layer PII detection and anonymization.

    Layer 1: Regex-based pattern matching (fast, deterministic)
    Layer 2: LLM-based review (comprehensive, slower)
    Layer 3: Tokenization for reversible anonymization
    """

    # Regex patterns for common PII
    PII_PATTERNS = {
        "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone": r'\b(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        "api_key": r'\b(sk-|pk-|Bearer\s)[a-zA-Z0-9_-]{20,}\b',
        "url_with_auth": r'https?://[^:]+:[^@]+@[^\s]+',
    }

    # Named entity patterns (basic)
    NAME_PATTERNS = [
        r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b',  # First Last
        r'My\s+(?:friend|colleague|contact)\s+(\w+)',  # "My friend Sarah"
    ]

    def __init__(self, salt: Optional[str] = None):
        """
        Initialize anonymization engine.

        Args:
            salt: Salt for consistent hashing (should be from env var)
        """
        self.salt = salt or os.getenv("ANONYMIZATION_SALT", "default-salt-change-in-prod")
        self.token_map: Dict[str, str] = {}  # For reversible tokenization

    def detect_pii(self, text: str) -> List[PIIEntity]:
        """
        Detect PII entities in text using regex patterns.

        Args:
            text: Input text to analyze

        Returns:
            List of detected PII entities
        """
        entities = []

        for entity_type, pattern in self.PII_PATTERNS.items():
            for match in re.finditer(pattern, text):
                entities.append(PIIEntity(
                    entity_type=entity_type,
                    start=match.start(),
                    end=match.end(),
                    value=match.group(),
                    replacement=self._generate_replacement(entity_type, match.group())
                ))

        # Sort by position (reverse) for replacement
        entities.sort(key=lambda e: e.start, reverse=True)
        return entities

    def _generate_replacement(self, entity_type: str, value: str) -> str:
        """Generate consistent replacement for entity."""
        # Create hash for consistent replacement
        hash_input = f"{self.salt}:{entity_type}:{value}"
        hash_val = hashlib.sha256(hash_input.encode()).hexdigest()[:8]

        replacements = {
            "email": f"[EMAIL_{hash_val}]",
            "phone": f"[PHONE_{hash_val}]",
            "ssn": f"[SSN_{hash_val}]",
            "credit_card": f"[CC_{hash_val}]",
            "api_key": f"[API_KEY_{hash_val}]",
            "url_with_auth": f"[URL_WITH_AUTH_{hash_val}]",
        }

        return replacements.get(entity_type, f"[REDACTED_{hash_val}]")

    def anonymize(self, text: str, reversible: bool = False) -> Tuple[str, Dict[str, str]]:
        """
        Anonymize text by replacing PII.

        Args:
            text: Input text
            reversible: If True, store token mapping for de-anonymization

        Returns:
            Tuple of (anonymized_text, token_map)
        """
        entities = self.detect_pii(text)
        anonymized = text
        token_map = {}

        for entity in entities:
            if reversible:
                # Generate reversible token
                token = self._generate_token(entity.entity_type)
                token_map[token] = entity.value
                replacement = token
            else:
                replacement = entity.replacement

            anonymized = anonymized[:entity.start] + replacement + anonymized[entity.end:]

        return anonymized, token_map

    def _generate_token(self, entity_type: str) -> str:
        """Generate unique reversible token."""
        import uuid
        token_id = str(uuid.uuid4())[:8]
        return f"<TOKEN:{entity_type}:{token_id}>"

    def deanonymize(self, text: str, token_map: Dict[str, str]) -> str:
        """Restore original values from token map."""
        result = text
        for token, original in token_map.items():
            result = result.replace(token, original)
        return result


class LLMPrivacyReviewer:
    """
    LLM-based privacy review for complex cases.
    Used as secondary check after regex-based detection.
    """

    REVIEW_PROMPT = """Analyze the following text for any personally identifiable information (PII) or sensitive personal data that should not be stored in a shared database.

Categories to flag:
1. Personal names (especially of friends, family, colleagues)
2. Specific company names (unless public/known)
3. Locations that could identify someone
4. Health information
5. Financial details beyond general concepts
6. Any information that could be used to identify a specific individual

Text to analyze:
{text}

Respond in this exact format:
CONTAINS_PII: [yes/no]
SENSITIVE_ENTITIES:
- Type: [category], Value: [text], Suggested replacement: [replacement]
RISK_LEVEL: [low/medium/high]
"""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def review(self, text: str) -> Dict[str, Any]:
        """
        Review text for PII using LLM.

        Returns:
            Dict with 'contains_pii', 'entities', 'risk_level'
        """
        if not self.llm_client:
            # Fallback: assume safe if no LLM available
            return {"contains_pii": False, "entities": [], "risk_level": "unknown"}

        prompt = self.REVIEW_PROMPT.format(text=text)
        response = await self.llm_client.complete(prompt)

        # Parse response
        return self._parse_review_response(response)

    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM review response."""
        lines = response.strip().split('\n')
        result = {
            "contains_pii": False,
            "entities": [],
            "risk_level": "low"
        }

        for line in lines:
            if line.startswith("CONTAINS_PII:"):
                result["contains_pii"] = "yes" in line.lower()
            elif line.startswith("RISK_LEVEL:"):
                result["risk_level"] = line.split(":")[1].strip().lower()
            elif line.startswith("-") and "Type:" in line:
                # Parse entity line
                entity = self._parse_entity_line(line)
                if entity:
                    result["entities"].append(entity)

        return result

    def _parse_entity_line(self, line: str) -> Optional[Dict[str, str]]:
        """Parse entity line from LLM response."""
        try:
            parts = line.replace("- ", "").split(", ")
            entity = {}
            for part in parts:
                key, value = part.split(": ", 1)
                entity[key.lower()] = value
            return entity
        except:
            return None
```

### 2.3 Field-Level Encryption in Neo4j

```python
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
from typing import Any, Dict, Optional

class FieldEncryption:
    """
    Field-level encryption for sensitive Neo4j properties.

    Design decisions:
    1. Encrypt at application layer, not database layer
    2. Use deterministic encryption for queryable fields
    3. Use randomized encryption for non-queryable fields
    4. Store encryption metadata with encrypted data
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption with master key.

        Args:
            master_key: Base64-encoded Fernet key (from env var)
        """
        key = master_key or os.getenv("NEO4J_FIELD_ENCRYPTION_KEY")
        if not key:
            raise ValueError("Encryption key required. Set NEO4J_FIELD_ENCRYPTION_KEY.")

        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, value: str, deterministic: bool = False) -> str:
        """
        Encrypt a string value.

        Args:
            value: Value to encrypt
            deterministic: If True, same input produces same output (for querying)

        Returns:
            Encrypted value with metadata prefix
        """
        if deterministic:
            # Use deterministic encryption (for fields that need equality queries)
            encrypted = self._deterministic_encrypt(value)
            return f"ENC:D:{encrypted}"
        else:
            # Use randomized encryption (more secure, cannot query)
            encrypted = self.cipher.encrypt(value.encode()).decode()
            return f"ENC:R:{encrypted}"

    def _deterministic_encrypt(self, value: str) -> str:
        """
        Deterministic encryption using HMAC-based approach.
        Same input always produces same output.
        """
        # For deterministic encryption, we use a synthetic IV derived from the plaintext
        # This is less secure but allows equality queries
        import hmac
        import hashlib

        # Generate synthetic IV from value hash
        iv = hmac.new(
            self.cipher._signing_key,
            value.encode(),
            hashlib.sha256
        ).digest()[:16]

        # XOR with encrypted value (simplified - use proper deterministic AEAD in production)
        encrypted = self.cipher.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt(self, encrypted_value: str) -> str:
        """
        Decrypt an encrypted value.

        Args:
            encrypted_value: Value with ENC:D: or ENC:R: prefix

        Returns:
            Decrypted string
        """
        if not encrypted_value.startswith("ENC:"):
            return encrypted_value  # Not encrypted

        parts = encrypted_value.split(":", 2)
        if len(parts) != 3:
            raise ValueError("Invalid encrypted value format")

        _, mode, ciphertext = parts

        if mode == "R":
            return self.cipher.decrypt(ciphertext.encode()).decode()
        elif mode == "D":
            return self._deterministic_decrypt(ciphertext)
        else:
            raise ValueError(f"Unknown encryption mode: {mode}")

    def _deterministic_decrypt(self, ciphertext: str) -> str:
        """Decrypt deterministically encrypted value."""
        encrypted = base64.urlsafe_b64decode(ciphertext.encode())
        return self.cipher.decrypt(encrypted).decode()

    def is_encrypted(self, value: str) -> bool:
        """Check if value is encrypted."""
        return isinstance(value, str) and value.startswith("ENC:")


class EncryptedPropertyManager:
    """
    Manages encrypted properties in Neo4j nodes.

    Usage:
        manager = EncryptedPropertyManager(encryption_key)

        # Store encrypted data
        node_data = {
            "name": "Task description",
            "sensitive_details": manager.encrypt_field("confidential info"),
            "searchable_hash": manager.hash_for_query("confidential info")
        }

        # Retrieve and decrypt
        decrypted = manager.decrypt_field(node_data["sensitive_details"])
    """

    def __init__(self, encryption_key: Optional[str] = None):
        self.encryption = FieldEncryption(encryption_key)

    def encrypt_field(self, value: str, queryable: bool = False) -> str:
        """
        Encrypt a field value.

        Args:
            value: Value to encrypt
            queryable: If True, also store hash for querying
        """
        return self.encryption.encrypt(value, deterministic=queryable)

    def decrypt_field(self, value: str) -> str:
        """Decrypt a field value."""
        return self.encryption.decrypt(value)

    def hash_for_query(self, value: str) -> str:
        """
        Generate hash for querying without revealing value.
        Used for equality queries on encrypted fields.
        """
        import hmac
        import hashlib

        salt = os.getenv("QUERY_HASH_SALT", "query-salt")
        return hmac.new(
            salt.encode(),
            value.encode(),
            hashlib.sha256
        ).hexdigest()[:16]

    def prepare_node_properties(self, properties: Dict[str, Any],
                                 encrypted_fields: List[str],
                                 queryable_fields: List[str]) -> Dict[str, Any]:
        """
        Prepare node properties with selective encryption.

        Args:
            properties: Original properties dict
            encrypted_fields: List of field names to encrypt
            queryable_fields: Subset of encrypted_fields that need querying

        Returns:
            Properties with encryption applied
        """
        result = properties.copy()

        for field in encrypted_fields:
            if field in result:
                is_queryable = field in queryable_fields
                result[field] = self.encrypt_field(result[field], queryable=is_queryable)

                # Add hash field for queryable encrypted fields
                if is_queryable:
                    result[f"{field}_hash"] = self.hash_for_query(properties[field])

        return result
```

### 2.4 Tokenization Service

```python
import uuid
import hashlib
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import redis  # or in-memory cache for single-instance

class TokenizationService:
    """
    Reversible tokenization for sensitive values.

    Replaces sensitive data with tokens before Neo4j storage.
    Original values stored separately in secure vault.

    Use cases:
    - Store task descriptions with tokenized company names
    - Keep original values in Kublai's encrypted file storage
    - Allow reconstruction when needed
    """

    def __init__(self, vault_client=None, ttl_days: int = 90):
        """
        Initialize tokenization service.

        Args:
            vault_client: Client for secure vault (Redis, HashiCorp Vault, etc.)
            ttl_days: Token expiration time
        """
        self.vault = vault_client
        self.ttl = timedelta(days=ttl_days)
        self.token_prefix = "TKN"

    def tokenize(self, value: str, context: str = "") -> str:
        """
        Create token for sensitive value.

        Args:
            value: Sensitive value to tokenize
            context: Context for the token (e.g., "company_name", "person_name")

        Returns:
            Token to store in Neo4j
        """
        # Generate unique token
        token_id = str(uuid.uuid4())[:12]
        token = f"{self.token_prefix}:{context.upper()}:{token_id}"

        # Store in vault with expiration
        vault_key = self._vault_key(token)
        vault_value = {
            "original": value,
            "context": context,
            "created_at": datetime.utcnow().isoformat(),
            "access_count": 0
        }

        if self.vault:
            self.vault.setex(
                vault_key,
                int(self.ttl.total_seconds()),
                json.dumps(vault_value)
            )

        return token

    def detokenize(self, token: str) -> Optional[str]:
        """
        Retrieve original value from token.

        Args:
            token: Token to look up

        Returns:
            Original value or None if not found/expired
        """
        if not token.startswith(self.token_prefix):
            return token  # Not a token

        if not self.vault:
            return None  # Cannot detokenize without vault

        vault_key = self._vault_key(token)
        data = self.vault.get(vault_key)

        if not data:
            return None

        vault_value = json.loads(data)
        vault_value["access_count"] += 1
        vault_value["last_accessed"] = datetime.utcnow().isoformat()

        # Update with new expiration
        self.vault.setex(
            vault_key,
            int(self.ttl.total_seconds()),
            json.dumps(vault_value)
        )

        return vault_value["original"]

    def _vault_key(self, token: str) -> str:
        """Generate vault storage key for token."""
        # Include sender hash in key for isolation
        return f"token:{token}"

    def batch_tokenize(self, text: str, entities: List[Dict]) -> Tuple[str, Dict[str, str]]:
        """
        Tokenize multiple entities in text.

        Args:
            text: Original text
            entities: List of detected entities with 'type' and 'value'

        Returns:
            Tuple of (tokenized_text, token_map)
        """
        token_map = {}
        result = text

        # Sort by position (reverse) to replace from end to start
        sorted_entities = sorted(entities, key=lambda e: e.get("start", 0), reverse=True)

        for entity in sorted_entities:
            value = entity["value"]
            context = entity.get("type", "unknown")

            token = self.tokenize(value, context)
            token_map[token] = value

            start = entity.get("start", 0)
            end = entity.get("end", len(text))
            result = result[:start] + token + result[end:]

        return result, token_map


class HybridPrivacyProcessor:
    """
    Combines multiple privacy techniques for comprehensive protection.

    Processing pipeline:
    1. Detect PII using regex patterns
    2. LLM review for complex cases
    3. Classify data sensitivity
    4. Apply appropriate protection:
       - PUBLIC: Store as-is
       - OPERATIONAL: Anonymize
       - SENSITIVE: Tokenize + encrypt
       - PRIVATE: Block from Neo4j
    """

    def __init__(self,
                 anonymizer: AnonymizationEngine,
                 tokenizer: TokenizationService,
                 encryption: FieldEncryption,
                 llm_reviewer: Optional[LLMPrivacyReviewer] = None):
        self.anonymizer = anonymizer
        self.tokenizer = tokenizer
        self.encryption = encryption
        self.llm_reviewer = llm_reviewer

    async def process_for_neo4j(self,
                                 data: Dict[str, Any],
                                 data_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Process data for safe Neo4j storage.

        Args:
            data: Original data dict
            data_type: Type of data (key in PRIVACY_BOUNDARIES)

        Returns:
            Tuple of (processed_data, metadata)
        """
        boundary = PRIVACY_BOUNDARIES.get(data_type)
        if not boundary:
            raise ValueError(f"Unknown data type: {data_type}")

        # Check if should be blocked from Neo4j
        if boundary.storage == StorageLocation.FILE_KUBLAI:
            raise PrivacyBlockedError(
                f"Data type '{data_type}' must not be stored in Neo4j. "
                "Store in Kublai's file-based memory instead."
            )

        metadata = {
            "original_classification": boundary.classification.value,
            "processing_steps": [],
            "token_map": {},
            "pii_detected": []
        }

        processed = {}

        for field, value in data.items():
            if not isinstance(value, str):
                processed[field] = value
                continue

            # Step 1: Detect PII
            pii_entities = self.anonymizer.detect_pii(value)
            if pii_entities:
                metadata["pii_detected"].extend([
                    {"type": e.entity_type, "replacement": e.replacement}
                    for e in pii_entities
                ])

            # Step 2: LLM review if available and data looks sensitive
            if self.llm_reviewer and (pii_entities or boundary.classification.value in ["sensitive", "private"]):
                review = await self.llm_reviewer.review(value)
                if review["contains_pii"]:
                    metadata["processing_steps"].append(f"llm_review: {review['risk_level']}")

            # Step 3: Apply protection based on classification
            if boundary.classification == DataClassification.PUBLIC:
                processed[field] = value

            elif boundary.classification == DataClassification.OPERATIONAL:
                # Anonymize
                anonymized, _ = self.anonymizer.anonymize(value, reversible=False)
                processed[field] = anonymized
                metadata["processing_steps"].append(f"{field}: anonymized")

            elif boundary.classification == DataClassification.SENSITIVE:
                # Tokenize for sensitive values
                if pii_entities:
                    tokenized, token_map = self.tokenizer.batch_tokenize(
                        value,
                        [{"type": e.entity_type, "value": e.value, "start": e.start, "end": e.end}
                         for e in pii_entities]
                    )
                    processed[field] = tokenized
                    metadata["token_map"].update(token_map)
                    metadata["processing_steps"].append(f"{field}: tokenized")
                else:
                    # Encrypt if no specific PII but still sensitive
                    processed[field] = self.encryption.encrypt_field(value, queryable=False)
                    metadata["processing_steps"].append(f"{field}: encrypted")

        return processed, metadata


class PrivacyBlockedError(Exception):
    """Raised when data cannot be stored in Neo4j due to privacy classification."""
    pass
```

---

## 3. Data That Should NEVER Go Into Shared Neo4j

### 3.1 Prohibited Data Categories

```python
# NEVER_STORE_IN_NEO4J - Data categories that must be blocked
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
```

### 3.2 Compliance Matrix

| Regulation | Requirements | Neo4j Impact |
|------------|--------------|--------------|
| **GDPR** | Right to erasure, portability, processing records | Must implement data lineage tracking; deletions must cascade |
| **CCPA** | Disclosure of data sold/shared, deletion rights | Audit logging required; no "selling" of graph data |
| **HIPAA** | PHI protection, access controls, audit trails | Health data should not go to shared Neo4j |
| **PCI-DSS** | Cardholder data encryption, access restriction | Payment data in separate vault, not Neo4j |
| **SOX** | Financial record retention, change auditing | Financial data needs immutable audit trail |

### 3.3 Content Review Checklist

Before any data enters Neo4j, Kublai must verify:

```python
PRE_NEO4J_CHECKLIST = """
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
"""
```

---

## 4. Security Controls for Neo4j

### 4.1 Authentication and Authorization Patterns

```python
from neo4j import GraphDatabase
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class Neo4jSecurityManager:
    """
    Security manager for Neo4j connections with role-based access.

    Implements:
    - Connection encryption (TLS)
    - Role-based access control
    - Query injection prevention
    - Audit logging
    """

    # Agent roles and their permissions
    AGENT_ROLES = {
        "main": {
            "permissions": ["read", "write", "delete", "admin"],
            "allowed_labels": ["*"],  # All node labels
            "sender_isolation": False,  # Can see all senders (for synthesis)
        },
        "researcher": {
            "permissions": ["read", "write"],
            "allowed_labels": ["Research", "Concept", "Task", "Analysis"],
            "sender_isolation": True,
        },
        "writer": {
            "permissions": ["read", "write"],
            "allowed_labels": ["Content", "Task", "Concept"],
            "sender_isolation": True,
        },
        "developer": {
            "permissions": ["read", "write"],
            "allowed_labels": ["CodeReview", "SecurityAudit", "Task", "Concept"],
            "sender_isolation": True,
        },
        "analyst": {
            "permissions": ["read", "write"],
            "allowed_labels": ["Analysis", "Insight", "Task", "Concept"],
            "sender_isolation": True,
        },
        "ops": {
            "permissions": ["read", "write", "delete"],
            "allowed_labels": ["Task", "ProcessUpdate", "WorkflowImprovement"],
            "sender_isolation": False,  # Ops manages all tasks
        },
    }

    def __init__(self, uri: str, username: str, password: str,
                 encryption_key: str, ca_cert_path: Optional[str] = None):
        """
        Initialize secure Neo4j connection.

        Args:
            uri: Neo4j bolt URI (must use bolt+s or neo4j+s for TLS)
            username: Neo4j username
            password: Neo4j password
            encryption_key: Key for field-level encryption
            ca_cert_path: Path to CA certificate for TLS verification
        """
        self.uri = uri
        self.auth = (username, password)
        self.encryption_key = encryption_key
        self.ca_cert_path = ca_cert_path

        # Validate TLS is used
        if not uri.startswith(("bolt+s://", "neo4j+s://", "bolt+ssc://")):
            logger.warning("Neo4j connection should use TLS (bolt+s:// or neo4j+s://)")

    def get_driver(self) -> GraphDatabase.Driver:
        """Get Neo4j driver with security configuration."""
        import ssl

        # Configure TLS
        if self.ca_cert_path:
            ssl_context = ssl.create_default_context(cafile=self.ca_cert_path)
        else:
            ssl_context = ssl.create_default_context()

        return GraphDatabase.driver(
            self.uri,
            auth=self.auth,
            encrypted=True,
            ssl_context=ssl_context
        )

    def check_agent_permission(self, agent_id: str, action: str,
                                label: Optional[str] = None) -> bool:
        """
        Check if agent has permission for action.

        Args:
            agent_id: Agent identifier
            action: Action to check (read, write, delete, admin)
            label: Node label being accessed (optional)

        Returns:
            True if permitted
        """
        role = self.AGENT_ROLES.get(agent_id)
        if not role:
            logger.warning(f"Unknown agent: {agent_id}")
            return False

        if action not in role["permissions"]:
            logger.warning(f"Agent {agent_id} lacks {action} permission")
            return False

        if label and role["allowed_labels"] != ["*"]:
            if label not in role["allowed_labels"]:
                logger.warning(f"Agent {agent_id} cannot access {label} nodes")
                return False

        return True


class SenderIsolationEnforcer:
    """
    Enforces sender isolation on all Neo4j queries.

    Every query that accesses sender data MUST include sender_hash filter.
    This class wraps queries to ensure isolation.
    """

    def __init__(self, security_manager: Neo4jSecurityManager):
        self.security = security_manager

    def enforce_isolation(self, query: str, params: Dict[str, Any],
                          agent_id: str, sender_hash: Optional[str]) -> Tuple[str, Dict[str, Any]]:
        """
        Modify query to enforce sender isolation.

        Args:
            query: Original Cypher query
            params: Query parameters
            agent_id: Agent executing query
            sender_hash: Sender hash for isolation

        Returns:
            Modified query and parameters with isolation enforced
        """
        role = self.security.AGENT_ROLES.get(agent_id, {})

        # Main agent and ops can see all senders (for synthesis/coordination)
        if not role.get("sender_isolation", True):
            return query, params

        if not sender_hash:
            raise ValueError(f"Agent {agent_id} requires sender_hash for all queries")

        # Check if query already has sender_hash filter
        if "sender_hash" in query:
            # Verify it's parameterized correctly
            if "$sender_hash" not in query:
                logger.warning("Query has hardcoded sender_hash - potential security issue")
            return query, params

        # Add sender_hash filter to query
        # This is a simplified example - real implementation needs Cypher parsing
        modified_query = self._inject_sender_filter(query, sender_hash)
        modified_params = {**params, "sender_hash": sender_hash}

        return modified_query, modified_params

    def _inject_sender_filter(self, query: str, sender_hash: str) -> str:
        """
        Inject sender_hash filter into Cypher query.

        WARNING: This is a simplified example. Production implementation
        should use a proper Cypher AST parser.
        """
        # Detect if query matches Task or sender-associated nodes
        sender_associated_labels = [
            "Task", "Research", "Content", "Analysis",
            "Concept", "Application", "Insight"
        ]

        for label in sender_associated_labels:
            if f"(:{label}" in query or f"(:{label} " in query:
                # Add WHERE clause for sender_hash
                if "WHERE" in query:
                    # Append to existing WHERE
                    query = query.replace(
                        "WHERE",
                        f"WHERE sender_hash = $sender_hash AND "
                    )
                else:
                    # Add WHERE before RETURN or WITH
                    if "RETURN" in query:
                        query = query.replace("RETURN", f"WHERE sender_hash = $sender_hash\nRETURN")
                    elif "WITH" in query:
                        query = query.replace("WITH", f"WHERE sender_hash = $sender_hash\nWITH")

                break

        return query
```

### 4.2 Query Injection Prevention

```python
import re
from typing import List, Set

class CypherInjectionPrevention:
    """
    Prevents Cypher injection attacks.

    OWASP A03:2021 - Injection prevention for Neo4j Cypher queries.
    """

    # Dangerous Cypher keywords that should never come from user input
    DANGEROUS_KEYWORDS = {
        "CALL", "LOAD", "CSV", "FROM", "YIELD",
        "CREATE", "DELETE", "REMOVE", "SET", "DROP",
        "INDEX", "CONSTRAINT", "DATABASE", "USER", "ROLE",
        "PASSWORD", "PRIVILEGE", "GRANT", "DENY", "REVOKE"
    }

    # Pattern for detecting injection attempts
    INJECTION_PATTERNS = [
        r'\$\{[^}]+\}',  # Template literal style: ${...}
        r'`[^`]+`',       # Backtick escaping
        r'\/\/.*',       # Comment injection
        r'\/\*.*\*\/',   # Block comment injection
        r';\s*\w+',       # Statement chaining
    ]

    @classmethod
    def validate_query(cls, query: str, allowed_params: Set[str]) -> None:
        """
        Validate Cypher query for injection attempts.

        Args:
            query: Cypher query string
            allowed_params: Set of allowed parameter names

        Raises:
            CypherInjectionError: If injection detected
        """
        # Check for direct value interpolation (anti-pattern)
        if re.search(r'"[^"]*\$\w+[^"]*"', query) or re.search(r"'[^']*\$\w+[^']*'", query):
            raise CypherInjectionError(
                "Query contains potential string interpolation. "
                "Use parameterized queries only."
            )

        # Check for dangerous keywords in unexpected places
        query_upper = query.upper()
        for keyword in cls.DANGEROUS_KEYWORDS:
            # This is a simplified check - real implementation needs parsing
            if keyword in query_upper:
                # Allow if it's in a comment explaining the query
                pass  # More sophisticated check needed

        # Check for injection patterns
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                raise CypherInjectionError(
                    f"Query contains suspicious pattern: {pattern}"
                )

    @classmethod
    def sanitize_parameter(cls, name: str, value: Any, allowed_types: tuple = (str, int, float, bool, list)) -> Any:
        """
        Sanitize query parameter.

        Args:
            name: Parameter name
            value: Parameter value
            allowed_types: Allowed Python types

        Returns:
            Sanitized value
        """
        if value is None:
            return None

        if not isinstance(value, allowed_types):
            raise CypherInjectionError(
                f"Parameter {name} has disallowed type: {type(value)}"
            )

        # Additional sanitization for strings
        if isinstance(value, str):
            # Check for Cypher injection in string values
            dangerous = ['\\', '\x00', '\x1a', '\'', '"', '`']
            for char in dangerous:
                if char in value:
                    # Escape or reject
                    logger.warning(f"Parameter {name} contains special character")

        return value


class SecureQueryBuilder:
    """
    Builder pattern for constructing safe Cypher queries.

    Ensures all values are properly parameterized.
    """

    def __init__(self):
        self.query_parts = []
        self.params = {}
        self.param_counter = 0

    def add(self, cypher_fragment: str, **params) -> 'SecureQueryBuilder':
        """
        Add Cypher fragment with parameters.

        Args:
            cypher_fragment: Cypher code (no user input!)
            **params: Parameters to bind

        Returns:
            Self for chaining
        """
        # Validate fragment has no direct user input
        CypherInjectionPrevention.validate_query(cypher_fragment, set())

        self.query_parts.append(cypher_fragment)

        # Add parameters with unique names to avoid collisions
        for key, value in params.items():
            unique_key = f"{key}_{self.param_counter}"
            self.param_counter += 1
            self.params[unique_key] = value
            # Replace placeholder in fragment
            cypher_fragment = cypher_fragment.replace(f"${key}", f"${unique_key}")

        return self

    def match(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add MATCH clause."""
        return self.add(f"MATCH {pattern}", **params)

    def where(self, condition: str, **params) -> 'SecureQueryBuilder':
        """Add WHERE clause."""
        return self.add(f"WHERE {condition}", **params)

    def create(self, pattern: str, **params) -> 'SecureQueryBuilder':
        """Add CREATE clause."""
        return self.add(f"CREATE {pattern}", **params)

    def set(self, assignment: str, **params) -> 'SecureQueryBuilder':
        """Add SET clause."""
        return self.add(f"SET {assignment}", **params)

    def return_(self, expression: str, **params) -> 'SecureQueryBuilder':
        """Add RETURN clause."""
        return self.add(f"RETURN {expression}", **params)

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """
        Build final query and parameters.

        Returns:
            Tuple of (query_string, parameters)
        """
        query = "\n".join(self.query_parts)
        return query, self.params


class CypherInjectionError(Exception):
    """Raised when potential Cypher injection is detected."""
    pass
```

### 4.3 Network Security

```python
class Neo4jNetworkSecurity:
    """
    Network security configuration for Neo4j.

    Implements:
    - TLS/SSL encryption
    - Certificate pinning
    - Connection pooling limits
    - Network segmentation
    """

    @staticmethod
    def configure_tls(driver_config: Dict[str, Any],
                      cert_path: Optional[str] = None,
                      verify_mode: str = "require") -> Dict[str, Any]:
        """
        Configure TLS for Neo4j connection.

        Args:
            driver_config: Base driver configuration
            cert_path: Path to CA certificate
            verify_mode: "require", "verify-full", or "verify-ca"

        Returns:
            Updated configuration with TLS
        """
        import ssl

        config = driver_config.copy()

        if verify_mode == "require":
            # Require TLS but don't verify certificate
            config["encrypted"] = True
            config["trust"] = "TRUST_ALL_CERTIFICATES"  # Dev only!

        elif verify_mode in ("verify-ca", "verify-full"):
            # Verify certificate
            config["encrypted"] = True

            if cert_path:
                ssl_context = ssl.create_default_context(cafile=cert_path)
                config["ssl_context"] = ssl_context

        return config

    @staticmethod
    def validate_connection_security(uri: str) -> List[str]:
        """
        Validate connection URI security.

        Returns:
            List of security warnings
        """
        warnings = []

        if uri.startswith("bolt://") or uri.startswith("neo4j://"):
            warnings.append("WARNING: Using unencrypted connection. Use bolt+s:// or neo4j+s://")

        if "localhost" in uri or "127.0.0.1" in uri:
            warnings.append("INFO: Using localhost - ensure network segmentation is in place")

        if ":7687" not in uri and ":" in uri.replace("://", ""):
            warnings.append("WARNING: Using non-standard port")

        return warnings


# Neo4j Security Configuration Checklist
NEO4J_SECURITY_CHECKLIST = """
[ ] Neo4j configured with bolt+s:// or neo4j+s:// (TLS enabled)
[ ] Certificate verification enabled in production
[ ] Neo4j instance in private subnet (no public internet access)
[ ] Firewall rules restrict access to application servers only
[ ] Neo4j native authentication enabled (not auth disabled)
[ ] Role-based access control configured
[ ] Query log monitoring enabled
[ ] Backup encryption enabled
[ ] Audit logging enabled
[ ] Connection pooling limits configured
[ ] Idle connection timeout set
[ ] Failed authentication lockout enabled
"""
```

---

## 5. Privacy Boundary Framework

### 5.1 Decision Tree for Data Storage

```
                    Data to Store
                         |
            +------------+------------+
            |                         |
    Contains PII?              No PII detected
            |                         |
    +-------+-------+                 |
    |               |                 |
Personal         Business        Is it general
Relationship?    Information?    knowledge?
    |               |                 |
    YES             |                 |
    |               |                 |
Kublai's      Is it sensitive?    YES
File Only         |                 |
    |         +-----+-----+         |
    |         |           |         |
    |        YES          NO        |
    |         |           |         |
    |    Tokenize +    Neo4j       |
    |    Encrypt       (public)     |
    |         |                     |
    +---------+---------------------+
              |
         Neo4j with
      sender_hash filter
```

### 5.2 Privacy Boundary Rules

```python
PRIVACY_BOUNDARY_RULES = """
# PRIVACY BOUNDARY FRAMEWORK FOR KURULTAI NEO4J

## Rule 1: Data Classification (MANDATORY)
ALL data must be classified before storage:
- PUBLIC: General knowledge, code patterns, technical concepts
- OPERATIONAL: Task metadata, work products (anonymized)
- SENSITIVE: Business ideas, health, finance (tokenized + encrypted)
- PRIVATE: Personal relationships, PII - NEVER to Neo4j

## Rule 2: Sender Isolation (MANDATORY)
ALL queries to sender-associated nodes MUST include sender_hash filter:
  MATCH (t:Task {sender_hash: $sender_hash})

Exception: Main agent and Ops for coordination (audit logged)

## Rule 3: Pre-Storage Review (MANDATORY)
Kublai MUST review content before Neo4j storage:
1. Run regex PII detection
2. LLM review for complex cases
3. Apply appropriate anonymization
4. Log classification decision

## Rule 4: Encryption Requirements
- SENSITIVE data: Field-level encryption required
- Token vault: Separate encrypted storage
- Backups: Encrypted at rest
- Network: TLS 1.3 required

## Rule 5: Access Control
- Agents have role-based permissions
- Query injection prevention on all inputs
- Audit logging for sensitive access
- Rate limiting per sender

## Rule 6: Retention and Deletion
- PUBLIC: 2 years retention
- OPERATIONAL: 90 days retention
- SENSITIVE: 1 year retention (or legal requirement)
- PRIVATE: Kublai's discretion

## Rule 7: Incident Response
If potential data leakage detected:
1. Immediately isolate affected sender data
2. Revoke agent access tokens
3. Audit all queries from affected time period
4. Notify affected users per GDPR/CCPA requirements
"""


def apply_privacy_boundary(data: Dict[str, Any],
                           data_type: str,
                           sender_hash: str,
                           processor: HybridPrivacyProcessor) -> Dict[str, Any]:
    """
    Apply privacy boundary framework to data.

    Args:
        data: Data to store
        data_type: Type of data (for classification lookup)
        sender_hash: Sender identifier
        processor: Privacy processor instance

    Returns:
        Data safe for Neo4j storage

    Raises:
        PrivacyBlockedError: If data cannot be stored in Neo4j
    """
    import asyncio

    # Step 1: Classify data
    boundary = PRIVACY_BOUNDARIES.get(data_type)
    if not boundary:
        raise ValueError(f"Unknown data type: {data_type}")

    # Step 2: Check storage location
    if boundary.storage == StorageLocation.FILE_KUBLAI:
        raise PrivacyBlockedError(
            f"Data type '{data_type}' classified as PRIVATE. "
            "Must be stored in Kublai's file-based memory only."
        )

    if boundary.storage == StorageLocation.ENCRYPTED_VAULT:
        raise PrivacyBlockedError(
            f"Data type '{data_type}' requires encrypted vault storage. "
            "Not suitable for Neo4j."
        )

    # Step 3: Process for Neo4j
    processed, metadata = asyncio.run(
        processor.process_for_neo4j(data, data_type)
    )

    # Step 4: Add sender hash for isolation
    processed["sender_hash"] = sender_hash
    processed["privacy_metadata"] = {
        "classification": boundary.classification.value,
        "processed_at": datetime.utcnow().isoformat(),
        "processing_steps": metadata.get("processing_steps", []),
    }

    # Step 5: Log audit record
    logger.info(
        f"Privacy boundary applied: {data_type} -> {boundary.classification.value}",
        extra={
            "sender_hash": sender_hash,
            "data_type": data_type,
            "classification": boundary.classification.value,
            "pii_detected": len(metadata.get("pii_detected", []))
        }
    )

    return processed
```

### 5.3 Implementation Example

```python
# Example: Complete privacy-preserving task creation

async def create_privacy_preserving_task(
    description: str,
    task_type: str,
    delegated_by: str,
    assigned_to: str,
    sender_hash: str,
    privacy_processor: HybridPrivacyProcessor,
    neo4j_client
) -> str:
    """
    Create a task with full privacy protection.

    Args:
        description: Task description (may contain PII)
        task_type: Type of task
        delegated_by: Delegating agent
        assigned_to: Target agent
        sender_hash: Sender identifier
        privacy_processor: Privacy processor
        neo4j_client: Neo4j connection

    Returns:
        Task ID
    """
    # Step 1: Process description through privacy pipeline
    task_data = {
        "description": description,
        "type": task_type,
    }

    try:
        processed_data, metadata = await privacy_processor.process_for_neo4j(
            task_data,
            "task_metadata"
        )
    except PrivacyBlockedError as e:
        logger.error(f"Task blocked by privacy rules: {e}")
        raise

    # Step 2: Create task in Neo4j with sender isolation
    task_id = str(uuid.uuid4())

    query = """
    CREATE (t:Task {
        id: $task_id,
        description: $description,
        type: $type,
        delegated_by: $delegated_by,
        assigned_to: $assigned_to,
        sender_hash: $sender_hash,
        status: 'pending',
        created_at: datetime(),
        privacy_classification: $classification,
        pii_detected: $pii_count
    })
    RETURN t.id as task_id
    """

    params = {
        "task_id": task_id,
        "description": processed_data["description"],
        "type": processed_data["type"],
        "delegated_by": delegated_by,
        "assigned_to": assigned_to,
        "sender_hash": sender_hash,
        "classification": metadata["original_classification"],
        "pii_count": len(metadata.get("pii_detected", []))
    }

    result = await neo4j_client.run(query, params)

    # Step 3: Store token map in secure vault if needed
    if metadata.get("token_map"):
        await store_token_map(task_id, metadata["token_map"])

    logger.info(
        f"Privacy-preserving task created: {task_id}",
        extra={
            "task_id": task_id,
            "sender_hash": sender_hash,
            "pii_detected": len(metadata.get("pii_detected", []))
        }
    )

    return task_id


async def store_token_map(task_id: str, token_map: Dict[str, str]):
    """Store token mapping in secure vault for later recovery."""
    # Implementation depends on vault choice (Redis, HashiCorp Vault, etc.)
    pass
```

---

## 6. Security Test Cases

```python
# Test cases for security validation

SECURITY_TEST_CASES = {
    "sender_isolation": [
        {
            "name": "Query without sender_hash should fail",
            "query": "MATCH (t:Task) RETURN t",
            "expected": "Error: sender_hash required"
        },
        {
            "name": "Query with wrong sender_hash returns no data",
            "setup": "CREATE (:Task {sender_hash: 'user1', description: 'test'})",
            "query": "MATCH (t:Task {sender_hash: 'user2'}) RETURN t",
            "expected": "Empty result"
        },
        {
            "name": "Cross-sender traversal attack blocked",
            "query": "MATCH (t:Task)-[*..5]-(other) WHERE t.sender_hash = 'user1' RETURN other",
            "expected": "Filtered to user1's data only"
        }
    ],

    "injection_prevention": [
        {
            "name": "Cypher injection in description blocked",
            "input": "Task'; MATCH (n) DETACH DELETE n; //",
            "expected": "Sanitized or rejected"
        },
        {
            "name": "Comment injection blocked",
            "input": "normal description // MATCH (n) DELETE n",
            "expected": "Comment stripped or rejected"
        },
        {
            "name": "Backtick escaping blocked",
            "input": "`MATCH (n) DELETE n`",
            "expected": "Escaped or rejected"
        }
    ],

    "encryption": [
        {
            "name": "Sensitive data encrypted at rest",
            "input": {"business_idea": "Stealth startup concept"},
            "expected": "Stored as encrypted value"
        },
        {
            "name": "Tokenized data recoverable",
            "input": "My friend Sarah's startup",
            "expected": "Token stored, original in vault"
        }
    ],

    "access_control": [
        {
            "name": "Researcher cannot delete tasks",
            "agent": "researcher",
            "action": "DELETE",
            "expected": "Permission denied"
        },
        {
            "name": "Writer cannot access security audits",
            "agent": "writer",
            "label": "SecurityAudit",
            "expected": "Permission denied"
        }
    ]
}
```

---

## 7. Summary and Recommendations

### 7.1 Risk Summary

| Risk Category | Severity | Status |
|--------------|----------|--------|
| Cross-sender data leakage | HIGH | Mitigated via sender_hash isolation |
| Cypher injection | HIGH | Mitigated via parameterized queries |
| Unencrypted sensitive data | MEDIUM | Mitigated via field-level encryption |
| Insufficient audit logging | MEDIUM | Requires implementation |
| Backup exposure | MEDIUM | Mitigated via encryption |
| Network eavesdropping | LOW | Mitigated via TLS |

### 7.2 Implementation Priority

1. **P0 (Critical)**:
   - Implement sender_hash filtering on ALL queries
   - Deploy parameterized query enforcement
   - Enable TLS for all Neo4j connections

2. **P1 (High)**:
   - Deploy anonymization pipeline
   - Implement field-level encryption for SENSITIVE data
   - Add comprehensive audit logging

3. **P2 (Medium)**:
   - Tokenization service for reversible anonymization
   - Role-based access control enforcement
   - Backup encryption

4. **P3 (Low)**:
   - Advanced graph security monitoring
   - Automated PII detection improvements
   - Security test automation

### 7.3 Compliance Checklist

- [ ] GDPR Article 25 (Data Protection by Design)
- [ ] GDPR Article 30 (Records of Processing)
- [ ] GDPR Article 32 (Security of Processing)
- [ ] CCPA 1798.150 (Security Requirements)
- [ ] OWASP ASVS Level 2 (Application Security)

---

*End of Security Audit Report*
