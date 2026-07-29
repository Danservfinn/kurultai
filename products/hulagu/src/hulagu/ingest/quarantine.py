"""Atomic tenant-local quarantine with bounded format validation."""

from __future__ import annotations

import hashlib
import io
import os
import secrets
import stat
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class DocumentRejected(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class QuarantineAuthority:
    root_device: int
    root_inode: int
    tenant_device: int
    tenant_inode: int
    quarantine_device: int
    quarantine_inode: int
    file_device: int
    file_inode: int

    def serialize(self) -> str:
        values = (
            self.root_device,
            self.root_inode,
            self.tenant_device,
            self.tenant_inode,
            self.quarantine_device,
            self.quarantine_inode,
            self.file_device,
            self.file_inode,
        )
        return ":".join(str(value) for value in values)

    @classmethod
    def parse(cls, value: str) -> QuarantineAuthority:
        parts = value.split(":")
        if len(parts) != 8 or any(not part.isdecimal() for part in parts):
            raise ValueError("invalid quarantine authority")
        return cls(*(int(part) for part in parts))


@dataclass(frozen=True, slots=True)
class QuarantinedDocument:
    path: Path
    digest: str
    size: int
    kind: str
    authority: QuarantineAuthority


def quarantine_document(
    chunks: Iterable[bytes],
    *,
    declared_filename: str,
    declared_mime: str,
    tenant_root: Path,
    tenant_id: UUID,
    max_bytes: int = 10 * 1024 * 1024,
) -> QuarantinedDocument:
    if not isinstance(tenant_id, UUID) or tenant_id.version != 4:
        raise DocumentRejected("invalid_tenant_authority")
    expected_kind = _declared_kind(declared_filename, declared_mime)
    root = tenant_root.absolute()
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    tenant_name = str(tenant_id)
    quarantine = root / tenant_name / "quarantine"
    try:
        root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise DocumentRejected("invalid_tenant_authority") from None
    try:
        root_status = os.fstat(root_descriptor)
        tenant_descriptor = _open_or_create_directory(root_descriptor, tenant_name)
    finally:
        os.close(root_descriptor)
    try:
        tenant_status = os.fstat(tenant_descriptor)
        quarantine_descriptor = _open_or_create_directory(tenant_descriptor, "quarantine")
    finally:
        os.close(tenant_descriptor)
    temporary_name = f".upload-{secrets.token_hex(16)}"
    digest = hashlib.sha256()
    payload = bytearray()
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=quarantine_descriptor,
        )
    except BaseException:
        os.close(quarantine_descriptor)
        raise
    try:
        for chunk in chunks:
            if not isinstance(chunk, bytes):
                raise DocumentRejected("invalid_document_chunk")
            if len(payload) + len(chunk) > max_bytes:
                raise DocumentRejected("document_too_large")
            payload.extend(chunk)
            digest.update(chunk)
            os.write(descriptor, chunk)
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        _unlink_if_present(quarantine_descriptor, temporary_name)
        os.close(quarantine_descriptor)
        raise
    else:
        os.close(descriptor)

    try:
        quarantine_status = os.fstat(quarantine_descriptor)
        observed_kind = _inspect(bytes(payload))
        if observed_kind != expected_kind:
            raise DocumentRejected("document_type_mismatch")
        document_digest = digest.hexdigest()
        suffix = ".pdf" if observed_kind == "pdf" else ".docx"
        final_name = f"{document_digest}{suffix}"
        final_path = quarantine / final_name
        try:
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=quarantine_descriptor,
                dst_dir_fd=quarantine_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            existing = os.stat(final_name, dir_fd=quarantine_descriptor, follow_symlinks=False)
            if not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1:
                raise DocumentRejected("unsafe_quarantine_target") from None
        _unlink_if_present(quarantine_descriptor, temporary_name)
        os.fsync(quarantine_descriptor)
        file_descriptor = os.open(final_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=quarantine_descriptor)
        try:
            file_status = os.fstat(file_descriptor)
        finally:
            os.close(file_descriptor)
        authority = _authority_from_statuses(root_status, tenant_status, quarantine_status, file_status)
        validation_descriptor = open_authorized_document(final_path, tenant_id=tenant_name, authority=authority)
        os.close(validation_descriptor)
        return QuarantinedDocument(final_path, document_digest, len(payload), observed_kind, authority)
    except BaseException:
        _unlink_if_present(quarantine_descriptor, temporary_name)
        raise
    finally:
        os.close(quarantine_descriptor)


def capture_quarantine_authority(path: Path, *, tenant_id: str) -> QuarantineAuthority:
    root_descriptor, tenant_descriptor, quarantine_descriptor = _open_quarantine_chain(path, tenant_id)
    try:
        file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=quarantine_descriptor)
        try:
            return _authority_from_statuses(
                os.fstat(root_descriptor),
                os.fstat(tenant_descriptor),
                os.fstat(quarantine_descriptor),
                os.fstat(file_descriptor),
            )
        finally:
            os.close(file_descriptor)
    except OSError:
        raise DocumentRejected("invalid_tenant_authority") from None
    finally:
        os.close(quarantine_descriptor)
        os.close(tenant_descriptor)
        os.close(root_descriptor)


def open_authorized_document(path: Path, *, tenant_id: str, authority: QuarantineAuthority) -> int:
    root_descriptor, tenant_descriptor, quarantine_descriptor = _open_quarantine_chain(path, tenant_id)
    try:
        _require_identity(os.fstat(root_descriptor), authority.root_device, authority.root_inode, directory=True)
        _require_identity(os.fstat(tenant_descriptor), authority.tenant_device, authority.tenant_inode, directory=True)
        _require_identity(
            os.fstat(quarantine_descriptor),
            authority.quarantine_device,
            authority.quarantine_inode,
            directory=True,
        )
        file_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=quarantine_descriptor)
        try:
            _require_identity(os.fstat(file_descriptor), authority.file_device, authority.file_inode, directory=False)
        except BaseException:
            os.close(file_descriptor)
            raise
        return file_descriptor
    except (OSError, DocumentRejected):
        raise DocumentRejected("invalid_tenant_authority") from None
    finally:
        os.close(quarantine_descriptor)
        os.close(tenant_descriptor)
        os.close(root_descriptor)


def copy_authorized_document(
    path: Path,
    destination_directory: int,
    destination_name: str,
    *,
    tenant_id: str,
    authority: QuarantineAuthority,
    expected_digest: str,
) -> int:
    if destination_name in ("", ".", "..") or "/" in destination_name:
        raise DocumentRejected("invalid_staging_authority")
    source_descriptor = open_authorized_document(path, tenant_id=tenant_id, authority=authority)
    destination_descriptor: int | None = None
    digest = hashlib.sha256()
    try:
        destination_descriptor = os.open(
            destination_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=destination_directory,
        )
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            os.write(destination_descriptor, chunk)
        os.fsync(destination_descriptor)
    except BaseException:
        _unlink_if_present(destination_directory, destination_name)
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        raise
    finally:
        os.close(source_descriptor)
    if digest.hexdigest() != expected_digest:
        _unlink_if_present(destination_directory, destination_name)
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        raise DocumentRejected("document_digest_mismatch")
    if destination_descriptor is None:
        raise DocumentRejected("invalid_staging_authority")
    os.lseek(destination_descriptor, 0, os.SEEK_SET)
    return destination_descriptor


def _open_quarantine_chain(path: Path, tenant_id: str) -> tuple[int, int, int]:
    if (
        not path.is_absolute()
        or path.name in ("", ".", "..")
        or path.parent.name != "quarantine"
        or path.parent.parent.name != tenant_id
    ):
        raise DocumentRejected("invalid_tenant_authority")
    root = path.parent.parent.parent
    try:
        root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            tenant_descriptor = os.open(
                tenant_id,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_descriptor,
            )
            try:
                quarantine_descriptor = os.open(
                    "quarantine",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=tenant_descriptor,
                )
            except BaseException:
                os.close(tenant_descriptor)
                raise
        except BaseException:
            os.close(root_descriptor)
            raise
    except OSError:
        raise DocumentRejected("invalid_tenant_authority") from None
    return root_descriptor, tenant_descriptor, quarantine_descriptor


def _authority_from_statuses(
    root: os.stat_result,
    tenant: os.stat_result,
    quarantine: os.stat_result,
    document: os.stat_result,
) -> QuarantineAuthority:
    _require_identity(root, root.st_dev, root.st_ino, directory=True)
    _require_identity(tenant, tenant.st_dev, tenant.st_ino, directory=True)
    _require_identity(quarantine, quarantine.st_dev, quarantine.st_ino, directory=True)
    _require_identity(document, document.st_dev, document.st_ino, directory=False)
    return QuarantineAuthority(
        root.st_dev,
        root.st_ino,
        tenant.st_dev,
        tenant.st_ino,
        quarantine.st_dev,
        quarantine.st_ino,
        document.st_dev,
        document.st_ino,
    )


def _require_identity(status: os.stat_result, device: int, inode: int, *, directory: bool) -> None:
    expected_kind = stat.S_ISDIR(status.st_mode) if directory else stat.S_ISREG(status.st_mode)
    if status.st_dev != device or status.st_ino != inode or not expected_kind or (not directory and status.st_nlink != 1):
        raise DocumentRejected("invalid_tenant_authority")


def _open_or_create_directory(parent_descriptor: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
    except FileExistsError:
        pass
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_descriptor)
    except OSError:
        raise DocumentRejected("invalid_tenant_authority") from None


def _unlink_if_present(directory_descriptor: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=directory_descriptor)
    except FileNotFoundError:
        pass


def _declared_kind(filename: str, mime: str) -> str:
    lowered = filename.casefold()
    if lowered.endswith(".pdf") and mime == PDF_MIME:
        return "pdf"
    if lowered.endswith(".docx") and mime == DOCX_MIME:
        return "docx"
    raise DocumentRejected("document_type_mismatch")


def _inspect(payload: bytes) -> str:
    is_pdf = payload.startswith(b"%PDF-")
    is_zip = payload.startswith(b"PK\x03\x04")
    if is_pdf and b"PK\x03\x04" in payload[5:]:
        raise DocumentRejected("document_polyglot")
    if is_pdf:
        _inspect_pdf(payload)
        return "pdf"
    if is_zip:
        _inspect_docx(payload)
        return "docx"
    raise DocumentRejected("document_type_mismatch")


def _inspect_pdf(payload: bytes) -> None:
    if b"/Encrypt" in payload:
        raise DocumentRejected("pdf_encrypted")
    active_markers = (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFile", b"/RichMedia")
    if any(marker in payload for marker in active_markers):
        raise DocumentRejected("pdf_active_content")
    if b"%%EOF" not in payload[-1024:]:
        raise DocumentRejected("pdf_malformed")


def _inspect_docx(payload: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise DocumentRejected("document_type_mismatch")
            expanded = 0
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in info.filename:
                    raise DocumentRejected("docx_path_traversal")
                if info.flag_bits & 0x1:
                    raise DocumentRejected("docx_encrypted")
                expanded += info.file_size
                if info.file_size > 131_072 and info.compress_size * 100 < info.file_size:
                    raise DocumentRejected("docx_expansion_limit")
                if expanded > 50 * 1024 * 1024:
                    raise DocumentRejected("docx_expansion_limit")
                lowered = info.filename.casefold()
                if lowered.endswith("vbaproject.bin") or "macros" in lowered:
                    raise DocumentRejected("docx_macro")
                if lowered.endswith(".rels"):
                    relationship = archive.read(info)
                    if b"TargetMode=\"External\"" in relationship or b"TargetMode='External'" in relationship:
                        raise DocumentRejected("docx_external_relationship")
    except zipfile.BadZipFile:
        raise DocumentRejected("docx_malformed") from None
