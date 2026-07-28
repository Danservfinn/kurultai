"""The three separate audited enrollment and identity authorities."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from .db import ConnectionProtocol
from .rls import TenantPrincipal


def resolve_enrollment(
    connection: ConnectionProtocol,
    *,
    subject_digest: str,
    subject_fence_digest: str,
    notice_version: str,
    consent_nonce_hash: str,
    expires_at: datetime,
) -> UUID:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT hulagu_api.resolve_enrollment(%s,%s,%s,%s,%s)",
            (subject_digest, subject_fence_digest, notice_version, consent_nonce_hash, expires_at),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("enrollment resolution returned no identifier")
    return UUID(str(row[0]))


def promote_consented_enrollment(
    connection: ConnectionProtocol,
    *,
    enrollment_id: UUID,
    notice_version: str,
    consent_nonce_hash: str,
) -> TenantPrincipal:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT hulagu_api.promote_consented_enrollment(%s,%s,%s)",
            (enrollment_id, notice_version, consent_nonce_hash),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("consent promotion returned no tenant")
    return TenantPrincipal.from_identity_resolution(str(row[0]), "telegram-customer")


def resolve_existing_tenant(connection: ConnectionProtocol, *, subject_digest: str) -> TenantPrincipal | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT hulagu_api.resolve_existing_tenant(%s)", (subject_digest,))
        row = cursor.fetchone()
    if row is None or row[0] is None:
        return None
    return TenantPrincipal.from_identity_resolution(str(row[0]), "telegram-customer")
