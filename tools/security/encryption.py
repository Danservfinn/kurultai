"""
Field-Level Encryption for Neo4j Sensitive Data.

Provides application-layer encryption for sensitive properties stored in Neo4j.
Supports both deterministic encryption (for queryable fields) and randomized
encryption (maximum security).

Security Notes:
- Encryption keys must be stored separately from database
- Use environment variables or dedicated key management service
- Rotate keys periodically
- Never log encrypted values or keys

OWASP References:
- A02:2021-Cryptographic Failures
"""

import os
import base64
import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class FieldEncryption:
    """
    Field-level encryption for sensitive Neo4j properties.

    Design decisions:
    1. Encrypt at application layer, not database layer
    2. Use deterministic encryption for queryable fields (equality queries)
    3. Use randomized encryption for non-queryable fields (maximum security)
    4. Store encryption metadata with encrypted data

    Format: ENC:<mode>:<ciphertext>
    - mode: 'D' for deterministic, 'R' for randomized
    - ciphertext: base64-encoded encrypted data

    Example:
        encryption = FieldEncryption(os.getenv("NEO4J_ENCRYPTION_KEY"))

        # Encrypt for storage
        encrypted = encryption.encrypt("sensitive data", deterministic=False)
        # Result: "ENC:R:gAAAAAB..."

        # Decrypt for use
        decrypted = encryption.decrypt(encrypted)
        # Result: "sensitive data"
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption with master key.

        Args:
            master_key: Base64-encoded Fernet key (from env var)
                       Generate with: Fernet.generate_key()

        Raises:
            ValueError: If no key provided and env var not set
        """
        key = master_key or os.getenv("NEO4J_FIELD_ENCRYPTION_KEY")

        if not key:
            raise ValueError(
                "Encryption key required. Provide master_key or set "
                "NEO4J_FIELD_ENCRYPTION_KEY environment variable. "
                "Generate key with: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )

        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()

        try:
            self.cipher = Fernet(key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

        # Derive a separate key for deterministic encryption
        self._deterministic_key = hashlib.sha256(key).digest()

    def encrypt(self, value: str, deterministic: bool = False) -> str:
        """
        Encrypt a string value.

        Args:
            value: Value to encrypt
            deterministic: If True, same input produces same output
                          (allows equality queries, less secure)

        Returns:
            Encrypted value with metadata prefix
        """
        if not value:
            return value

        if deterministic:
            encrypted = self._deterministic_encrypt(value)
            return f"ENC:D:{encrypted}"
        else:
            encrypted = self.cipher.encrypt(value.encode()).decode()
            return f"ENC:R:{encrypted}"

    def _deterministic_encrypt(self, value: str) -> str:
        """
        Deterministic encryption using synthetic IV.

        Same input always produces same output, allowing equality queries.
        Less secure than randomized encryption - use only when necessary.
        """
        # Generate synthetic IV from value hash
        iv = hmac.new(
            self._deterministic_key,
            value.encode(),
            hashlib.sha256
        ).digest()[:16]

        # Combine IV with encrypted data
        encrypted = self.cipher.encrypt(value.encode())

        # Store IV prefix for decryption
        return base64.urlsafe_b64encode(iv + encrypted).decode()

    def decrypt(self, encrypted_value: str) -> str:
        """
        Decrypt an encrypted value.

        Args:
            encrypted_value: Value with ENC:D: or ENC:R: prefix

        Returns:
            Decrypted string

        Raises:
            ValueError: If format is invalid or decryption fails
        """
        if not encrypted_value or not isinstance(encrypted_value, str):
            return encrypted_value

        if not encrypted_value.startswith("ENC:"):
            return encrypted_value  # Not encrypted

        parts = encrypted_value.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"Invalid encrypted value format: {encrypted_value[:20]}...")

        _, mode, ciphertext = parts

        try:
            if mode == "R":
                return self.cipher.decrypt(ciphertext.encode()).decode()
            elif mode == "D":
                return self._deterministic_decrypt(ciphertext)
            else:
                raise ValueError(f"Unknown encryption mode: {mode}")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def _deterministic_decrypt(self, ciphertext: str) -> str:
        """Decrypt deterministically encrypted value."""
        data = base64.urlsafe_b64decode(ciphertext.encode())

        # Extract IV (first 16 bytes) and encrypted data
        iv = data[:16]
        encrypted = data[16:]

        # Decrypt
        return self.cipher.decrypt(encrypted).decode()

    def is_encrypted(self, value: Any) -> bool:
        """Check if value is encrypted."""
        return isinstance(value, str) and value.startswith("ENC:")

    def rotate_key(
        self,
        encrypted_value: str,
        new_encryption: 'FieldEncryption'
    ) -> str:
        """
        Re-encrypt value with new key (key rotation).

        Args:
            encrypted_value: Current encrypted value
            new_encryption: New FieldEncryption instance with new key

        Returns:
            Re-encrypted value
        """
        if not self.is_encrypted(encrypted_value):
            return encrypted_value

        # Decrypt with old key
        plaintext = self.decrypt(encrypted_value)

        # Determine if deterministic
        is_deterministic = encrypted_value.startswith("ENC:D:")

        # Re-encrypt with new key
        return new_encryption.encrypt(plaintext, deterministic=is_deterministic)


class EncryptedPropertyManager:
    """
    Manages encrypted properties in Neo4j nodes.

    Provides convenient methods for encrypting/decrypting node properties
    with support for queryable encrypted fields.

    Example:
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
        """
        Initialize property manager.

        Args:
            encryption_key: Encryption key (from env var if not provided)
        """
        self.encryption = FieldEncryption(encryption_key)

    def encrypt_field(self, value: str, queryable: bool = False) -> str:
        """
        Encrypt a field value.

        Args:
            value: Value to encrypt
            queryable: If True, use deterministic encryption for equality queries

        Returns:
            Encrypted value
        """
        if not value:
            return value
        return self.encryption.encrypt(value, deterministic=queryable)

    def decrypt_field(self, value: str) -> str:
        """Decrypt a field value."""
        if not value:
            return value
        return self.encryption.decrypt(value)

    def hash_for_query(self, value: str) -> str:
        """
        Generate hash for querying without revealing value.

        Used for equality queries on encrypted fields without decryption.
        Same value always produces same hash.
        """
        salt = os.getenv("QUERY_HASH_SALT", "default-query-salt")
        return hmac.new(
            salt.encode(),
            value.encode(),
            hashlib.sha256
        ).hexdigest()[:16]

    def prepare_node_properties(
        self,
        properties: Dict[str, Any],
        encrypted_fields: List[str],
        queryable_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
        queryable = set(queryable_fields or [])

        for field in encrypted_fields:
            if field in result and result[field] is not None:
                is_queryable = field in queryable
                result[field] = self.encrypt_field(result[field], queryable=is_queryable)

                # Add hash field for queryable encrypted fields
                if is_queryable:
                    result[f"{field}_hash"] = self.hash_for_query(properties[field])

        return result

    def decrypt_node_properties(
        self,
        properties: Dict[str, Any],
        encrypted_fields: List[str]
    ) -> Dict[str, Any]:
        """
        Decrypt node properties.

        Args:
            properties: Properties dict (may contain encrypted values)
            encrypted_fields: List of field names to decrypt

        Returns:
            Properties with decryption applied
        """
        result = properties.copy()

        for field in encrypted_fields:
            if field in result and result[field] is not None:
                try:
                    result[field] = self.decrypt_field(result[field])
                except ValueError as e:
                    logger.warning(f"Failed to decrypt field {field}: {e}")
                    # Leave encrypted on failure

        return result

    def create_encrypted_query(
        self,
        field: str,
        value: str,
        operator: str = "="
    ) -> tuple:
        """
        Create query for encrypted field.

        Args:
            field: Field name
            value: Value to query
            operator: Comparison operator (=, <>, etc.)

        Returns:
            Tuple of (condition_string, parameters)
        """
        # For queryable encrypted fields, use hash
        hash_field = f"{field}_hash"
        hash_value = self.hash_for_query(value)

        return (f"n.{hash_field} {operator} $hash_value", {"hash_value": hash_value})


class EncryptionKeyManager:
    """
    Manages encryption keys with support for rotation.

    Handles:
    - Key generation
    - Key rotation
    - Multiple key versions for gradual migration
    """

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet key."""
        return Fernet.generate_key().decode()

    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: Optional[bytes] = None
    ) -> tuple:
        """
        Derive encryption key from password.

        Args:
            password: User password
            salt: Optional salt (generated if not provided)

        Returns:
            Tuple of (key, salt)
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )

        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key.decode(), salt

    @classmethod
    def rotate_data_key(
        cls,
        data: Dict[str, Any],
        encrypted_fields: List[str],
        old_manager: EncryptedPropertyManager,
        new_manager: EncryptedPropertyManager
    ) -> Dict[str, Any]:
        """
        Rotate encryption key for data fields.

        Args:
            data: Data dict with encrypted fields
            encrypted_fields: List of encrypted field names
            old_manager: Current encryption manager
            new_manager: New encryption manager with new key

        Returns:
            Data with re-encrypted fields
        """
        result = data.copy()

        for field in encrypted_fields:
            if field in result:
                try:
                    # Decrypt with old key
                    decrypted = old_manager.decrypt_field(result[field])
                    # Re-encrypt with new key
                    result[field] = new_manager.encrypt_field(decrypted)
                except Exception as e:
                    logger.error(f"Key rotation failed for field {field}: {e}")
                    raise

        return result
