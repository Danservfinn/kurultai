#!/usr/bin/env python3
"""
Field Encryption — Fernet AES-128-CBC encrypt/decrypt for Neo4j properties.

Encrypts sensitive fields (e.g., Message.content) at rest.
Key is loaded from ~/.openclaw/credentials/field_encryption.key.

Usage:
    from field_encryption import encrypt_field, decrypt_field

    encrypted = encrypt_field("Hello, world!")
    plaintext = decrypt_field(encrypted)
"""

import os
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY_PATH = os.path.expanduser("~/.openclaw/credentials/field_encryption.key")
_fernet: Optional[Fernet] = None


def _load_key() -> Optional[Fernet]:
    """Load encryption key from file. Cached after first load."""
    global _fernet
    if _fernet is not None:
        return _fernet

    if not os.path.exists(_KEY_PATH):
        logger.error(f"Encryption key not found at {_KEY_PATH}")
        return None

    try:
        with open(_KEY_PATH, "r") as f:
            key = f.read().strip()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return _fernet
    except Exception as e:
        logger.error(f"Failed to load encryption key: {e}")
        return None


def encrypt_field(plaintext: str) -> Optional[str]:
    """Encrypt a string field using Fernet.

    Args:
        plaintext: String to encrypt

    Returns:
        Base64-encoded encrypted string, or None if encryption fails
    """
    if not plaintext:
        return plaintext

    fernet = _load_key()
    if not fernet:
        logger.error("No encryption key available — refusing to store unencrypted")
        return None

    try:
        return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return None


def decrypt_field(encrypted: str) -> Optional[str]:
    """Decrypt a Fernet-encrypted string.

    Args:
        encrypted: Base64-encoded encrypted string

    Returns:
        Decrypted plaintext, or None if decryption fails
    """
    if not encrypted:
        return encrypted

    fernet = _load_key()
    if not fernet:
        logger.warning("No encryption key available — cannot decrypt")
        return None

    try:
        return fernet.decrypt(encrypted.encode("ascii")).decode("utf-8")
    except InvalidToken:
        # Might be plaintext (pre-encryption data or encryption was disabled)
        logger.debug("Decrypt failed — data may be unencrypted plaintext")
        return encrypted
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return None


def is_encrypted(value: str) -> bool:
    """Check if a string looks like Fernet-encrypted data.

    Fernet tokens are base64-encoded and start with 'gAAAAA'.
    """
    if not value or len(value) < 50:
        return False
    return value.startswith("gAAAAA")


if __name__ == "__main__":
    print("Field encryption self-test:")

    test_msg = "Hello from Kublai! This is a secret message."
    encrypted = encrypt_field(test_msg)
    print(f"  Plaintext:  {test_msg}")
    print(f"  Encrypted:  {encrypted[:60]}...")
    print(f"  Is encrypted: {is_encrypted(encrypted)}")

    decrypted = decrypt_field(encrypted)
    print(f"  Decrypted:  {decrypted}")
    assert decrypted == test_msg, "Round-trip failed!"
    print("  Round-trip: OK")

    # Test plaintext passthrough
    plain_result = decrypt_field("not encrypted text")
    print(f"  Plaintext passthrough: {plain_result}")
    print("\nAll tests passed.")
