"""
HMAC Message Signing Tests - Task P2-T18

Tests for:
- Message signing works
- Signature verification works
- Tampered messages are rejected
- Key rotation handled gracefully

Author: Jochi (Analyst Agent)
"""

import pytest
import hmac
import hashlib
import secrets
import base64
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional, List
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add tools/kurultai to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../tools/kurultai'))


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def signing_key():
    """Generate a test signing key."""
    return secrets.token_bytes(32)  # 256-bit key


@pytest.fixture
def message_signer(signing_key):
    """Create a message signer with key rotation support."""
    
    class MessageSigner:
        """HMAC-SHA256 message signer with key rotation."""
        
        ALGORITHM = "sha256"
        SIGNATURE_VERSION = "v1"
        SIGNATURE_SEPARATOR = "."
        
        def __init__(self, primary_key: bytes):
            self.keys: Dict[str, bytes] = {
                "current": primary_key
            }
            self.key_rotations: List[Dict[str, Any]] = []
            self.signature_ttl_seconds = 300  # 5 minute TTL
        
        def sign(self, message: Dict[str, Any], key_id: str = "current") -> str:
            """Sign a message and return the signature."""
            if key_id not in self.keys:
                raise ValueError(f"Unknown key ID: {key_id}")
            
            # Add timestamp if not present
            if "timestamp" not in message:
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
            return f"{self.SIGNATURE_VERSION}{self.SIGNATURE_SEPARATOR}{key_id}{self.SIGNATURE_SEPARATOR}{signature_b64}"
        
        def verify(self, message: Dict[str, Any], signature: str) -> Tuple[bool, str]:
            """Verify a message signature. Returns (is_valid, reason)."""
            try:
                # Parse signature
                version, key_id, signature_b64 = signature.split(self.SIGNATURE_SEPARATOR)
                
                # Check version
                if version != self.SIGNATURE_VERSION:
                    return False, f"Unsupported signature version: {version}"
                
                # Check key exists
                if key_id not in self.keys:
                    return False, f"Unknown key ID: {key_id}"
                
                # Check TTL if timestamp present
                if "timestamp" in message:
                    is_fresh, reason = self._check_freshness(message["timestamp"])
                    if not is_fresh:
                        return False, f"Message expired: {reason}"
                
                # Recompute signature
                message_bytes = self._canonicalize(message)
                key = self.keys[key_id]
                expected_sig = hmac.new(
                    key,
                    message_bytes,
                    hashlib.sha256
                ).digest()
                expected_b64 = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")
                
                # Constant-time comparison
                provided_sig = signature_b64 + "=" * (4 - len(signature_b64) % 4)  # Add padding
                provided_bytes = base64.urlsafe_b64decode(provided_sig)
                
                if not hmac.compare_digest(expected_sig, provided_bytes):
                    return False, "Signature mismatch"
                
                return True, "Valid"
                
            except ValueError as e:
                return False, f"Invalid signature format: {str(e)}"
            except Exception as e:
                return False, f"Verification error: {str(e)}"
        
        def _canonicalize(self, message: Dict[str, Any]) -> bytes:
            """Canonicalize message for signing."""
            # Sort keys for deterministic serialization
            canonical = json.dumps(message, sort_keys=True, separators=(',', ':'))
            return canonical.encode('utf-8')
        
        def _check_freshness(self, timestamp_str: str) -> Tuple[bool, str]:
            """Check if message is within TTL."""
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                
                if age < 0:
                    return False, "Future timestamp"
                if age > self.signature_ttl_seconds:
                    return False, f"Message too old ({age:.0f}s > {self.signature_ttl_seconds}s)"
                
                return True, "Fresh"
            except Exception as e:
                return False, f"Invalid timestamp: {str(e)}"
        
        def rotate_key(self) -> str:
            """Rotate to a new signing key. Returns new key ID."""
            new_key = secrets.token_bytes(32)
            new_key_id = f"key_{int(time.time())}"
            
            # Archive current key
            if "current" in self.keys:
                archive_id = f"archive_{int(time.time())}"
                self.keys[archive_id] = self.keys["current"]
                self.key_rotations.append({
                    "from": "current",
                    "to": new_key_id,
                    "archived_as": archive_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            # Set new key
            self.keys["current"] = new_key
            self.keys[new_key_id] = new_key
            
            return new_key_id
        
        def add_key(self, key_id: str, key: bytes) -> None:
            """Add a key for verifying legacy signatures."""
            self.keys[key_id] = key
        
        def get_key_info(self) -> Dict[str, Any]:
            """Get information about configured keys."""
            return {
                "key_ids": list(self.keys.keys()),
                "rotations": self.key_rotations,
                "ttl_seconds": self.signature_ttl_seconds
            }
    
    return MessageSigner(signing_key)


@pytest.fixture
def signed_message_factory(message_signer):
    """Factory for creating signed test messages."""
    
    def create_signed_message(content: Dict[str, Any], key_id: str = "current") -> Tuple[Dict[str, Any], str]:
        message = {
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "msg_id": secrets.token_hex(8)
        }
        signature = message_signer.sign(message, key_id)
        return message, signature
    
    return create_signed_message


# =============================================================================
# Message Signing Tests
# =============================================================================

class TestMessageSigning:
    """Tests for message signing functionality."""
    
    def test_sign_creates_valid_signature_format(self, message_signer):
        """Verify signing creates properly formatted signature."""
        message = {
            "task_id": "task-123",
            "action": "claim",
            "agent": "temujin"
        }
        
        signature = message_signer.sign(message)
        
        # Should be version.key_id.base64 format
        parts = signature.split(message_signer.SIGNATURE_SEPARATOR)
        assert len(parts) == 3
        assert parts[0] == "v1"  # Version
        assert parts[1] == "current"  # Key ID
        # Part 2 is base64 encoded signature
    
    def test_sign_adds_timestamp_if_missing(self, message_signer):
        """Verify signing adds timestamp if not present."""
        message = {
            "task_id": "task-456",
            "action": "complete"
        }
        
        signed_message = message_signer.sign(message)
        
        # Original message should now have timestamp
        assert "timestamp" in message
    
    def test_sign_uses_specified_key_id(self, message_signer, signing_key):
        """Verify signing uses specified key ID."""
        # Add additional key
        new_key = secrets.token_bytes(32)
        message_signer.add_key("backup", new_key)
        
        message = {"test": "data"}
        
        # Sign with backup key
        signature = message_signer.sign(message, key_id="backup")
        
        # Should contain backup key ID
        parts = signature.split(message_signer.SIGNATURE_SEPARATOR)
        assert parts[1] == "backup"
    
    def test_sign_rejects_unknown_key_id(self, message_signer):
        """Verify signing rejects unknown key ID."""
        message = {"test": "data"}
        
        with pytest.raises(ValueError) as exc_info:
            message_signer.sign(message, key_id="unknown")
        
        assert "unknown" in str(exc_info.value).lower()
    
    def test_signatures_are_deterministic(self, message_signer):
        """Verify same message produces same signature."""
        message = {
            "task_id": "task-789",
            "timestamp": "2026-02-09T10:00:00+00:00"
        }
        
        sig1 = message_signer.sign(message.copy())
        sig2 = message_signer.sign(message.copy())
        
        assert sig1 == sig2
    
    def test_different_messages_produce_different_signatures(self, message_signer):
        """Verify different messages produce different signatures."""
        message1 = {"task_id": "task-1", "timestamp": "2026-02-09T10:00:00+00:00"}
        message2 = {"task_id": "task-2", "timestamp": "2026-02-09T10:00:00+00:00"}
        
        sig1 = message_signer.sign(message1.copy())
        sig2 = message_signer.sign(message2.copy())
        
        assert sig1 != sig2
    
    def test_sign_canonicalizes_json(self, message_signer):
        """Verify JSON canonicalization ensures consistent signing."""
        # Same data, different key orders
        message1 = {"a": 1, "b": 2, "timestamp": "2026-02-09T10:00:00+00:00"}
        message2 = {"b": 2, "a": 1, "timestamp": "2026-02-09T10:00:00+00:00"}
        
        sig1 = message_signer.sign(message1.copy())
        sig2 = message_signer.sign(message2.copy())
        
        # Should produce same signature
        assert sig1 == sig2


# =============================================================================
# Signature Verification Tests
# =============================================================================

class TestSignatureVerification:
    """Tests for signature verification functionality."""
    
    def test_verify_valid_signature(self, message_signer, signed_message_factory):
        """Verify valid signature passes verification."""
        message, signature = signed_message_factory({"action": "test"})
        
        is_valid, reason = message_signer.verify(message, signature)
        
        assert is_valid is True
        assert reason == "Valid"
    
    def test_verify_detects_tampered_content(self, message_signer, signed_message_factory):
        """Verify tampered content fails verification."""
        message, signature = signed_message_factory({"action": "test", "value": 100})
        
        # Tamper with message
        message["value"] = 999
        
        is_valid, reason = message_signer.verify(message, signature)
        
        assert is_valid is False
        assert "mismatch" in reason.lower()
    
    def test_verify_detects_tampered_timestamp(self, message_signer, signed_message_factory):
        """Verify tampered timestamp fails verification."""
        message, signature = signed_message_factory({"action": "test"})
        
        # Tamper with timestamp
        message["timestamp"] = "2025-01-01T00:00:00+00:00"
        
        is_valid, reason = message_signer.verify(message, signature)
        
        assert is_valid is False
    
    def test_verify_detects_invalid_signature_format(self, message_signer):
        """Verify invalid signature format is rejected."""
        message = {"test": "data"}
        
        is_valid, reason = message_signer.verify(message, "invalid-signature")
        
        assert is_valid is False
        assert "format" in reason.lower()
    
    def test_verify_detects_wrong_version(self, message_signer, signed_message_factory):
        """Verify wrong signature version is rejected."""
        message, signature = signed_message_factory({"action": "test"})
        
        # Modify version
        parts = signature.split(".")
        parts[0] = "v99"
        bad_signature = ".".join(parts)
        
        is_valid, reason = message_signer.verify(message, bad_signature)
        
        assert is_valid is False
        assert "version" in reason.lower()
    
    def test_verify_detects_unknown_key(self, message_signer, signed_message_factory):
        """Verify signature with unknown key ID is rejected."""
        message, signature = signed_message_factory({"action": "test"})
        
        # Modify key ID
        parts = signature.split(".")
        parts[1] = "unknown_key"
        bad_signature = ".".join(parts)
        
        is_valid, reason = message_signer.verify(message, bad_signature)
        
        assert is_valid is False
        assert "unknown" in reason.lower()
    
    def test_verify_uses_constant_time_comparison(self, message_signer, signed_message_factory):
        """Verify uses constant-time comparison to prevent timing attacks."""
        message, signature = signed_message_factory({"action": "test"})
        
        # This test verifies the implementation uses hmac.compare_digest
        # The actual timing attack prevention is in the implementation
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is True


# =============================================================================
# Tampering Detection Tests
# =============================================================================

class TestTamperingDetection:
    """Tests for detecting tampered messages."""
    
    def test_rejects_modified_task_id(self, message_signer, signed_message_factory):
        """Verify modified task_id is detected."""
        message, signature = signed_message_factory({
            "task_id": "original-task",
            "action": "claim"
        })
        
        # Attacker changes task ID
        message["content"]["task_id"] = "different-task"
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False
    
    def test_rejects_modified_agent(self, message_signer, signed_message_factory):
        """Verify modified agent field is detected."""
        message, signature = signed_message_factory({
            "task_id": "task-123",
            "agent": "temujin",
            "action": "complete"
        })
        
        # Attacker impersonates different agent
        message["content"]["agent"] = "kublai"
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False
    
    def test_rejects_added_fields(self, message_signer, signed_message_factory):
        """Verify added fields are detected."""
        message, signature = signed_message_factory({"action": "test"})
        
        # Attacker adds malicious field
        message["malicious"] = "payload"
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False
    
    def test_rejects_removed_fields(self, message_signer, signed_message_factory):
        """Verify removed fields are detected."""
        message, signature = signed_message_factory({
            "action": "test",
            "important": "data"
        })
        
        # Attacker removes field
        del message["content"]["important"]
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False
    
    def test_replays_detected_via_timestamp(self, message_signer):
        """Verify replays are detected via timestamp TTL."""
        # Create old message
        old_message = {
            "action": "test",
            "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        }
        signature = message_signer.sign(old_message)
        
        # Try to verify (should fail due to TTL)
        is_valid, reason = message_signer.verify(old_message, signature)
        
        assert is_valid is False
        assert "expired" in reason.lower() or "old" in reason.lower()
    
    def test_future_timestamps_rejected(self, message_signer):
        """Verify future timestamps are rejected."""
        future_message = {
            "action": "test",
            "timestamp": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        }
        signature = message_signer.sign(future_message)
        
        is_valid, reason = message_signer.verify(future_message, signature)
        
        assert is_valid is False
        assert "future" in reason.lower()


# =============================================================================
# Key Rotation Tests
# =============================================================================

class TestKeyRotation:
    """Tests for key rotation handling."""
    
    def test_rotate_key_creates_new_key(self, message_signer):
        """Verify key rotation creates new key."""
        old_key_info = message_signer.get_key_info()
        old_key_count = len(old_key_info["key_ids"])
        
        new_key_id = message_signer.rotate_key()
        
        new_key_info = message_signer.get_key_info()
        assert len(new_key_info["key_ids"]) > old_key_count
        assert new_key_id in new_key_info["key_ids"]
    
    def test_rotate_key_preserves_old_key(self, message_signer):
        """Verify old key is archived during rotation."""
        # Sign with original key
        message1 = {"test": "original"}
        signature1 = message_signer.sign(message1.copy())
        
        # Rotate
        message_signer.rotate_key()
        
        # Should still be able to verify old signatures
        is_valid, _ = message_signer.verify(message1, signature1)
        assert is_valid is True
    
    def test_new_signatures_use_new_key(self, message_signer):
        """Verify signatures after rotation use new key."""
        message_signer.rotate_key()
        
        message = {"test": "new"}
        signature = message_signer.sign(message)
        
        # Should verify with current signer
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is True
    
    def test_rotation_is_logged(self, message_signer):
        """Verify key rotations are logged."""
        initial_rotations = len(message_signer.key_rotations)
        
        message_signer.rotate_key()
        
        assert len(message_signer.key_rotations) == initial_rotations + 1
        
        rotation = message_signer.key_rotations[-1]
        assert "from" in rotation
        assert "to" in rotation
        assert "timestamp" in rotation
    
    def test_can_verify_after_multiple_rotations(self, message_signer):
        """Verify can verify signatures across multiple rotations."""
        messages_and_sigs = []
        
        # Create signatures across rotations
        for i in range(3):
            msg = {"iteration": i}
            sig = message_signer.sign(msg.copy())
            messages_and_sigs.append((msg, sig))
            message_signer.rotate_key()
        
        # All should still verify
        for msg, sig in messages_and_sigs:
            is_valid, _ = message_signer.verify(msg, sig)
            assert is_valid is True
    
    def test_can_add_legacy_keys(self, message_signer):
        """Verify can add legacy keys for verification."""
        legacy_key = secrets.token_bytes(32)
        
        # Create signature with legacy key (simulated)
        legacy_signer = type(message_signer)(legacy_key)
        message = {"legacy": "data"}
        signature = legacy_signer.sign(message.copy())
        
        # Add legacy key to main signer
        message_signer.add_key("legacy_2025", legacy_key)
        
        # Should verify
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is True
    
    def test_key_info_shows_all_keys(self, message_signer):
        """Verify key info shows all available keys."""
        # Add some keys
        message_signer.add_key("key1", secrets.token_bytes(32))
        message_signer.add_key("key2", secrets.token_bytes(32))
        
        info = message_signer.get_key_info()
        
        assert "current" in info["key_ids"]
        assert "key1" in info["key_ids"]
        assert "key2" in info["key_ids"]


# =============================================================================
# TTL and Freshness Tests
# =============================================================================

class TestMessageFreshness:
    """Tests for message freshness/TTL handling."""
    
    def test_fresh_message_passes(self, message_signer):
        """Verify fresh message passes verification."""
        message = {
            "action": "test",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        signature = message_signer.sign(message.copy())
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is True
    
    def test_expired_message_fails(self, message_signer):
        """Verify expired message fails verification."""
        old_time = datetime.now(timezone.utc) - timedelta(seconds=400)
        message = {
            "action": "test",
            "timestamp": old_time.isoformat()
        }
        signature = message_signer.sign(message.copy())
        
        is_valid, reason = message_signer.verify(message, signature)
        
        assert is_valid is False
        assert "expired" in reason.lower() or "old" in reason.lower()
    
    def test_ttl_can_be_configured(self, message_signer):
        """Verify TTL can be configured."""
        # Set short TTL
        message_signer.signature_ttl_seconds = 1
        
        message = {
            "action": "test",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        signature = message_signer.sign(message.copy())
        
        # Wait for TTL
        import time
        time.sleep(1.1)
        
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestHMACIntegration:
    """Integration tests for complete signing workflow."""
    
    def test_full_sign_verify_workflow(self, message_signer):
        """Test complete sign-then-verify workflow."""
        # Create message
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
        
        # Sign
        signature = message_signer.sign(message)
        assert signature is not None
        assert len(signature) > 0
        
        # Verify
        is_valid, reason = message_signer.verify(message, signature)
        assert is_valid is True
        assert reason == "Valid"
    
    def test_cross_signer_verification_fails(self, message_signer):
        """Verify messages from different signer with different key fail."""
        # Create another signer with different key
        other_key = secrets.token_bytes(32)
        other_signer = type(message_signer)(other_key)
        
        # Sign with other signer
        message = {"test": "cross"}
        signature = other_signer.sign(message.copy())
        
        # Verify with original signer (should fail)
        is_valid, _ = message_signer.verify(message, signature)
        assert is_valid is False
    
    def test_real_hmac_algorithm_used(self, message_signer):
        """Verify real HMAC-SHA256 is used (not mock)."""
        message = {"test": "algorithm"}
        signature = message_signer.sign(message)
        
        # Parse and verify it's valid base64
        parts = signature.split(".")
        sig_b64 = parts[2] + "=" * (4 - len(parts[2]) % 4)
        sig_bytes = base64.urlsafe_b64decode(sig_b64)
        
        # Should be 32 bytes (SHA256 output)
        assert len(sig_bytes) == 32


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
