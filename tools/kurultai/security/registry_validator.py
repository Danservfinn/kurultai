#!/usr/bin/env python3
"""
Security Layer 7: Registry Validation

Cryptographic signing and validation of learned capabilities.
Ensures code integrity and non-repudiation.
"""

import os
import sys
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RegistryEntry:
    id: str
    name: str
    agent: str
    version: str
    tool_path: str
    code_hash: str
    signature: str
    risk_level: str
    required_capabilities: list
    min_trust_level: str
    created_at: datetime
    expires_at: Optional[datetime]


class RegistryValidator:
    """
    Validate and manage the capability registry.
    Uses HMAC-SHA256 for signing and verification.
    """
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize with signing key.
        
        Args:
            secret_key: Secret key for HMAC signing. If None, uses env var.
        """
        self.secret_key = secret_key or os.environ.get('REGISTRY_SIGNING_KEY')
        if not self.secret_key:
            # Generate a temporary key for development
            self.secret_key = os.urandom(32).hex()
            print("⚠️  WARNING: Using temporary signing key. Set REGISTRY_SIGNING_KEY env var.")
    
    def _compute_hash(self, code: str) -> str:
        """Compute SHA-256 hash of code."""
        return hashlib.sha256(code.encode('utf-8')).hexdigest()
    
    def _sign(self, entry_data: Dict) -> str:
        """
        Create HMAC-SHA256 signature for registry entry.
        
        Args:
            entry_data: Dictionary with entry fields
            
        Returns:
            Hex-encoded signature
        """
        # Create canonical JSON representation
        canonical = json.dumps(entry_data, sort_keys=True, separators=(',', ':'))
        
        # Create HMAC
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            canonical.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _verify(self, entry_data: Dict, signature: str) -> bool:
        """
        Verify HMAC signature.
        
        Args:
            entry_data: Dictionary with entry fields
            signature: Expected signature
            
        Returns:
            True if signature is valid
        """
        expected = self._sign(entry_data)
        return hmac.compare_digest(expected, signature)
    
    def register_capability(
        self,
        name: str,
        agent: str,
        version: str,
        tool_path: str,
        code: str,
        risk_level: str = "MEDIUM",
        required_capabilities: list = None,
        min_trust_level: str = "MEDIUM",
        ttl_days: int = 90
    ) -> Tuple[bool, str, Optional[RegistryEntry]]:
        """
        Register a new capability with signature.
        
        Returns:
            (success: bool, message: str, entry: Optional[RegistryEntry])
        """
        # Compute code hash
        code_hash = self._compute_hash(code)
        
        # Create entry data
        entry_id = f"{agent}_{name}_{int(datetime.now().timestamp())}"
        
        entry_data = {
            'id': entry_id,
            'name': name,
            'agent': agent,
            'version': version,
            'tool_path': tool_path,
            'code_hash': code_hash,
            'risk_level': risk_level,
            'required_capabilities': required_capabilities or [],
            'min_trust_level': min_trust_level,
            'created_at': datetime.now().isoformat()
        }
        
        # Sign entry
        signature = self._sign(entry_data)
        entry_data['signature'] = signature
        
        # Create entry object
        entry = RegistryEntry(
            id=entry_id,
            name=name,
            agent=agent,
            version=version,
            tool_path=tool_path,
            code_hash=code_hash,
            signature=signature,
            risk_level=risk_level,
            required_capabilities=required_capabilities or [],
            min_trust_level=min_trust_level,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(days=ttl_days) if ttl_days else None
        )
        
        return True, f"Capability {name} registered successfully", entry
    
    def verify_capability(self, entry: RegistryEntry, current_code: str) -> Tuple[bool, str]:
        """
        Verify a capability's signature and code integrity.
        
        Args:
            entry: Registry entry to verify
            current_code: Current code to check against hash
            
        Returns:
            (is_valid: bool, message: str)
        """
        # Reconstruct entry data
        entry_data = {
            'id': entry.id,
            'name': entry.name,
            'agent': entry.agent,
            'version': entry.version,
            'tool_path': entry.tool_path,
            'code_hash': entry.code_hash,
            'risk_level': entry.risk_level,
            'required_capabilities': entry.required_capabilities,
            'min_trust_level': entry.min_trust_level,
            'created_at': entry.created_at.isoformat()
        }
        
        # Verify signature
        if not self._verify(entry_data, entry.signature):
            return False, "Signature verification failed - entry may be tampered"
        
        # Verify code hash
        current_hash = self._compute_hash(current_code)
        if current_hash != entry.code_hash:
            return False, "Code hash mismatch - code has been modified"
        
        # Check expiration
        if entry.expires_at and datetime.now() > entry.expires_at:
            return False, f"Capability expired on {entry.expires_at}"
        
        return True, "Capability verified successfully"
    
    def check_agent_trust(self, agent_trust: str, required_trust: str) -> bool:
        """
        Check if agent meets minimum trust level.
        
        Args:
            agent_trust: Agent's current trust level
            required_trust: Minimum required trust level
            
        Returns:
            True if agent has sufficient trust
        """
        trust_levels = ['LOW', 'MEDIUM', 'HIGH']
        
        try:
            agent_idx = trust_levels.index(agent_trust.upper())
            required_idx = trust_levels.index(required_trust.upper())
            return agent_idx >= required_idx
        except ValueError:
            return False
    
    def check_capabilities_granted(
        self,
        agent_id: str,
        required_caps: list,
        neo4j_driver
    ) -> Tuple[bool, list]:
        """
        Check if agent has all required capabilities.
        
        Args:
            agent_id: Agent ID
            required_caps: List of required capability names
            neo4j_driver: Neo4j driver for query
            
        Returns:
            (has_all: bool, missing: list)
        """
        from neo4j import GraphDatabase
        
        with neo4j_driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {id: $agent_id})-[:HAS_CAPABILITY]->(c:Capability)
                WHERE c.expires_at IS NULL OR c.expires_at > datetime()
                RETURN collect(c.name) as granted_caps
            """, agent_id=agent_id)
            
            record = result.single()
            if not record:
                return False, required_caps
            
            granted = set(record['granted_caps'])
            required = set(required_caps)
            
            missing = list(required - granted)
            return len(missing) == 0, missing


class CapabilityRegistry:
    """
    Manage the registry of learned capabilities in Neo4j.
    """
    
    def __init__(self, neo4j_driver, validator: RegistryValidator):
        self.driver = neo4j_driver
        self.validator = validator
    
    def store_entry(self, entry: RegistryEntry) -> bool:
        """Store registry entry in Neo4j."""
        with self.driver.session() as session:
            try:
                session.run("""
                    CREATE (lc:LearnedCapability {
                        id: $id,
                        name: $name,
                        agent: $agent,
                        version: $version,
                        tool_path: $tool_path,
                        code_hash: $code_hash,
                        signature: $signature,
                        risk_level: $risk_level,
                        required_capabilities: $required_caps,
                        min_trust_level: $min_trust_level,
                        created_at: $created_at,
                        expires_at: $expires_at,
                        status: 'active'
                    })
                """,
                    id=entry.id,
                    name=entry.name,
                    agent=entry.agent,
                    version=entry.version,
                    tool_path=entry.tool_path,
                    code_hash=entry.code_hash,
                    signature=entry.signature,
                    risk_level=entry.risk_level,
                    required_caps=json.dumps(entry.required_capabilities),
                    min_trust_level=entry.min_trust_level,
                    created_at=entry.created_at.isoformat(),
                    expires_at=entry.expires_at.isoformat() if entry.expires_at else None
                )
                return True
            except Exception as e:
                print(f"Failed to store registry entry: {e}")
                return False
    
    def get_entry(self, name: str) -> Optional[RegistryEntry]:
        """Retrieve registry entry by name."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (lc:LearnedCapability {name: $name})
                RETURN lc
            """, name=name)
            
            record = result.single()
            if not record:
                return None
            
            props = record['lc']
            return RegistryEntry(
                id=props['id'],
                name=props['name'],
                agent=props['agent'],
                version=props['version'],
                tool_path=props['tool_path'],
                code_hash=props['code_hash'],
                signature=props['signature'],
                risk_level=props['risk_level'],
                required_capabilities=json.loads(props['required_capabilities']),
                min_trust_level=props['min_trust_level'],
                created_at=datetime.fromisoformat(props['created_at']),
                expires_at=datetime.fromisoformat(props['expires_at']) if props.get('expires_at') else None
            )


if __name__ == '__main__':
    print("Testing Registry Validator...")
    
    validator = RegistryValidator(secret_key="test_secret_key_123")
    
    test_code = """
def safe_function(data):
    return data.strip().lower()
"""
    
    # Register capability
    success, msg, entry = validator.register_capability(
        name="SafeStringProcessor",
        agent="temüjin",
        version="1.0.0",
        tool_path="tools/generated/safe_string.py",
        code=test_code,
        risk_level="LOW"
    )
    
    print(f"Registration: {success} - {msg}")
    
    if entry:
        # Verify capability
        is_valid, verify_msg = validator.verify_capability(entry, test_code)
        print(f"Verification: {is_valid} - {verify_msg}")
        
        # Test with modified code
        modified_code = test_code + "\n# Modified"
        is_valid2, verify_msg2 = validator.verify_capability(entry, modified_code)
        print(f"Modified code verification: {is_valid2} - {verify_msg2}")
