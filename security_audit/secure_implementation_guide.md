# Secure Implementation Guide

**Platform:** FinVault Pro Enterprise Fintech Platform
**Version:** 1.0
**Classification:** Internal Use Only

---

## Table of Contents

1. [Secure Authentication Implementation](#1-secure-authentication-implementation)
2. [Authorization and Access Control](#2-authorization-and-access-control)
3. [Data Protection](#3-data-protection)
4. [Secure API Development](#4-secure-api-development)
5. [Input Validation and Sanitization](#5-input-validation-and-sanitization)
6. [Cryptographic Operations](#6-cryptographic-operations)
7. [Logging and Monitoring](#7-logging-and-monitoring)
8. [Error Handling](#8-error-handling)

---

## 1. Secure Authentication Implementation

### 1.1 Multi-Factor Authentication (MFA)

```python
# /src/auth/mfa_service.py
"""
PCI-DSS Compliant Multi-Factor Authentication Service.

Requirements:
- MFA required for all administrative access
- MFA required for high-value transactions (>$100K)
- TOTP per RFC 6238
- Backup codes for account recovery
"""

import pyotp
import qrcode
import io
import base64
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional
import hashlib
import hmac

class MFAMethod(Enum):
    TOTP = auto()           # Time-based One-Time Password
    HARDWARE_KEY = auto()   # FIDO2/WebAuthn
    PUSH = auto()           # Mobile push notification
    BACKUP_CODE = auto()    # Single-use backup codes

@dataclass
class MFAVerificationResult:
    success: bool
    method: MFAMethod
    remaining_attempts: int
    locked_until: Optional[datetime]
    new_backup_codes: Optional[list] = None

class MFAService:
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION_MINUTES = 30
    TOTP_ISSUER = "FinVault Pro"

    def __init__(self, redis_client, audit_logger):
        self.redis = redis_client
        self.audit = audit_logger

    async def enroll_totp(self, user_id: str) -> TOTPEnrollment:
        """
        Enroll user in TOTP-based MFA.

        Returns provisioning URI and QR code for authenticator apps.
        """
        # Generate cryptographically secure secret
        secret = pyotp.random_base32()

        # Store encrypted secret (pending verification)
        await self.store_pending_secret(user_id, secret)

        # Generate provisioning URI
        user = await self.get_user(user_id)
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name=self.TOTP_ISSUER
        )

        # Generate QR code
        qr = qrcode.make(provisioning_uri)
        buffer = io.BytesIO()
        qr.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        # Generate backup codes
        backup_codes = await self.generate_backup_codes(user_id)

        self.audit.log('MFA_ENROLLMENT_STARTED', {
            'user_id': hashlib.sha256(user_id.encode()).hexdigest()[:16],
            'method': 'TOTP'
        })

        return TOTPEnrollment(
            secret=secret,  # Only shown once
            qr_code_base64=qr_base64,
            backup_codes=backup_codes,  # Only shown once
            provisioning_uri=provisioning_uri
        )

    async def verify_totp(self, user_id: str, token: str,
                          context: dict) -> MFAVerificationResult:
        """
        Verify TOTP token with rate limiting and replay protection.
        """
        # Check for lockout
        lockout_key = f"mfa_lockout:{user_id}"
        if await self.redis.exists(lockout_key):
            ttl = await self.redis.ttl(lockout_key)
            return MFAVerificationResult(
                success=False,
                method=MFAMethod.TOTP,
                remaining_attempts=0,
                locked_until=datetime.utcnow() + timedelta(seconds=ttl)
            )

        # Get user's secret
        secret = await self.get_user_totp_secret(user_id)
        if not secret:
            return MFAVerificationResult(
                success=False,
                method=MFAMethod.TOTP,
                remaining_attempts=0,
                locked_until=None
            )

        # Verify token with time drift tolerance
        totp = pyotp.TOTP(secret)
        valid_window = 1  # Allow 1 step before/after (±30 seconds)

        if not totp.verify(token, valid_window=valid_window):
            # Increment failed attempts
            attempts_key = f"mfa_attempts:{user_id}"
            attempts = await self.redis.incr(attempts_key)

            if attempts == 1:
                await self.redis.expire(attempts_key, 300)  # 5 minute window

            if attempts >= self.MAX_ATTEMPTS:
                await self.redis.setex(
                    lockout_key,
                    self.LOCKOUT_DURATION_MINUTES * 60,
                    'locked'
                )
                await self.redis.delete(attempts_key)

                self.audit.log('MFA_LOCKOUT_TRIGGERED', {
                    'user_id': hashlib.sha256(user_id.encode()).hexdigest()[:16],
                    'context': context
                })

            return MFAVerificationResult(
                success=False,
                method=MFAMethod.TOTP,
                remaining_attempts=self.MAX_ATTEMPTS - attempts,
                locked_until=None
            )

        # Check for replay (token already used)
        used_tokens_key = f"mfa_used_tokens:{user_id}"
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        if await self.redis.sismember(used_tokens_key, token_hash):
            self.audit.log('MFA_REPLAY_ATTEMPT', {
                'user_id': hashlib.sha256(user_id.encode()).hexdigest()[:16]
            })
            return MFAVerificationResult(
                success=False,
                method=MFAMethod.TOTP,
                remaining_attempts=0,
                locked_until=None
            )

        # Mark token as used (TOTP window)
        await self.redis.sadd(used_tokens_key, token_hash)
        await self.redis.expire(used_tokens_key, 60)  # 1 minute expiry

        # Clear failed attempts
        await self.redis.delete(f"mfa_attempts:{user_id}")

        self.audit.log('MFA_VERIFICATION_SUCCESS', {
            'user_id': hashlib.sha256(user_id.encode()).hexdigest()[:16],
            'method': 'TOTP',
            'context': context
        })

        return MFAVerificationResult(
            success=True,
            method=MFAMethod.TOTP,
            remaining_attempts=self.MAX_ATTEMPTS,
            locked_until=None
        )

    async def verify_webauthn(self, user_id: str, assertion: dict,
                              challenge: str) -> MFAVerificationResult:
        """
        Verify FIDO2/WebAuthn assertion.
        """
        from webauthn import verify_authentication_response

        credential = await self.get_webauthn_credential(user_id)

        try:
            verification = verify_authentication_response(
                credential=credential,
                assertion=assertion,
                expected_challenge=challenge,
                expected_origin="https://app.finvault-pro.com",
                expected_rp_id="finvault-pro.com",
                require_user_verification=True
            )

            # Update credential counter (anti-cloning)
            await self.update_credential_counter(
                user_id,
                verification.new_sign_count
            )

            return MFAVerificationResult(
                success=True,
                method=MFAMethod.HARDWARE_KEY,
                remaining_attempts=self.MAX_ATTEMPTS,
                locked_until=None
            )

        except Exception as e:
            self.audit.log('WEBAUTHN_VERIFICATION_FAILED', {
                'user_id': hashlib.sha256(user_id.encode()).hexdigest()[:16],
                'error': str(e)
            })
            return MFAVerificationResult(
                success=False,
                method=MFAMethod.HARDWARE_KEY,
                remaining_attempts=0,
                locked_until=None
            )
```

### 1.2 Step-Up Authentication

```python
# /src/auth/step_up_auth.py
"""
Step-up authentication for high-risk operations.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional

@dataclass
class RiskContext:
    amount: Decimal
    recipient_new: bool
    recipient_risk_score: float
    device_trust_score: float
    time_since_last_auth: int  # minutes
    transaction_velocity_1h: int

class StepUpAuthService:
    """
    Risk-based step-up authentication.

    Triggers additional authentication based on:
    - Transaction amount
    - Recipient risk profile
    - Device trust
    - Behavioral patterns
    """

    THRESHOLDS = {
        'amount': Decimal('100000'),      # $100K
        'recipient_risk': 0.7,
        'device_trust': 0.5,
        'time_since_auth': 10,            # minutes
        'velocity': 5                     # transactions/hour
    }

    async def evaluate_step_up_required(
        self,
        user_id: str,
        operation: str,
        context: RiskContext
    ) -> StepUpDecision:
        """
        Determine if step-up authentication is required.
        """
        required_methods = []
        risk_factors = []

        # Factor 1: Amount
        if context.amount >= self.THRESHOLDS['amount']:
            risk_factors.append('HIGH_AMOUNT')
            required_methods.extend([MFAMethod.HARDWARE_KEY, MFAMethod.TOTP])

        # Factor 2: New recipient
        if context.recipient_new:
            risk_factors.append('NEW_RECIPIENT')
            required_methods.append(MFAMethod.TOTP)

        # Factor 3: Recipient risk
        if context.recipient_risk_score >= self.THRESHOLDS['recipient_risk']:
            risk_factors.append('HIGH_RISK_RECIPIENT')
            required_methods.extend([MFAMethod.HARDWARE_KEY])

        # Factor 4: Device trust
        if context.device_trust_score < self.THRESHOLDS['device_trust']:
            risk_factors.append('UNTRUSTED_DEVICE')
            required_methods.append(MFAMethod.TOTP)

        # Factor 5: Session age
        if context.time_since_last_auth > self.THRESHOLDS['time_since_auth']:
            risk_factors.append('STALE_SESSION')
            required_methods.append(MFAMethod.TOTP)

        # Factor 6: Velocity
        if context.transaction_velocity_1h > self.THRESHOLDS['velocity']:
            risk_factors.append('VELOCITY_EXCEEDED')
            required_methods.extend([MFAMethod.HARDWARE_KEY, MFAMethod.TOTP])

        if not required_methods:
            return StepUpDecision(
                required=False,
                methods=[],
                risk_factors=[],
                expires_at=None
            )

        # Deduplicate and prioritize methods
        unique_methods = list(dict.fromkeys(required_methods))

        # Create step-up challenge
        challenge = await self.create_step_up_challenge(
            user_id=user_id,
            operation=operation,
            methods=unique_methods,
            risk_factors=risk_factors,
            context=context
        )

        return StepUpDecision(
            required=True,
            methods=unique_methods,
            risk_factors=risk_factors,
            challenge_id=challenge.id,
            expires_at=challenge.expires_at
        )
```

---

## 2. Authorization and Access Control

### 2.1 Role-Based Access Control (RBAC)

```python
# /src/auth/rbac.py
"""
Role-Based Access Control with attribute support.
"""

from enum import Enum
from functools import wraps
from typing import Set, List, Callable

class Permission(Enum):
    # Account permissions
    ACCOUNT_READ = "account:read"
    ACCOUNT_WRITE = "account:write"
    ACCOUNT_DELETE = "account:delete"
    ACCOUNT_ADMIN = "account:admin"

    # Transaction permissions
    TRANSACTION_READ = "transaction:read"
    TRANSACTION_CREATE = "transaction:create"
    TRANSACTION_APPROVE = "transaction:approve"
    TRANSACTION_ADMIN = "transaction:admin"

    # User management
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # System
    SYSTEM_CONFIG = "system:config"
    AUDIT_READ = "audit:read"

# Role definitions
ROLES = {
    'customer': {
        Permission.ACCOUNT_READ,
        Permission.TRANSACTION_READ,
        Permission.TRANSACTION_CREATE,
        Permission.USER_READ
    },
    'premium_customer': {
        Permission.ACCOUNT_READ,
        Permission.ACCOUNT_WRITE,
        Permission.TRANSACTION_READ,
        Permission.TRANSACTION_CREATE,
        Permission.TRANSACTION_APPROVE,
        Permission.USER_READ,
        Permission.USER_WRITE
    },
    'relationship_manager': {
        Permission.ACCOUNT_READ,
        Permission.TRANSACTION_READ,
        Permission.USER_READ
    },
    'compliance_officer': {
        Permission.ACCOUNT_READ,
        Permission.TRANSACTION_READ,
        Permission.TRANSACTION_ADMIN,
        Permission.AUDIT_READ
    },
    'admin': set(Permission)  # All permissions
}

class RBACService:
    def __init__(self):
        self.role_hierarchy = {
            'admin': ['compliance_officer', 'relationship_manager', 'premium_customer', 'customer'],
            'compliance_officer': ['relationship_manager'],
            'relationship_manager': [],
            'premium_customer': ['customer'],
            'customer': []
        }

    def get_effective_permissions(self, role: str) -> Set[Permission]:
        """
        Get all permissions including inherited ones.
        """
        permissions = set(ROLES.get(role, set()))

        # Add inherited permissions
        for child_role in self.role_hierarchy.get(role, []):
            permissions.update(self.get_effective_permissions(child_role))

        return permissions

    def has_permission(self, user: User, permission: Permission) -> bool:
        """
        Check if user has specific permission.
        """
        user_permissions = self.get_effective_permissions(user.role)
        return permission in user_permissions

    def require_permission(permission: Permission):
        """
        Decorator to require specific permission.
        """
        def decorator(func: Callable):
            @wraps(func)
            async def wrapper(request, *args, **kwargs):
                if not request.user:
                    raise AuthenticationError("Authentication required")

                rbac = RBACService()
                if not rbac.has_permission(request.user, permission):
                    await AuditLogger.log('PERMISSION_DENIED', {
                        'user': request.user.id,
                        'required': permission.value,
                        'resource': request.path
                    })
                    raise AuthorizationError(
                        f"Permission '{permission.value}' required"
                    )

                return await func(request, *args, **kwargs)
            return wrapper
        return decorator
```

### 2.2 Attribute-Based Access Control (ABAC)

```python
# /src/auth/abac.py
"""
Attribute-Based Access Control for fine-grained authorization.
"""

from dataclasses import dataclass
from typing import Any, Dict, Callable
import operator

@dataclass
class AttributeCondition:
    attribute: str
    operator: str
    value: Any

class ABACPolicy:
    """
    ABAC policy definition.

    Example: Allow access if:
    - User.department == Resource.department
    - User.clearance >= Resource.classification
    - Time is business hours
    """

    def __init__(self):
        self.operators = {
            'eq': operator.eq,
            'ne': operator.ne,
            'gt': operator.gt,
            'gte': operator.ge,
            'lt': operator.lt,
            'lte': operator.le,
            'in': lambda x, y: x in y,
            'contains': lambda x, y: y in x if x else False,
            'startswith': lambda x, y: str(x).startswith(str(y)),
        }

    def evaluate(self, subject: Dict, resource: Dict,
                 action: str, environment: Dict) -> bool:
        """
        Evaluate ABAC policy.
        """
        # Subject attributes (user)
        user_dept = subject.get('department')
        user_clearance = subject.get('clearance_level', 0)
        user_roles = subject.get('roles', [])

        # Resource attributes
        resource_dept = resource.get('department')
        resource_classification = resource.get('classification', 0)
        resource_owner = resource.get('owner_id')

        # Environment attributes
        current_time = environment.get('time')
        is_business_hours = self._is_business_hours(current_time)
        source_ip = environment.get('source_ip')
        is_trusted_network = self._is_trusted_network(source_ip)

        # Policy evaluation
        rules = [
            # Rule 1: Owner always has access
            subject.get('id') == resource_owner,

            # Rule 2: Same department + sufficient clearance
            (user_dept == resource_dept and
             user_clearance >= resource_classification),

            # Rule 3: Admin role (any time)
            'admin' in user_roles,

            # Rule 4: Manager role during business hours from trusted network
            ('manager' in user_roles and
             is_business_hours and
             is_trusted_network)
        ]

        return any(rules)

    def _is_business_hours(self, dt: datetime) -> bool:
        """Check if datetime is within business hours (9-5, M-F)."""
        if dt.weekday() >= 5:  # Weekend
            return False
        return 9 <= dt.hour < 17

    def _is_trusted_network(self, ip: str) -> bool:
        """Check if IP is from trusted network range."""
        trusted_ranges = ['10.0.0.0/8', '172.16.0.0/12']
        return any(self._ip_in_range(ip, range_) for range_ in trusted_ranges)
```

---

## 3. Data Protection

### 3.1 Tokenization Service

```python
# /src/security/tokenization.py
"""
PCI-DSS compliant payment data tokenization.
"""

import hashlib
import hmac
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from uuid import uuid4

class TokenVault:
    """
    HSM-backed tokenization service for PAN data.

    Features:
    - Format-preserving tokens
    - Deterministic tokens for duplicate detection
    - Full audit trail
    - Geographic restrictions
    """

    TOKEN_PREFIX = "TKN"
    TOKEN_VERSION = "2"

    def __init__(self, hsm_client, audit_logger):
        self.hsm = hsm_client
        self.audit = audit_logger

    async def tokenize(self, pan: str, context: TokenizationContext) -> Token:
        """
        Convert PAN to secure token.

        Args:
            pan: Primary Account Number (13-19 digits)
            context: Tokenization context (merchant, user, etc.)

        Returns:
            Token object with token string and metadata
        """
        # Validate PAN
        if not self._validate_pan(pan):
            raise ValueError("Invalid PAN format")

        # Check Luhn checksum
        if not self._luhn_check(pan):
            raise ValueError("Invalid PAN checksum")

        # Generate deterministic fingerprint for duplicate detection
        fingerprint = self._generate_fingerprint(pan, context.merchant_id)

        # Check for existing token
        existing = await self._find_by_fingerprint(fingerprint)
        if existing:
            self.audit.log('TOKEN_REUSE', {
                'token_id': existing.id,
                'merchant': context.merchant_id
            })
            return existing

        # Generate unique token ID
        token_id = str(uuid4())

        # Encrypt PAN with HSM
        encrypted_pan = await self.hsm.encrypt(
            data=pan.encode(),
            key_id='tokenization_key',
            context={
                'token_id': token_id,
                'merchant_id': context.merchant_id
            }
        )

        # Store in vault
        token_record = {
            'id': token_id,
            'encrypted_pan': encrypted_pan,
            'fingerprint': fingerprint,
            'last_four': pan[-4:],
            'bin': pan[:6],
            'card_brand': self._detect_card_brand(pan),
            'merchant_id': context.merchant_id,
            'created_at': datetime.utcnow().isoformat(),
            'access_policy': {
                'allowed_merchants': [context.merchant_id],
                'geographic_restrictions': context.allowed_regions,
                'requires_justification': True,
                'max_access_frequency': '10/hour'
            }
        }

        await self._store_token(token_record)

        # Create public token
        public_token = f"{self.TOKEN_PREFIX}_{self.TOKEN_VERSION}_{token_id}_{pan[-4:]}"

        self.audit.log('TOKEN_CREATED', {
            'token_id': token_id,
            'merchant': context.merchant_id,
            'bin': pan[:6]
        })

        return Token(
            token=public_token,
            id=token_id,
            last_four=pan[-4:],
            bin=pan[:6],
            brand=token_record['card_brand']
        )

    async def detokenize(self, token: str, context: DetokenizationContext) -> str:
        """
        Retrieve PAN from token with full authorization check.
        """
        # Parse token
        token_id = self._extract_token_id(token)

        # Retrieve from vault
        record = await self._get_token(token_id)
        if not record:
            self.audit.log('DETOKENIZATION_NOT_FOUND', {
                'token_id_hash': self._hash_id(token_id),
                'requester': context.requester_id
            })
            raise TokenNotFoundError()

        # Verify authorization
        if not self._authorized_for_detokenization(record, context):
            self.audit.log('DETOKENIZATION_UNAUTHORIZED', {
                'token_id_hash': self._hash_id(token_id),
                'requester': context.requester_id,
                'justification': context.justification
            })
            raise AuthorizationError("Not authorized for detokenization")

        # Check rate limit
        if not await self._check_detokenization_rate(token_id, context):
            raise RateLimitError("Detokenization rate limit exceeded")

        # Decrypt PAN
        pan = await self.hsm.decrypt(
            ciphertext=record['encrypted_pan'],
            key_id='tokenization_key',
            context={
                'token_id': token_id,
                'requester': context.requester_id
            }
        )

        # Log access
        self.audit.log('DETOKENIZATION_ACCESS', {
            'token_id_hash': self._hash_id(token_id),
            'requester': context.requester_id,
            'justification': context.justification,
            'timestamp': datetime.utcnow().isoformat()
        })

        return pan.decode()

    def _generate_fingerprint(self, pan: str, merchant_id: str) -> str:
        """
        Generate deterministic fingerprint for duplicate detection.
        Uses HMAC to prevent rainbow table attacks.
        """
        key = self.hsm.get_key('fingerprint_key')
        data = f"{pan}:{merchant_id}"
        return hmac.new(key, data.encode(), hashlib.sha256).hexdigest()

    def _validate_pan(self, pan: str) -> bool:
        """Validate PAN format."""
        return bool(re.match(r'^\d{13,19}$', pan))

    def _luhn_check(self, pan: str) -> bool:
        """Validate PAN using Luhn algorithm."""
        digits = [int(d) for d in pan]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]

        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))

        return checksum % 10 == 0
```

### 3.2 Field-Level Encryption

```python
# /src/security/field_encryption.py
"""
Field-level encryption for sensitive data.
"""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import json
from base64 import b64encode, b64decode

class FieldEncryption:
    """
    Transparent field-level encryption for database fields.

    Supports:
    - Deterministic encryption (for search)
    - Randomized encryption (maximum security)
    - Blind indexing (for partial search)
    """

    def __init__(self, key_manager):
        self.key_manager = key_manager

    def encrypt_deterministic(self, plaintext: str, field_name: str) -> str:
        """
        Deterministic encryption - same plaintext = same ciphertext.
        Used for fields that need exact match queries.
        """
        key = self.key_manager.get_key(f"det:{field_name}")
        aesgcm = AESGCM(key)

        # Use field name as additional authenticated data
        aad = field_name.encode()

        # Deterministic: use hash of plaintext as nonce
        nonce = hashlib.sha256(plaintext.encode()).digest()[:12]

        ciphertext = aesgcm.encrypt(
            nonce=nonce,
            data=plaintext.encode(),
            associated_data=aad
        )

        # Format: version:field:base64(ciphertext)
        return f"1:{field_name}:{b64encode(ciphertext).decode()}"

    def encrypt_randomized(self, plaintext: str, field_name: str) -> str:
        """
        Randomized encryption - same plaintext = different ciphertext.
        Maximum security, no search capability.
        """
        key = self.key_manager.get_key(f"rnd:{field_name}")
        aesgcm = AESGCM(key)

        # Random 96-bit nonce
        nonce = os.urandom(12)
        aad = field_name.encode()

        ciphertext = aesgcm.encrypt(
            nonce=nonce,
            data=plaintext.encode(),
            associated_data=aad
        )

        # Format: version:field:base64(nonce:ciphertext)
        combined = nonce + ciphertext
        return f"2:{field_name}:{b64encode(combined).decode()}"

    def create_blind_index(self, plaintext: str, field_name: str,
                          index_bits: int = 32) -> List[str]:
        """
        Create blind index for partial search on encrypted data.

        Uses Bloom filter-like approach with HMAC of substrings.
        """
        key = self.key_manager.get_key(f"idx:{field_name}")
        indices = []

        # Index substrings for partial matching
        plaintext_lower = plaintext.lower()
        for i in range(len(plaintext_lower)):
            for length in [3, 4, 5]:  # Index 3, 4, 5 character substrings
                if i + length <= len(plaintext_lower):
                    substring = plaintext_lower[i:i + length]
                    index = hmac.new(
                        key,
                        substring.encode(),
                        hashlib.sha256
                    ).hexdigest()[:index_bits // 4]
                    indices.append(index)

        return list(set(indices))  # Deduplicate
```

---

## 4. Secure API Development

### 4.1 Request Validation

```python
# /src/api/validation.py
"""
Comprehensive API request validation.
"""

from pydantic import BaseModel, Field, validator
from decimal import Decimal
from typing import Optional
import re

class TransactionRequest(BaseModel):
    """
    Validated transaction request model.
    """
    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(..., regex=r'^[A-Z]{3}$')
    source_account: str = Field(..., min_length=10, max_length=20)
    destination_account: str = Field(..., min_length=10, max_length=20)
    description: Optional[str] = Field(None, max_length=140)
    idempotency_key: str = Field(..., min_length=32, max_length=64)

    @validator('amount')
    def validate_amount_precision(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount cannot have more than 2 decimal places')
        return v

    @validator('amount')
    def validate_amount_reasonable(cls, v):
        """Ensure amount is within reasonable bounds."""
        if v > Decimal('999999999.99'):
            raise ValueError('Amount exceeds maximum allowed')
        return v

    @validator('source_account', 'destination_account')
    def validate_account_format(cls, v):
        """Validate account number format."""
        if not re.match(r'^[A-Z0-9]+$', v):
            raise ValueError('Account number must be alphanumeric')
        return v

    @validator('description')
    def sanitize_description(cls, v):
        """Remove potentially dangerous characters."""
        if v is None:
            return v
        # Remove control characters
        v = ''.join(char for char in v if ord(char) >= 32)
        # Normalize whitespace
        v = ' '.join(v.split())
        return v.strip()

    @validator('currency')
    def validate_supported_currency(cls, v):
        """Check currency is supported."""
        supported = {'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD'}
        if v not in supported:
            raise ValueError(f'Currency {v} not supported')
        return v

    class Config:
        # Reject extra fields (prevent mass assignment)
        extra = 'forbid'

        # Example for documentation
        schema_extra = {
            "example": {
                "amount": "1000.00",
                "currency": "USD",
                "source_account": "ACC123456789",
                "destination_account": "ACC987654321",
                "description": "Invoice payment",
                "idempotency_key": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
```

### 4.2 Response Serialization

```python
# /src/api/serialization.py
"""
Secure response serialization with field-level access control.
"""

from typing import Dict, Set, Any
from enum import Enum

class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

class SecureSerializer:
    """
    Serializes responses based on user permissions and data classification.
    """

    # Field definitions with classification and required roles
    FIELD_DEFINITIONS = {
        'transaction_id': {
            'classification': DataClassification.PUBLIC,
            'roles': {'user', 'admin', 'auditor'}
        },
        'amount': {
            'classification': DataClassification.CONFIDENTIAL,
            'roles': {'user', 'admin', 'auditor'}
        },
        'currency': {
            'classification': DataClassification.PUBLIC,
            'roles': {'user', 'admin', 'auditor'}
        },
        'card_last_four': {
            'classification': DataClassification.CONFIDENTIAL,
            'roles': {'user', 'admin'},
            'mask_for_roles': {'auditor'}
        },
        'internal_risk_score': {
            'classification': DataClassification.RESTRICTED,
            'roles': {'admin', 'risk_analyst'}
        },
        'compliance_notes': {
            'classification': DataClassification.RESTRICTED,
            'roles': {'compliance_officer'}
        },
        'raw_card_data': {
            'classification': DataClassification.RESTRICTED,
            'roles': set()  # Never expose
        }
    }

    def serialize(self, data: Dict, user_roles: Set[str]) -> Dict:
        """
        Serialize data with field-level filtering.
        """
        result = {}

        for field, value in data.items():
            definition = self.FIELD_DEFINITIONS.get(field)

            if not definition:
                # Unknown field - exclude for security
                continue

            # Check if user has permission for this field
            allowed_roles = definition['roles']
            if not any(role in allowed_roles for role in user_roles):
                continue

            # Check if field should be masked
            mask_roles = definition.get('mask_for_roles', set())
            if any(role in mask_roles for role in user_roles):
                value = self._mask_value(value, field)

            # Apply transformation based on classification
            classification = definition['classification']
            value = self._apply_classification_transform(value, classification)

            result[field] = value

        # Add security metadata
        result['_meta'] = {
            'schema_version': '2.0',
            'data_classification': self._calculate_response_classification(
                result
            ),
            'request_id': generate_request_id()
        }

        return result

    def _mask_value(self, value: Any, field: str) -> str:
        """Mask sensitive values."""
        if field.endswith('_last_four'):
            return f"****{value}" if value else None
        if isinstance(value, str):
            return "*" * len(value)
        return "[REDACTED]"

    def _apply_classification_transform(self, value: Any,
                                        classification: DataClassification):
        """Apply transforms based on data classification."""
        # Add watermarking for confidential data
        if classification == DataClassification.CONFIDENTIAL:
            # Could add invisible watermarking here
            pass
        return value

    def _calculate_response_classification(self, data: Dict) -> str:
        """Determine overall classification of response."""
        max_classification = DataClassification.PUBLIC

        for field in data.keys():
            definition = self.FIELD_DEFINITIONS.get(field)
            if definition:
                classification = definition['classification']
                if classification.value > max_classification.value:
                    max_classification = classification

        return max_classification.value
```

---

## 5. Input Validation and Sanitization

### 5.1 SQL Injection Prevention

```python
# /src/database/secure_queries.py
"""
Secure database query patterns.
"""

from typing import List, Any, Optional
import re

class SecureQueryBuilder:
    """
    Parameterized query builder with additional safety checks.
    """

    ALLOWED_OPERATORS = {'=', '<', '>', '<=', '>=', '!=', 'LIKE', 'IN'}
    ALLOWED_SORT_DIRECTIONS = {'ASC', 'DESC'}
    MAX_LIMIT = 1000

    def __init__(self, table_name: str):
        # Validate table name against whitelist
        if not self._is_valid_identifier(table_name):
            raise ValueError(f"Invalid table name: {table_name}")
        self.table = table_name
        self.conditions = []
        self.params = []
        self.order_by = []
        self.limit_val = None
        self.offset_val = None

    def where(self, column: str, operator: str, value: Any) -> 'SecureQueryBuilder':
        """Add WHERE condition with validation."""
        # Validate column name
        if not self._is_valid_identifier(column):
            raise ValueError(f"Invalid column name: {column}")

        # Validate operator
        operator = operator.upper()
        if operator not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Invalid operator: {operator}")

        # Build condition with parameter placeholder
        if operator == 'IN':
            if not isinstance(value, (list, tuple)):
                raise ValueError("IN operator requires list value")
            placeholders = ', '.join(f'${i}' for i in range(
                len(self.params) + 1,
                len(self.params) + len(value) + 1
            ))
            condition = f"{column} IN ({placeholders})"
            self.params.extend(value)
        else:
            self.params.append(value)
            condition = f"{column} {operator} ${len(self.params)}"

        self.conditions.append(condition)
        return self

    def order_by(self, column: str, direction: str = 'ASC') -> 'SecureQueryBuilder':
        """Add ORDER BY clause with validation."""
        if not self._is_valid_identifier(column):
            raise ValueError(f"Invalid column name: {column}")

        direction = direction.upper()
        if direction not in self.ALLOWED_SORT_DIRECTIONS:
            raise ValueError(f"Invalid sort direction: {direction}")

        self.order_by.append(f"{column} {direction}")
        return self

    def limit(self, count: int) -> 'SecureQueryBuilder':
        """Set LIMIT with maximum check."""
        if count > self.MAX_LIMIT:
            raise ValueError(f"Limit exceeds maximum of {self.MAX_LIMIT}")
        if count < 1:
            raise ValueError("Limit must be positive")
        self.limit_val = count
        return self

    def build(self) -> tuple:
        """Build final query and parameters."""
        query = f"SELECT * FROM {self.table}"

        if self.conditions:
            query += " WHERE " + " AND ".join(self.conditions)

        if self.order_by:
            query += " ORDER BY " + ", ".join(self.order_by)

        if self.limit_val:
            query += f" LIMIT {self.limit_val}"

        if self.offset_val:
            query += f" OFFSET {self.offset_val}"

        return query, self.params

    def _is_valid_identifier(self, identifier: str) -> bool:
        """
        Validate SQL identifier (table/column name).
        Only allows alphanumeric and underscore.
        """
        return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier))


# Usage example
async def search_transactions(
    db: Database,
    user_id: str,
    min_amount: Optional[Decimal] = None,
    start_date: Optional[datetime] = None
):
    """
    Secure transaction search with parameterized queries.
    """
    query = SecureQueryBuilder('transactions')

    # Always filter by user_id (authorization)
    query.where('user_id', '=', user_id)

    # Optional filters
    if min_amount is not None:
        query.where('amount', '>=', min_amount)

    if start_date is not None:
        query.where('transaction_date', '>=', start_date)

    # Safe ordering and limiting
    query.order_by('transaction_date', 'DESC')
    query.limit(100)

    sql, params = query.build()
    return await db.fetch(sql, *params)
```

### 5.2 XSS Prevention

```python
# /src/security/xss_protection.py
"""
Cross-Site Scripting (XSS) protection utilities.
"""

import html
import re
from markupsafe import Markup
from bleach import clean

class XSSProtection:
    """
    Comprehensive XSS protection for web applications.
    """

    # Allowed HTML tags for rich text (if needed)
    ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'u']
    ALLOWED_ATTRIBUTES = {}

    @staticmethod
    def escape_html(text: str) -> str:
        """
        Escape HTML entities to prevent XSS.
        Use for all user input displayed in HTML context.
        """
        if not isinstance(text, str):
            text = str(text)
        return html.escape(text, quote=True)

    @staticmethod
    def escape_javascript(text: str) -> str:
        """
        Escape for JavaScript context.
        Use when inserting user data into JavaScript strings.
        """
        # JSON serialization is safer than manual escaping
        import json
        return json.dumps(text)

    @staticmethod
    def escape_css(text: str) -> str:
        """
        Escape for CSS context.
        Use when inserting user data into CSS.
        """
        # Only allow safe CSS values
        if not re.match(r'^[\w\-#.,\s()]+$', text):
            return ''
        return text

    @staticmethod
    def escape_url(text: str) -> str:
        """
        Escape for URL context.
        Use when constructing URLs with user data.
        """
        from urllib.parse import quote
        return quote(text, safe='')

    @staticmethod
    def sanitize_html(text: str, allow_tags: bool = False) -> str:
        """
        Sanitize HTML content.
        Use when allowing limited HTML from users.
        """
        if not allow_tags:
            # Strip all HTML
            clean_text = re.sub(r'<[^>]+>', '', text)
            return XSSProtection.escape_html(clean_text)

        # Allow specific safe HTML
        return clean(
            text,
            tags=XSSProtection.ALLOWED_TAGS,
            attributes=XSSProtection.ALLOWED_ATTRIBUTES,
            strip=True
        )

    @staticmethod
    def validate_content_security_policy_nonce(nonce: str) -> bool:
        """
        Validate CSP nonce format.
        """
        # Nonce should be base64 encoded, at least 16 bytes
        if not re.match(r'^[A-Za-z0-9+/]{22,}={0,2}$', nonce):
            return False
        return True


# Template helper (Jinja2)
def setup_template_security(app):
    """
    Configure Jinja2 with automatic escaping.
    """
    from jinja2 import Environment, select_autoescape

    env = Environment(
        autoescape=select_autoescape(['html', 'xml']),
        enable_async=True
    )

    # Add security filters
    env.filters['escape_js'] = XSSProtection.escape_javascript
    env.filters['escape_css'] = XSSProtection.escape_css
    env.filters['escape_url'] = XSSProtection.escape_url

    # Add CSP nonce to context
    @app.context_processor
    def inject_csp_nonce():
        import secrets
        nonce = secrets.token_urlsafe(16)
        # Store nonce for CSP header validation
        g.csp_nonce = nonce
        return {'csp_nonce': nonce}

    return env
```

---

## 6. Cryptographic Operations

### 6.1 Secure Key Management

```python
# /src/crypto/key_management.py
"""
HSM-backed key management with rotation support.
"""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os
from datetime import datetime, timedelta

class KeyManager:
    """
    Secure key lifecycle management.

    Features:
    - Automatic key rotation
    - Key versioning
    - Secure key derivation
    - HSM integration
    """

    KEY_VERSION_BYTES = 4
    CURRENT_KEY_VERSION = 1

    def __init__(self, hsm_client):
        self.hsm = hsm_client
        self._key_cache = {}

    async def get_key(self, key_id: str, version: int = None) -> bytes:
        """
        Retrieve key by ID and optional version.
        """
        cache_key = f"{key_id}:{version or 'current'}"

        if cache_key in self._key_cache:
            return self._key_cache[cache_key]

        # Fetch from HSM
        key = await self.hsm.get_key(key_id, version)

        # Cache with short TTL
        self._key_cache[cache_key] = key

        return key

    async def rotate_key(self, key_id: str) -> int:
        """
        Rotate key to new version.
        """
        # Generate new key in HSM
        new_version = await self.hsm.generate_key(
            key_id=key_id,
            algorithm='AES-256-GCM',
            extractable=False
        )

        # Mark old version for deprecation
        await self.hsm.schedule_key_deletion(
            key_id=key_id,
            version=self.CURRENT_KEY_VERSION,
            delete_after=timedelta(days=90)  # Grace period
        )

        # Clear cache
        self._key_cache.clear()

        # Log rotation
        await AuditLogger.log('KEY_ROTATION', {
            'key_id': key_id,
            'new_version': new_version,
            'previous_version': self.CURRENT_KEY_VERSION
        })

        return new_version

    def derive_key(self, master_key: bytes, context: str,
                   salt: bytes = None) -> bytes:
        """
        Derive key from master key using HKDF-like construction.
        """
        if salt is None:
            salt = os.urandom(32)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )

        derived = kdf.derive(master_key + context.encode())
        return salt + derived

    async def encrypt_with_key_version(self, plaintext: bytes,
                                        key_id: str) -> bytes:
        """
        Encrypt with automatic key versioning.
        """
        key = await self.get_key(key_id)
        version = self.CURRENT_KEY_VERSION.to_bytes(
            self.KEY_VERSION_BYTES, 'big'
        )

        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext, version)

        # Format: version || nonce || ciphertext
        return version + nonce + ciphertext

    async def decrypt_with_key_version(self, ciphertext: bytes,
                                        key_id: str) -> bytes:
        """
        Decrypt with automatic key version detection.
        """
        version = int.from_bytes(
            ciphertext[:self.KEY_VERSION_BYTES], 'big'
        )
        key = await self.get_key(key_id, version)

        nonce = ciphertext[self.KEY_VERSION_BYTES:self.KEY_VERSION_BYTES + 12]
        encrypted = ciphertext[self.KEY_VERSION_BYTES + 12:]

        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, encrypted, None)
```

---

## 7. Logging and Monitoring

### 7.1 Security Audit Logging

```python
# /src/security/audit_logger.py
"""
Tamper-evident security audit logging.
"""

import hashlib
import json
from datetime import datetime
from typing import Dict, Any

class AuditLogger:
    """
    Immutable security audit logging with chain hashing.

    Features:
    - Structured JSON logging
    - Chain hashing for tamper detection
    - Sensitive data redaction
    - Async batch processing
    """

    SENSITIVE_FIELDS = {
        'password', 'ssn', 'card_number', 'cvv', 'pin',
        'secret', 'token', 'api_key', 'private_key'
    }

    def __init__(self, storage_backend, signing_key):
        self.storage = storage_backend
        self.signing_key = signing_key
        self._last_hash = None
        self._batch = []

    async def log(self, event_type: str, data: Dict[str, Any],
                  user_id: str = None, resource_id: str = None):
        """
        Log security event with tamper-evident hashing.
        """
        # Redact sensitive data
        sanitized_data = self._redact_sensitive_data(data)

        # Build audit entry
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'event_id': generate_uuid(),
            'user_id': self._hash_identifier(user_id) if user_id else None,
            'resource_id': self._hash_identifier(resource_id) if resource_id else None,
            'data': sanitized_data,
            'source_ip': get_client_ip(),
            'user_agent': get_user_agent(),
            'session_id': get_session_id()
        }

        # Calculate chain hash
        entry['previous_hash'] = self._last_hash
        entry_hash = self._calculate_hash(entry)
        entry['entry_hash'] = entry_hash
        entry['signature'] = self._sign_entry(entry_hash)

        self._last_hash = entry_hash

        # Add to batch
        self._batch.append(entry)

        # Flush if batch size reached
        if len(self._batch) >= 100:
            await self._flush_batch()

    def _redact_sensitive_data(self, data: Dict) -> Dict:
        """
        Recursively redact sensitive fields.
        """
        if not isinstance(data, dict):
            return data

        redacted = {}
        for key, value in data.items():
            # Check if field name indicates sensitive data
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                redacted[key] = '[REDACTED]'
            elif isinstance(value, dict):
                redacted[key] = self._redact_sensitive_data(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self._redact_sensitive_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                redacted[key] = value

        return redacted

    def _hash_identifier(self, identifier: str) -> str:
        """
        One-way hash of identifiers for privacy.
        """
        return hashlib.sha256(
            (identifier + self.signing_key).encode()
        ).hexdigest()[:16]

    def _calculate_hash(self, entry: Dict) -> str:
        """
        Calculate hash of entry for chain integrity.
        """
        # Canonical JSON representation
        canonical = json.dumps(entry, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _sign_entry(self, entry_hash: str) -> str:
        """
        Sign entry hash with HMAC.
        """
        return hmac.new(
            self.signing_key.encode(),
            entry_hash.encode(),
            hashlib.sha256
        ).hexdigest()

    async def _flush_batch(self):
        """
        Write batch to immutable storage.
        """
        if not self._batch:
            return

        await self.storage.write_batch(self._batch)
        self._batch = []

    async def verify_chain_integrity(self) -> bool:
        """
        Verify integrity of entire audit chain.
        """
        entries = await self.storage.read_all()

        previous_hash = None
        for entry in entries:
            # Verify hash chain
            if entry.get('previous_hash') != previous_hash:
                return False

            # Verify signature
            calculated_hash = self._calculate_hash(entry)
            if calculated_hash != entry.get('entry_hash'):
                return False

            expected_signature = self._sign_entry(calculated_hash)
            if expected_signature != entry.get('signature'):
                return False

            previous_hash = entry['entry_hash']

        return True
```

---

## 8. Error Handling

### 8.1 Secure Error Responses

```python
# /src/api/error_handling.py
"""
Secure error handling that prevents information leakage.
"""

from enum import Enum
from typing import Optional, Dict
import logging
import uuid

class ErrorCode(Enum):
    """
    Standardized error codes for API responses.
    """
    # Authentication errors (1000-1099)
    AUTH_INVALID_CREDENTIALS = 1000
    AUTH_TOKEN_EXPIRED = 1001
    AUTH_TOKEN_INVALID = 1002
    AUTH_MFA_REQUIRED = 1003
    AUTH_MFA_FAILED = 1004
    AUTH_ACCOUNT_LOCKED = 1005

    # Authorization errors (1100-1199)
    ACCESS_DENIED = 1100
    INSUFFICIENT_PERMISSIONS = 1101
    RESOURCE_NOT_FOUND = 1102

    # Validation errors (1200-1299)
    VALIDATION_ERROR = 1200
    INVALID_FORMAT = 1201
    MISSING_REQUIRED_FIELD = 1202

    # Business logic errors (1300-1399)
    INSUFFICIENT_FUNDS = 1300
    LIMIT_EXCEEDED = 1301
    DUPLICATE_TRANSACTION = 1302

    # System errors (9000-9099) - Internal only
    INTERNAL_ERROR = 9000
    DATABASE_ERROR = 9001
    EXTERNAL_SERVICE_ERROR = 9002

class SecureErrorHandler:
    """
    Error handler that prevents information leakage.
    """

    # Errors that should return generic message to client
    INTERNAL_ERROR_CODES = {
        ErrorCode.INTERNAL_ERROR,
        ErrorCode.DATABASE_ERROR,
        ErrorCode.EXTERNAL_SERVICE_ERROR
    }

    # Error messages for public consumption
    PUBLIC_MESSAGES = {
        ErrorCode.AUTH_INVALID_CREDENTIALS: "Invalid credentials",
        ErrorCode.AUTH_TOKEN_EXPIRED: "Session expired, please login again",
        ErrorCode.AUTH_TOKEN_INVALID: "Invalid session",
        ErrorCode.AUTH_MFA_REQUIRED: "Additional verification required",
        ErrorCode.AUTH_MFA_FAILED: "Verification failed",
        ErrorCode.AUTH_ACCOUNT_LOCKED: "Account temporarily locked",
        ErrorCode.ACCESS_DENIED: "Access denied",
        ErrorCode.INSUFFICIENT_PERMISSIONS: "Insufficient permissions",
        ErrorCode.RESOURCE_NOT_FOUND: "Resource not found",
        ErrorCode.VALIDATION_ERROR: "Invalid request",
        ErrorCode.INVALID_FORMAT: "Invalid data format",
        ErrorCode.MISSING_REQUIRED_FIELD: "Missing required field",
        ErrorCode.INSUFFICIENT_FUNDS: "Insufficient funds",
        ErrorCode.LIMIT_EXCEEDED: "Limit exceeded",
        ErrorCode.DUPLICATE_TRANSACTION: "Duplicate transaction detected",
    }

    @staticmethod
    def handle_error(error: Exception, request_id: str = None) -> Dict:
        """
        Convert exception to safe error response.
        """
        if request_id is None:
            request_id = str(uuid.uuid4())

        # Determine error code
        if isinstance(error, AuthenticationError):
            error_code = ErrorCode.AUTH_INVALID_CREDENTIALS
            status_code = 401
        elif isinstance(error, AuthorizationError):
            error_code = ErrorCode.ACCESS_DENIED
            status_code = 403
        elif isinstance(error, ValidationError):
            error_code = ErrorCode.VALIDATION_ERROR
            status_code = 400
        elif isinstance(error, NotFoundError):
            error_code = ErrorCode.RESOURCE_NOT_FOUND
            status_code = 404
        else:
            error_code = ErrorCode.INTERNAL_ERROR
            status_code = 500

        # Get public message
        if error_code in SecureErrorHandler.INTERNAL_ERROR_CODES:
            public_message = "An error occurred. Please try again later."
        else:
            public_message = SecureErrorHandler.PUBLIC_MESSAGES.get(
                error_code, "An error occurred"
            )

        # Log full details internally
        SecureErrorHandler._log_error(error, error_code, request_id)

        # Return safe response
        return {
            'error': {
                'code': error_code.value,
                'message': public_message,
                'request_id': request_id
            }
        }, status_code

    @staticmethod
    def _log_error(error: Exception, error_code: ErrorCode, request_id: str):
        """
        Log full error details for internal debugging.
        """
        logger = logging.getLogger('security')

        log_data = {
            'request_id': request_id,
            'error_code': error_code.value,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'stack_trace': traceback.format_exc(),
            'timestamp': datetime.utcnow().isoformat()
        }

        if error_code in SecureErrorHandler.INTERNAL_ERROR_CODES:
            logger.error("Internal error occurred", extra=log_data)
        else:
            logger.warning("Application error occurred", extra=log_data)


# Exception classes
class AuthenticationError(Exception):
    pass

class AuthorizationError(Exception):
    pass

class ValidationError(Exception):
    pass

class NotFoundError(Exception):
    pass

class RateLimitError(Exception):
    pass
