"""Audit event helpers with conservative secret redaction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tracing import new_trace_id

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "password",
    "private_key",
    "secret",
    "token",
}
REDACTION = "[REDACTED]"


def redact_secrets(value: Any) -> Any:
    """Recursively redact common secret-bearing fields from JSON-like data."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[key] = REDACTION
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secrets(item) for item in value)
    return value


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    action: str
    decision: str
    details: dict[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
    resource: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "action": self.action,
            "decision": self.decision,
            "resource": self.resource,
            "trace_id": self.trace_id,
            "details": redact_secrets(self.details),
        }

    def write(self, store: Any) -> str:
        return store.record_audit_event(**self.to_record())


def _is_sensitive_key(key: str) -> bool:
    key_l = key.lower().replace("-", "_")
    return key_l in SENSITIVE_KEYS or key_l.endswith("_token") or key_l.endswith("_secret")
