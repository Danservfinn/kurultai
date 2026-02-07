# Agent Orchestration Patterns for Sensitive Data Handling

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KUBLAI ORCHESTRATOR                                │
│                    (Real-time Secure Data Access)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  User Auth   │  │  Session Mgr │  │  Intent Parser│  │  Router      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│    TEMÜJIN SECURITY   │  │   SECURE DATA VAULT   │  │   AUDIT & MONITORING  │
│    (Gatekeeper Agent) │  │   (Encrypted Storage) │  │   (Compliance Layer)  │
└───────────────────────┘  └───────────────────────┘  └───────────────────────┘
           │                           │                           │
           └───────────────────────────┼───────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │                              │                              │
        ▼                              ▼                              ▼
┌───────────────┐            ┌───────────────┐            ┌───────────────┐
│   MÖNGKE      │            │   CHAGATAI    │            │     JOCHI     │
│  (Research)   │            │  (Synthesis)  │            │  (Analysis)   │
│               │            │               │            │               │
│  No sensitive │            │  Masked data  │            │  Anonymized   │
│  data access  │            │  only         │            │  aggregates   │
└───────────────┘            └───────────────┘            └───────────────┘
        │                              │                              │
        └──────────────────────────────┼──────────────────────────────┘
                                       │
                                       ▼
                            ┌───────────────┐
                            │    ÖGEDEI     │
                            │  (Operations) │
                            │               │
                            │  Token-based  │
                            │  ephemeral    │
                            └───────────────┘
```

---

## 1. ACCESS PATTERNS

### Pattern A: Security Agent as Gatekeeper (Recommended)

```python
# /src/security/temujin_gatekeeper.py

from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import secrets

class AccessLevel(Enum):
    NONE = 0
    MASKED = 1        # Partial data with redaction (e.g., ****1234)
    TOKENIZED = 2     # Reference tokens only
    TEMPORARY = 3     # Time-limited full access
    FULL = 4          # Complete access (Kublai only)

class DataClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"      # PII, financial
    CRITICAL = "critical"          # Passwords, master keys

@dataclass
class AccessRequest:
    agent_id: str
    data_classification: DataClassification
    purpose: str
    requested_fields: List[str]
    correlation_id: str
    timestamp: datetime

@dataclass
class AccessGrant:
    grant_id: str
    access_level: AccessLevel
    allowed_fields: List[str]
    expires_at: datetime
    token: Optional[str] = None
    audit_reference: str = ""

class TemujinGatekeeper:
    """
    Security Agent - Centralized gatekeeper for all sensitive data access.
    No agent accesses secure DB directly; all requests flow through Temüjin.
    """

    # Agent capability matrix - defines what each agent can access
    AGENT_CAPABILITIES = {
        "kublai": {
            "max_level": AccessLevel.FULL,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL,
                                        DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED,
                                        DataClassification.CRITICAL],
            "requires_approval": False,
            "session_timeout": timedelta(hours=8)
        },
        "temujin": {
            "max_level": AccessLevel.FULL,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL,
                                        DataClassification.CONFIDENTIAL, DataClassification.RESTRICTED,
                                        DataClassification.CRITICAL],
            "requires_approval": False,
            "session_timeout": timedelta(hours=1)
        },
        "mongke": {
            "max_level": AccessLevel.MASKED,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL],
            "requires_approval": True,
            "session_timeout": timedelta(minutes=30)
        },
        "chagatai": {
            "max_level": AccessLevel.TOKENIZED,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL,
                                        DataClassification.CONFIDENTIAL],
            "requires_approval": False,
            "session_timeout": timedelta(minutes=30)
        },
        "jochi": {
            "max_level": AccessLevel.MASKED,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL],
            "requires_approval": True,
            "session_timeout": timedelta(minutes=30)
        },
        "ogedei": {
            "max_level": AccessLevel.TEMPORARY,
            "allowed_classifications": [DataClassification.PUBLIC, DataClassification.INTERNAL,
                                        DataClassification.CONFIDENTIAL],
            "requires_approval": True,
            "session_timeout": timedelta(minutes=15)
        }
    }

    def __init__(self, audit_logger, secure_vault):
        self.audit_logger = audit_logger
        self.secure_vault = secure_vault
        self.active_grants: Dict[str, AccessGrant] = {}
        self.approval_queue: List[AccessRequest] = []

    async def request_access(self, request: AccessRequest) -> AccessGrant:
        """
        Primary entry point for all sensitive data access requests.
        Evaluates request against agent capabilities and security policies.
        """
        # Log the request attempt
        await self.audit_logger.log_access_attempt(request)

        # Validate agent identity
        if request.agent_id not in self.AGENT_CAPABILITIES:
            await self.audit_logger.log_security_event(
                event_type="UNAUTHORIZED_AGENT",
                details={"agent_id": request.agent_id}
            )
            raise SecurityException(f"Unknown agent: {request.agent_id}")

        capabilities = self.AGENT_CAPABILITIES[request.agent_id]

        # Check if classification is allowed
        if request.data_classification not in capabilities["allowed_classifications"]:
            await self.audit_logger.log_security_event(
                event_type="CLASSIFICATION_VIOLATION",
                details={
                    "agent_id": request.agent_id,
                    "requested": request.data_classification.value,
                    "allowed": [c.value for c in capabilities["allowed_classifications"]]
                }
            )
            raise SecurityException(
                f"Agent {request.agent_id} not authorized for {request.data_classification.value} data"
            )

        # Determine access level based on agent and purpose
        access_level = self._determine_access_level(request, capabilities)

        # Check if approval is required
        if capabilities["requires_approval"] and access_level.value > AccessLevel.MASKED.value:
            self.approval_queue.append(request)
            await self.audit_logger.log_approval_required(request)
            raise ApprovalRequiredException("Access requires approval from Kublai or Temüjin")

        # Generate access grant
        grant = self._create_access_grant(request, access_level, capabilities)
        self.active_grants[grant.grant_id] = grant

        await self.audit_logger.log_access_granted(request, grant)

        return grant

    def _determine_access_level(
        self,
        request: AccessRequest,
        capabilities: Dict
    ) -> AccessLevel:
        """Determine appropriate access level based on request context."""
        max_level = capabilities["max_level"]

        # Kublai gets full access during active sessions
        if request.agent_id == "kublai":
            return AccessLevel.FULL

        # Critical data never goes below tokenized
        if request.data_classification == DataClassification.CRITICAL:
            return min(AccessLevel.TOKENIZED, max_level)

        # Restricted data gets masked by default
        if request.data_classification == DataClassification.RESTRICTED:
            return min(AccessLevel.MASKED, max_level)

        # Operations agent may need temporary tokens for API calls
        if request.agent_id == "ogedei" and "api_operation" in request.purpose:
            return AccessLevel.TEMPORARY

        return min(AccessLevel.MASKED, max_level)

    def _create_access_grant(
        self,
        request: AccessRequest,
        access_level: AccessLevel,
        capabilities: Dict
    ) -> AccessGrant:
        """Create an access grant with appropriate constraints."""
        grant_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + capabilities["session_timeout"]

        # Filter fields based on classification and purpose
        allowed_fields = self._filter_fields(
            request.requested_fields,
            request.data_classification,
            access_level
        )

        # Generate ephemeral token for temporary access
        token = None
        if access_level == AccessLevel.TEMPORARY:
            token = self._generate_ephemeral_token(request, expires_at)

        return AccessGrant(
            grant_id=grant_id,
            access_level=access_level,
            allowed_fields=allowed_fields,
            expires_at=expires_at,
            token=token,
            audit_reference=hashlib.sha256(
                f"{request.agent_id}:{request.correlation_id}".encode()
            ).hexdigest()[:16]
        )

    async def retrieve_data(
        self,
        grant: AccessGrant,
        data_query: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Retrieve data through the gatekeeper, applying appropriate transforms.
        This is the ONLY method that accesses the secure vault.
        """
        # Validate grant is still active
        if datetime.utcnow() > grant.expires_at:
            await self.audit_logger.log_security_event(
                event_type="EXPIRED_GRANT_ACCESS_ATTEMPT",
                details={"grant_id": grant.grant_id}
            )
            raise SecurityException("Access grant has expired")

        # Fetch raw data from secure vault
        raw_data = await self.secure_vault.fetch(data_query)

        # Apply transformations based on access level
        transformed_data = self._apply_data_transforms(
            raw_data,
            grant.access_level,
            grant.allowed_fields
        )

        await self.audit_logger.log_data_retrieval(
            grant=grant,
            query=data_query,
            fields_accessed=list(transformed_data.keys())
        )

        return transformed_data

    def _apply_data_transforms(
        self,
        data: Dict[str, Any],
        access_level: AccessLevel,
        allowed_fields: List[str]
    ) -> Dict[str, Any]:
        """Apply security transformations based on access level."""
        transformers = {
            AccessLevel.NONE: lambda d: {},
            AccessLevel.MASKED: self._mask_sensitive_data,
            AccessLevel.TOKENIZED: self._tokenize_sensitive_data,
            AccessLevel.TEMPORARY: self._prepare_temporary_access,
            AccessLevel.FULL: lambda d, fields: {k: v for k, v in d.items() if k in fields}
        }

        transformer = transformers.get(access_level, transformers[AccessLevel.NONE])
        return transformer(data, allowed_fields)

    def _mask_sensitive_data(
        self,
        data: Dict[str, Any],
        allowed_fields: List[str]
    ) -> Dict[str, Any]:
        """Mask sensitive fields while preserving structure."""
        masked = {}
        for field in allowed_fields:
            if field not in data:
                continue

            value = data[field]

            # Apply field-specific masking
            if "password" in field.lower():
                masked[field] = "********"
            elif "ssn" in field.lower() or "social" in field.lower():
                masked[field] = f"***-**-{value[-4:]}" if len(value) >= 4 else "***-**-****"
            elif "credit_card" in field.lower() or "card_number" in field.lower():
                masked[field] = f"****-****-****-{value[-4:]}" if len(value) >= 4 else "****-****-****-****"
            elif "api_key" in field.lower() or "secret" in field.lower():
                masked[field] = f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"
            elif "email" in field.lower():
                parts = value.split("@")
                if len(parts) == 2:
                    local = parts[0]
                    masked[field] = f"{local[0]}{'*' * (len(local)-1)}@{parts[1]}"
                else:
                    masked[field] = "***@***.***"
            elif "phone" in field.lower():
                masked[field] = f"(***) ***-{value[-4:]}" if len(value) >= 4 else "(***) ***-****"
            else:
                # Generic masking for other sensitive fields
                str_value = str(value)
                if len(str_value) > 8:
                    masked[field] = f"{str_value[:2]}{'*' * (len(str_value)-4)}{str_value[-2:]}"
                else:
                    masked[field] = "*" * len(str_value)

        return masked

    def _tokenize_sensitive_data(
        self,
        data: Dict[str, Any],
        allowed_fields: List[str]
    ) -> Dict[str, Any]:
        """Replace sensitive values with opaque tokens."""
        tokenized = {}
        for field in allowed_fields:
            if field not in data:
                continue

            # Generate deterministic token for this value
            value = data[field]
            token = hashlib.sha256(
                f"{field}:{value}:{self.secure_vault.token_salt}".encode()
            ).hexdigest()[:24]

            tokenized[field] = f"tok_{token}"

            # Store token-to-value mapping in vault for later retrieval
            self.secure_vault.store_token_mapping(token, value)

        return tokenized

    def _prepare_temporary_access(
        self,
        data: Dict[str, Any],
        allowed_fields: List[str]
    ) -> Dict[str, Any]:
        """Prepare data for temporary access with full values but limited time."""
        # Return full values but wrapped with access metadata
        return {
            "_access_metadata": {
                "type": "temporary",
                "expires": "session_end",
                "audit_required": True
            },
            "data": {k: v for k, v in data.items() if k in allowed_fields}
        }

    def _generate_ephemeral_token(self, request: AccessRequest, expires_at: datetime) -> str:
        """Generate a short-lived token for temporary access."""
        payload = {
            "agent": request.agent_id,
            "purpose": request.purpose,
            "exp": expires_at.isoformat(),
            "jti": secrets.token_urlsafe(16)
        }
        # Sign with vault's signing key
        return self.secure_vault.sign_token(payload)

    async def revoke_grant(self, grant_id: str, reason: str):
        """Revoke an active access grant."""
        if grant_id in self.active_grants:
            grant = self.active_grants.pop(grant_id)
            await self.audit_logger.log_grant_revocation(grant, reason)

    async def approve_pending_request(
        self,
        request_id: str,
        approved_by: str,
        approved_level: AccessLevel
    ) -> AccessGrant:
        """Approve a pending access request (Kublai/Temüjin only)."""
        # Find the request
        request = None
        for req in self.approval_queue:
            if req.correlation_id == request_id:
                request = req
                break

        if not request:
            raise SecurityException("Request not found in approval queue")

        # Only Kublai or Temüjin can approve
        if approved_by not in ["kublai", "temujin"]:
            raise SecurityException("Insufficient privileges for approval")

        # Create grant at approved level
        capabilities = self.AGENT_CAPABILITIES[request.agent_id]
        grant = self._create_access_grant(request, approved_level, capabilities)
        self.active_grants[grant.grant_id] = grant

        await self.audit_logger.log_approval(request, approved_by, grant)

        return grant
```

### Pattern B: API/Proxy Pattern

```python
# /src/security/secure_data_proxy.py

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, Optional
import asyncio

class SecureDataProxy:
    """
    API Proxy pattern for controlled access to sensitive data.
    Acts as a middleman between agents and secure storage.
    """

    def __init__(self, gatekeeper: TemujinGatekeeper):
        self.gatekeeper = gatekeeper
        self.app = FastAPI(title="Secure Data Proxy")
        self.security = HTTPBearer()
        self._setup_routes()

    def _setup_routes(self):
        @self.app.post("/data/request")
        async def request_data_access(
            request: DataAccessRequest,
            credentials: HTTPAuthorizationCredentials = Security(self.security)
        ):
            """Request access to sensitive data."""
            # Validate agent token
            agent_id = await self._validate_agent_token(credentials.credentials)

            access_request = AccessRequest(
                agent_id=agent_id,
                data_classification=DataClassification(request.classification),
                purpose=request.purpose,
                requested_fields=request.fields,
                correlation_id=request.correlation_id,
                timestamp=datetime.utcnow()
            )

            try:
                grant = await self.gatekeeper.request_access(access_request)
                return {
                    "grant_id": grant.grant_id,
                    "access_level": grant.access_level.value,
                    "expires_at": grant.expires_at.isoformat(),
                    "allowed_fields": grant.allowed_fields,
                    "token": grant.token
                }
            except ApprovalRequiredException:
                return {
                    "status": "pending_approval",
                    "message": "Access request submitted for approval",
                    "request_id": request.correlation_id
                }

        @self.app.post("/data/retrieve")
        async def retrieve_data(
            query: DataQuery,
            credentials: HTTPAuthorizationCredentials = Security(self.security)
        ):
            """Retrieve data using an active grant."""
            grant = await self._validate_grant_token(
                credentials.credentials,
                query.grant_id
            )

            data = await self.gatekeeper.retrieve_data(grant, query.filters)
            return {"data": data, "audit_reference": grant.audit_reference}

        @self.app.post("/data/token/exchange")
        async def exchange_token(
            token_request: TokenExchangeRequest,
            credentials: HTTPAuthorizationCredentials = Security(self.security)
        ):
            """
            Exchange a token for actual value (for operations that need real data).
            Only Ögedei with temporary access can use this.
            """
            agent_id = await self._validate_agent_token(credentials.credentials)

            if agent_id != "ogedei":
                raise HTTPException(403, "Only operations agent can exchange tokens")

            value = await self.gatekeeper.secure_vault.resolve_token(
                token_request.token
            )

            # Log the exchange
            await self.gatekeeper.audit_logger.log_token_exchange(
                token=token_request.token,
                agent_id=agent_id,
                purpose=token_request.purpose
            )

            return {"value": value}

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "service": "secure-data-proxy"}

    async def _validate_agent_token(self, token: str) -> str:
        """Validate agent JWT and return agent_id."""
        # Implementation using secure vault's verification
        pass

    async def _validate_grant_token(self, token: str, grant_id: str) -> AccessGrant:
        """Validate that token matches the grant."""
        # Implementation
        pass
```

---

## 2. DATA HANDLING PATTERNS

### Masking and Redaction System

```python
# /src/security/data_transforms.py

import re
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass

@dataclass
class FieldMask:
    """Configuration for field masking."""
    field_pattern: str  # Regex pattern to match field names
    mask_type: str      # Type of masking to apply
    preserve_chars: int = 0  # Number of chars to preserve at end
    preserve_start: int = 0  # Number of chars to preserve at start

class DataMaskingEngine:
    """Engine for applying various masking strategies to sensitive data."""

    # Predefined masking patterns
    MASK_PATTERNS = {
        "password": FieldMask(
            field_pattern=r"(?i)(password|passwd|pwd|secret)$",
            mask_type="full",
            preserve_chars=0
        ),
        "ssn": FieldMask(
            field_pattern=r"(?i)(ssn|social_security|social_security_number)$",
            mask_type="partial",
            preserve_chars=4
        ),
        "credit_card": FieldMask(
            field_pattern=r"(?i)(credit_card|card_number|cc_number|pan)$",
            mask_type="credit_card",
            preserve_chars=4
        ),
        "email": FieldMask(
            field_pattern=r"(?i)(email|email_address|mail)$",
            mask_type="email",
            preserve_chars=0
        ),
        "phone": FieldMask(
            field_pattern=r"(?i)(phone|phone_number|mobile|cell)$",
            mask_type="phone",
            preserve_chars=4
        ),
        "api_key": FieldMask(
            field_pattern=r"(?i)(api_key|apikey|api_secret|secret_key|access_key)$",
            mask_type="api_key",
            preserve_chars=4
        ),
        "token": FieldMask(
            field_pattern=r"(?i)(token|auth_token|bearer_token|jwt)$",
            mask_type="token",
            preserve_chars=4
        ),
        "pii_name": FieldMask(
            field_pattern=r"(?i)(first_name|last_name|full_name|person_name)$",
            mask_type="name",
            preserve_chars=0
        ),
        "address": FieldMask(
            field_pattern=r"(?i)(address|street|city|zip|postal_code)$",
            mask_type="partial_address",
            preserve_chars=0
        ),
        "financial": FieldMask(
            field_pattern=r"(?i)(balance|amount|salary|income|revenue)$",
            mask_type="range",
            preserve_chars=0
        )
    }

    def __init__(self, custom_patterns: Optional[Dict[str, FieldMask]] = None):
        self.patterns = {**self.MASK_PATTERNS, **(custom_patterns or {})}
        self.mask_functions: Dict[str, Callable[[Any, FieldMask], Any]] = {
            "full": self._mask_full,
            "partial": self._mask_partial,
            "credit_card": self._mask_credit_card,
            "email": self._mask_email,
            "phone": self._mask_phone,
            "api_key": self._mask_api_key,
            "token": self._mask_token,
            "name": self._mask_name,
            "partial_address": self._mask_address,
            "range": self._mask_range
        }

    def mask_data(
        self,
        data: Dict[str, Any],
        agent_id: str,
        purpose: str
    ) -> Dict[str, Any]:
        """
        Apply appropriate masking to data based on field patterns.
        """
        masked = {}

        for field, value in data.items():
            mask_config = self._get_mask_config(field)

            if mask_config:
                mask_func = self.mask_functions.get(
                    mask_config.mask_type,
                    self._mask_full
                )
                masked[field] = mask_func(value, mask_config)
            else:
                # No masking pattern matched - apply default based on value type
                masked[field] = self._apply_default_masking(value)

        return masked

    def _get_mask_config(self, field_name: str) -> Optional[FieldMask]:
        """Find matching mask configuration for a field."""
        for pattern_name, config in self.patterns.items():
            if re.match(config.field_pattern, field_name):
                return config
        return None

    def _mask_full(self, value: Any, config: FieldMask) -> str:
        """Fully mask a value."""
        str_val = str(value)
        return "*" * min(len(str_val), 16)

    def _mask_partial(self, value: Any, config: FieldMask) -> str:
        """Mask all but last N characters."""
        str_val = str(value)
        if len(str_val) <= config.preserve_chars:
            return "*" * len(str_val)
        visible = str_val[-config.preserve_chars:]
        return "*" * (len(str_val) - config.preserve_chars) + visible

    def _mask_credit_card(self, value: Any, config: FieldMask) -> str:
        """Mask credit card number."""
        str_val = re.sub(r"\D", "", str(value))  # Remove non-digits
        if len(str_val) >= 4:
            return f"****-****-****-{str_val[-4:]}"
        return "****-****-****-****"

    def _mask_email(self, value: Any, config: FieldMask) -> str:
        """Mask email address."""
        email = str(value)
        parts = email.split("@")
        if len(parts) != 2:
            return "***@***.***"

        local, domain = parts
        if len(local) <= 1:
            masked_local = "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 1)

        domain_parts = domain.split(".")
        if len(domain_parts) >= 2:
            masked_domain = domain_parts[0][0] + "***" + "." + domain_parts[-1]
        else:
            masked_domain = "***"

        return f"{masked_local}@{masked_domain}"

    def _mask_phone(self, value: Any, config: FieldMask) -> str:
        """Mask phone number."""
        digits = re.sub(r"\D", "", str(value))
        if len(digits) >= 10:
            return f"(***) ***-{digits[-4:]}"
        return "(***) ***-****"

    def _mask_api_key(self, value: Any, config: FieldMask) -> str:
        """Mask API key showing only first and last few chars."""
        str_val = str(value)
        if len(str_val) <= 8:
            return "****"
        return f"{str_val[:4]}...{str_val[-4:]}"

    def _mask_token(self, value: Any, config: FieldMask) -> str:
        """Mask authentication token."""
        str_val = str(value)
        if len(str_val) <= 12:
            return "****"
        return f"{str_val[:4]}...{str_val[-4:]}"

    def _mask_name(self, value: Any, config: FieldMask) -> str:
        """Mask person name."""
        name = str(value)
        parts = name.split()
        masked_parts = []
        for part in parts:
            if len(part) <= 2:
                masked_parts.append("*" * len(part))
            else:
                masked_parts.append(part[0] + "*" * (len(part) - 1))
        return " ".join(masked_parts)

    def _mask_address(self, value: Any, config: FieldMask) -> str:
        """Mask address components."""
        # For addresses, return a hash-based identifier
        import hashlib
        hashed = hashlib.sha256(str(value).encode()).hexdigest()[:8]
        return f"[ADDRESS-{hashed}]"

    def _mask_range(self, value: Any, config: FieldMask) -> str:
        """Mask financial amount to a range."""
        try:
            amount = float(value)
            # Round to nearest range bucket
            if amount < 1000:
                bucket = 100
            elif amount < 10000:
                bucket = 1000
            elif amount < 100000:
                bucket = 10000
            else:
                bucket = 100000

            lower = (int(amount) // bucket) * bucket
            upper = lower + bucket
            return f"${lower:,}-${upper:,}"
        except (ValueError, TypeError):
            return "[FINANCIAL-VALUE]"

    def _apply_default_masking(self, value: Any) -> Any:
        """Apply default masking for unrecognized fields."""
        if isinstance(value, str):
            # Check if it looks like sensitive data
            if len(value) > 20:  # Likely a key or token
                return f"{value[:4]}...{value[-4:]}"
        return value


class TokenizationEngine:
    """
    Engine for tokenizing sensitive data - replacing values with opaque tokens.
    """

    def __init__(self, vault):
        self.vault = vault
        self.token_cache: Dict[str, str] = {}  # value_hash -> token
        self.reverse_cache: Dict[str, str] = {}  # token -> value_hash

    async def tokenize(self, value: Any, context: str) -> str:
        """
        Convert a sensitive value to an opaque token.
        """
        value_str = str(value)
        value_hash = hashlib.sha256(value_str.encode()).hexdigest()

        # Check if already tokenized
        if value_hash in self.token_cache:
            return self.token_cache[value_hash]

        # Generate new token
        token = f"tok_{secrets.token_urlsafe(24)}"

        # Store mapping in vault
        await self.vault.store_token_mapping(
            token=token,
            value_hash=value_hash,
            encrypted_value=await self.vault.encrypt(value_str),
            context=context
        )

        # Update caches
        self.token_cache[value_hash] = token
        self.reverse_cache[token] = value_hash

        return token

    async def detokenize(self, token: str, agent_id: str, purpose: str) -> Any:
        """
        Convert a token back to its original value.
        Requires proper authorization and is fully audited.
        """
        # Verify agent has permission to detokenize
        if not await self._can_detokenize(agent_id, token):
            raise SecurityException(f"Agent {agent_id} cannot detokenize")

        # Retrieve from vault
        mapping = await self.vault.get_token_mapping(token)
        if not mapping:
            raise SecurityException("Invalid or expired token")

        # Decrypt value
        value = await self.vault.decrypt(mapping["encrypted_value"])

        # Log the detokenization
        await self.vault.audit_logger.log_detokenization(
            token=token,
            agent_id=agent_id,
            purpose=purpose,
            context=mapping["context"]
        )

        return value

    async def _can_detokenize(self, agent_id: str, token: str) -> bool:
        """Check if agent is authorized to detokenize."""
        # Only Kublai, Temüjin, and Ögedei (for operations) can detokenize
        allowed_agents = ["kublai", "temujin", "ogedei"]
        return agent_id in allowed_agents
```

### Temporary Access Grant System

```python
# /src/security/temporary_access.py

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
import secrets

class TemporaryAccessManager:
    """
    Manages time-limited access grants for sensitive operations.
    Used primarily by Ögedei for executing operations with sensitive data.
    """

    def __init__(self, gatekeeper: TemujinGatekeeper, audit_logger):
        self.gatekeeper = gatekeeper
        self.audit_logger = audit_logger
        self.active_sessions: Dict[str, TemporarySession] = {}
        self.cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the cleanup background task."""
        self.cleanup_task = asyncio.create_task(self._cleanup_expired())

    async def create_temporary_session(
        self,
        agent_id: str,
        operation_type: str,
        required_data: List[str],
        duration: timedelta = timedelta(minutes=5)
    ) -> TemporarySession:
        """
        Create a temporary session for sensitive operations.
        Only Ögedei (operations) should typically use this.
        """
        if agent_id != "ogedei":
            raise SecurityException(
                f"Agent {agent_id} not authorized for temporary sessions"
            )

        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + duration

        # Request access through gatekeeper
        access_request = AccessRequest(
            agent_id=agent_id,
            data_classification=DataClassification.RESTRICTED,
            purpose=f"temporary_session:{operation_type}",
            requested_fields=required_data,
            correlation_id=session_id,
            timestamp=datetime.utcnow()
        )

        grant = await self.gatekeeper.request_access(access_request)

        session = TemporarySession(
            session_id=session_id,
            agent_id=agent_id,
            operation_type=operation_type,
            grant=grant,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            data_cache={}
        )

        self.active_sessions[session_id] = session

        await self.audit_logger.log_session_created(session)

        return session

    async def execute_with_temporary_access(
        self,
        session_id: str,
        operation: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute an operation with temporary access to sensitive data.
        Data is automatically cleared after operation completes.
        """
        session = self.active_sessions.get(session_id)
        if not session:
            raise SecurityException("Invalid or expired session")

        if datetime.utcnow() > session.expires_at:
            await self._destroy_session(session_id, "expired")
            raise SecurityException("Session has expired")

        try:
            # Load required data into session cache
            await self._load_session_data(session)

            # Execute operation with access to cached data
            result = await operation(
                *args,
                sensitive_data=session.data_cache,
                **kwargs
            )

            await self.audit_logger.log_operation_completed(
                session=session,
                success=True
            )

            return result

        except Exception as e:
            await self.audit_logger.log_operation_completed(
                session=session,
                success=False,
                error=str(e)
            )
            raise

        finally:
            # Always clear sensitive data from cache
            session.data_cache.clear()

    async def _load_session_data(self, session: TemporarySession):
        """Load sensitive data into session cache."""
        data = await self.gatekeeper.retrieve_data(
            session.grant,
            {"fields": session.grant.allowed_fields}
        )
        session.data_cache = data

    async def _destroy_session(self, session_id: str, reason: str):
        """Destroy a temporary session and revoke its grant."""
        session = self.active_sessions.pop(session_id, None)
        if session:
            await self.gatekeeper.revoke_grant(session.grant.grant_id, reason)
            await self.audit_logger.log_session_destroyed(session, reason)

    async def _cleanup_expired(self):
        """Background task to clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute

            now = datetime.utcnow()
            expired = [
                sid for sid, session in self.active_sessions.items()
                if now > session.expires_at
            ]

            for session_id in expired:
                await self._destroy_session(session_id, "expired_cleanup")


@dataclass
class TemporarySession:
    """Represents a temporary access session."""
    session_id: str
    agent_id: str
    operation_type: str
    grant: AccessGrant
    created_at: datetime
    expires_at: datetime
    data_cache: Dict[str, Any]
```

---

## 3. AUDIT & MONITORING

### Comprehensive Audit System

```python
# /src/security/audit_system.py

from datetime import datetime
from typing import Dict, Any, List, Optional
from enum import Enum
import json
import hashlib

class AuditEventType(Enum):
    # Access events
    ACCESS_ATTEMPT = "access_attempt"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    ACCESS_REVOKED = "access_revoked"

    # Data events
    DATA_RETRIEVED = "data_retrieved"
    DATA_MASKED = "data_masked"
    DATA_TOKENIZED = "data_tokenized"
    DATA_DETOKENIZED = "data_detokenized"

    # Session events
    SESSION_CREATED = "session_created"
    SESSION_DESTROYED = "session_destroyed"
    SESSION_EXPIRED = "session_expired"

    # Approval events
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    # Security events
    SECURITY_VIOLATION = "security_violation"
    ANOMALY_DETECTED = "anomaly_detected"
    UNAUTHORIZED_ATTEMPT = "unauthorized_attempt"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"

    # Operation events
    OPERATION_STARTED = "operation_started"
    OPERATION_COMPLETED = "operation_completed"
    OPERATION_FAILED = "operation_failed"


class AuditLogger:
    """
    Comprehensive audit logging for all sensitive data access.
    Immutable, tamper-evident logging with compliance reporting.
    """

    def __init__(self, storage_backend, alert_manager):
        self.storage = storage_backend
        self.alert_manager = alert_manager
        self.event_chain_hash: Optional[str] = None  # For tamper detection

    async def log_access_attempt(self, request: AccessRequest):
        """Log an access attempt."""
        event = AuditEvent(
            event_type=AuditEventType.ACCESS_ATTEMPT,
            timestamp=datetime.utcnow(),
            agent_id=request.agent_id,
            correlation_id=request.correlation_id,
            details={
                "data_classification": request.data_classification.value,
                "purpose": request.purpose,
                "requested_fields": request.requested_fields
            }
        )
        await self._persist_event(event)

    async def log_access_granted(self, request: AccessRequest, grant: AccessGrant):
        """Log successful access grant."""
        event = AuditEvent(
            event_type=AuditEventType.ACCESS_GRANTED,
            timestamp=datetime.utcnow(),
            agent_id=request.agent_id,
            correlation_id=request.correlation_id,
            details={
                "grant_id": grant.grant_id,
                "access_level": grant.access_level.value,
                "allowed_fields": grant.allowed_fields,
                "expires_at": grant.expires_at.isoformat(),
                "audit_reference": grant.audit_reference
            }
        )
        await self._persist_event(event)

    async def log_data_retrieval(
        self,
        grant: AccessGrant,
        query: Dict[str, Any],
        fields_accessed: List[str]
    ):
        """Log data retrieval with field-level tracking."""
        event = AuditEvent(
            event_type=AuditEventType.DATA_RETRIEVED,
            timestamp=datetime.utcnow(),
            agent_id=grant.grant_id,  # Reference to grant for traceability
            correlation_id=grant.audit_reference,
            details={
                "grant_id": grant.grant_id,
                "access_level": grant.access_level.value,
                "fields_accessed": fields_accessed,
                "query_hash": hashlib.sha256(
                    json.dumps(query, sort_keys=True).encode()
                ).hexdigest()[:16]
            }
        )
        await self._persist_event(event)

    async def log_security_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        severity: str = "warning"
    ):
        """Log security-related events."""
        event = AuditEvent(
            event_type=AuditEventType.SECURITY_VIOLATION,
            timestamp=datetime.utcnow(),
            agent_id=details.get("agent_id", "unknown"),
            correlation_id=details.get("correlation_id", "none"),
            details={
                "violation_type": event_type,
                **details
            },
            severity=severity
        )
        await self._persist_event(event)

        # Trigger alerts for high-severity events
        if severity in ["high", "critical"]:
            await self.alert_manager.send_alert(
                alert_type="security_violation",
                event=event
            )

    async def log_detokenization(
        self,
        token: str,
        agent_id: str,
        purpose: str,
        context: str
    ):
        """Log detokenization (reversal of tokenization)."""
        event = AuditEvent(
            event_type=AuditEventType.DATA_DETOKENIZED,
            timestamp=datetime.utcnow(),
            agent_id=agent_id,
            correlation_id=token[:16],
            details={
                "token_prefix": token[:8],
                "purpose": purpose,
                "context": context
            },
            severity="high"  # Always high severity - sensitive operation
        )
        await self._persist_event(event)

    async def _persist_event(self, event: AuditEvent):
        """Persist event with tamper-evident chaining."""
        # Create event hash including previous chain hash
        event_data = {
            "event_type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "agent_id": event.agent_id,
            "correlation_id": event.correlation_id,
            "details": event.details,
            "severity": event.severity,
            "previous_hash": self.event_chain_hash
        }

        event_hash = hashlib.sha256(
            json.dumps(event_data, sort_keys=True).encode()
        ).hexdigest()

        self.event_chain_hash = event_hash

        # Store with hash
        await self.storage.store({
            **event_data,
            "event_hash": event_hash
        })


class AnomalyDetector:
    """
    Real-time anomaly detection for sensitive data access patterns.
    """

    def __init__(self, audit_logger: AuditLogger):
        self.audit_logger = audit_logger
        self.baseline_stats: Dict[str, Any] = {}
        self.recent_events: List[AuditEvent] = []
        self.max_events_window = 1000

    async def analyze_event(self, event: AuditEvent):
        """Analyze an event for anomalies."""
        self.recent_events.append(event)
        if len(self.recent_events) > self.max_events_window:
            self.recent_events.pop(0)

        anomalies = []

        # Check for rate anomalies
        rate_anomaly = self._check_rate_anomaly(event)
        if rate_anomaly:
            anomalies.append(rate_anomaly)

        # Check for access pattern anomalies
        pattern_anomaly = self._check_pattern_anomaly(event)
        if pattern_anomaly:
            anomalies.append(pattern_anomaly)

        # Check for time-based anomalies
        time_anomaly = self._check_time_anomaly(event)
        if time_anomaly:
            anomalies.append(time_anomaly)

        # Check for agent behavior anomalies
        behavior_anomaly = self._check_behavior_anomaly(event)
        if behavior_anomaly:
            anomalies.append(behavior_anomaly)

        if anomalies:
            await self.audit_logger.log_security_event(
                event_type="ANOMALY_DETECTED",
                details={
                    "triggering_event": event.event_type.value,
                    "anomalies": anomalies,
                    "agent_id": event.agent_id
                },
                severity="high"
            )

        return anomalies

    def _check_rate_anomaly(self, event: AuditEvent) -> Optional[Dict]:
        """Check for unusual access rates."""
        agent_id = event.agent_id
        window_start = datetime.utcnow() - timedelta(minutes=5)

        recent_accesses = [
            e for e in self.recent_events
            if e.agent_id == agent_id
            and e.timestamp > window_start
            and e.event_type in [
                AuditEventType.ACCESS_ATTEMPT,
                AuditEventType.DATA_RETRIEVED
            ]
        ]

        # Baseline: max 20 accesses per 5 minutes for most agents
        baseline = 20 if agent_id != "kublai" else 100

        if len(recent_accesses) > baseline * 2:  # 2x baseline = anomaly
            return {
                "type": "rate_anomaly",
                "description": f"Agent {agent_id} made {len(recent_accesses)} "
                              f"access attempts in 5 minutes (baseline: {baseline})",
                "severity": "medium"
            }

        return None

    def _check_pattern_anomaly(self, event: AuditEvent) -> Optional[Dict]:
        """Check for unusual access patterns."""
        if event.event_type != AuditEventType.DATA_RETRIEVED:
            return None

        agent_id = event.agent_id

        # Check for bulk access (many fields at once)
        fields_accessed = event.details.get("fields_accessed", [])
        if len(fields_accessed) > 10:
            return {
                "type": "bulk_access",
                "description": f"Agent {agent_id} accessed {len(fields_accessed)} "
                              f"fields in single request",
                "severity": "low"
            }

        # Check for sensitive field combinations
        sensitive_combinations = [
            {"ssn", "date_of_birth", "address"},  # Identity theft pattern
            {"credit_card", "cvv", "expiry"},      # Card fraud pattern
            {"password", "email"}                   # Account takeover pattern
        ]

        accessed_set = set(fields_accessed)
        for combo in sensitive_combinations:
            if combo.issubset(accessed_set):
                return {
                    "type": "sensitive_combination",
                    "description": f"Agent {agent_id} accessed potentially "
                                  f"dangerous field combination: {combo}",
                    "severity": "high"
                }

        return None

    def _check_time_anomaly(self, event: AuditEvent) -> Optional[Dict]:
        """Check for unusual access times."""
        hour = event.timestamp.hour

        # Flag access outside business hours for non-Kublai agents
        if event.agent_id != "kublai" and (hour < 6 or hour > 22):
            return {
                "type": "off_hours_access",
                "description": f"Agent {event.agent_id} accessed data at "
                              f"{event.timestamp.isoformat()}",
                "severity": "low"
            }

        return None

    def _check_behavior_anomaly(self, event: AuditEvent) -> Optional[Dict]:
        """Check for unusual agent behavior."""
        agent_id = event.agent_id

        # Check for rapid classification escalation
        recent_classifications = []
        for e in self.recent_events[-20:]:
            if e.agent_id == agent_id and "data_classification" in e.details:
                recent_classifications.append(e.details["data_classification"])

        # If agent suddenly accessing higher classification than usual
        if len(recent_classifications) >= 3:
            recent_set = set(recent_classifications[-3:])
            earlier_set = set(recent_classifications[:-3]) if len(recent_classifications) > 3 else set()

            if recent_set - earlier_set and earlier_set:
                new_access = recent_set - earlier_set
                return {
                    "type": "classification_escalation",
                    "description": f"Agent {agent_id} accessing new classification "
                                  f"levels: {new_access}",
                    "severity": "medium"
                }

        return None


class ComplianceReporter:
    """
    Generate compliance reports for audits and regulatory requirements.
    """

    def __init__(self, audit_storage):
        self.storage = audit_storage

    async def generate_access_report(
        self,
        start_date: datetime,
        end_date: datetime,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a report of all sensitive data access."""
        events = await self.storage.query_events(
            event_types=[
                AuditEventType.ACCESS_GRANTED,
                AuditEventType.DATA_RETRIEVED,
                AuditEventType.DATA_DETOKENIZED
            ],
            start_date=start_date,
            end_date=end_date,
            agent_id=agent_id
        )

        report = {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_access_events": len(events),
                "unique_agents": len(set(e.agent_id for e in events)),
                "detokenization_events": len([
                    e for e in events
                    if e.event_type == AuditEventType.DATA_DETOKENIZED
                ])
            },
            "agent_breakdown": {},
            "classification_breakdown": {},
            "events": []
        }

        for event in events:
            # Agent breakdown
            if event.agent_id not in report["agent_breakdown"]:
                report["agent_breakdown"][event.agent_id] = 0
            report["agent_breakdown"][event.agent_id] += 1

            # Classification breakdown
            classification = event.details.get("data_classification", "unknown")
            if classification not in report["classification_breakdown"]:
                report["classification_breakdown"][classification] = 0
            report["classification_breakdown"][classification] += 1

            # Event details
            report["events"].append({
                "timestamp": event.timestamp.isoformat(),
                "agent": event.agent_id,
                "type": event.event_type.value,
                "classification": classification,
                "correlation_id": event.correlation_id
            })

        return report

    async def generate_security_report(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Generate a security-focused report."""
        events = await self.storage.query_events(
            event_types=[
                AuditEventType.SECURITY_VIOLATION,
                AuditEventType.ANOMALY_DETECTED,
                AuditEventType.UNAUTHORIZED_ATTEMPT,
                AuditEventType.ACCESS_DENIED
            ],
            start_date=start_date,
            end_date=end_date
        )

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "security_summary": {
                "total_violations": len(events),
                "by_severity": self._group_by_severity(events),
                "by_type": self._group_by_type(events)
            },
            "violations": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "type": e.event_type.value,
                    "severity": e.severity,
                    "agent": e.agent_id,
                    "details": e.details
                }
                for e in events
            ]
        }

    def _group_by_severity(self, events: List[AuditEvent]) -> Dict[str, int]:
        """Group events by severity."""
        severity_counts = {}
        for e in events:
            sev = e.severity
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        return severity_counts

    def _group_by_type(self, events: List[AuditEvent]) -> Dict[str, int]:
        """Group events by type."""
        type_counts = {}
        for e in events:
            t = e.event_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return type_counts
```

---

## 4. AGENT BOUNDARIES

### Capability-Based Access Control

```python
# /src/security/agent_boundaries.py

from enum import Enum, auto
from typing import Dict, Set, List, Optional, Callable
from dataclasses import dataclass
import asyncio

class Capability(Enum):
    """Capabilities that can be granted to agents."""
    # Data access capabilities
    READ_PUBLIC = auto()
    READ_INTERNAL = auto()
    READ_CONFIDENTIAL = auto()
    READ_RESTRICTED_MASKED = auto()
    READ_RESTRICTED_FULL = auto()
    READ_CRITICAL_TOKENIZED = auto()
    READ_CRITICAL_FULL = auto()

    # Data transformation capabilities
    MASK_DATA = auto()
    TOKENIZE_DATA = auto()
    DETOKENIZE_DATA = auto()

    # Operation capabilities
    EXECUTE_OPERATION = auto()
    CREATE_TEMPORARY_SESSION = auto()
    APPROVE_ACCESS_REQUESTS = auto()

    # System capabilities
    AUDIT_LOG_ACCESS = auto()
    SECURITY_POLICY_MODIFY = auto()
    AGENT_CAPABILITY_GRANT = auto()


@dataclass(frozen=True)
class AgentIdentity:
    """Immutable agent identity with cryptographic verification."""
    agent_id: str
    public_key: str
    capabilities: Set[Capability]
    max_classification: DataClassification
    created_at: str
    signature: str  # Signed by system authority

    def has_capability(self, capability: Capability) -> bool:
        return capability in self.capabilities

    def verify(self, authority_public_key: str) -> bool:
        """Verify the identity signature."""
        # Cryptographic verification implementation
        pass


class AgentBoundaryEnforcer:
    """
    Enforces strict boundaries between agents using capability-based access control.
    """

    def __init__(self, gatekeeper: TemujinGatekeeper):
        self.gatekeeper = gatekeeper
        self.registered_agents: Dict[str, AgentIdentity] = {}
        self.message_router = SecureMessageRouter()
        self.boundary_callbacks: Dict[str, List[Callable]] = {}

    def register_agent(self, identity: AgentIdentity):
        """Register an agent with the boundary system."""
        self.registered_agents[identity.agent_id] = identity

    async def enforce_boundary(
        self,
        source_agent: str,
        target_agent: str,
        message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Enforce boundaries when one agent communicates with another.
        Returns sanitized message or None if blocked.
        """
        source = self.registered_agents.get(source_agent)
        target = self.registered_agents.get(target_agent)

        if not source or not target:
            raise SecurityException(f"Unknown agent in communication: {source_agent} -> {target_agent}")

        # Check if message contains sensitive data
        contains_sensitive = self._detect_sensitive_data(message)

        if contains_sensitive:
            # Validate source has right to share this data
            if not self._can_share_sensitive(source, message):
                await self.gatekeeper.audit_logger.log_security_event(
                    event_type="BOUNDARY_VIOLATION",
                    details={
                        "source": source_agent,
                        "target": target_agent,
                        "violation": "unauthorized_sensitive_sharing"
                    },
                    severity="high"
                )
                raise SecurityException(
                    f"Agent {source_agent} cannot share sensitive data with {target_agent}"
                )

            # Sanitize message for target's clearance level
            sanitized = await self._sanitize_for_target(message, target)

            # Log the data sharing
            await self.gatekeeper.audit_logger.log_security_event(
                event_type="SENSITIVE_DATA_SHARED",
                details={
                    "source": source_agent,
                    "target": target_agent,
                    "fields_shared": list(sanitized.keys())
                },
                severity="medium"
            )

            return sanitized

        return message

    def _detect_sensitive_data(self, message: Dict[str, Any]) -> bool:
        """Detect if message contains sensitive data."""
        sensitive_indicators = [
            "password", "secret", "key", "token", "ssn", "credit_card",
            "pii", "phi", "financial", "restricted", "confidential"
        ]

        message_str = str(message).lower()
        return any(indicator in message_str for indicator in sensitive_indicators)

    def _can_share_sensitive(self, source: AgentIdentity, message: Dict[str, Any]) -> bool:
        """Check if source agent is authorized to share sensitive data."""
        # Only Kublai and Temüjin can share sensitive data
        return source.agent_id in ["kublai", "temujin"]

    async def _sanitize_for_target(
        self,
        message: Dict[str, Any],
        target: AgentIdentity
    ) -> Dict[str, Any]:
        """Sanitize message content based on target agent's capabilities."""
        sanitized = {}

        for key, value in message.items():
            # Determine classification of this field
            classification = self._classify_field(key, value)

            # Check if target can receive this classification
            if classification.value <= target.max_classification.value:
                # Apply appropriate masking based on target's capabilities
                if classification in [DataClassification.RESTRICTED, DataClassification.CRITICAL]:
                    if Capability.READ_RESTRICTED_FULL in target.capabilities:
                        sanitized[key] = value
                    elif Capability.READ_RESTRICTED_MASKED in target.capabilities:
                        sanitized[key] = self._mask_value(key, value)
                    else:
                        sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = value
            else:
                sanitized[key] = "[CLASSIFICATION_TOO_HIGH]"

        return sanitized

    def _classify_field(self, key: str, value: Any) -> DataClassification:
        """Determine classification of a field."""
        key_lower = key.lower()

        critical_patterns = ["password", "secret_key", "master_key", "private_key"]
        if any(p in key_lower for p in critical_patterns):
            return DataClassification.CRITICAL

        restricted_patterns = ["ssn", "credit_card", "pii", "dob", "address"]
        if any(p in key_lower for p in restricted_patterns):
            return DataClassification.RESTRICTED

        confidential_patterns = ["financial", "revenue", "salary", "strategy"]
        if any(p in key_lower for p in confidential_patterns):
            return DataClassification.CONFIDENTIAL

        return DataClassification.INTERNAL

    def _mask_value(self, key: str, value: Any) -> str:
        """Apply basic masking to a value."""
        str_val = str(value)
        if len(str_val) <= 4:
            return "****"
        return f"{str_val[:2]}...{str_val[-2:]}"


class SecureMessageRouter:
    """
    Routes messages between agents with boundary enforcement.
    """

    def __init__(self):
        self.routes: Dict[str, Set[str]] = {}  # agent -> allowed destinations
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.boundary_enforcer: Optional[AgentBoundaryEnforcer] = None

    def set_boundary_enforcer(self, enforcer: AgentBoundaryEnforcer):
        self.boundary_enforcer = enforcer

    def define_route(self, source: str, allowed_targets: List[str]):
        """Define allowed message routes from a source agent."""
        self.routes[source] = set(allowed_targets)

    async def send_message(
        self,
        source: str,
        target: str,
        message: Dict[str, Any],
        message_type: str = "standard"
    ) -> bool:
        """
        Send a message from source to target with all security checks.
        """
        # Check route is allowed
        if target not in self.routes.get(source, set()):
            raise SecurityException(
                f"Route not allowed: {source} -> {target}"
            )

        # Enforce boundaries if enforcer is configured
        if self.boundary_enforcer:
            sanitized = await self.boundary_enforcer.enforce_boundary(
                source, target, message
            )
        else:
            sanitized = message

        # Wrap message with security metadata
        secure_message = SecureMessage(
            source=source,
            target=target,
            payload=sanitized,
            message_type=message_type,
            timestamp=datetime.utcnow().isoformat(),
            integrity_hash=self._compute_hash(sanitized)
        )

        await self.message_queue.put(secure_message)
        return True

    def _compute_hash(self, payload: Dict[str, Any]) -> str:
        """Compute integrity hash for message."""
        import hashlib
        import json
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]


@dataclass
class SecureMessage:
    """A message with security metadata."""
    source: str
    target: str
    payload: Dict[str, Any]
    message_type: str
    timestamp: str
    integrity_hash: str


class AgentSandbox:
    """
    Sandbox environment for executing agent code with restricted access.
    """

    def __init__(self, agent_id: str, allowed_capabilities: Set[Capability]):
        self.agent_id = agent_id
        self.allowed_capabilities = allowed_capabilities
        self.data_access_log: List[Dict] = []
        self.execution_context: Dict[str, Any] = {}

    async def execute(
        self,
        code: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute agent code in a restricted sandbox.
        """
        # Create restricted execution environment
        restricted_globals = {
            "__builtins__": self._get_restricted_builtins(),
            "context": self._sanitize_context(context),
            "log_access": self._log_data_access,
            "request_data": self._create_data_request_proxy(),
        }

        # Execute with timeout and resource limits
        try:
            result = await self._run_with_limits(code, restricted_globals)
            return {
                "success": True,
                "result": result,
                "access_log": self.data_access_log
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "access_log": self.data_access_log
            }

    def _get_restricted_builtins(self) -> Dict[str, Any]:
        """Get restricted builtins for sandbox."""
        safe_builtins = {
            "len", "range", "enumerate", "zip", "map", "filter",
            "sum", "min", "max", "abs", "round", "str", "int",
            "float", "bool", "list", "dict", "set", "tuple"
        }
        return {name: __builtins__[name] for name in safe_builtins}

    def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive data from execution context."""
        sanitized = {}
        for key, value in context.items():
            # Only include non-sensitive context
            if not self._is_sensitive_key(key):
                sanitized[key] = value
        return sanitized

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key indicates sensitive data."""
        sensitive = ["password", "secret", "key", "token", "credential"]
        return any(s in key.lower() for s in sensitive)

    def _log_data_access(self, field: str, purpose: str):
        """Log data access within sandbox."""
        self.data_access_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "field": field,
            "purpose": purpose,
            "agent": self.agent_id
        })

    def _create_data_request_proxy(self):
        """Create a proxy for data requests that enforces capabilities."""
        async def request_data(field: str, classification: str) -> Any:
            # Check capability
            required_cap = self._capability_for_classification(classification)
            if required_cap not in self.allowed_capabilities:
                raise SecurityException(
                    f"Agent {self.agent_id} lacks capability: {required_cap}"
                )

            self._log_data_access(field, "sandbox_request")

            # Request through gatekeeper
            # Implementation would call gatekeeper
            return f"[DATA:{field}]"

        return request_data

    def _capability_for_classification(self, classification: str) -> Capability:
        """Map classification to required capability."""
        mapping = {
            "public": Capability.READ_PUBLIC,
            "internal": Capability.READ_INTERNAL,
            "confidential": Capability.READ_CONFIDENTIAL,
            "restricted": Capability.READ_RESTRICTED_MASKED,
            "critical": Capability.READ_CRITICAL_TOKENIZED
        }
        return mapping.get(classification, Capability.READ_PUBLIC)

    async def _run_with_limits(self, code: str, globals_dict: Dict) -> Any:
        """Run code with resource and time limits."""
        import asyncio

        # Set execution timeout
        try:
            return await asyncio.wait_for(
                self._execute_code(code, globals_dict),
                timeout=30  # 30 second limit
            )
        except asyncio.TimeoutError:
            raise SecurityException("Sandbox execution timeout")

    async def _execute_code(self, code: str, globals_dict: Dict) -> Any:
        """Execute code in restricted environment."""
        # Use exec with restricted globals
        locals_dict = {}
        exec(code, globals_dict, locals_dict)
        return locals_dict.get("result", None)
```

---

## 5. INTEGRATION EXAMPLE

### Complete Orchestration Flow

```python
# /src/security/orchestration_example.py

async def example_sensitive_data_flow():
    """
    Example showing the complete flow of sensitive data handling
    in the multi-agent system.
    """

    # Initialize components
    audit_logger = AuditLogger(storage_backend, alert_manager)
    anomaly_detector = AnomalyDetector(audit_logger)
    secure_vault = SecureVault(encryption_key)
    gatekeeper = TemujinGatekeeper(audit_logger, secure_vault)
    temp_access = TemporaryAccessManager(gatekeeper, audit_logger)
    boundary_enforcer = AgentBoundaryEnforcer(gatekeeper)

    # Register agents with capabilities
    agents = {
        "kublai": AgentIdentity(
            agent_id="kublai",
            public_key="kublai_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL,
                Capability.READ_CONFIDENTIAL, Capability.READ_RESTRICTED_FULL,
                Capability.READ_CRITICAL_FULL, Capability.MASK_DATA,
                Capability.TOKENIZE_DATA, Capability.DETOKENIZE_DATA,
                Capability.APPROVE_ACCESS_REQUESTS, Capability.AUDIT_LOG_ACCESS
            },
            max_classification=DataClassification.CRITICAL,
            created_at="2024-01-01",
            signature="signed_by_authority"
        ),
        "temujin": AgentIdentity(
            agent_id="temujin",
            public_key="temujin_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL,
                Capability.READ_CONFIDENTIAL, Capability.READ_RESTRICTED_FULL,
                Capability.READ_CRITICAL_FULL, Capability.MASK_DATA,
                Capability.TOKENIZE_DATA, Capability.APPROVE_ACCESS_REQUESTS
            },
            max_classification=DataClassification.CRITICAL,
            created_at="2024-01-01",
            signature="signed_by_authority"
        ),
        "mongke": AgentIdentity(
            agent_id="mongke",
            public_key="mongke_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL
            },
            max_classification=DataClassification.INTERNAL,
            created_at="2024-01-01",
            signature="signed_by_authority"
        ),
        "chagatai": AgentIdentity(
            agent_id="chagatai",
            public_key="chagatai_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL,
                Capability.READ_CONFIDENTIAL, Capability.READ_RESTRICTED_MASKED,
                Capability.MASK_DATA, Capability.TOKENIZE_DATA
            },
            max_classification=DataClassification.CONFIDENTIAL,
            created_at="2024-01-01",
            signature="signed_by_authority"
        ),
        "jochi": AgentIdentity(
            agent_id="jochi",
            public_key="jochi_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL,
                Capability.READ_RESTRICTED_MASKED
            },
            max_classification=DataClassification.RESTRICTED,
            created_at="2024-01-01",
            signature="signed_by_authority"
        ),
        "ogedei": AgentIdentity(
            agent_id="ogedei",
            public_key="ogedei_pub_key",
            capabilities={
                Capability.READ_PUBLIC, Capability.READ_INTERNAL,
                Capability.READ_CONFIDENTIAL, Capability.READ_RESTRICTED_MASKED,
                Capability.CREATE_TEMPORARY_SESSION, Capability.EXECUTE_OPERATION
            },
            max_classification=DataClassification.CONFIDENTIAL,
            created_at="2024-01-01",
            signature="signed_by_authority"
        )
    }

    for agent in agents.values():
        boundary_enforcer.register_agent(agent)

    # Define message routes
    router = SecureMessageRouter()
    router.set_boundary_enforcer(boundary_enforcer)

    # Kublai can communicate with all agents
    router.define_route("kublai", ["temujin", "mongke", "chagatai", "jochi", "ogedei"])
    # Temüjin can communicate with Kublai and Ögedei (for security ops)
    router.define_route("temujin", ["kublai", "ogedei"])
    # Other agents can only communicate with Kublai
    router.define_route("mongke", ["kublai"])
    router.define_route("chagatai", ["kublai"])
    router.define_route("jochi", ["kublai"])
    router.define_route("ogedei", ["kublai", "temujin"])

    # Example 1: Kublai needs user password during conversation
    print("=== Example 1: Kublai accessing critical data ===")

    kublai_request = AccessRequest(
        agent_id="kublai",
        data_classification=DataClassification.CRITICAL,
        purpose="user_authentication_verification",
        requested_fields=["password_hash", "mfa_secret"],
        correlation_id="conv_12345",
        timestamp=datetime.utcnow()
    )

    grant = await gatekeeper.request_access(kublai_request)
    print(f"Kublai granted {grant.access_level.name} access until {grant.expires_at}")

    # Retrieve the data
    user_data = await gatekeeper.retrieve_data(
        grant,
        {"user_id": "user_123", "fields": ["password_hash", "mfa_secret"]}
    )
    print(f"Kublai retrieved: {user_data}")

    # Example 2: Chagatai needs to synthesize report with financial data
    print("\n=== Example 2: Chagatai accessing confidential data ===")

    chagatai_request = AccessRequest(
        agent_id="chagatai",
        data_classification=DataClassification.CONFIDENTIAL,
        purpose="financial_report_synthesis",
        requested_fields=["revenue", "expenses", "profit_margin"],
        correlation_id="report_67890",
        timestamp=datetime.utcnow()
    )

    chagatai_grant = await gatekeeper.request_access(chagatai_request)
    print(f"Chagatai granted {chagatai_grant.access_level.name} access")

    financial_data = await gatekeeper.retrieve_data(
        chagatai_grant,
        {"report_id": "q4_2024", "fields": ["revenue", "expenses", "profit_margin"]}
    )
    print(f"Chagatai retrieved (tokenized): {financial_data}")

    # Example 3: Ögedei needs to execute API call with credentials
    print("\n=== Example 3: Ögedei temporary access for operation ===")

    session = await temp_access.create_temporary_session(
        agent_id="ogedei",
        operation_type="api_payment_processing",
        required_data=["api_key", "merchant_id"],
        duration=timedelta(minutes=2)
    )
    print(f"Created temporary session: {session.session_id}")

    async def process_payment(sensitive_data, amount, recipient):
        """Operation that needs real API credentials."""
        api_key = sensitive_data.get("api_key")
        merchant_id = sensitive_data.get("merchant_id")

        # In real implementation, make API call
        print(f"Processing payment with merchant {merchant_id}")
        return {"status": "success", "transaction_id": "txn_123"}

    result = await temp_access.execute_with_temporary_access(
        session.session_id,
        process_payment,
        amount=100.00,
        recipient="vendor_456"
    )
    print(f"Operation result: {result}")

    # Example 4: Attempted unauthorized access by Mongke
    print("\n=== Example 4: Unauthorized access attempt ===")

    try:
        mongke_request = AccessRequest(
            agent_id="mongke",
            data_classification=DataClassification.RESTRICTED,
            purpose="research_user_data",
            requested_fields=["ssn", "date_of_birth"],
            correlation_id="research_999",
            timestamp=datetime.utcnow()
        )

        await gatekeeper.request_access(mongke_request)
    except SecurityException as e:
        print(f"Access denied as expected: {e}")

    # Example 5: Secure message routing with boundary enforcement
    print("\n=== Example 5: Secure message routing ===")

    # Kublai sends sensitive data to Chagatai for synthesis
    sensitive_message = {
        "task": "synthesize_financial_summary",
        "user_email": "ceo@company.com",
        "financial_data": {
            "revenue": 1000000,
            "expenses": 750000,
            "profit_margin": 0.25
        }
    }

    success = await router.send_message(
        source="kublai",
        target="chagatai",
        message=sensitive_message,
        message_type="task_assignment"
    )
    print(f"Message sent successfully: {success}")

    # Attempt unauthorized sensitive data sharing (Mongke trying to share with Jochi)
    print("\n=== Example 6: Blocked unauthorized data sharing ===")

    try:
        await router.send_message(
            source="mongke",
            target="jochi",
            message={
                "found_this_data": "some_sensitive_info_12345"
            }
        )
    except SecurityException as e:
        print(f"Route blocked as expected: {e}")

    # Generate compliance report
    print("\n=== Compliance Report ===")

    reporter = ComplianceReporter(audit_logger.storage)
    report = await reporter.generate_access_report(
        start_date=datetime.utcnow() - timedelta(hours=1),
        end_date=datetime.utcnow()
    )
    print(f"Access events: {report['summary']['total_access_events']}")
    print(f"Agent breakdown: {report['agent_breakdown']}")


if __name__ == "__main__":
    asyncio.run(example_sensitive_data_flow())
```

---

## Summary

### Recommended Architecture

1. **Security Agent (Temüjin) as Gatekeeper**: All sensitive data access flows through Temüjin. No agent accesses the secure database directly.

2. **Capability-Based Access Control**: Each agent has explicitly defined capabilities. Access is granted based on these capabilities, not just identity.

3. **Tiered Data Access**:
   - **Kublai**: Full access during active sessions
   - **Chagatai**: Tokenized/masked access for synthesis
   - **Jochi**: Masked access for analysis
   - **Möngke**: No sensitive data access (public/internal only)
   - **Ögedei**: Temporary access for operations

4. **Data Transformation Pipeline**:
   - Full -> Masked -> Tokenized -> None
   - Automatic application based on agent clearance

5. **Comprehensive Audit Trail**:
   - Every access logged with tamper-evident chaining
   - Real-time anomaly detection
   - Compliance reporting for regulatory requirements

6. **Agent Boundaries**:
   - Secure message routing between agents
   - Automatic sanitization of cross-agent communication
   - Sandboxed execution environments

### Key Files

- `/src/security/temujin_gatekeeper.py` - Central security agent
- `/src/security/data_transforms.py` - Masking and tokenization
- `/src/security/temporary_access.py` - Ephemeral access for operations
- `/src/security/audit_system.py` - Audit logging and compliance
- `/src/security/agent_boundaries.py` - Inter-agent security boundaries
