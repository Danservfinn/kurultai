# Secure Architecture: Sensitive Data Storage in Isolated Neo4j Database

**Classification:** Security Architecture Document
**Date:** 2026-02-04
**Scope:** Multi-agent system (Kurultai/OpenClaw) with 6 specialized agents
**Threat Level:** High (PII, Financial Data, API Keys)
**OWASP References:** A01:2021-Broken Access Control, A02:2021-Cryptographic Failures, A05:2021-Security Misconfiguration

---

## Executive Summary

This document outlines a defense-in-depth architecture for storing sensitive data (passwords, PII, financial data, API keys) in a separate, isolated Neo4j database instance with strict access controls. This architecture complements the existing operational memory system by creating a dedicated "Secure Vault" tier for data requiring the highest protection levels.

### Key Security Principles

1. **Complete Physical Separation**: Sensitive data resides in a separate Neo4j instance
2. **Zero-Trust Architecture**: Every access is authenticated, authorized, and audited
3. **Defense in Depth**: Multiple security layers (network, application, database)
4. **Principle of Least Privilege**: Minimal access rights for each agent
5. **Fail Securely**: Deny access by default on any security control failure

---

## 1. Architecture Overview

### 1.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KURULTAI MULTI-AGENT SYSTEM                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     KUBLAI (Orchestrator Agent)                      │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │    │
│  │  │  Intent Router  │  │  Access Gateway │  │  Audit Logger       │  │    │
│  │  │  (Task Queue)   │  │  (Auth Proxy)   │  │  (Compliance)       │  │    │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│          ┌───────────────────┼───────────────────┐                          │
│          │                   │                   │                          │
│          ▼                   ▼                   ▼                          │
│  ┌───────────────┐   ┌───────────────┐   ┌───────────────────────┐          │
│  │  OPERATIONAL  │   │   PERSONAL    │   │      SECURE VAULT     │          │
│  │    NEO4J      │   │    FILES      │   │    (Neo4j Secure)     │          │
│  │  (Shared)     │   │  (Kublai Only)│   │   (Isolated Instance) │          │
│  ├───────────────┤   ├───────────────┤   ├───────────────────────┤          │
│  │ • Tasks       │   │ • Preferences │   │ • API Keys            │          │
│  │ • Research    │   │ • History     │   │ • Passwords           │          │
│  │ • Code        │   │ • Private     │   │ • PII (encrypted)     │          │
│  │   Patterns    │   │   Context     │   │ • Financial Data      │          │
│  │ • Analysis    │   │               │   │ • Session Tokens      │          │
│  │               │   │ ACCESS:       │   │                       │          │
│  │ ACCESS:       │   │ Kublai only   │   │ ACCESS:               │          │
│  │ All 6 agents  │   │ (file-based)  │   │ Kublai + proxy only   │          │
│  │               │   │               │   │                       │          │
│  │ ENCRYPTION:   │   │ ENCRYPTION:   │   │ ENCRYPTION:           │          │
│  │ Field-level   │   │ N/A           │   │ AES-256-GCM + TLS     │          │
│  │ (sensitive)   │   │               │   │ (at rest + in transit)│          │
│  └───────────────┘   └───────────────┘   └───────────────────────┘          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    OTHER AGENTS (5 Specialized)                      │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │    │
│  │  │ Möngke  │ │ Chagatai│ │ Temüjin │ │  Jochi  │ │ Ögedei  │       │    │
│  │  │Research │ │ Writer  │ │Developer│ │ Analyst │ │   Ops   │       │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘       │    │
│  │                                                                      │    │
│  │  ACCESS: Operational Neo4j only (NO Secure Vault access)            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Classification Matrix

| Classification | Examples | Storage | Encryption | Access Control |
|----------------|----------|---------|------------|----------------|
| **PUBLIC** | Code patterns, general knowledge | Operational Neo4j | None | All agents |
| **OPERATIONAL** | Task metadata, research findings | Operational Neo4j | Field-level (optional) | All agents + sender isolation |
| **SENSITIVE** | Business ideas, health topics | Operational Neo4j | Field-level (required) | All agents + sender isolation |
| **PRIVATE** | Personal relationships, preferences | Kublai's files | N/A (local) | Kublai only |
| **RESTRICTED** | API keys, passwords, PII, financial | **Secure Vault Neo4j** | **AES-256-GCM + envelope encryption** | **Kublai + proxy only** |

---

## 2. Secure Vault Architecture

### 2.1 Physical Isolation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NETWORK SEGMENTATION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────┐         ┌─────────────────────┐                   │
│   │   PUBLIC/APP TIER   │         │    SECURE TIER      │                   │
│   │   (10.0.1.0/24)     │         │   (10.0.100.0/24)   │                   │
│   │                     │         │                     │                   │
│   │  ┌───────────────┐  │         │  ┌───────────────┐  │                   │
│   │  │   Kublai      │  │         │  │  Secure Vault │  │                   │
│   │  │   Gateway     │◄─┼────────►│  │    Neo4j      │  │                   │
│   │  │   (Proxy)     │  │  mTLS   │  │   :7687       │  │                   │
│   │  └───────────────┘  │         │  └───────────────┘  │                   │
│   │         ▲           │         │          ▲          │                   │
│   │         │           │         │          │          │                   │
│   │  ┌──────┴──────┐    │         │  ┌───────┴──────┐   │                   │
│   │  │  Other      │    │         │  │  HSM/KMS     │   │                   │
│   │  │  Agents     │    │         │  │  (Key Mgmt)  │   │                   │
│   │  └─────────────┘    │         │  └──────────────┘   │                   │
│   │                     │         │                     │                   │
│   └─────────────────────┘         └─────────────────────┘                   │
│                                                                              │
│   FIREWALL RULES:                                                            │
│   - Secure Tier accepts connections ONLY from Kublai Gateway IP              │
│   - No inbound from Public/App Tier except port 7687 from Gateway            │
│   - Outbound blocked except to KMS/HSM                                       │
│   - Inter-tier communication requires mutual TLS (mTLS)                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Secure Vault Database Schema

```cypher
// ============================================================================
// SECURE VAULT NEO4J SCHEMA
// ============================================================================

// Master encryption key reference (stored in HSM, reference only)
CREATE CONSTRAINT encryption_key_id IF NOT EXISTS
FOR (k:EncryptionKey) REQUIRE k.key_id IS UNIQUE;

// Data classification labels
CREATE CONSTRAINT secret_id IF NOT EXISTS
FOR (s:Secret) REQUIRE s.secret_id IS UNIQUE;

// Access audit log
CREATE CONSTRAINT audit_event_id IF NOT EXISTS
FOR (a:AuditEvent) REQUIRE a.event_id IS UNIQUE;

// ============================================================================
// NODE TYPES
// ============================================================================

(:Secret {
  secret_id: string,           // UUID v4
  secret_type: string,         // 'api_key', 'password', 'pii', 'financial', 'token'
  owner_hash: string,          // HMAC-SHA256 of owner identifier
  encrypted_value: string,     // AES-256-GCM encrypted (format: ENC:<ciphertext>:<nonce>:<tag>)
  encryption_key_id: string,   // Reference to key in HSM
  metadata: string,            // JSON (encrypted if contains sensitive info)
  access_tier: string,         // 'critical', 'high', 'medium', 'low'
  created_at: datetime,
  expires_at: datetime,        // TTL for session tokens
  last_rotated: datetime,
  rotation_count: int,
  access_count: int,
  version: int                 // For optimistic locking
})

(:EncryptionKey {
  key_id: string,              // Reference to HSM key
  key_type: string,            // 'data_encryption', 'key_encryption'
  algorithm: string,           // 'AES-256-GCM'
  created_at: datetime,
  expires_at: datetime,        // Key rotation schedule
  status: string               // 'active', 'rotating', 'deprecated', 'revoked'
})

(:AccessPolicy {
  policy_id: string,
  name: string,
  allowed_types: [string],     // ['api_key', 'password']
  max_access_count: int,       // Rate limiting
  ttl_seconds: int,            // Auto-expiry
  requires_justification: boolean
})

(:AuditEvent {
  event_id: string,
  event_type: string,          // 'access', 'create', 'update', 'delete', 'rotation'
  actor_hash: string,          // HMAC of accessing entity
  secret_id: string,
  action: string,
  success: boolean,
  justification: string,       // Required for sensitive access
  timestamp: datetime,
  source_ip: string,           // Hashed
  session_id: string
})

(:AgentCredential {
  credential_id: string,
  agent_id: string,
  public_key: string,          // For mTLS authentication
  fingerprint: string,         // Certificate fingerprint
  issued_at: datetime,
  expires_at: datetime,
  last_used: datetime,
  status: string               // 'active', 'suspended', 'revoked'
})

// ============================================================================
// RELATIONSHIPS
// ============================================================================

(:Secret)-[:ENCRYPTED_WITH]->(:EncryptionKey)
(:Secret)-[:GOVERNED_BY]->(:AccessPolicy)
(:AuditEvent)-[:TARGETS]->(:Secret)
(:AgentCredential)-[:ACCESSED]->(:Secret)
```

---

## 3. Security Patterns

### 3.1 Database-Level Encryption (At Rest)

```python
"""
Database-Level Encryption for Secure Vault Neo4j.

Implements:
- Transparent Data Encryption (TDE) at database level
- Application-layer field encryption for defense in depth
- Envelope encryption pattern for key management
"""

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import hashlib
import hmac
import os
import base64
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class EncryptionContext:
    """Context for encryption operations."""
    key_id: str
    algorithm: str
    created_at: datetime
    expires_at: Optional[datetime]


class SecureVaultEncryption:
    """
    Multi-layer encryption for Secure Vault.

    Layer 1: Neo4j Enterprise TDE (transparent data encryption)
    Layer 2: Application field-level AES-256-GCM
    Layer 3: Envelope encryption with HSM-backed keys
    """

    def __init__(
        self,
        hsm_client: Optional[Any] = None,
        master_key_env: str = "SECURE_VAULT_MASTER_KEY"
    ):
        """
        Initialize encryption with HSM or environment-based key.

        Args:
            hsm_client: HSM client (AWS KMS, HashiCorp Vault, etc.)
            master_key_env: Environment variable for master key (fallback)
        """
        self.hsm = hsm_client
        self._data_key_cache: Dict[str, bytes] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._key_last_fetched: Dict[str, datetime] = {}

        if hsm_client:
            self.key_source = "hsm"
        else:
            # Fallback to environment (development only!)
            master_key = os.getenv(master_key_env)
            if not master_key:
                raise ValueError(
                    f"No HSM client and {master_key_env} not set. "
                    "Secure Vault requires key management."
                )
            self._master_key = base64.urlsafe_b64decode(master_key)
            self.key_source = "environment"
            logger.warning(
                "Using environment-based keys - NOT FOR PRODUCTION"
            )

    def _get_data_encryption_key(self, key_id: str) -> bytes:
        """
        Retrieve or generate data encryption key.

        Uses envelope encryption:
        1. Master key encrypts data encryption keys (DEKs)
        2. DEKs encrypt actual data
        3. DEKs are cached briefly for performance
        """
        now = datetime.utcnow()

        # Check cache
        if key_id in self._data_key_cache:
            last_fetch = self._key_last_fetched.get(key_id, now)
            if now - last_fetch < self._cache_ttl:
                return self._data_key_cache[key_id]

        # Fetch or generate DEK
        if self.hsm:
            dek = self._get_key_from_hsm(key_id)
        else:
            # Derive key from master (development only)
            dek = self._derive_key(key_id)

        # Cache with TTL
        self._data_key_cache[key_id] = dek
        self._key_last_fetched[key_id] = now

        return dek

    def _get_key_from_hsm(self, key_id: str) -> bytes:
        """Retrieve key from HSM/KMS."""
        # Implementation depends on HSM (AWS KMS, Azure Key Vault, etc.)
        # Example for AWS KMS:
        # response = self.hsm.generate_data_key(
        #     KeyId=key_id,
        #     KeySpec='AES_256'
        # )
        # return response['Plaintext']
        raise NotImplementedError("HSM integration required")

    def _derive_key(self, key_id: str) -> bytes:
        """Derive key from master using HKDF-like approach."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=key_id.encode(),
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self._master_key)

    def encrypt(
        self,
        plaintext: str,
        key_id: str = "default",
        associated_data: Optional[bytes] = None
    ) -> str:
        """
        Encrypt value using AES-256-GCM.

        Format: ENC:<base64(ciphertext)>:<base64(nonce)>:<base64(tag)>:<key_id>

        Args:
            plaintext: Value to encrypt
            key_id: Encryption key identifier
            associated_data: Additional authenticated data (AAD)

        Returns:
            Encrypted value with metadata
        """
        try:
            # Get data encryption key
            dek = self._get_data_encryption_key(key_id)

            # Generate nonce
            nonce = os.urandom(12)  # 96 bits for GCM

            # Create cipher
            aesgcm = AESGCM(dek)

            # Encrypt
            plaintext_bytes = plaintext.encode('utf-8')
            aad = associated_data or b''

            ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, aad)

            # Split ciphertext and tag (last 16 bytes)
            tag = ciphertext[-16:]
            ciphertext_only = ciphertext[:-16]

            # Encode components
            return (
                f"ENC:{base64.b64encode(ciphertext_only).decode()}:"
                f"{base64.b64encode(nonce).decode()}:"
                f"{base64.b64encode(tag).decode()}:"
                f"{key_id}"
            )

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt value: {e}")

    def decrypt(
        self,
        encrypted_value: str,
        associated_data: Optional[bytes] = None
    ) -> str:
        """
        Decrypt value encrypted with AES-256-GCM.

        Args:
            encrypted_value: Format from encrypt()
            associated_data: Must match encryption AAD

        Returns:
            Decrypted plaintext
        """
        try:
            # Parse format
            if not encrypted_value.startswith("ENC:"):
                raise ValueError("Invalid encrypted value format")

            parts = encrypted_value.split(":")
            if len(parts) != 5:
                raise ValueError("Invalid encrypted value format")

            _, ciphertext_b64, nonce_b64, tag_b64, key_id = parts

            # Decode components
            ciphertext = base64.b64decode(ciphertext_b64)
            nonce = base64.b64decode(nonce_b64)
            tag = base64.b64decode(tag_b64)

            # Get key
            dek = self._get_data_encryption_key(key_id)

            # Reconstruct ciphertext with tag
            full_ciphertext = ciphertext + tag

            # Decrypt
            aesgcm = AESGCM(dek)
            aad = associated_data or b''

            plaintext = aesgcm.decrypt(nonce, full_ciphertext, aad)

            return plaintext.decode('utf-8')

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt value: {e}")

    def rotate_key(
        self,
        encrypted_value: str,
        new_key_id: str
    ) -> str:
        """
        Re-encrypt value with new key (key rotation).

        Args:
            encrypted_value: Current encrypted value
            new_key_id: New key identifier

        Returns:
            Re-encrypted value
        """
        plaintext = self.decrypt(encrypted_value)
        return self.encrypt(plaintext, new_key_id)


class EncryptionError(Exception):
    """Raised when encryption fails."""
    pass


class DecryptionError(Exception):
    """Raised when decryption fails."""
    pass
```

### 3.2 Field-Level Encryption for Ultra-Sensitive Fields

```python
"""
Field-Level Encryption with Searchable Encryption Support.

Provides:
- Deterministic encryption for queryable fields
- Randomized encryption for maximum security
- Blind indexing for search without decryption
"""

import hashlib
import hmac
import os
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass


@dataclass
class EncryptedField:
    """Represents an encrypted field with metadata."""
    ciphertext: str
    encryption_mode: str  # 'deterministic' or 'randomized'
    blind_index: Optional[str]  # For searchable fields
    field_name: str


class SearchableEncryption:
    """
    Searchable encryption for encrypted fields.

    Allows equality queries on encrypted data without decryption
    using blind indexing (HMAC-based searchable encryption).
    """

    def __init__(self, index_key: Optional[bytes] = None):
        """
        Initialize searchable encryption.

        Args:
            index_key: Key for blind index generation (from HSM)
        """
        if index_key:
            self._index_key = index_key
        else:
            # Generate from environment (development only)
            key_material = os.getenv("BLIND_INDEX_KEY", "default-key")
            self._index_key = hashlib.sha256(key_material.encode()).digest()

    def create_blind_index(self, value: str, field_name: str) -> str:
        """
        Create blind index for searchable encryption.

        The index is deterministic (same value + field = same index)
        but reveals no information about the plaintext.

        Args:
            value: Plaintext value
            field_name: Field name (for field-specific indexing)

        Returns:
            Blind index (HMAC-SHA256 truncated)
        """
        # Include field name to prevent cross-field attacks
        index_input = f"{field_name}:{value.lower().strip()}"

        index = hmac.new(
            self._index_key,
            index_input.encode(),
            hashlib.sha256
        ).hexdigest()[:32]  # 128 bits

        return index

    def verify_blind_index(self, value: str, field_name: str, index: str) -> bool:
        """Verify if value matches the blind index."""
        computed = self.create_blind_index(value, field_name)
        return hmac.compare_digest(computed, index)


class FieldLevelEncryption:
    """
    Field-level encryption with support for searchable fields.

    Usage:
        fle = FieldLevelEncryption(secure_vault_encryption)

        # Encrypt searchable field
        encrypted = fle.encrypt_field(
            "sensitive@email.com",
            "email",
            searchable=True
        )

        # Query using blind index
        index = fle.searchable.create_blind_index("sensitive@email.com", "email")
        # Query: MATCH (s:Secret) WHERE s.email_index = $index
    """

    # Fields that should use deterministic encryption for querying
    SEARCHABLE_FIELDS = {
        'owner_hash',      # Always need to query by owner
        'secret_type',     # Filter by type
        'access_tier',     # Filter by sensitivity
        'status',          # Filter by status
    }

    # Fields requiring maximum security (randomized encryption)
    HIGH_SECURITY_FIELDS = {
        'encrypted_value',  # The actual secret value
        'api_key',
        'password',
        'private_key',
        'session_token',
    }

    def __init__(
        self,
        vault_encryption: SecureVaultEncryption,
        index_key: Optional[bytes] = None
    ):
        self.encryption = vault_encryption
        self.searchable = SearchableEncryption(index_key)

    def encrypt_field(
        self,
        value: str,
        field_name: str,
        searchable: Optional[bool] = None
    ) -> EncryptedField:
        """
        Encrypt a field with appropriate mode.

        Args:
            value: Plaintext value
            field_name: Name of the field
            searchable: Force searchable mode (auto-detected if None)

        Returns:
            EncryptedField with ciphertext and metadata
        """
        if searchable is None:
            searchable = field_name in self.SEARCHABLE_FIELDS

        # Determine encryption mode
        if field_name in self.HIGH_SECURITY_FIELDS:
            mode = "randomized"
            searchable = False  # Never searchable for high-security fields
        elif searchable:
            mode = "deterministic"
        else:
            mode = "randomized"

        # Encrypt
        if mode == "deterministic":
            # Use deterministic encryption (same input = same output)
            ciphertext = self._deterministic_encrypt(value, field_name)
        else:
            # Use randomized encryption (maximum security)
            ciphertext = self.encryption.encrypt(value)

        # Create blind index if searchable
        blind_index = None
        if searchable:
            blind_index = self.searchable.create_blind_index(value, field_name)

        return EncryptedField(
            ciphertext=ciphertext,
            encryption_mode=mode,
            blind_index=blind_index,
            field_name=field_name
        )

    def _deterministic_encrypt(self, value: str, context: str) -> str:
        """
        Deterministic encryption using synthetic IV.

        Same input always produces same output, allowing equality queries.
        Less secure than randomized - use only when necessary.
        """
        # Derive synthetic nonce from value hash
        nonce_input = f"deterministic:{context}:{value}"
        synthetic_nonce = hashlib.sha256(nonce_input.encode()).digest()[:12]

        # Use encryption with synthetic nonce
        dek = self.encryption._get_data_encryption_key("deterministic")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(dek)
        ciphertext = aesgcm.encrypt(
            synthetic_nonce,
            value.encode(),
            associated_data=context.encode()
        )

        # Format: DET:<ciphertext>:<context>
        return f"DET:{base64.b64encode(ciphertext).decode()}:{context}"

    def decrypt_field(self, encrypted_field: EncryptedField) -> str:
        """Decrypt an encrypted field."""
        if encrypted_field.ciphertext.startswith("DET:"):
            return self._deterministic_decrypt(encrypted_field.ciphertext)
        return self.encryption.decrypt(encrypted_field.ciphertext)

    def _deterministic_decrypt(self, ciphertext: str) -> str:
        """Decrypt deterministically encrypted value."""
        parts = ciphertext.split(":")
        if len(parts) != 3:
            raise ValueError("Invalid deterministic ciphertext format")

        _, ct_b64, context = parts
        ct = base64.b64decode(ct_b64)

        # Extract nonce (first 12 bytes) and actual ciphertext
        nonce = ct[:12]
        encrypted = ct[12:]

        dek = self.encryption._get_data_encryption_key("deterministic")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(dek)
        plaintext = aesgcm.decrypt(nonce, encrypted, context.encode())

        return plaintext.decode()

    def prepare_node_properties(
        self,
        properties: Dict[str, Any],
        encrypt_fields: Set[str],
        searchable_fields: Optional[Set[str]] = None
    ) -> Dict[str, Any]:
        """
        Prepare node properties with selective encryption.

        Args:
            properties: Original properties
            encrypt_fields: Fields to encrypt
            searchable_fields: Fields that need blind indexing

        Returns:
            Properties with encryption applied
        """
        result = properties.copy()
        searchable = searchable_fields or set()

        for field in encrypt_fields:
            if field in result and result[field] is not None:
                is_searchable = field in searchable
                encrypted = self.encrypt_field(
                    str(result[field]),
                    field,
                    searchable=is_searchable
                )
                result[field] = encrypted.ciphertext

                # Add blind index for searchable fields
                if encrypted.blind_index:
                    result[f"{field}_index"] = encrypted.blind_index

        return result
```

### 3.3 Access Control Mechanisms (RBAC + ABAC)

```python
"""
Access Control for Secure Vault.

Implements:
- Role-Based Access Control (RBAC) for agent permissions
- Attribute-Based Access Control (ABAC) for fine-grained decisions
- Just-in-Time (JIT) access for sensitive operations
"""

from enum import Enum, auto
from typing import Optional, List, Dict, Any, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """Access levels for secrets."""
    DENY = auto()
    READ_METADATA = auto()  # Can see existence but not value
    READ = auto()
    WRITE = auto()
    DELETE = auto()
    ADMIN = auto()


class SecretType(Enum):
    """Types of secrets in the vault."""
    API_KEY = "api_key"
    PASSWORD = "password"
    PII = "pii"
    FINANCIAL = "financial"
    SESSION_TOKEN = "session_token"
    CERTIFICATE = "certificate"
    ENCRYPTION_KEY = "encryption_key"


@dataclass
class AgentRole:
    """Role definition for an agent."""
    role_id: str
    name: str
    allowed_secret_types: Set[SecretType]
    max_access_count: int  # Per time window
    access_window_minutes: int
    requires_justification: bool
    allowed_operations: Set[str]  # 'create', 'read', 'update', 'delete', 'rotate'
    can_access_cross_sender: bool  # For admin/ops roles


@dataclass
class AccessRequest:
    """Request to access a secret."""
    agent_id: str
    role: AgentRole
    secret_id: Optional[str]
    secret_type: SecretType
    operation: str
    justification: Optional[str]
    timestamp: datetime
    session_id: str
    source_ip: str
    sender_hash: Optional[str]  # For sender isolation


@dataclass
class AccessDecision:
    """Decision for an access request."""
    granted: bool
    level: AccessLevel
    reason: str
    expires_at: Optional[datetime]
    audit_log_id: str
    conditions: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# RBAC DEFINITIONS
# ============================================================================

AGENT_ROLES = {
    "kublai": AgentRole(
        role_id="kublai",
        name="Orchestrator",
        allowed_secret_types={
            SecretType.API_KEY,
            SecretType.PASSWORD,
            SecretType.PII,
            SecretType.FINANCIAL,
            SecretType.SESSION_TOKEN,
        },
        max_access_count=100,
        access_window_minutes=60,
        requires_justification=True,
        allowed_operations={"create", "read", "update", "delete", "rotate"},
        can_access_cross_sender=False  # Still respects sender isolation
    ),

    "ops_emergency": AgentRole(
        role_id="ops_emergency",
        name="Emergency Operations",
        allowed_secret_types={
            SecretType.API_KEY,
            SecretType.SESSION_TOKEN,
        },
        max_access_count=10,
        access_window_minutes=30,
        requires_justification=True,  # Always required for emergency access
        allowed_operations={"read", "rotate"},  # Can read and rotate, not create/delete
        can_access_cross_sender=True  # Emergency access may need cross-sender
    ),

    # Other agents have NO direct vault access
    "researcher": None,
    "writer": None,
    "developer": None,
    "analyst": None,
}


class SecureVaultAccessControl:
    """
    Access control for Secure Vault with RBAC + ABAC.

    Implements defense-in-depth:
    1. Role-based permission checking
    2. Attribute-based contextual decisions
    3. Rate limiting per agent
    4. Justification requirements
    5. Time-based access windows
    """

    def __init__(self, audit_logger: Optional[Any] = None):
        self.audit = audit_logger
        self._access_counts: Dict[str, List[datetime]] = {}
        self._active_sessions: Dict[str, datetime] = {}

    def evaluate_access(self, request: AccessRequest) -> AccessDecision:
        """
        Evaluate access request using RBAC + ABAC.

        Decision flow:
        1. Check role exists and has vault access
        2. Check secret type permission
        3. Check operation permission
        4. Check rate limits
        5. Check justification (if required)
        6. Check sender isolation
        7. Evaluate contextual attributes
        """
        audit_id = self._generate_audit_id()

        # Step 1: Role validation
        if not request.role:
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason="Agent has no vault access role",
                expires_at=None,
                audit_log_id=audit_id
            )

        # Step 2: Secret type permission
        if request.secret_type not in request.role.allowed_secret_types:
            self._log_access(request, False, "Secret type not allowed for role", audit_id)
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason=f"Role {request.role.role_id} cannot access {request.secret_type.value}",
                expires_at=None,
                audit_log_id=audit_id
            )

        # Step 3: Operation permission
        if request.operation not in request.role.allowed_operations:
            self._log_access(request, False, "Operation not allowed", audit_id)
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason=f"Operation {request.operation} not allowed for role",
                expires_at=None,
                audit_log_id=audit_id
            )

        # Step 4: Rate limiting
        if not self._check_rate_limit(request):
            self._log_access(request, False, "Rate limit exceeded", audit_id)
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason="Rate limit exceeded",
                expires_at=None,
                audit_log_id=audit_id
            )

        # Step 5: Justification requirement
        if request.role.requires_justification and not request.justification:
            self._log_access(request, False, "Justification required", audit_id)
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason="Access justification required",
                expires_at=None,
                audit_log_id=audit_id
            )

        # Step 6: Sender isolation (unless explicitly allowed)
        if not request.role.can_access_cross_sender and request.sender_hash:
            # Will be enforced at query time with sender_hash filter
            pass

        # Step 7: Contextual evaluation (ABAC)
        context_check = self._evaluate_context(request)
        if not context_check["allowed"]:
            self._log_access(request, False, context_check["reason"], audit_id)
            return AccessDecision(
                granted=False,
                level=AccessLevel.DENY,
                reason=context_check["reason"],
                expires_at=None,
                audit_log_id=audit_id
            )

        # Access granted
        self._record_access(request)
        self._log_access(request, True, "Access granted", audit_id)

        # Determine access level
        level = self._determine_access_level(request)

        # Set expiration
        expires = datetime.utcnow() + timedelta(
            minutes=request.role.access_window_minutes
        )

        return AccessDecision(
            granted=True,
            level=level,
            reason="Access granted based on RBAC+ABAC evaluation",
            expires_at=expires,
            audit_log_id=audit_id,
            conditions=context_check.get("conditions", {})
        )

    def _check_rate_limit(self, request: AccessRequest) -> bool:
        """Check if agent has exceeded rate limit."""
        key = request.agent_id
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=request.role.access_window_minutes)

        # Get recent accesses
        recent = self._access_counts.get(key, [])
        recent = [t for t in recent if t > window_start]

        return len(recent) < request.role.max_access_count

    def _record_access(self, request: AccessRequest):
        """Record access for rate limiting."""
        key = request.agent_id
        if key not in self._access_counts:
            self._access_counts[key] = []
        self._access_counts[key].append(datetime.utcnow())

    def _evaluate_context(self, request: AccessRequest) -> Dict[str, Any]:
        """
        Evaluate contextual attributes (ABAC).

        Checks:
        - Time-based restrictions (business hours)
        - Session validity
        - IP reputation
        - Anomaly detection
        """
        now = datetime.utcnow()

        # Check session validity
        if request.session_id not in self._active_sessions:
            return {"allowed": False, "reason": "Invalid or expired session"}

        session_age = now - self._active_sessions[request.session_id]
        if session_age > timedelta(hours=8):  # Max session duration
            return {"allowed": False, "reason": "Session expired"}

        # Time-based restrictions for sensitive operations
        if request.secret_type in {SecretType.FINANCIAL, SecretType.PII}:
            hour = now.hour
            if hour < 6 or hour > 22:  # Restrict to 6 AM - 10 PM
                return {"allowed": False, "reason": "Access restricted during off-hours"}

        # All checks passed
        return {
            "allowed": True,
            "conditions": {
                "session_max_age": "8h",
                "business_hours_only": request.secret_type in {
                    SecretType.FINANCIAL, SecretType.PII
                }
            }
        }

    def _determine_access_level(self, request: AccessRequest) -> AccessLevel:
        """Determine the access level to grant."""
        if request.operation == "delete":
            return AccessLevel.DELETE
        elif request.operation == "write" or request.operation == "update":
            return AccessLevel.WRITE
        elif request.operation == "read":
            # For high-security types, only allow metadata read
            if request.secret_type in {SecretType.PASSWORD, SecretType.API_KEY}:
                return AccessLevel.READ
            return AccessLevel.READ
        elif request.operation == "create":
            return AccessLevel.WRITE
        return AccessLevel.READ

    def _generate_audit_id(self) -> str:
        """Generate unique audit log ID."""
        return hashlib.sha256(
            f"{datetime.utcnow().isoformat()}:{os.urandom(16)}".encode()
        ).hexdigest()[:16]

    def _log_access(
        self,
        request: AccessRequest,
        granted: bool,
        reason: str,
        audit_id: str
    ):
        """Log access attempt to audit system."""
        event = {
            "event_id": audit_id,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_id": request.agent_id,
            "role": request.role.role_id if request.role else None,
            "secret_id": request.secret_id,
            "secret_type": request.secret_type.value,
            "operation": request.operation,
            "granted": granted,
            "reason": reason,
            "session_id": request.session_id,
            "source_ip_hash": hashlib.sha256(request.source_ip.encode()).hexdigest()[:16],
        }

        if granted:
            logger.info(f"Vault access granted: {request.agent_id}", extra=event)
        else:
            logger.warning(f"Vault access denied: {request.agent_id}", extra=event)

        if self.audit:
            self.audit.log_event(event)


class JustInTimeAccess:
    """
    Just-in-Time (JIT) access for elevated permissions.

    For sensitive operations, requires explicit approval.
    """

    def __init__(self, approval_timeout_minutes: int = 15):
        self.approval_timeout = timedelta(minutes=approval_timeout_minutes)
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._approved_sessions: Dict[str, datetime] = {}

    def request_elevated_access(
        self,
        agent_id: str,
        reason: str,
        requested_permissions: List[str],
        approver: str = "kublai"  # Kublai approves elevated access
    ) -> str:
        """
        Request elevated access permissions.

        Returns:
            Request ID for tracking
        """
        request_id = hashlib.sha256(
            f"{agent_id}:{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]

        self._pending_requests[request_id] = {
            "agent_id": agent_id,
            "reason": reason,
            "permissions": requested_permissions,
            "requested_at": datetime.utcnow(),
            "status": "pending",
            "approver": approver
        }

        logger.info(
            f"Elevated access requested by {agent_id}",
            extra={"request_id": request_id, "reason": reason}
        )

        return request_id

    def approve_request(self, request_id: str, approver_id: str) -> bool:
        """Approve an elevated access request."""
        if request_id not in self._pending_requests:
            return False

        request = self._pending_requests[request_id]

        if request["approver"] != approver_id:
            logger.warning(
                f"Unauthorized approval attempt by {approver_id}",
                extra={"request_id": request_id}
            )
            return False

        request["status"] = "approved"
        request["approved_at"] = datetime.utcnow()

        # Create approved session
        session_key = f"{request['agent_id']}:{request_id}"
        self._approved_sessions[session_key] = datetime.utcnow()

        logger.info(
            f"Elevated access approved for {request['agent_id']}",
            extra={"request_id": request_id, "approver": approver_id}
        )

        return True

    def check_elevated_access(self, agent_id: str, permission: str) -> bool:
        """Check if agent has active elevated access for permission."""
        for key, approved_at in list(self._approved_sessions.items()):
            # Check expiration
            if datetime.utcnow() - approved_at > self.approval_timeout:
                del self._approved_sessions[key]
                continue

            session_agent, _ = key.split(":", 1)
            if session_agent == agent_id:
                # Check if permission is in approved list
                # (simplified - would need to track per-request permissions)
                return True

        return False
```

---

## 4. Threat Model

### 4.1 Attack Vectors and Mitigations

| Threat Vector | Severity | Likelihood | Mitigation |
|---------------|----------|------------|------------|
| **Database Breach** | Critical | Low | Encryption at rest, HSM-backed keys, network isolation |
| **Man-in-the-Middle** | High | Low | mTLS for all connections, certificate pinning |
| **Insider Threat (Agent)** | High | Medium | RBAC, audit logging, justification requirements, rate limiting |
| **Insider Threat (Admin)** | Critical | Low | Dual-control, JIT access, comprehensive audit trail |
| **Credential Theft** | High | Medium | Short-lived tokens, session binding, IP restrictions |
| **Privilege Escalation** | High | Low | Strict RBAC, no wildcard permissions, regular access reviews |
| **Query Injection** | Medium | Low | Parameterized queries, input validation, query allowlisting |
| **Side-Channel Attacks** | Medium | Low | Constant-time crypto operations, noise injection |
| **Backup Exposure** | High | Low | Encrypted backups, separate backup keys, air-gapped storage |
| **Key Compromise** | Critical | Low | HSM storage, key rotation, envelope encryption |

### 4.2 Unauthorized Agent Access Prevention

```python
"""
Unauthorized Access Prevention System.

Multi-layer defense against unauthorized access attempts.
"""

from typing import Optional, Set
from datetime import datetime, timedelta
import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


class UnauthorizedAccessPrevention:
    """
    Prevents unauthorized access to Secure Vault.

    Layers:
    1. Network-layer IP allowlisting
    2. mTLS certificate validation
    3. Agent authentication
    4. Request signing verification
    5. Behavioral anomaly detection
    """

    def __init__(self):
        self._allowed_ips: Set[str] = set()
        self._failed_attempts: Dict[str, List[datetime]] = {}
        self._lockout_duration = timedelta(minutes=30)
        self._max_failures = 5

    def authenticate_request(
        self,
        client_cert: Optional[bytes],
        client_ip: str,
        request_signature: str,
        timestamp: datetime,
        agent_id: str
    ) -> bool:
        """
        Authenticate request using multiple factors.

        Returns:
            True if authentication successful
        """
        # Check IP allowlist
        if not self._validate_ip(client_ip):
            self._record_failure(agent_id)
            logger.warning(f"Access from unauthorized IP: {client_ip}")
            return False

        # Check for lockout
        if self._is_locked_out(agent_id):
            logger.warning(f"Access attempt from locked-out agent: {agent_id}")
            return False

        # Validate mTLS certificate
        if not self._validate_certificate(client_cert, agent_id):
            self._record_failure(agent_id)
            logger.warning(f"Invalid certificate for agent: {agent_id}")
            return False

        # Verify request signature
        if not self._verify_signature(request_signature, agent_id, timestamp):
            self._record_failure(agent_id)
            logger.warning(f"Invalid signature for agent: {agent_id}")
            return False

        # Check timestamp (prevent replay attacks)
        if datetime.utcnow() - timestamp > timedelta(minutes=5):
            logger.warning(f"Stale request from agent: {agent_id}")
            return False

        # Success - clear failures
        self._clear_failures(agent_id)
        return True

    def _validate_ip(self, ip: str) -> bool:
        """Validate client IP against allowlist."""
        if not self._allowed_ips:  # Allow all if not configured (dev only)
            return True
        return ip in self._allowed_ips

    def _validate_certificate(
        self,
        cert: Optional[bytes],
        agent_id: str
    ) -> bool:
        """Validate mTLS certificate."""
        if not cert:
            return False

        # Verify certificate matches agent
        expected_fingerprint = self._get_agent_cert_fingerprint(agent_id)
        actual_fingerprint = hashlib.sha256(cert).hexdigest()

        return hmac.compare_digest(expected_fingerprint, actual_fingerprint)

    def _verify_signature(
        self,
        signature: str,
        agent_id: str,
        timestamp: datetime
    ) -> bool:
        """Verify request HMAC signature."""
        # Implementation would verify HMAC of request
        # using agent's secret key
        pass

    def _is_locked_out(self, agent_id: str) -> bool:
        """Check if agent is locked out due to failed attempts."""
        if agent_id not in self._failed_attempts:
            return False

        recent_failures = [
            t for t in self._failed_attempts[agent_id]
            if datetime.utcnow() - t < self._lockout_duration
        ]

        return len(recent_failures) >= self._max_failures

    def _record_failure(self, agent_id: str):
        """Record failed authentication attempt."""
        if agent_id not in self._failed_attempts:
            self._failed_attempts[agent_id] = []
        self._failed_attempts[agent_id].append(datetime.utcnow())

    def _clear_failures(self, agent_id: str):
        """Clear failure record on successful auth."""
        if agent_id in self._failed_attempts:
            del self._failed_attempts[agent_id]

    def _get_agent_cert_fingerprint(self, agent_id: str) -> str:
        """Get expected certificate fingerprint for agent."""
        # Would lookup from secure storage
        pass
```

### 4.3 Audit and Compliance Logging

```python
"""
Comprehensive Audit Logging for Secure Vault.

Implements:
- Immutable audit trail
- Tamper detection
- Compliance reporting
- Real-time alerting
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    ACCESS_ATTEMPT = "access_attempt"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    SECRET_CREATED = "secret_created"
    SECRET_READ = "secret_read"
    SECRET_UPDATED = "secret_updated"
    SECRET_DELETED = "secret_deleted"
    SECRET_ROTATED = "secret_rotated"
    KEY_ROTATION = "key_rotation"
    POLICY_VIOLATION = "policy_violation"
    ANOMALY_DETECTED = "anomaly_detected"


@dataclass
class AuditEvent:
    """Immutable audit event."""
    event_id: str
    timestamp: datetime
    event_type: AuditEventType
    agent_id: str
    role: Optional[str]
    secret_id: Optional[str]
    secret_type: Optional[str]
    operation: Optional[str]
    success: bool
    reason: str
    source_ip_hash: str
    session_id: str
    justification: Optional[str]
    previous_hash: Optional[str]  # For blockchain-style integrity

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "agent_id": self.agent_id,
            "role": self.role,
            "secret_id": self.secret_id,
            "secret_type": self.secret_type,
            "operation": self.operation,
            "success": self.success,
            "reason": self.reason,
            "source_ip_hash": self.source_ip_hash,
            "session_id": self.session_id,
            "justification": self.justification,
            "previous_hash": self.previous_hash,
        }

    def compute_hash(self) -> str:
        """Compute hash of event for integrity chain."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class SecureVaultAuditLogger:
    """
    Immutable audit logging with tamper detection.

    Features:
    - Blockchain-style integrity chain
    - Dual-write to separate storage
    - Real-time alerting on anomalies
    - Compliance report generation
    """

    def __init__(
        self,
        neo4j_client: Optional[Any] = None,
        external_storage: Optional[Any] = None
    ):
        self.neo4j = neo4j_client
        self.external = external_storage
        self._last_hash: Optional[str] = None
        self._alert_handlers: List[Callable] = []

    def log_event(self, event: AuditEvent):
        """
        Log audit event with integrity protection.

        Writes to:
        1. Neo4j (primary)
        2. External storage (WORM/S3 with object lock)
        """
        # Link to previous event (blockchain-style)
        event.previous_hash = self._last_hash

        # Compute this event's hash
        event_hash = event.compute_hash()
        self._last_hash = event_hash

        # Store event
        self._store_event(event)

        # Check for anomalies
        self._check_anomalies(event)

    def _store_event(self, event: AuditEvent):
        """Store event to multiple locations."""
        event_data = event.to_dict()
        event_data["integrity_hash"] = event.compute_hash()

        # Store in Neo4j
        if self.neo4j:
            cypher = """
            CREATE (a:AuditEvent {
                event_id: $event_id,
                timestamp: datetime($timestamp),
                event_type: $event_type,
                agent_id: $agent_id,
                integrity_hash: $integrity_hash,
                details: $details
            })
            """
            self.neo4j.run(cypher, {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "agent_id": event.agent_id,
                "integrity_hash": event_data["integrity_hash"],
                "details": json.dumps(event_data)
            })

        # Store in external WORM storage
        if self.external:
            self.external.store_immutable(event_data)

    def _check_anomalies(self, event: AuditEvent):
        """Check for anomalous patterns and alert."""
        anomalies = []

        # Check for multiple failed attempts
        if event.event_type == AuditEventType.ACCESS_DENIED:
            recent_failures = self._count_recent_failures(
                event.agent_id,
                minutes=5
            )
            if recent_failures > 5:
                anomalies.append(f"Multiple access denials: {recent_failures}")

        # Check for off-hours access
        hour = event.timestamp.hour
        if hour < 6 or hour > 22:
            if event.event_type in {
                AuditEventType.SECRET_READ,
                AuditEventType.SECRET_DELETED
            }:
                anomalies.append("Off-hours sensitive access")

        # Check for unusual access patterns
        if event.event_type == AuditEventType.SECRET_READ:
            recent_accesses = self._count_recent_accesses(
                event.agent_id,
                minutes=60
            )
            if recent_accesses > 100:
                anomalies.append(f"Unusual access volume: {recent_accesses}")

        # Trigger alerts
        for anomaly in anomalies:
            self._trigger_alert(event, anomaly)

    def _trigger_alert(self, event: AuditEvent, anomaly: str):
        """Trigger security alert."""
        alert = {
            "severity": "HIGH",
            "anomaly": anomaly,
            "event": event.to_dict(),
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.error(f"SECURITY ALERT: {anomaly}", extra=alert)

        for handler in self._alert_handlers:
            handler(alert)

    def verify_integrity(self) -> bool:
        """
        Verify integrity of audit chain.

        Returns:
            True if chain is intact
        """
        if not self.neo4j:
            return True

        # Fetch all events in order
        cypher = """
        MATCH (a:AuditEvent)
        RETURN a
        ORDER BY a.timestamp
        """

        events = self.neo4j.run(cypher).data()
        previous_hash = None

        for record in events:
            event_data = json.loads(record["a"]["details"])

            # Verify previous hash link
            if event_data.get("previous_hash") != previous_hash:
                logger.error(
                    f"Audit chain broken at event {event_data['event_id']}"
                )
                return False

            # Verify event hash
            computed = hashlib.sha256(
                json.dumps(event_data, sort_keys=True).encode()
            ).hexdigest()

            if computed != record["a"]["integrity_hash"]:
                logger.error(
                    f"Event tampered: {event_data['event_id']}"
                )
                return False

            previous_hash = computed

        return True

    def generate_compliance_report(
        self,
        start_date: datetime,
        end_date: datetime,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate compliance report for audit period.

        Returns:
            Report with access statistics and anomalies
        """
        # Query audit events
        cypher = """
        MATCH (a:AuditEvent)
        WHERE a.timestamp >= datetime($start)
          AND a.timestamp <= datetime($end)
        """
        params = {"start": start_date.isoformat(), "end": end_date.isoformat()}

        if agent_id:
            cypher += " AND a.agent_id = $agent_id"
            params["agent_id"] = agent_id

        cypher += """
        RETURN
            count(a) as total_events,
            count(CASE WHEN a.success = true THEN 1 END) as successful,
            count(CASE WHEN a.success = false THEN 1 END) as failed,
            collect(DISTINCT a.agent_id) as agents
        """

        result = self.neo4j.run(cypher, params).single()

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "agent_filter": agent_id,
            "total_events": result["total_events"],
            "successful_accesses": result["successful"],
            "failed_attempts": result["failed"],
            "unique_agents": len(result["agents"]),
            "integrity_verified": self.verify_integrity()
        }
```

---

## 5. Compliance Considerations

### 5.1 GDPR Compliance for PII

| Requirement | Implementation |
|-------------|----------------|
| **Lawful Basis** | Consent recorded at onboarding; legitimate interest for operational needs |
| **Data Minimization** | Only necessary PII stored; anonymization where possible |
| **Purpose Limitation** | PII only used for stated purposes; access logged |
| **Storage Limitation** | Automatic TTL on PII; retention policies enforced |
| **Accuracy** | Regular data quality checks; update mechanisms |
| **Integrity/Confidentiality** | Encryption at rest and in transit; access controls |
| **Right to Erasure** | Secure deletion with cryptographic erasure |
| **Right to Access** | Export functionality for user data |
| **Data Portability** | JSON export of user secrets |
| **Privacy by Design** | Privacy controls built into architecture |

### 5.2 PCI-DSS for Financial Data

| Requirement | Implementation |
|-------------|----------------|
| **Firewall** | Network segmentation; Secure Vault in isolated subnet |
| **Default Passwords** | No default credentials; strong password policy |
| **Stored Data Protection** | AES-256-GCM encryption; HSM key storage |
| **Encryption in Transit** | TLS 1.3; mTLS between services |
| **Anti-Virus** | Host-based security on Secure Vault servers |
| **Secure Systems** | Hardened OS; minimal attack surface |
| **Access Control** | RBAC; need-to-know basis; regular reviews |
| **Unique IDs** | UUID v4 for all secrets; no sequential IDs |
| **Physical Access** | Cloud provider controls; no direct access |
| **Access Logging** | Comprehensive audit trail; integrity protection |
| **Regular Testing** | Penetration testing; vulnerability scanning |
| **Security Policy** | Documented policies; regular training |

### 5.3 Key Rotation Requirements

```python
"""
Key Rotation System for Secure Vault.

Implements:
- Automatic key rotation
- Graceful key transition
- Re-encryption of existing data
- Emergency key revocation
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class KeyRotationPolicy:
    """Policy for automatic key rotation."""

    def __init__(
        self,
        data_key_rotation_days: int = 90,
        master_key_rotation_days: int = 365,
        emergency_rotation_hours: int = 1
    ):
        self.data_key_rotation = timedelta(days=data_key_rotation_days)
        self.master_key_rotation = timedelta(days=master_key_rotation_days)
        self.emergency_rotation = timedelta(hours=emergency_rotation_hours)


class KeyRotationManager:
    """
    Manages encryption key rotation.

    Supports:
    - Scheduled rotation
    - Emergency rotation
    - Gradual re-encryption
    - Key versioning
    """

    def __init__(
        self,
        encryption: SecureVaultEncryption,
        policy: KeyRotationPolicy,
        neo4j_client: Any
    ):
        self.encryption = encryption
        self.policy = policy
        self.neo4j = neo4j_client
        self._active_rotations: Dict[str, Any] = {}

    async def schedule_rotation(
        self,
        key_id: str,
        rotation_type: str = "scheduled"
    ) -> str:
        """
        Schedule key rotation.

        Args:
            key_id: Key to rotate
            rotation_type: 'scheduled', 'emergency', or 'compliance'

        Returns:
            Rotation job ID
        """
        job_id = f"rotation:{key_id}:{datetime.utcnow().isoformat()}"

        # Create new key
        new_key_id = f"{key_id}_v{self._get_next_version(key_id)}"

        self._active_rotations[job_id] = {
            "key_id": key_id,
            "new_key_id": new_key_id,
            "status": "in_progress",
            "started_at": datetime.utcnow(),
            "type": rotation_type,
            "progress": 0
        }

        logger.info(
            f"Key rotation started: {key_id} -> {new_key_id}",
            extra={"job_id": job_id, "type": rotation_type}
        )

        # Start gradual re-encryption
        await self._gradual_reencryption(job_id, key_id, new_key_id)

        return job_id

    async def _gradual_reencryption(
        self,
        job_id: str,
        old_key_id: str,
        new_key_id: str,
        batch_size: int = 100
    ):
        """
        Gradually re-encrypt data with new key.

        Process:
        1. Query batch of secrets using old key
        2. Decrypt with old key
        3. Re-encrypt with new key
        4. Update in database
        5. Repeat until complete
        """
        offset = 0
        total = self._count_secrets_with_key(old_key_id)

        while offset < total:
            # Get batch
            secrets = self._get_secrets_batch(old_key_id, batch_size, offset)

            for secret in secrets:
                try:
                    # Decrypt with old key
                    plaintext = self.encryption.decrypt(
                        secret["encrypted_value"]
                    )

                    # Re-encrypt with new key
                    new_ciphertext = self.encryption.encrypt(
                        plaintext,
                        key_id=new_key_id
                    )

                    # Update in database
                    self._update_secret_encryption(
                        secret["secret_id"],
                        new_ciphertext,
                        new_key_id
                    )

                except Exception as e:
                    logger.error(
                        f"Re-encryption failed for {secret['secret_id']}: {e}"
                    )
                    # Continue with next; will retry on next rotation

            offset += batch_size
            progress = (offset / total) * 100
            self._active_rotations[job_id]["progress"] = progress

            # Brief pause to avoid overwhelming database
            await asyncio.sleep(0.1)

        # Mark old key as deprecated
        self._deprecate_key(old_key_id)

        self._active_rotations[job_id]["status"] = "completed"
        self._active_rotations[job_id]["completed_at"] = datetime.utcnow()

        logger.info(
            f"Key rotation completed: {old_key_id} -> {new_key_id}",
            extra={"job_id": job_id, "secrets_processed": total}
        )

    async def emergency_revoke(self, key_id: str):
        """
        Emergency key revocation.

        Immediately marks key as revoked and triggers emergency rotation.
        All data must be re-encrypted before old key is deleted.
        """
        logger.critical(f"EMERGENCY KEY REVOCATION: {key_id}")

        # Mark key as revoked
        self._revoke_key(key_id)

        # Trigger emergency rotation
        await self.schedule_rotation(key_id, rotation_type="emergency")

        # Alert security team
        self._alert_security_team(
            f"Emergency key revocation: {key_id}",
            severity="CRITICAL"
        )

    def _get_next_version(self, key_id: str) -> int:
        """Get next version number for key."""
        # Parse current version and increment
        if "_v" in key_id:
            base, version = key_id.rsplit("_v", 1)
            return int(version) + 1
        return 1

    def _count_secrets_with_key(self, key_id: str) -> int:
        """Count secrets encrypted with specific key."""
        cypher = """
        MATCH (s:Secret {encryption_key_id: $key_id})
        RETURN count(s) as total
        """
        result = self.neo4j.run(cypher, {"key_id": key_id}).single()
        return result["total"]

    def _get_secrets_batch(
        self,
        key_id: str,
        limit: int,
        offset: int
    ) -> List[Dict]:
        """Get batch of secrets for re-encryption."""
        cypher = """
        MATCH (s:Secret {encryption_key_id: $key_id})
        RETURN s.secret_id as secret_id, s.encrypted_value as encrypted_value
        SKIP $offset LIMIT $limit
        """
        return self.neo4j.run(cypher, {
            "key_id": key_id,
            "offset": offset,
            "limit": limit
        }).data()

    def _update_secret_encryption(
        self,
        secret_id: str,
        new_ciphertext: str,
        new_key_id: str
    ):
        """Update secret with new encryption."""
        cypher = """
        MATCH (s:Secret {secret_id: $secret_id})
        SET s.encrypted_value = $ciphertext,
            s.encryption_key_id = $key_id,
            s.last_rotated = datetime(),
            s.rotation_count = s.rotation_count + 1
        """
        self.neo4j.run(cypher, {
            "secret_id": secret_id,
            "ciphertext": new_ciphertext,
            "key_id": new_key_id
        })

    def _deprecate_key(self, key_id: str):
        """Mark key as deprecated."""
        cypher = """
        MATCH (k:EncryptionKey {key_id: $key_id})
        SET k.status = 'deprecated',
            k.deprecated_at = datetime()
        """
        self.neo4j.run(cypher, {"key_id": key_id})

    def _revoke_key(self, key_id: str):
        """Mark key as revoked."""
        cypher = """
        MATCH (k:EncryptionKey {key_id: $key_id})
        SET k.status = 'revoked',
            k.revoked_at = datetime()
        """
        self.neo4j.run(cypher, {"key_id": key_id})
```

---

## 6. Integration Architecture

### 6.1 Kublai Authentication to Secure Vault

```python
"""
Kublai Gateway for Secure Vault Access.

Acts as the sole entry point for sensitive data access.
Implements:
- Authentication proxy
- Request validation
- Audit logging
- Rate limiting
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import asyncio


@dataclass
class VaultAccessRequest:
    """Request to access Secure Vault."""
    operation: str  # 'create', 'read', 'update', 'delete'
    secret_type: str
    secret_id: Optional[str]
    data: Optional[Dict[str, Any]]
    justification: str
    sender_hash: str
    session_id: str


class KublaiVaultGateway:
    """
    Gateway for Kublai to access Secure Vault.

    This is the ONLY component that directly connects to Secure Vault.
    All other agents must request access through Kublai.
    """

    def __init__(
        self,
        vault_uri: str,
        vault_credentials: Dict[str, str],
        access_control: SecureVaultAccessControl,
        encryption: SecureVaultEncryption,
        audit_logger: SecureVaultAuditLogger
    ):
        self.vault_uri = vault_uri
        self.credentials = vault_credentials
        self.access_control = access_control
        self.encryption = encryption
        self.audit = audit_logger
        self._connection_pool: Optional[Any] = None

    async def initialize(self):
        """Initialize connection to Secure Vault."""
        # Establish mTLS connection
        self._connection_pool = await self._create_secure_connection()

    async def execute(
        self,
        agent_id: str,
        request: VaultAccessRequest
    ) -> Dict[str, Any]:
        """
        Execute vault operation on behalf of agent.

        Args:
            agent_id: Requesting agent
            request: Vault access request

        Returns:
            Operation result
        """
        # Build access request
        role = AGENT_ROLES.get(agent_id)

        access_request = AccessRequest(
            agent_id=agent_id,
            role=role,
            secret_id=request.secret_id,
            secret_type=SecretType(request.secret_type),
            operation=request.operation,
            justification=request.justification,
            timestamp=datetime.utcnow(),
            session_id=request.session_id,
            source_ip="internal",  # Would be actual IP in production
            sender_hash=request.sender_hash
        )

        # Evaluate access
        decision = self.access_control.evaluate_access(access_request)

        if not decision.granted:
            raise VaultAccessDenied(decision.reason)

        # Execute operation
        if request.operation == "create":
            return await self._create_secret(request, decision)
        elif request.operation == "read":
            return await self._read_secret(request, decision)
        elif request.operation == "update":
            return await self._update_secret(request, decision)
        elif request.operation == "delete":
            return await self._delete_secret(request, decision)
        else:
            raise ValueError(f"Unknown operation: {request.operation}")

    async def _create_secret(
        self,
        request: VaultAccessRequest,
        decision: AccessDecision
    ) -> Dict[str, Any]:
        """Create new secret in vault."""
        # Encrypt value
        encrypted = self.encryption.encrypt(
            request.data["value"],
            key_id="default"
        )

        # Create blind index if needed
        blind_index = None
        if request.data.get("searchable"):
            blind_index = self._create_blind_index(
                request.data["value"],
                request.secret_type
            )

        # Store in vault
        secret_id = await self._store_in_vault({
            "secret_type": request.secret_type,
            "owner_hash": request.sender_hash,
            "encrypted_value": encrypted,
            "metadata": request.data.get("metadata", {}),
            "access_tier": request.data.get("access_tier", "high"),
            "expires_at": request.data.get("expires_at"),
            "blind_index": blind_index
        })

        return {"secret_id": secret_id, "created": True}

    async def _read_secret(
        self,
        request: VaultAccessRequest,
        decision: AccessDecision
    ) -> Dict[str, Any]:
        """Read secret from vault."""
        # Query vault
        secret = await self._query_vault(
            request.secret_id,
            request.sender_hash
        )

        if not secret:
            raise VaultNotFound(f"Secret {request.secret_id} not found")

        # Decrypt if access level allows
        if decision.level in {AccessLevel.READ, AccessLevel.WRITE, AccessLevel.DELETE}:
            plaintext = self.encryption.decrypt(secret["encrypted_value"])
            secret["value"] = plaintext
        else:
            # Metadata only
            secret["value"] = None

        return secret

    async def _create_secure_connection(self) -> Any:
        """Create mTLS connection to Secure Vault."""
        # Implementation would use neo4j driver with mTLS
        pass

    async def _store_in_vault(self, data: Dict[str, Any]) -> str:
        """Store secret in vault database."""
        # Implementation would execute Cypher query
        pass

    async def _query_vault(
        self,
        secret_id: str,
        sender_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Query secret from vault with sender isolation."""
        # Implementation would execute Cypher with sender_hash filter
        pass


class VaultAccessDenied(Exception):
    """Raised when vault access is denied."""
    pass


class VaultNotFound(Exception):
    """Raised when secret is not found."""
    pass
```

### 6.2 Proxy/Gateway Layer

```python
"""
Secure Vault Proxy Layer.

Provides:
- Single entry point
- Protocol translation
- Request/response validation
- Circuit breaker pattern
"""

from typing import Optional, Dict, Any
import asyncio
from datetime import datetime


class SecureVaultProxy:
    """
    Proxy layer for Secure Vault.

    Sits between Kublai and Secure Vault Neo4j.
    Provides additional security and reliability layers.
    """

    def __init__(
        self,
        vault_gateway: KublaiVaultGateway,
        max_retries: int = 3,
        circuit_breaker_threshold: int = 5
    ):
        self.gateway = vault_gateway
        self.max_retries = max_retries
        self.circuit_breaker = CircuitBreaker(circuit_breaker_threshold)

    async def proxy_request(
        self,
        agent_id: str,
        request: VaultAccessRequest
    ) -> Dict[str, Any]:
        """
        Proxy request to vault with reliability patterns.

        Implements:
        - Circuit breaker
        - Retry with backoff
        - Request validation
        - Response sanitization
        """
        # Check circuit breaker
        if self.circuit_breaker.is_open():
            raise VaultUnavailable("Circuit breaker open")

        # Validate request
        self._validate_request(request)

        # Execute with retry
        for attempt in range(self.max_retries):
            try:
                result = await self.gateway.execute(agent_id, request)
                self.circuit_breaker.record_success()
                return self._sanitize_response(result)

            except VaultAccessDenied:
                # Don't retry auth failures
                raise

            except Exception as e:
                self.circuit_breaker.record_failure()
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise VaultUnavailable(f"Max retries exceeded: {e}")

    def _validate_request(self, request: VaultAccessRequest):
        """Validate request format and content."""
        if not request.justification:
            raise ValueError("Justification required")

        if len(request.justification) < 10:
            raise ValueError("Justification too short")

        if request.operation not in {"create", "read", "update", "delete"}:
            raise ValueError(f"Invalid operation: {request.operation}")

    def _sanitize_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize response before returning."""
        # Remove internal fields
        sanitized = {k: v for k, v in response.items()
                     if not k.startswith("_")}
        return sanitized


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(self, threshold: int = 5, timeout_seconds: int = 60):
        self.threshold = threshold
        self.timeout = timeout_seconds
        self.failures = 0
        self.last_failure: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open

    def is_open(self) -> bool:
        """Check if circuit is open."""
        if self.state == "open":
            # Check if timeout has passed
            if self.last_failure:
                elapsed = (datetime.utcnow() - self.last_failure).seconds
                if elapsed > self.timeout:
                    self.state = "half-open"
                    return False
            return True
        return False

    def record_success(self):
        """Record successful operation."""
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        """Record failed operation."""
        self.failures += 1
        self.last_failure = datetime.utcnow()

        if self.failures >= self.threshold:
            self.state = "open"


class VaultUnavailable(Exception):
    """Raised when vault is unavailable."""
    pass
```

### 6.3 Session Management Patterns

```python
"""
Secure Session Management for Vault Access.

Implements:
- Short-lived sessions
- Session binding
- Concurrent session limits
- Automatic expiration
"""

from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import secrets
import hashlib


@dataclass
class VaultSession:
    """Secure vault access session."""
    session_id: str
    agent_id: str
    sender_hash: str
    created_at: datetime
    expires_at: datetime
    last_accessed: datetime
    access_count: int = 0
    ip_address: Optional[str] = None
    fingerprint: Optional[str] = None  # Client certificate fingerprint
    permissions: Set[str] = field(default_factory=set)

    def is_valid(self) -> bool:
        """Check if session is still valid."""
        return datetime.utcnow() < self.expires_at

    def touch(self):
        """Update last accessed time."""
        self.last_accessed = datetime.utcnow()
        self.access_count += 1


class VaultSessionManager:
    """
    Manages secure sessions for vault access.

    Features:
    - Cryptographically random session IDs
    - Automatic expiration
    - IP binding (optional)
    - Certificate binding
    - Concurrent session limits
    """

    def __init__(
        self,
        session_ttl_minutes: int = 30,
        max_concurrent_sessions: int = 3,
        bind_to_ip: bool = True,
        bind_to_certificate: bool = True
    ):
        self.ttl = timedelta(minutes=session_ttl_minutes)
        self.max_concurrent = max_concurrent_sessions
        self.bind_to_ip = bind_to_ip
        self.bind_to_certificate = bind_to_certificate
        self._sessions: Dict[str, VaultSession] = {}

    def create_session(
        self,
        agent_id: str,
        sender_hash: str,
        ip_address: Optional[str] = None,
        cert_fingerprint: Optional[str] = None,
        permissions: Optional[Set[str]] = None
    ) -> VaultSession:
        """
        Create new vault access session.

        Args:
            agent_id: Agent identifier
            sender_hash: Sender hash for isolation
            ip_address: Client IP for binding
            cert_fingerprint: Certificate fingerprint for binding
            permissions: Granted permissions

        Returns:
            New session
        """
        # Check concurrent session limit
        agent_sessions = self._get_agent_sessions(agent_id)
        if len(agent_sessions) >= self.max_concurrent:
            # Revoke oldest session
            oldest = min(agent_sessions, key=lambda s: s.created_at)
            self.revoke_session(oldest.session_id)

        # Generate cryptographically random session ID
        session_id = self._generate_session_id()

        now = datetime.utcnow()
        session = VaultSession(
            session_id=session_id,
            agent_id=agent_id,
            sender_hash=sender_hash,
            created_at=now,
            expires_at=now + self.ttl,
            last_accessed=now,
            ip_address=ip_address if self.bind_to_ip else None,
            fingerprint=cert_fingerprint if self.bind_to_certificate else None,
            permissions=permissions or {"read"}
        )

        self._sessions[session_id] = session

        return session

    def validate_session(
        self,
        session_id: str,
        ip_address: Optional[str] = None,
        cert_fingerprint: Optional[str] = None
    ) -> Optional[VaultSession]:
        """
        Validate and return session if valid.

        Args:
            session_id: Session identifier
            ip_address: Current IP for validation
            cert_fingerprint: Current cert fingerprint for validation

        Returns:
            Session if valid, None otherwise
        """
        session = self._sessions.get(session_id)

        if not session:
            return None

        # Check expiration
        if not session.is_valid():
            del self._sessions[session_id]
            return None

        # Validate IP binding
        if self.bind_to_ip and session.ip_address:
            if ip_address != session.ip_address:
                # Possible session hijacking attempt
                self._handle_security_event(
                    "ip_mismatch",
                    session,
                    {"expected": session.ip_address, "actual": ip_address}
                )
                return None

        # Validate certificate binding
        if self.bind_to_certificate and session.fingerprint:
            if cert_fingerprint != session.fingerprint:
                self._handle_security_event(
                    "cert_mismatch",
                    session,
                    {"expected": session.fingerprint, "actual": cert_fingerprint}
                )
                return None

        # Update activity
        session.touch()

        return session

    def revoke_session(self, session_id: str):
        """Revoke a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]

    def revoke_all_agent_sessions(self, agent_id: str):
        """Revoke all sessions for an agent."""
        to_revoke = [
            sid for sid, session in self._sessions.items()
            if session.agent_id == agent_id
        ]
        for sid in to_revoke:
            self.revoke_session(sid)

    def _get_agent_sessions(self, agent_id: str) -> List[VaultSession]:
        """Get all active sessions for an agent."""
        return [
            session for session in self._sessions.values()
            if session.agent_id == agent_id
        ]

    def _generate_session_id(self) -> str:
        """Generate cryptographically secure session ID."""
        # 256-bit random value
        random_bytes = secrets.token_bytes(32)
        return hashlib.sha256(random_bytes).hexdigest()

    def _handle_security_event(
        self,
        event_type: str,
        session: VaultSession,
        details: Dict[str, Any]
    ):
        """Handle security event (binding mismatch)."""
        # Log security event
        logger.warning(
            f"Vault session security event: {event_type}",
            extra={
                "session_id": session.session_id,
                "agent_id": session.agent_id,
                "event_type": event_type,
                "details": details
            }
        )

        # Revoke session
        self.revoke_session(session.session_id)

        # Alert security team for suspicious activity
        if event_type in {"ip_mismatch", "cert_mismatch"}:
            self._alert_security_team(event_type, session, details)

    def _alert_security_team(
        self,
        event_type: str,
        session: VaultSession,
        details: Dict[str, Any]
    ):
        """Alert security team of suspicious activity."""
        # Implementation would send to SIEM, PagerDuty, etc.
        pass
```

---

## 7. Security Recommendations Summary

### 7.1 Implementation Priority

| Priority | Component | Severity | Effort |
|----------|-----------|----------|--------|
| **P0** | Network isolation and mTLS | Critical | Medium |
| **P0** | HSM integration for key storage | Critical | High |
| **P0** | RBAC implementation | Critical | Medium |
| **P1** | Field-level encryption | High | Medium |
| **P1** | Audit logging with integrity | High | Medium |
| **P1** | Session management | High | Low |
| **P2** | Searchable encryption | Medium | High |
| **P2** | Key rotation automation | Medium | Medium |
| **P2** | Anomaly detection | Medium | High |
| **P3** | JIT access approval | Low | Medium |

### 7.2 Security Checklist

#### Pre-Deployment
- [ ] HSM provisioned and configured
- [ ] mTLS certificates generated and distributed
- [ ] Network segmentation rules configured
- [ ] Encryption keys generated (never logged)
- [ ] Audit logging infrastructure ready
- [ ] Backup encryption keys stored offline
- [ ] Incident response procedures documented

#### Deployment
- [ ] Secure Vault Neo4j in isolated subnet
- [ ] Firewall rules restricting access to gateway only
- [ ] TLS 1.3 enforced for all connections
- [ ] Certificate pinning configured
- [ ] Rate limiting enabled
- [ ] Monitoring and alerting active

#### Post-Deployment
- [ ] Regular key rotation scheduled
- [ ] Access reviews conducted quarterly
- [ ] Penetration testing performed annually
- [ ] Audit logs reviewed weekly
- [ ] Disaster recovery drills conducted
- [ ] Security training for all operators

### 7.3 OWASP Mapping

| Control | OWASP Category | Implementation |
|---------|----------------|----------------|
| Encryption at rest | A02:2021 - Cryptographic Failures | AES-256-GCM with HSM keys |
| mTLS connections | A02:2021 - Cryptographic Failures | Certificate pinning |
| RBAC | A01:2021 - Broken Access Control | Role-based permissions |
| Input validation | A03:2021 - Injection | Parameterized queries |
| Audit logging | A09:2021 - Security Logging | Immutable audit trail |
| Session management | A07:2021 - Auth Failures | Short-lived bound sessions |
| Rate limiting | A07:2021 - Auth Failures | Per-agent limits |
| Network isolation | A05:2021 - Security Misconfiguration | Subnet segmentation |

---

## 8. References

- OWASP Top 10: https://owasp.org/Top10/
- Neo4j Security: https://neo4j.com/docs/operations-manual/current/security/
- NIST SP 800-57: Key Management Guidelines
- GDPR Article 32: Security of Processing
- PCI-DSS v4.0: Payment Card Industry Standards

---

**Document Classification:** Security Architecture
**Distribution:** Kurultai Security Team, Architecture Review Board
**Review Cycle:** Quarterly
**Next Review:** 2026-05-04
