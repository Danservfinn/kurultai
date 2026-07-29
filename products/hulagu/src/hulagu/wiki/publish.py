"""Descriptor-relative atomic publication with PostgreSQL as visibility authority."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import stat
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

from hulagu.persistence.db import ConnectionProtocol
from hulagu.persistence.rls import TenantPrincipal

from .model import PublicationRecord, PublicationRequest, RenderedWiki, WikiPage
from .render import render_wiki, validate_rendered

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def _has_extended_acl(fd: int) -> bool:
    """Ask macOS for ACL entries without re-resolving the tenant-root path."""

    libc = ctypes.CDLL(None, use_errno=True)
    get_acl = getattr(libc, "acl_get_fd_np", None)
    get_entry = getattr(libc, "acl_get_entry", None)
    free_acl = getattr(libc, "acl_free", None)
    if get_acl is None or get_entry is None or free_acl is None:
        return False
    get_acl.argtypes = (ctypes.c_int, ctypes.c_int)
    get_acl.restype = ctypes.c_void_p
    get_entry.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
    get_entry.restype = ctypes.c_int
    free_acl.argtypes = (ctypes.c_void_p,)
    free_acl.restype = ctypes.c_int
    acl = get_acl(fd, 0x100)
    if not acl:
        return False
    try:
        entry = ctypes.c_void_p()
        return bool(get_entry(acl, 0, ctypes.byref(entry)) == 0)
    finally:
        free_acl(acl)


class PublicationCrash(RuntimeError):
    """Synthetic process-death injection used by the durability matrix."""


class PublicationRejected(RuntimeError):
    """The publication lost its authority or monotonic activation race."""


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("database integer has invalid type")
    return value


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, str):
        return value
    raise TypeError("database text has invalid type")


@contextmanager
def _publication_transaction(
    connection: ConnectionProtocol,
    principal: TenantPrincipal,
    *,
    correlation_id: str,
) -> Iterator[ConnectionProtocol]:
    """Install transaction-local RLS context through parameterizable set_config()."""

    if not correlation_id or len(correlation_id) > 128:
        raise ValueError("invalid correlation id")
    try:
        with connection.cursor() as cursor:
            cursor.execute("BEGIN")
            cursor.execute("SELECT set_config('app.tenant_id',%s,true)", (str(principal.tenant_id),))
            cursor.execute("SELECT set_config('app.actor',%s,true)", (principal.actor,))
            cursor.execute("SELECT set_config('app.correlation_id',%s,true)", (correlation_id,))
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


class PublicationStore(Protocol):
    def reserve(self, request: PublicationRequest) -> PublicationRecord: ...

    def seal(self, record: PublicationRecord, manifest_digest: str) -> PublicationRecord: ...

    def activate(self, record: PublicationRecord) -> PublicationRecord | None: ...

    def active(self, tenant_id: UUID) -> PublicationRecord | None: ...

    def records(self, tenant_id: UUID) -> tuple[PublicationRecord, ...]: ...

    @contextmanager
    def pin(self, record: PublicationRecord) -> Iterator[None]: ...

    @contextmanager
    def guard_active(self, record: PublicationRecord) -> Iterator[bool]: ...

    @contextmanager
    def guard_prune(self, record: PublicationRecord) -> Iterator[bool]: ...

    @contextmanager
    def guard_abandon(self, record: PublicationRecord) -> Iterator[bool]: ...

    @contextmanager
    def guard_orphan_generation(self, tenant_id: UUID, generation: int) -> Iterator[bool]: ...


class MemoryPublicationStore:
    """Thread-safe executable model of the PostgreSQL publication CAS."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._authority: dict[UUID, tuple[int, int, int, str]] = {}
        self._records: dict[UUID, PublicationRecord] = {}
        self._pins: dict[UUID, int] = {}

    def set_authority(
        self,
        tenant_id: UUID,
        *,
        lifecycle_epoch: int,
        work_epoch: int,
        profile_version: int,
        state: str,
    ) -> None:
        with self._lock:
            previous = self._authority.get(tenant_id)
            if previous is not None and (lifecycle_epoch < previous[0] or work_epoch < previous[1]):
                raise ValueError("authority epoch rewind")
            self._authority[tenant_id] = (lifecycle_epoch, work_epoch, profile_version, state)

    def _authorized(self, request: PublicationRequest) -> bool:
        return self._authority.get(request.tenant_id) == (
            request.lifecycle_epoch,
            request.work_epoch,
            request.profile_version,
            "READY",
        )

    def _record_authorized(self, record: PublicationRecord) -> bool:
        return self._authority.get(record.tenant_id) == (
            record.lifecycle_epoch,
            record.work_epoch,
            record.profile_version,
            "READY",
        )

    def reserve(self, request: PublicationRequest) -> PublicationRecord:
        with self._lock:
            if not self._authorized(request):
                raise PermissionError("publication authority rejected")
            tenant_records = [row for row in self._records.values() if row.tenant_id == request.tenant_id]
            generation = max((row.generation for row in tenant_records), default=0) + 1
            sequence = max((row.publication_sequence for row in tenant_records), default=0) + 1
            record = PublicationRecord(
                publication_id=uuid4(),
                tenant_id=request.tenant_id,
                run_id=request.run_id,
                profile_id=request.profile_id,
                generation=generation,
                publication_sequence=sequence,
                lifecycle_epoch=request.lifecycle_epoch,
                work_epoch=request.work_epoch,
                profile_version=request.profile_version,
                manifest_input_digest=request.manifest_input_digest,
                manifest_digest=request.manifest_input_digest,
                storage_ref=f"/tenants/{request.tenant_id}/wiki/generations/{generation}",
                visibility_state="staged",
            )
            self._records[record.publication_id] = record
            return record

    def seal(self, record: PublicationRecord, manifest_digest: str) -> PublicationRecord:
        with self._lock:
            current = self._records.get(record.publication_id)
            if current != record or current.visibility_state != "staged" or not self._record_authorized(current):
                raise PermissionError("publication authority rejected")
            sealed = replace(current, manifest_digest=manifest_digest)
            self._records[record.publication_id] = sealed
            return sealed

    def activate(self, record: PublicationRecord) -> PublicationRecord | None:
        with self._lock:
            current = self._records.get(record.publication_id)
            if current != record or current.visibility_state != "staged" or not self._record_authorized(current):
                raise PermissionError("publication authority rejected")
            active = self.active(record.tenant_id)
            if active is not None and active.publication_sequence >= record.publication_sequence:
                self._records[record.publication_id] = replace(current, visibility_state="superseded")
                return None
            for publication_id, candidate in tuple(self._records.items()):
                if candidate.tenant_id == record.tenant_id and candidate.visibility_state == "active":
                    self._records[publication_id] = replace(candidate, visibility_state="superseded")
            activated = replace(current, visibility_state="active")
            self._records[record.publication_id] = activated
            return activated

    def active(self, tenant_id: UUID) -> PublicationRecord | None:
        with self._lock:
            candidates = [
                row
                for row in self._records.values()
                if row.tenant_id == tenant_id and row.visibility_state == "active"
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda row: row.publication_sequence)

    def records(self, tenant_id: UUID) -> tuple[PublicationRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (row for row in self._records.values() if row.tenant_id == tenant_id),
                    key=lambda row: row.publication_sequence,
                )
            )

    @contextmanager
    def guard_abandon(self, record: PublicationRecord) -> Iterator[bool]:
        with self._lock:
            current = self._records.get(record.publication_id)
            if current is None or current != record or current.visibility_state != "staged":
                yield False
                return
            self._records[record.publication_id] = replace(current, visibility_state="superseded")
            yield True

    @contextmanager
    def guard_orphan_generation(self, tenant_id: UUID, generation: int) -> Iterator[bool]:
        with self._lock:
            yield not any(
                record.tenant_id == tenant_id and record.generation == generation for record in self._records.values()
            )

    @contextmanager
    def pin(self, record: PublicationRecord) -> Iterator[None]:
        with self._lock:
            current = self._records.get(record.publication_id)
            if current != record or current.visibility_state != "active":
                raise PublicationRejected("publication cannot be pinned")
            self._pins[record.publication_id] = self._pins.get(record.publication_id, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                count = self._pins.get(record.publication_id, 0) - 1
                if count > 0:
                    self._pins[record.publication_id] = count
                else:
                    self._pins.pop(record.publication_id, None)

    @contextmanager
    def guard_active(self, record: PublicationRecord) -> Iterator[bool]:
        with self._lock:
            yield self._records.get(record.publication_id) == record and self._record_authorized(record)

    @contextmanager
    def guard_prune(self, record: PublicationRecord) -> Iterator[bool]:
        with self._lock:
            current = self._records.get(record.publication_id)
            yield bool(
                current is not None
                and current.visibility_state == "superseded"
                and self._pins.get(record.publication_id, 0) == 0
            )


class PostgresPublicationStore:
    """RLS-scoped adapter using the frozen schema and `claim_publication` gate."""

    def __init__(self, connection: ConnectionProtocol, principal: TenantPrincipal) -> None:
        self._connection = connection
        self._principal = principal
        self._requests: dict[UUID, PublicationRequest] = {}
        self._pins: dict[UUID, int] = {}
        self._pin_lock = threading.Lock()

    def _check_tenant(self, tenant_id: UUID) -> None:
        if tenant_id != self._principal.tenant_id:
            raise PermissionError("publication tenant mismatch")

    @staticmethod
    def _authority_matches(row: tuple[object, ...] | None, request: PublicationRequest) -> bool:
        return bool(
            row is not None
            and _as_text(row[0]) == "READY"
            and _as_int(row[1]) == request.lifecycle_epoch
            and _as_text(row[2]).lower() not in {"paused", "cancelled", "failed"}
            and _as_int(row[3]) == request.work_epoch
            and _as_text(row[4]) == "confirmed"
            and _as_int(row[5]) == request.profile_version
        )

    def _select_authority(self, cursor: object, request: PublicationRequest) -> tuple[object, ...] | None:
        typed = cast("_Cursor", cursor)
        typed.execute(
            "SELECT t.state,t.lifecycle_epoch,r.state,r.work_epoch,p.state,p.profile_version "
            "FROM hulagu.tenants AS t "
            "JOIN hulagu.search_runs AS r ON r.tenant_id=t.id AND r.id=%s "
            "JOIN hulagu.customer_profiles AS p ON p.tenant_id=t.id AND p.id=%s "
            "WHERE t.id=%s FOR UPDATE OF t,r,p",
            (request.run_id, request.profile_id, request.tenant_id),
        )
        return typed.fetchone()

    def reserve(self, request: PublicationRequest) -> PublicationRecord:
        self._check_tenant(request.tenant_id)
        correlation = f"wiki-reserve:{request.manifest_input_digest[:24]}"
        with _publication_transaction(self._connection, self._principal, correlation_id=correlation), self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(request.tenant_id),))
            if not self._authority_matches(self._select_authority(cursor, request), request):
                raise PermissionError("publication authority rejected")
            cursor.execute(
                "SELECT COALESCE(MAX(generation),0)+1,COALESCE(MAX(publication_sequence),0)+1 "
                "FROM hulagu.wiki_publications"
            )
            allocation = cursor.fetchone()
            if allocation is None:
                raise RuntimeError("publication allocation failed")
            generation, sequence = int(allocation[0]), int(allocation[1])
            cursor.execute(
                "INSERT INTO hulagu.wiki_publications("
                "tenant_id,generation,manifest_digest,storage_ref,visibility_state,lifecycle_epoch,work_epoch,publication_sequence"
                ") VALUES(current_setting('app.tenant_id')::uuid,%s,%s,%s,'staged',%s,%s,%s) RETURNING id",
                (
                    generation,
                    request.manifest_input_digest,
                    f"/tenants/{request.tenant_id}/wiki/generations/{generation}",
                    request.lifecycle_epoch,
                    request.work_epoch,
                    sequence,
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raise RuntimeError("publication allocation failed")
        record = PublicationRecord(
            publication_id=UUID(str(inserted[0])),
            tenant_id=request.tenant_id,
            run_id=request.run_id,
            profile_id=request.profile_id,
            generation=generation,
            publication_sequence=sequence,
            lifecycle_epoch=request.lifecycle_epoch,
            work_epoch=request.work_epoch,
            profile_version=request.profile_version,
            manifest_input_digest=request.manifest_input_digest,
            manifest_digest=request.manifest_input_digest,
            storage_ref=f"/tenants/{request.tenant_id}/wiki/generations/{generation}",
            visibility_state="staged",
        )
        self._requests[record.publication_id] = request
        return record

    def seal(self, record: PublicationRecord, manifest_digest: str) -> PublicationRecord:
        self._check_tenant(record.tenant_id)
        request = self._requests.get(record.publication_id)
        if request is None:
            raise PermissionError("publication authority rejected")
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-seal:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute("SELECT hulagu_api.claim_publication(%s)", (record.publication_id,))
            claimed = cursor.fetchone()
            if claimed is None or not bool(claimed[0]) or not self._authority_matches(self._select_authority(cursor, request), request):
                raise PermissionError("publication authority rejected")
            cursor.execute(
                "UPDATE hulagu.wiki_publications SET manifest_digest=%s "
                "WHERE id=%s AND visibility_state='staged' AND manifest_digest=%s RETURNING id",
                (manifest_digest, record.publication_id, record.manifest_digest),
            )
            if cursor.fetchone() is None:
                raise PermissionError("publication authority rejected")
        return replace(record, manifest_digest=manifest_digest)

    def activate(self, record: PublicationRecord) -> PublicationRecord | None:
        self._check_tenant(record.tenant_id)
        request = self._requests.get(record.publication_id)
        if request is None:
            raise PermissionError("publication authority rejected")
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-activate:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(record.tenant_id),))
            cursor.execute("SELECT hulagu_api.claim_publication(%s)", (record.publication_id,))
            claimed = cursor.fetchone()
            if claimed is None or not bool(claimed[0]) or not self._authority_matches(self._select_authority(cursor, request), request):
                raise PermissionError("publication authority rejected")
            cursor.execute(
                "SELECT COALESCE(MAX(publication_sequence),0) FROM hulagu.wiki_publications "
                "WHERE visibility_state='active'"
            )
            row = cursor.fetchone()
            active_sequence = int(row[0]) if row is not None else 0
            if active_sequence >= record.publication_sequence:
                cursor.execute(
                    "UPDATE hulagu.wiki_publications SET visibility_state='superseded' "
                    "WHERE id=%s AND visibility_state='staged'",
                    (record.publication_id,),
                )
                return None
            cursor.execute(
                "UPDATE hulagu.wiki_publications SET visibility_state='superseded' "
                "WHERE visibility_state='active' AND publication_sequence<%s",
                (record.publication_sequence,),
            )
            cursor.execute(
                "UPDATE hulagu.wiki_publications SET visibility_state='active' "
                "WHERE id=%s AND visibility_state='staged' AND lifecycle_epoch=%s AND work_epoch=%s "
                "AND manifest_digest=%s AND publication_sequence=%s RETURNING id",
                (
                    record.publication_id,
                    record.lifecycle_epoch,
                    record.work_epoch,
                    record.manifest_digest,
                    record.publication_sequence,
                ),
            )
            if cursor.fetchone() is None:
                raise PermissionError("publication authority rejected")
            cursor.execute(
                "UPDATE hulagu.tenants SET current_wiki_generation=%s,updated_at=now() "
                "WHERE id=current_setting('app.tenant_id')::uuid AND state='READY' AND lifecycle_epoch=%s RETURNING id",
                (record.generation, record.lifecycle_epoch),
            )
            if cursor.fetchone() is None:
                raise PermissionError("publication authority rejected")
        return replace(record, visibility_state="active")

    def _row_to_record(self, row: tuple[object, ...]) -> PublicationRecord:
        publication_id = row[0] if isinstance(row[0], UUID) else UUID(_as_text(row[0]))
        request = self._requests.get(publication_id)
        tenant_id = self._principal.tenant_id
        return PublicationRecord(
            publication_id=publication_id,
            tenant_id=tenant_id,
            run_id=request.run_id if request else tenant_id,
            profile_id=request.profile_id if request else tenant_id,
            generation=_as_int(row[1]),
            publication_sequence=_as_int(row[2]),
            lifecycle_epoch=_as_int(row[3]),
            work_epoch=_as_int(row[4]),
            profile_version=request.profile_version if request else 1,
            manifest_input_digest=request.manifest_input_digest if request else _as_text(row[5]),
            manifest_digest=_as_text(row[5]),
            storage_ref=_as_text(row[6]),
            visibility_state=_as_text(row[7]),
        )

    def active(self, tenant_id: UUID) -> PublicationRecord | None:
        self._check_tenant(tenant_id)
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-active:{tenant_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,generation,publication_sequence,lifecycle_epoch,work_epoch,manifest_digest,storage_ref,visibility_state "
                "FROM hulagu.wiki_publications WHERE visibility_state='active' "
                "ORDER BY publication_sequence DESC LIMIT 1"
            )
            row = cursor.fetchone()
        return self._row_to_record(row) if row is not None else None

    def records(self, tenant_id: UUID) -> tuple[PublicationRecord, ...]:
        self._check_tenant(tenant_id)
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-records:{tenant_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,generation,publication_sequence,lifecycle_epoch,work_epoch,manifest_digest,storage_ref,visibility_state "
                "FROM hulagu.wiki_publications ORDER BY publication_sequence"
            )
            rows = cursor.fetchall()
        return tuple(self._row_to_record(row) for row in rows)

    @contextmanager
    def guard_abandon(self, record: PublicationRecord) -> Iterator[bool]:
        self._check_tenant(record.tenant_id)
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-abandon:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(record.tenant_id),))
            cursor.execute(
                "UPDATE hulagu.wiki_publications SET visibility_state='superseded' "
                "WHERE id=%s AND visibility_state='staged' AND manifest_digest=%s AND publication_sequence=%s "
                "RETURNING id",
                (record.publication_id, record.manifest_digest, record.publication_sequence),
            )
            yield cursor.fetchone() is not None

    @contextmanager
    def guard_orphan_generation(self, tenant_id: UUID, generation: int) -> Iterator[bool]:
        self._check_tenant(tenant_id)
        if generation < 1:
            yield False
            return
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-orphan:{generation}",
        ), self._connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(tenant_id),))
            cursor.execute(
                "SELECT id FROM hulagu.wiki_publications WHERE generation=%s LIMIT 1",
                (generation,),
            )
            yield cursor.fetchone() is None

    @contextmanager
    def pin(self, record: PublicationRecord) -> Iterator[None]:
        self._check_tenant(record.tenant_id)
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-pin:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (str(record.publication_id),),
            )
            cursor.execute(
                "SELECT visibility_state,manifest_digest,publication_sequence "
                "FROM hulagu.wiki_publications WHERE id=%s",
                (record.publication_id,),
            )
            row = cursor.fetchone()
            if (
                row is None
                or _as_text(row[0]) != "active"
                or _as_text(row[1]) != record.manifest_digest
                or _as_int(row[2]) != record.publication_sequence
            ):
                raise PublicationRejected("publication cannot be pinned")
            yield

    @contextmanager
    def guard_active(self, record: PublicationRecord) -> Iterator[bool]:
        self._check_tenant(record.tenant_id)
        request = self._requests.get(record.publication_id)
        if request is None:
            try:
                request = PublicationRequest(
                    tenant_id=record.tenant_id,
                    run_id=record.run_id,
                    profile_id=record.profile_id,
                    lifecycle_epoch=record.lifecycle_epoch,
                    work_epoch=record.work_epoch,
                    profile_version=record.profile_version,
                    manifest_input_digest=record.manifest_input_digest,
                )
            except ValueError:
                request = None
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-guard:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT w.id,t.state,t.lifecycle_epoch,w.work_epoch,w.manifest_digest,w.publication_sequence "
                "FROM hulagu.wiki_publications AS w JOIN hulagu.tenants AS t ON t.id=w.tenant_id "
                "WHERE w.id=%s AND w.visibility_state='active' FOR UPDATE OF t,w",
                (record.publication_id,),
            )
            row = cursor.fetchone()
            current = bool(
                row is not None
                and _as_text(row[1]) == "READY"
                and int(row[2]) == record.lifecycle_epoch
                and int(row[3]) == record.work_epoch
                and _as_text(row[4]) == record.manifest_digest
                and int(row[5]) == record.publication_sequence
                and request is not None
                and self._authority_matches(self._select_authority(cursor, request), request)
            )
            yield current

    @contextmanager
    def guard_prune(self, record: PublicationRecord) -> Iterator[bool]:
        self._check_tenant(record.tenant_id)
        with _publication_transaction(
            self._connection,
            self._principal,
            correlation_id=f"wiki-prune:{record.publication_id}",
        ), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                (str(record.publication_id),),
            )
            locked = cursor.fetchone()
            if locked is None or not bool(locked[0]):
                yield False
                return
            cursor.execute(
                "SELECT visibility_state,manifest_digest,publication_sequence "
                "FROM hulagu.wiki_publications WHERE id=%s FOR UPDATE",
                (record.publication_id,),
            )
            row = cursor.fetchone()
            yield bool(
                row is not None
                and _as_text(row[0]) == "superseded"
                and _as_text(row[1]) == record.manifest_digest
                and _as_int(row[2]) == record.publication_sequence
            )


class _Cursor(Protocol):
    def execute(self, statement: str, params: tuple[object, ...] | None = None) -> None: ...

    def fetchone(self) -> tuple[object, ...] | None: ...


class AtomicWikiPublisher:
    def __init__(
        self,
        tenant_root: Path,
        tenant_id: UUID,
        store: PublicationStore,
        *,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        self._tenant_id = tenant_id
        self._store = store
        self._fault = fault or (lambda _point: None)
        self._tenant_root_hint = tenant_root
        self._root_fd = os.open(tenant_root, os.O_RDONLY | _DIRECTORY | _NOFOLLOW)
        try:
            self._verify_private_dir(self._root_fd, "tenant root")
            if _has_extended_acl(self._root_fd):
                raise PermissionError("tenant root has extended ACL")
        except BaseException:
            os.close(self._root_fd)
            raise

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    @property
    def store(self) -> PublicationStore:
        return self._store

    @property
    def tenant_root_hint(self) -> Path:
        """Non-authoritative diagnostic hint; publication never re-resolves it."""

        return self._tenant_root_hint

    @staticmethod
    def _verify_private_dir(fd: int, label: str) -> None:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise PermissionError(f"{label} must be same-euid mode 0700")

    def _open_dir(self, parent_fd: int, name: str) -> int:
        fd = os.open(name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=parent_fd)
        try:
            self._verify_private_dir(fd, name)
        except BaseException:
            os.close(fd)
            raise
        return fd

    def _ensure_dir(self, parent_fd: int, name: str) -> int:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        return self._open_dir(parent_fd, name)

    def _layout(self) -> tuple[int, int, int]:
        wiki_fd = self._ensure_dir(self._root_fd, "wiki")
        try:
            staging_fd = self._ensure_dir(wiki_fd, ".staging")
            generations_fd = self._ensure_dir(wiki_fd, "generations")
        except BaseException:
            os.close(wiki_fd)
            raise
        return wiki_fd, staging_fd, generations_fd

    def publish(
        self,
        request: PublicationRequest,
        pages: tuple[WikiPage, ...],
        *,
        on_committed: Callable[[PublicationRecord], None] | None = None,
    ) -> PublicationRecord:
        if request.tenant_id != self._tenant_id:
            raise PermissionError("publication tenant mismatch")
        record = self._store.reserve(request)
        rendered = render_wiki(
            request,
            pages,
            generation=record.generation,
            publication_sequence=record.publication_sequence,
        )
        record = self._store.seal(record, rendered.manifest_digest)
        wiki_fd, staging_fd, generations_fd = self._layout()
        stage_name = f"stage-{record.publication_id.hex}"
        stage_fd = -1
        try:
            os.mkdir(stage_name, mode=0o700, dir_fd=staging_fd)
            stage_fd = self._open_dir(staging_fd, stage_name)
            self._write_files(stage_fd, rendered)
            self._fault("before:file_fsync")
            self._fsync_files(stage_fd)
            self._fault("after:file_fsync")
            self._fault("before:directory_fsync")
            self._fsync_directories(stage_fd)
            self._fault("after:directory_fsync")
            self._fault("before:generation_rename")
            os.rename(
                stage_name,
                str(record.generation),
                src_dir_fd=staging_fd,
                dst_dir_fd=generations_fd,
            )
            self._fault("after:generation_rename")
            os.fsync(generations_fd)
            self._fault("before:database_cas")
            active = self._store.activate(record)
            self._fault("after:database_cas")
            if active is None:
                raise PublicationRejected("a newer publication is already active")
            with self._store.guard_active(active) as current:
                if not current:
                    raise PermissionError("publication authority rejected")
                if on_committed is not None:
                    on_committed(active)
                self._repair_current(wiki_fd, active.generation)
            return active
        finally:
            if stage_fd >= 0:
                os.close(stage_fd)
            os.close(generations_fd)
            os.close(staging_fd)
            os.close(wiki_fd)

    def _write_files(self, stage_fd: int, rendered: RenderedWiki) -> None:
        for relative, payload in rendered.files:
            parts = relative.split("/")
            parent_fd = os.dup(stage_fd)
            try:
                for component in parts[:-1]:
                    next_fd = self._ensure_dir(parent_fd, component)
                    os.close(parent_fd)
                    parent_fd = next_fd
                fd = os.open(
                    parts[-1],
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
                try:
                    view = memoryview(payload)
                    while view:
                        written = os.write(fd, view)
                        if written <= 0:
                            raise OSError("short wiki write")
                        view = view[written:]
                finally:
                    os.close(fd)
            finally:
                os.close(parent_fd)

    def _walk(self, directory_fd: int) -> Iterator[tuple[str, int, os.stat_result]]:
        for name in sorted(os.listdir(directory_fd)):
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            yield name, directory_fd, info

    def _fsync_files(self, directory_fd: int) -> None:
        for name, parent_fd, info in self._walk(directory_fd):
            if stat.S_ISLNK(info.st_mode):
                raise PermissionError("symlink in rendered generation")
            if stat.S_ISDIR(info.st_mode):
                child_fd = self._open_dir(parent_fd, name)
                try:
                    self._fsync_files(child_fd)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                self._fault(f"before:file_fsync:{name}")
                fd = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=parent_fd)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
                self._fault(f"after:file_fsync:{name}")
            else:
                raise PermissionError("non-regular rendered generation entry")

    def _fsync_directories(self, directory_fd: int) -> None:
        for name, parent_fd, info in self._walk(directory_fd):
            if stat.S_ISDIR(info.st_mode):
                child_fd = self._open_dir(parent_fd, name)
                try:
                    self._fsync_directories(child_fd)
                finally:
                    os.close(child_fd)
        self._fault("before:directory_fsync:entry")
        os.fsync(directory_fd)
        self._fault("after:directory_fsync:entry")

    def _repair_current(self, wiki_fd: int, generation: int) -> None:
        temporary = f".CURRENT-{uuid4().hex}"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=wiki_fd)
        try:
            payload = f"{generation}\n".encode()
            if os.write(fd, payload) != len(payload):
                raise OSError("short CURRENT write")
            os.fsync(fd)
        finally:
            os.close(fd)
        self._fault("before:current_replace")
        os.replace(temporary, "CURRENT", src_dir_fd=wiki_fd, dst_dir_fd=wiki_fd)
        self._fault("after:current_replace")
        self._fault("before:parent_fsync")
        os.fsync(wiki_fd)
        self._fault("after:parent_fsync")

    def active_record(self) -> PublicationRecord | None:
        return self._store.active(self._tenant_id)

    def read_active(self) -> RenderedWiki:
        record = self.active_record()
        if record is None:
            raise LookupError("no active publication")
        with self._store.pin(record):
            return self.read_record(record)

    def read_record(self, record: PublicationRecord) -> RenderedWiki:
        if record.tenant_id != self._tenant_id:
            raise PermissionError("publication tenant mismatch")
        wiki_fd, staging_fd, generations_fd = self._layout()
        try:
            generation_fd = self._open_dir(generations_fd, str(record.generation))
            try:
                files = self._read_tree(generation_fd)
            finally:
                os.close(generation_fd)
        finally:
            os.close(generations_fd)
            os.close(staging_fd)
            os.close(wiki_fd)
        manifest = dict(files).get("manifest.json")
        if manifest is None:
            raise ValueError("invalid manifest")
        rendered = RenderedWiki(files, record.manifest_digest)
        validate_rendered(rendered)
        self.bind_record(record, rendered)
        return rendered

    def bind_record(self, record: PublicationRecord, rendered: RenderedWiki) -> PublicationRecord:
        """Recover the full CAS binding from the digest-verified immutable manifest."""

        try:
            manifest = json.loads(dict(rendered.files)["manifest.json"])
            if (
                not isinstance(manifest, dict)
                or manifest.get("tenant_id") != str(record.tenant_id)
                or manifest.get("generation") != record.generation
                or manifest.get("publication_sequence") != record.publication_sequence
                or manifest.get("lifecycle_epoch") != record.lifecycle_epoch
                or manifest.get("work_epoch") != record.work_epoch
                or not isinstance(manifest.get("run_id"), str)
                or not isinstance(manifest.get("profile_id"), str)
                or isinstance(manifest.get("profile_version"), bool)
                or not isinstance(manifest.get("profile_version"), int)
                or not isinstance(manifest.get("manifest_input_digest"), str)
            ):
                raise ValueError
            bound = replace(
                record,
                run_id=UUID(manifest["run_id"]),
                profile_id=UUID(manifest["profile_id"]),
                profile_version=manifest["profile_version"],
                manifest_input_digest=manifest["manifest_input_digest"],
            )
            PublicationRequest(
                tenant_id=bound.tenant_id,
                run_id=bound.run_id,
                profile_id=bound.profile_id,
                lifecycle_epoch=bound.lifecycle_epoch,
                work_epoch=bound.work_epoch,
                profile_version=bound.profile_version,
                manifest_input_digest=bound.manifest_input_digest,
            )
            return bound
        except (KeyError, TypeError, ValueError):
            raise ValueError("manifest authority binding mismatch") from None

    def _read_tree(self, directory_fd: int, prefix: str = "") -> tuple[tuple[str, bytes], ...]:
        files: list[tuple[str, bytes]] = []
        total = 0
        for name, parent_fd, info in self._walk(directory_fd):
            relative = f"{prefix}{name}"
            if stat.S_ISLNK(info.st_mode):
                raise PermissionError("symlink in generation")
            if stat.S_ISDIR(info.st_mode):
                child_fd = self._open_dir(parent_fd, name)
                try:
                    files.extend(self._read_tree(child_fd, f"{relative}/"))
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                if info.st_size > 1_048_576:
                    raise ValueError("wiki file size limit")
                fd = os.open(name, os.O_RDONLY | _NOFOLLOW, dir_fd=parent_fd)
                try:
                    chunks: list[bytes] = []
                    remaining = info.st_size
                    while remaining:
                        chunk = os.read(fd, min(remaining, 65_536))
                        if not chunk:
                            raise ValueError("short wiki read")
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    payload = b"".join(chunks)
                finally:
                    os.close(fd)
                total += len(payload)
                if total > 8_388_608:
                    raise ValueError("wiki generation size limit")
                files.append((relative, payload))
            else:
                raise PermissionError("non-regular generation entry")
        return tuple(sorted(files))

    def reconcile(self) -> None:
        wiki_fd, staging_fd, generations_fd = self._layout()
        try:
            for name in tuple(os.listdir(staging_fd)):
                self._remove_entry(staging_fd, name)
            records = self._store.records(self._tenant_id)
            for record in records:
                if record.visibility_state == "staged":
                    deletion_error: BaseException | None = None
                    with self._store.guard_abandon(record) as allowed:
                        if not allowed:
                            continue
                        try:
                            self._remove_entry(generations_fd, str(record.generation))
                        except FileNotFoundError:
                            pass
                        except BaseException as exc:  # noqa: BLE001 - commit superseded before any process exit
                            deletion_error = exc
                    if deletion_error is not None:
                        raise deletion_error
            retained = {
                str(record.generation)
                for record in self._store.records(self._tenant_id)
                if record.visibility_state in {"active", "superseded"}
            }
            for name in tuple(os.listdir(generations_fd)):
                if name not in retained:
                    try:
                        generation = int(name)
                    except ValueError:
                        self._remove_entry(generations_fd, name)
                        continue
                    with self._store.guard_orphan_generation(self._tenant_id, generation) as orphan:
                        if orphan:
                            self._remove_entry(generations_fd, name)
            for name in tuple(os.listdir(wiki_fd)):
                if name.startswith(".CURRENT-"):
                    self._remove_entry(wiki_fd, name)
            active = self._store.active(self._tenant_id)
            if active is not None:
                active = self.bind_record(active, self.read_record(active))
                with self._store.guard_active(active) as current:
                    if current:
                        self._repair_current(wiki_fd, active.generation)
            os.fsync(generations_fd)
            os.fsync(wiki_fd)
        finally:
            os.close(generations_fd)
            os.close(staging_fd)
            os.close(wiki_fd)

    def prune_superseded(self) -> None:
        _wiki_fd, staging_fd, generations_fd = self._layout()
        try:
            for record in self._store.records(self._tenant_id):
                if record.visibility_state != "superseded":
                    continue
                with self._store.guard_prune(record) as allowed:
                    if not allowed:
                        continue
                    try:
                        self._remove_entry(generations_fd, str(record.generation))
                    except FileNotFoundError:
                        pass
            os.fsync(generations_fd)
        finally:
            os.close(generations_fd)
            os.close(staging_fd)
            os.close(_wiki_fd)

    def _remove_entry(self, parent_fd: int, name: str) -> None:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child_fd = os.open(name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=parent_fd)
            try:
                for child in tuple(os.listdir(child_fd)):
                    self._remove_entry(child_fd, child)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=parent_fd)
        else:
            os.unlink(name, dir_fd=parent_fd)

    def close(self) -> None:
        if self._root_fd >= 0:
            os.close(self._root_fd)
            self._root_fd = -1

    def __del__(self) -> None:
        root_fd = getattr(self, "_root_fd", -1)
        if root_fd >= 0:
            try:
                os.close(root_fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
