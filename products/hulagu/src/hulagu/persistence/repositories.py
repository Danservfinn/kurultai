"""Tenant-scoped repositories with fixed SQL and principal-only authority."""

from __future__ import annotations

from uuid import UUID

from .db import ConnectionProtocol, tenant_transaction
from .rls import TenantPrincipal


class HulaguRepository:
    def get_profile(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        profile_id: UUID,
        correlation_id: str,
    ) -> tuple[object, ...] | None:
        with tenant_transaction(connection, principal, correlation_id=correlation_id), connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, profile_version, profile_json, state FROM hulagu.customer_profiles WHERE id=%s",
                (profile_id,),
            )
            return cursor.fetchone()

    def update_profile(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        profile_id: UUID,
        expected_version: int,
        profile_json: str,
        correlation_id: str,
    ) -> tuple[object, ...] | None:
        with tenant_transaction(connection, principal, correlation_id=correlation_id), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE hulagu.customer_profiles SET profile_json=%s::jsonb, profile_version=profile_version+1 "
                "WHERE id=%s AND profile_version=%s RETURNING id,profile_version",
                (profile_json, profile_id, expected_version),
            )
            return cursor.fetchone()

    def get_candidate(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        candidate_id: UUID,
        correlation_id: str,
    ) -> tuple[object, ...] | None:
        with tenant_transaction(connection, principal, correlation_id=correlation_id), connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,run_id,listing_key,evidence FROM hulagu.search_candidates WHERE id=%s",
                (candidate_id,),
            )
            return cursor.fetchone()

    def add_decision(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        candidate_id: UUID,
        decision: str,
        reason: str | None,
        correlation_id: str,
    ) -> tuple[object, ...] | None:
        if decision not in {"saved", "rejected"}:
            raise ValueError("invalid candidate decision")
        with tenant_transaction(connection, principal, correlation_id=correlation_id), connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO hulagu.candidate_decisions(tenant_id,candidate_id,decision,reason) "
                "VALUES (current_setting('app.tenant_id')::uuid,%s,%s,%s) RETURNING id",
                (candidate_id, decision, reason),
            )
            return cursor.fetchone()
