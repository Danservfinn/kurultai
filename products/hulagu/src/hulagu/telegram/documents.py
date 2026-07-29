"""Credential-free Telegram document admission into immutable parser jobs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..ingest.quarantine import QuarantinedDocument, quarantine_document
from ..persistence.rls import TenantPrincipal
from ..runner_app import ParserJob, ParserJobQueue


@dataclass(frozen=True, slots=True)
class IncomingDocument:
    bot_id: int
    update_id: int
    message_id: int
    tenant: TenantPrincipal
    filename: str
    mime_type: str
    chunks: Iterable[bytes]


@dataclass(frozen=True, slots=True)
class IngressResult:
    document: QuarantinedDocument
    job: ParserJob
    created: bool


class DocumentIngress:
    def __init__(self, tenant_root: Path, queue: ParserJobQueue) -> None:
        self._tenant_root = tenant_root
        self._queue = queue
        self._messages: dict[tuple[int, str, int], IngressResult] = {}

    def accept(self, incoming: IncomingDocument) -> IngressResult:
        if incoming.bot_id <= 0 or incoming.update_id < 0 or incoming.message_id <= 0:
            raise ValueError("invalid Telegram document authority")
        if not isinstance(incoming.tenant, TenantPrincipal):
            raise TypeError("invalid server-resolved tenant authority")
        tenant_id = str(incoming.tenant.tenant_id)
        message_key = (incoming.bot_id, tenant_id, incoming.message_id)
        replay = self._messages.get(message_key)
        if replay is not None:
            return IngressResult(replay.document, replay.job, False)
        document = quarantine_document(
            incoming.chunks,
            declared_filename=incoming.filename,
            declared_mime=incoming.mime_type,
            tenant_root=self._tenant_root,
            tenant_id=incoming.tenant.tenant_id,
        )
        job, created = self._queue.enqueue(
            tenant_id=tenant_id,
            document_digest=document.digest,
            input_path=document.path,
            input_authority=document.authority,
        )
        result = IngressResult(document, job, created)
        self._messages[message_key] = result
        return result
