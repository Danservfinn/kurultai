"""
Tokenization Service for Reversible Anonymization.

Replaces sensitive data with tokens before Neo4j storage.
Original values stored separately in secure vault.

Use cases:
- Store task descriptions with tokenized company names
- Keep original values in Kublai's encrypted file storage
- Allow reconstruction when needed by authorized agents

OWASP References:
- A02:2021-Cryptographic Failures (data protection)
"""

import uuid
import json
import hashlib
import logging
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenVaultEntry:
    """Entry in the token vault."""
    original: str
    context: str
    created_at: str
    access_count: int
    last_accessed: Optional[str] = None
    expires_at: Optional[str] = None


class TokenizationService:
    """
    Reversible tokenization for sensitive values.

    Replaces sensitive data with tokens before Neo4j storage.
    Original values stored separately in secure vault.

    Example:
        # Initialize with Redis or other vault backend
        vault = redis.Redis(host='localhost', port=6379, db=0)
        tokenizer = TokenizationService(vault, ttl_days=90)

        # Tokenize sensitive value
        token = tokenizer.tokenize("Acme Corp", context="company_name")
        # Result: "TKN:COMPANY_NAME:a1b2c3d4"

        # Store token in Neo4j (safe)
        # ...

        # Later, recover original value
        original = tokenizer.detokenize(token)
        # Result: "Acme Corp"
    """

    def __init__(
        self,
        vault_client=None,
        ttl_days: int = 90,
        token_prefix: str = "TKN"
    ):
        """
        Initialize tokenization service.

        Args:
            vault_client: Client for secure vault (Redis, HashiCorp Vault, etc.)
            ttl_days: Token expiration time in days
            token_prefix: Prefix for generated tokens
        """
        self.vault = vault_client
        self.ttl = timedelta(days=ttl_days)
        self.token_prefix = token_prefix

    def tokenize(self, value: str, context: str = "", sender_hash: str = "") -> str:
        """
        Create token for sensitive value.

        Args:
            value: Sensitive value to tokenize
            context: Context for the token (e.g., "company_name", "person_name")
            sender_hash: Sender identifier for isolation

        Returns:
            Token to store in Neo4j
        """
        if not value:
            return value

        # Generate unique token
        token_id = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}:{value}".encode()
        ).hexdigest()[:12]

        context_upper = context.upper() if context else "GENERAL"
        token = f"{self.token_prefix}:{context_upper}:{token_id}"

        # Store in vault with expiration
        if self.vault:
            vault_key = self._vault_key(token, sender_hash)
            vault_value = {
                "original": value,
                "context": context,
                "sender_hash": sender_hash,
                "created_at": datetime.utcnow().isoformat(),
                "access_count": 0,
                "expires_at": (datetime.utcnow() + self.ttl).isoformat()
            }

            try:
                self.vault.setex(
                    vault_key,
                    int(self.ttl.total_seconds()),
                    json.dumps(vault_value)
                )
            except Exception as e:
                logger.error(f"Failed to store token in vault: {e}")
                # Continue with token generation even if vault storage fails
                # The token just won't be recoverable

        return token

    def detokenize(self, token: str, sender_hash: str = "") -> Optional[str]:
        """
        Retrieve original value from token.

        Args:
            token: Token to look up
            sender_hash: Sender identifier for access control

        Returns:
            Original value or None if not found/expired
        """
        if not token or not token.startswith(self.token_prefix):
            return token  # Not a token

        if not self.vault:
            logger.warning("No vault configured for detokenization")
            return None

        vault_key = self._vault_key(token, sender_hash)
        data = self.vault.get(vault_key)

        if not data:
            logger.warning(f"Token not found or expired: {token}")
            return None

        try:
            vault_value = json.loads(data)

            # Verify sender isolation
            stored_sender = vault_value.get("sender_hash", "")
            if stored_sender and stored_sender != sender_hash:
                logger.warning(
                    f"Sender mismatch for token: {token}. "
                    f"Access denied."
                )
                return None

            # Update access metadata
            vault_value["access_count"] = vault_value.get("access_count", 0) + 1
            vault_value["last_accessed"] = datetime.utcnow().isoformat()

            # Extend expiration on access (optional - remove if not desired)
            vault_value["expires_at"] = (datetime.utcnow() + self.ttl).isoformat()

            # Update in vault with new expiration
            self.vault.setex(
                vault_key,
                int(self.ttl.total_seconds()),
                json.dumps(vault_value)
            )

            return vault_value["original"]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse vault entry: {e}")
            return None

    def _vault_key(self, token: str, sender_hash: str) -> str:
        """Generate vault storage key for token."""
        # Include sender hash in key for isolation
        if sender_hash:
            return f"token:{sender_hash}:{token}"
        return f"token:{token}"

    def batch_tokenize(
        self,
        text: str,
        entities: List[Dict],
        sender_hash: str = ""
    ) -> Tuple[str, Dict[str, str]]:
        """
        Tokenize multiple entities in text.

        Args:
            text: Original text
            entities: List of detected entities with 'type', 'value', 'start', 'end'
            sender_hash: Sender identifier

        Returns:
            Tuple of (tokenized_text, token_map)
        """
        token_map = {}
        result = text

        # Sort by position (reverse) to replace from end to start
        sorted_entities = sorted(
            entities,
            key=lambda e: e.get("start", 0),
            reverse=True
        )

        for entity in sorted_entities:
            value = entity.get("value", "")
            context = entity.get("type", "unknown")
            start = entity.get("start", 0)
            end = entity.get("end", len(text))

            if not value:
                continue

            token = self.tokenize(value, context, sender_hash)
            token_map[token] = value

            result = result[:start] + token + result[end:]

        return result, token_map

    def delete_token(self, token: str, sender_hash: str = "") -> bool:
        """
        Delete a token from the vault (GDPR right to erasure).

        Args:
            token: Token to delete
            sender_hash: Sender identifier

        Returns:
            True if deleted, False if not found
        """
        if not self.vault:
            return False

        vault_key = self._vault_key(token, sender_hash)
        result = self.vault.delete(vault_key)
        return bool(result)

    def get_token_stats(self, token: str, sender_hash: str = "") -> Optional[Dict]:
        """
        Get statistics for a token.

        Args:
            token: Token to look up
            sender_hash: Sender identifier

        Returns:
            Token statistics or None if not found
        """
        if not self.vault:
            return None

        vault_key = self._vault_key(token, sender_hash)
        data = self.vault.get(vault_key)

        if not data:
            return None

        try:
            vault_value = json.loads(data)
            return {
                "context": vault_value.get("context"),
                "created_at": vault_value.get("created_at"),
                "access_count": vault_value.get("access_count", 0),
                "last_accessed": vault_value.get("last_accessed"),
                "expires_at": vault_value.get("expires_at")
            }
        except json.JSONDecodeError:
            return None


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

    Example:
        from tools.security import (
            AnonymizationEngine,
            TokenizationService,
            FieldEncryption,
            HybridPrivacyProcessor
        )

        processor = HybridPrivacyProcessor(
            anonymizer=AnonymizationEngine(salt="..."),
            tokenizer=TokenizationService(vault_client),
            encryption=FieldEncryption(key="...")
        )

        processed, metadata = await processor.process_for_neo4j(
            {"description": "My friend Sarah's startup idea"},
            "task_metadata"
        )
        # Result: {"description": "My friend [PERSON_NAME_abc123] startup idea"}
    """

    def __init__(
        self,
        anonymizer,
        tokenizer: TokenizationService,
        encryption,
        llm_reviewer=None
    ):
        """
        Initialize hybrid privacy processor.

        Args:
            anonymizer: AnonymizationEngine instance
            tokenizer: TokenizationService instance
            encryption: FieldEncryption instance
            llm_reviewer: Optional LLMPrivacyReviewer for complex cases
        """
        self.anonymizer = anonymizer
        self.tokenizer = tokenizer
        self.encryption = encryption
        self.llm_reviewer = llm_reviewer

    async def process_for_neo4j(
        self,
        data: Dict[str, Any],
        data_type: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Process data for safe Neo4j storage.

        Args:
            data: Original data dict
            data_type: Type of data (key in PRIVACY_BOUNDARIES)

        Returns:
            Tuple of (processed_data, metadata)
        """
        from .privacy_boundary import (
            PRIVACY_BOUNDARIES,
            DataClassification,
            PrivacyBlockedError
        )

        boundary = PRIVACY_BOUNDARIES.get(data_type)
        if not boundary:
            raise ValueError(f"Unknown data type: {data_type}")

        # Check if should be blocked from Neo4j
        if boundary.storage.value == "kublai_file":
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
            if self.llm_reviewer and (
                pii_entities or
                boundary.classification in (
                    DataClassification.SENSITIVE,
                    DataClassification.PRIVATE
                )
            ):
                try:
                    review = await self.llm_reviewer.review(value)
                    if review.get("contains_pii"):
                        metadata["processing_steps"].append(
                            f"llm_review: {review.get('risk_level', 'unknown')}"
                        )
                except Exception as e:
                    logger.warning(f"LLM review failed: {e}")

            # Step 3: Apply protection based on classification
            if boundary.classification == DataClassification.PUBLIC:
                processed[field] = value

            elif boundary.classification == DataClassification.OPERATIONAL:
                # Anonymize
                anonymized, _ = self.anonymizer.anonymize(
                    value,
                    reversible=False
                )
                processed[field] = anonymized
                metadata["processing_steps"].append(f"{field}: anonymized")

            elif boundary.classification == DataClassification.SENSITIVE:
                # Tokenize for sensitive values
                if pii_entities:
                    tokenized, token_map = self.tokenizer.batch_tokenize(
                        value,
                        [
                            {
                                "type": e.entity_type,
                                "value": e.value,
                                "start": e.start,
                                "end": e.end
                            }
                            for e in pii_entities
                        ]
                    )
                    processed[field] = tokenized
                    metadata["token_map"].update(token_map)
                    metadata["processing_steps"].append(f"{field}: tokenized")
                else:
                    # Encrypt if no specific PII but still sensitive
                    processed[field] = self.encryption.encrypt_field(
                        value,
                        queryable=False
                    )
                    metadata["processing_steps"].append(f"{field}: encrypted")

            elif boundary.classification == DataClassification.PRIVATE:
                # This should have been caught earlier
                raise PrivacyBlockedError(
                    f"Field '{field}' classified as PRIVATE cannot be stored"
                )

        return processed, metadata

    def restore_from_tokens(
        self,
        data: Dict[str, Any],
        sender_hash: str = ""
    ) -> Dict[str, Any]:
        """
        Restore tokenized values in data.

        Args:
            data: Data potentially containing tokens
            sender_hash: Sender identifier for access control

        Returns:
            Data with tokens replaced by original values
        """
        result = {}

        for key, value in data.items():
            if isinstance(value, str) and value.startswith("TKN:"):
                # This is a token, detokenize
                original = self.tokenizer.detokenize(value, sender_hash)
                result[key] = original if original else value
            elif isinstance(value, str) and value.startswith("ENC:"):
                # This is encrypted, decrypt
                try:
                    result[key] = self.encryption.decrypt_field(value)
                except Exception as e:
                    logger.warning(f"Failed to decrypt field {key}: {e}")
                    result[key] = value
            else:
                result[key] = value

        return result
