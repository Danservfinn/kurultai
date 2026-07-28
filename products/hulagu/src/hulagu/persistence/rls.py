"""Immutable tenant authority produced only by audited identity resolution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    """A validated tenant context, not a caller-supplied repository argument."""

    tenant_id: UUID
    actor: str

    @classmethod
    def from_identity_resolution(cls, tenant_id: str, actor: str) -> TenantPrincipal:
        parsed = UUID(tenant_id)
        if parsed.version != 4 or actor != "telegram-customer":
            raise ValueError("invalid audited tenant principal")
        return cls(tenant_id=parsed, actor=actor)
