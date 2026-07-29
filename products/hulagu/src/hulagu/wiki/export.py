"""Atomic archive construction and commit-fenced private export delivery."""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable
from uuid import UUID

from .model import ExportArtifact
from .publish import AtomicWikiPublisher


class WikiExporter:
    def __init__(
        self,
        publisher: AtomicWikiPublisher,
        *,
        max_bytes: int = 8_388_608,
        fault: Callable[[str], None] | None = None,
    ) -> None:
        if not 1 <= max_bytes <= 33_554_432:
            raise ValueError("invalid export size limit")
        self._publisher = publisher
        self._max_bytes = max_bytes
        self._fault = fault or (lambda _point: None)

    def build_archive(self, authenticated_tenant_id: UUID) -> ExportArtifact:
        if authenticated_tenant_id != self._publisher.tenant_id:
            raise PermissionError("export tenant mismatch")
        record = self._publisher.active_record()
        if record is None:
            raise LookupError("no active publication")
        with self._publisher.store.pin(record):
            self._fault("after:pin")
            rendered = self._publisher.read_record(record)
            record = self._publisher.bind_record(record, rendered)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path, payload in rendered.files:
                    info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, payload)
            payload = output.getvalue()
            if len(payload) > self._max_bytes:
                raise ValueError("export size limit")
            return ExportArtifact(record, payload, hashlib.sha256(payload).hexdigest())

    def deliver(
        self,
        authenticated_tenant_id: UUID,
        send: Callable[[bytes], None],
    ) -> ExportArtifact:
        artifact = self.build_archive(authenticated_tenant_id)
        with self._publisher.store.guard_active(artifact.publication) as current:
            if not current:
                raise PermissionError("export publication is no longer active")
            send(artifact.payload)
        return artifact
