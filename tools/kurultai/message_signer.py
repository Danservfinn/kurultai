"""
HMAC-SHA256 Message Signing for Kurultai System

Provides secure message signing and verification for inter-agent communication.
Uses HMAC-SHA256 with proper key management, rotation, and constant-time comparison.

Security Features:
- HMAC-SHA256 with 256-bit keys
- Constant-time signature comparison
- Key rotation support
- Message freshness validation (TTL)
- Versioned signatures

Author: Temüjin (Developer Agent)
"""

import hmac
import hashlib
import secrets
import base64
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import sys

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class SigningError(Exception):
    """Base exception for signing errors."""
    pass


class VerificationError(SigningError):
    """Exception for verification failures."""
    pass


class KeyError(SigningError):
    """Exception for key-related errors."""
    pass


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SignatureResult:
    """Result of a signing operation."""
    signature: str
    timestamp: str
    key_id: str
    version: str
    signed_message: Optional[Dict[str, Any]] = None  # Full message that was signed


@dataclass
class VerificationResult:
    """Result of a verification operation."""
    is_valid: bool
    reason: str
    timestamp: Optional[datetime] = None
    key_id: Optional[str] = None
    message_age_seconds: Optional[float] = None


@dataclass
class KeyInfo:
    """Information about a signing key."""
    key_id: str
    created_at: str
    algorithm: str
    is_current: bool = False


# =============================================================================
# Message Signer
# =============================================================================

class MessageSigner:
    """
    HMAC-SHA256 message signer with key rotation support.
    
    Features:
    - Deterministic JSON canonicalization for signing
    - Automatic timestamp injection
    - Versioned signatures
    - Configurable TTL
    """
    
    ALGORITHM = "sha256"
    SIGNATURE_VERSION = "v1"
    SIGNATURE_SEPARATOR = "."
    DEFAULT_TTL_SECONDS = 300  # 5 minutes
    
    def __init__(
        self,
        primary_key: Optional[bytes] = None,
        signature_ttl_seconds: int = DEFAULT_TTL_SECONDS
    ):
        """
        Initialize the MessageSigner.
        
        Args:
            primary_key: Primary signing key (generates if not provided)
            signature_ttl_seconds: Signature time-to-live in seconds
        """
        self.keys: Dict[str, bytes] = {}
        self.key_rotations: List[Dict[str, Any]] = []
        self.signature_ttl_seconds = signature_ttl_seconds
        
        # Initialize with primary key
        if primary_key:
            self.keys["current"] = primary_key
        else:
            self.keys["current"] = self._generate_key()
    
    @staticmethod
    def _generate_key() -> bytes:
        """Generate a new 256-bit key."""
        return secrets.token_bytes(32)
    
    def _canonicalize(self, message: Dict[str, Any]) -> bytes:
        """
        Canonicalize message for signing.
        
        Uses sorted keys and compact JSON to ensure deterministic serialization.
        """
        canonical = json.dumps(message, sort_keys=True, separators=(',', ':'))
        return canonical.encode('utf-8')
    
    def sign(
        self,
        message: Dict[str, Any],
        key_id: str = "current",
        add_timestamp: bool = True
    ) -> SignatureResult:
        """
        Sign a message.
        
        Args:
            message: Message dictionary to sign
            key_id: Key ID to use for signing
            add_timestamp: Whether to add timestamp if missing
        
        Returns:
            SignatureResult with signature and metadata
        
        Raises:
            KeyError: If key_id is not found
        """
        if key_id not in self.keys:
            raise KeyError(f"Unknown key ID: {key_id}")
        
        # Add timestamp if needed
        if add_timestamp and "timestamp" not in message:
            message = {**message, "timestamp": datetime.now(timezone.utc).isoformat()}
        
        # Canonicalize message
        message_bytes = self._canonicalize(message)
        
        # Create signature
        key = self.keys[key_id]
        signature = hmac.new(
            key,
            message_bytes,
            hashlib.sha256
        ).digest()
        
        # Encode: version.key_id.base64_signature
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        full_signature = f"{self.SIGNATURE_VERSION}{self.SIGNATURE_SEPARATOR}{key_id}{self.SIGNATURE_SEPARATOR}{signature_b64}"
        
        # Create result with full signed message for verification
        result = SignatureResult(
            signature=full_signature,
            timestamp=message.get("timestamp", datetime.now(timezone.utc).isoformat()),
            key_id=key_id,
            version=self.SIGNATURE_VERSION,
            signed_message=message if add_timestamp else None
        )
        
        return result
    
    def verify(self, message: Dict[str, Any], signature: str) -> VerificationResult:
        """
        Verify a message signature.
        
        Args:
            message: Message dictionary to verify
            signature: Signature string
        
        Returns:
            VerificationResult with validation status
        """
        try:
            # Parse signature
            version, key_id, signature_b64 = signature.split(self.SIGNATURE_SEPARATOR)
            
            # Check version
            if version != self.SIGNATURE_VERSION:
                return VerificationResult(
                    is_valid=False,
                    reason=f"Unsupported signature version: {version}"
                )
            
            # Check key exists
            if key_id not in self.keys:
                return VerificationResult(
                    is_valid=False,
                    reason=f"Unknown key ID: {key_id}"
                )
            
            # Check freshness if timestamp present
            timestamp = None
            message_age = None
            
            if "timestamp" in message:
                timestamp_str = message["timestamp"]
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    is_fresh, reason = self._check_freshness(timestamp)
                    if not is_fresh:
                        return VerificationResult(
                            is_valid=False,
                            reason=reason,
                            timestamp=timestamp,
                            key_id=key_id
                        )
                    message_age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                except ValueError as e:
                    return VerificationResult(
                        is_valid=False,
                        reason=f"Invalid timestamp: {e}",
                        key_id=key_id
                    )
            
            # Recompute signature
            message_bytes = self._canonicalize(message)
            key = self.keys[key_id]
            expected_sig = hmac.new(
                key,
                message_bytes,
                hashlib.sha256
            ).digest()
            
            # Add padding for decoding
            padding_needed = 4 - len(signature_b64) % 4
            if padding_needed != 4:
                signature_b64 += "=" * padding_needed
            
            # Decode provided signature
            try:
                provided_sig = base64.urlsafe_b64decode(signature_b64)
            except Exception as e:
                return VerificationResult(
                    is_valid=False,
                    reason=f"Invalid signature encoding: {e}",
                    timestamp=timestamp,
                    key_id=key_id,
                    message_age_seconds=message_age
                )
            
            # Constant-time comparison (prevents timing attacks)
            if not hmac.compare_digest(expected_sig, provided_sig):
                # If verification failed and we have archived keys, try those
                archived = getattr(self, '_archived_keys', {})
                if key_id in archived:
                    archived_key = archived[key_id]
                    expected_sig_archived = hmac.new(
                        archived_key,
                        message_bytes,
                        hashlib.sha256
                    ).digest()
                    if hmac.compare_digest(expected_sig_archived, provided_sig):
                        return VerificationResult(
                            is_valid=True,
                            reason="Valid (archived key)",
                            timestamp=timestamp,
                            key_id=key_id,
                            message_age_seconds=message_age
                        )
                return VerificationResult(
                    is_valid=False,
                    reason="Signature mismatch",
                    timestamp=timestamp,
                    key_id=key_id,
                    message_age_seconds=message_age
                )
            
            return VerificationResult(
                is_valid=True,
                reason="Valid",
                timestamp=timestamp,
                key_id=key_id,
                message_age_seconds=message_age
            )
            
        except ValueError as e:
            return VerificationResult(
                is_valid=False,
                reason=f"Invalid signature format: {str(e)}"
            )
        except Exception as e:
            return VerificationResult(
                is_valid=False,
                reason=f"Verification error: {str(e)}"
            )
    
    def _check_freshness(self, timestamp: datetime) -> Tuple[bool, str]:
        """
        Check if message is within TTL.
        
        Args:
            timestamp: Message timestamp
        
        Returns:
            Tuple of (is_fresh, reason)
        """
        now = datetime.now(timezone.utc)
        
        if timestamp.tzinfo is None:
            # Assume UTC if no timezone
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        age = (now - timestamp).total_seconds()
        
        if age < 0:
            return False, "Future timestamp"
        
        if age > self.signature_ttl_seconds:
            return False, f"Message too old ({age:.0f}s > {self.signature_ttl_seconds}s)"
        
        return True, "Fresh"
    
    def rotate_key(self) -> str:
        """
        Rotate to a new signing key.
        
        Archives the current key and generates a new one.
        Old signatures remain verifiable.
        
        Returns:
            New key ID
        """
        new_key = self._generate_key()
        new_key_id = f"key_{int(time.time())}"
        
        # Archive current key with timestamp to make it unique
        if "current" in self.keys:
            archive_id = f"archive_{int(time.time() * 1000)}"  # Use milliseconds for uniqueness
            old_key = self.keys["current"]
            self.keys[archive_id] = old_key
            # Also store under the key_id that was used for signing (to preserve old signatures)
            # We keep "current" pointing to the new key, but archived keys are available
            self._archived_keys = getattr(self, '_archived_keys', {})
            self._archived_keys["current"] = old_key  # Save what "current" was
            self.key_rotations.append({
                "from": "current",
                "to": new_key_id,
                "archived_as": archive_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        # Set new key - "current" now points to new key
        self.keys["current"] = new_key
        self.keys[new_key_id] = new_key
        
        logger.info(f"Key rotated. New key ID: {new_key_id}")
        return new_key_id
    
    def add_key(self, key_id: str, key: bytes) -> None:
        """
        Add a key for verifying legacy signatures.
        
        Args:
            key_id: Key identifier
            key: Key bytes
        """
        self.keys[key_id] = key
        logger.debug(f"Added key: {key_id}")
    
    def remove_key(self, key_id: str) -> bool:
        """
        Remove a key.
        
        Args:
            key_id: Key identifier to remove
        
        Returns:
            True if key was removed
        """
        if key_id == "current":
            logger.warning("Cannot remove current key")
            return False
        
        if key_id in self.keys:
            del self.keys[key_id]
            logger.info(f"Removed key: {key_id}")
            return True
        
        return False
    
    def get_key_info(self) -> List[KeyInfo]:
        """
        Get information about configured keys.
        
        Returns:
            List of KeyInfo objects
        """
        info = []
        
        for key_id in self.keys:
            # Find creation time from rotations if available
            created_at = datetime.now(timezone.utc).isoformat()
            for rotation in self.key_rotations:
                if rotation.get("to") == key_id:
                    created_at = rotation.get("timestamp", created_at)
            
            info.append(KeyInfo(
                key_id=key_id,
                created_at=created_at,
                algorithm=self.ALGORITHM,
                is_current=(key_id == "current")
            ))
        
        return info
    
    def get_rotations(self) -> List[Dict[str, Any]]:
        """Get key rotation history."""
        return self.key_rotations.copy()


# =============================================================================
# Message Verifier
# =============================================================================

class MessageVerifier:
    """
    Standalone message verifier.
    
    Used by agents that only need to verify signatures, not create them.
    """
    
    def __init__(self, signer: Optional[MessageSigner] = None):
        """
        Initialize verifier.
        
        Args:
            signer: MessageSigner instance to use for verification
        """
        self.signer = signer or MessageSigner()
    
    def verify(self, message: Dict[str, Any], signature: str) -> VerificationResult:
        """
        Verify a message signature.
        
        Args:
            message: Message to verify
            signature: Signature string
        
        Returns:
            VerificationResult
        """
        return self.signer.verify(message, signature)
    
    def add_key(self, key_id: str, key: bytes) -> None:
        """Add a verification key."""
        self.signer.add_key(key_id, key)


# =============================================================================
# Key Store
# =============================================================================

class KeyStore:
    """
    Secure key storage for agent keys.
    
    Manages keys per agent with:
    - Secure key generation
    - Key persistence (with proper permissions)
    - Key rotation tracking
    - Cross-agent key sharing (for verification)
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize key store.
        
        Args:
            storage_path: Path to store keys (default: ~/.kurultai/keys)
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path.home() / ".kurultai" / "keys"
        
        self._keys: Dict[str, bytes] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        
        # Ensure storage directory exists with proper permissions
        self._ensure_storage()
    
    def _ensure_storage(self) -> None:
        """Ensure storage directory exists with secure permissions."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Set restrictive permissions (owner only)
        os.chmod(self.storage_path, 0o700)
    
    def generate_key(self, agent_id: str) -> bytes:
        """
        Generate a new key for an agent.
        
        Args:
            agent_id: Agent identifier
        
        Returns:
            New key bytes
        """
        key = secrets.token_bytes(32)
        self._keys[agent_id] = key
        self._metadata[agent_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rotated_from": None
        }
        
        logger.info(f"Generated key for agent: {agent_id}")
        return key
    
    def get_key(self, agent_id: str) -> Optional[bytes]:
        """
        Get key for an agent.
        
        Args:
            agent_id: Agent identifier
        
        Returns:
            Key bytes or None if not found
        """
        return self._keys.get(agent_id)
    
    def rotate_key(self, agent_id: str) -> bytes:
        """
        Rotate key for an agent.
        
        Args:
            agent_id: Agent identifier
        
        Returns:
            New key bytes
        """
        old_key = self._keys.get(agent_id)
        new_key = secrets.token_bytes(32)
        
        self._keys[agent_id] = new_key
        self._metadata[agent_id] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rotated_from": old_key.hex()[:16] + "..." if old_key else None
        }
        
        logger.info(f"Rotated key for agent: {agent_id}")
        return new_key
    
    def list_agents(self) -> List[str]:
        """List all agents with keys."""
        return list(self._keys.keys())
    
    def get_metadata(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for an agent's key."""
        return self._metadata.get(agent_id)
    
    def save_to_file(self, filename: Optional[str] = None) -> str:
        """
        Save keys to file (encrypted format recommended for production).
        
        Args:
            filename: Output filename
        
        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"keystore_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.storage_path / filename
        
        # NOTE: In production, encrypt this file!
        data = {
            "agents": {
                agent_id: {
                    "key": key.hex(),
                    "metadata": self._metadata.get(agent_id, {})
                }
                for agent_id, key in self._keys.items()
            },
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Set restrictive permissions
        os.chmod(filepath, 0o600)
        
        logger.info(f"Saved keystore to: {filepath}")
        return str(filepath)
    
    def load_from_file(self, filepath: str) -> bool:
        """
        Load keys from file.
        
        Args:
            filepath: Path to key file
        
        Returns:
            True if successful
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            for agent_id, agent_data in data.get("agents", {}).items():
                key_hex = agent_data.get("key")
                if key_hex:
                    self._keys[agent_id] = bytes.fromhex(key_hex)
                    self._metadata[agent_id] = agent_data.get("metadata", {})
            
            logger.info(f"Loaded keystore from: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to load keystore: {e}")
            return False


# =============================================================================
# Agent Message Signer (High-level interface)
# =============================================================================

class AgentMessageSigner:
    """
    High-level interface for agent-to-agent message signing.
    
    Combines MessageSigner and KeyStore for easy agent integration.
    """
    
    AGENT_MAPPING = {
        "main": "Kublai",
        "researcher": "Möngke",
        "writer": "Chagatai",
        "developer": "Temüjin",
        "analyst": "Jochi",
        "ops": "Ögedei",
        "kublai": "main",
        "mongke": "researcher",
        "chagatai": "writer",
        "temujin": "developer",
        "jochi": "analyst",
        "ogedei": "ops"
    }
    
    def __init__(
        self,
        agent_id: str,
        keystore: Optional[KeyStore] = None,
        signature_ttl: int = 300
    ):
        """
        Initialize agent message signer.
        
        Args:
            agent_id: Agent identifier
            keystore: KeyStore instance (creates default if not provided)
            signature_ttl: Signature TTL in seconds
        """
        self.agent_id = agent_id
        self.keystore = keystore or KeyStore()
        
        # Get or generate key for this agent
        key = self.keystore.get_key(agent_id)
        if not key:
            key = self.keystore.generate_key(agent_id)
        
        self.signer = MessageSigner(primary_key=key, signature_ttl_seconds=signature_ttl)
    
    def sign_message(
        self,
        message: Dict[str, Any],
        to_agent: Optional[str] = None
    ) -> SignatureResult:
        """
        Sign an agent-to-agent message.
        
        Args:
            message: Message content
            to_agent: Target agent ID
        
        Returns:
            SignatureResult with signed_message field containing the full message that was signed
        """
        # Add agent metadata
        message_to_sign = {
            **message,
            "from_agent": self.agent_id,
            "signed_at": datetime.now(timezone.utc).isoformat()
        }
        
        if to_agent:
            message_to_sign["to_agent"] = to_agent
        
        result = self.signer.sign(message_to_sign)
        
        # Return result with the full signed message for verification
        return result
    
    def verify_message(
        self,
        message: Dict[str, Any],
        signature: str,
        from_agent: Optional[str] = None
    ) -> VerificationResult:
        """
        Verify an agent message.
        
        Args:
            message: Full message dict that was signed (including from_agent, signed_at, timestamp)
            signature: Signature string
            from_agent: Expected sender agent ID
        
        Returns:
            VerificationResult
        """
        result = self.signer.verify(message, signature)
        
        # Additional validation if from_agent specified
        if from_agent and result.is_valid:
            msg_from = message.get("from_agent")
            if msg_from and msg_from != from_agent:
                return VerificationResult(
                    is_valid=False,
                    reason=f"Agent mismatch: expected {from_agent}, got {msg_from}",
                    timestamp=result.timestamp,
                    key_id=result.key_id
                )
        
        return result
    
    def add_trusted_key(self, agent_id: str, key: bytes) -> None:
        """Add a trusted key for another agent."""
        self.signer.add_key(agent_id, key)
        self.keystore._keys[agent_id] = key
    
    def rotate_key(self) -> str:
        """Rotate this agent's signing key."""
        new_key_id = self.signer.rotate_key()
        self.keystore._keys[self.agent_id] = self.signer.keys["current"]
        return new_key_id


# =============================================================================
# Convenience functions
# =============================================================================

def create_signed_message(
    content: Dict[str, Any],
    key: Optional[bytes] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Create a signed message.
    
    Args:
        content: Message content
        key: Signing key (generates if not provided)
    
    Returns:
        Tuple of (message with metadata, signature)
    """
    signer = MessageSigner(primary_key=key)
    
    message = {
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "msg_id": secrets.token_hex(8)
    }
    
    result = signer.sign(message)
    
    return message, result.signature


def verify_signed_message(
    message: Dict[str, Any],
    signature: str,
    key: Optional[bytes] = None
) -> bool:
    """
    Verify a signed message.
    
    Args:
        message: Message dictionary
        signature: Signature string
        key: Verification key (creates default if not provided)
    
    Returns:
        True if valid
    """
    signer = MessageSigner(primary_key=key)
    result = signer.verify(message, signature)
    return result.is_valid


# =============================================================================
# Example usage
# =============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("Message Signing Demo")
    print("=" * 60)
    
    # Create signer
    signer = MessageSigner()
    
    # Create a message
    message = {
        "msg_type": "task_assignment",
        "task_id": "task-12345",
        "from_agent": "kublai",
        "to_agent": "temujin",
        "payload": {
            "description": "Implement OAuth",
            "priority": "high"
        }
    }
    
    print(f"\nOriginal message:")
    print(json.dumps(message, indent=2))
    
    # Sign the message
    result = signer.sign(message)
    print(f"\nSignature: {result.signature}")
    print(f"Timestamp: {result.timestamp}")
    print(f"Key ID: {result.key_id}")
    
    # Verify the message
    verify_result = signer.verify(message, result.signature)
    print(f"\nVerification: {'✓ VALID' if verify_result.is_valid else '✗ INVALID'}")
    print(f"Reason: {verify_result.reason}")
    
    # Tamper with message
    print("\n--- Tampering Detection ---")
    tampered_message = message.copy()
    tampered_message["payload"]["priority"] = "critical"
    
    tamper_result = signer.verify(tampered_message, result.signature)
    print(f"Tampered message verification: {'✓ VALID' if tamper_result.is_valid else '✗ INVALID'}")
    print(f"Reason: {tamper_result.reason}")
    
    # Key rotation demo
    print("\n--- Key Rotation ---")
    old_key_id = result.key_id
    new_key_id = signer.rotate_key()
    print(f"Rotated from {old_key_id} to {new_key_id}")
    
    # Old signature still validates
    old_verify = signer.verify(message, result.signature)
    print(f"Old signature still valid: {'✓ YES' if old_verify.is_valid else '✗ NO'}")
    
    # New signatures use new key
    new_message = {"test": "data"}
    new_result = signer.sign(new_message)
    print(f"New signature uses key: {new_result.key_id}")
    
    # Agent signer demo
    print("\n--- Agent Message Signer ---")
    agent_signer = AgentMessageSigner(agent_id="temujin")
    
    agent_message = {
        "action": "task_complete",
        "task_id": "task-67890",
        "result": "success"
    }
    
    agent_result = agent_signer.sign_message(agent_message, to_agent="kublai")
    print(f"Agent message signed: {agent_result.signature[:50]}...")
    
    agent_verify = agent_signer.verify_message(
        {**agent_message, "from_agent": "temujin"},
        agent_result.signature
    )
    print(f"Agent verification: {'✓ VALID' if agent_verify.is_valid else '✗ INVALID'}")
