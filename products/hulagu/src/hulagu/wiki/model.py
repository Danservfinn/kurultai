"""Typed immutable values for private wiki publication."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class PublicationRequest:
    tenant_id: UUID
    run_id: UUID
    profile_id: UUID
    lifecycle_epoch: int
    work_epoch: int
    profile_version: int
    manifest_input_digest: str

    def __post_init__(self) -> None:
        if (
            self.tenant_id.version != 4
            or self.run_id.version != 4
            or self.profile_id.version != 4
            or self.lifecycle_epoch < 0
            or self.work_epoch < 0
            or self.profile_version < 1
            or _HEX_DIGEST.fullmatch(self.manifest_input_digest) is None
        ):
            raise ValueError("invalid publication request")


@dataclass(frozen=True, slots=True)
class WikiPage:
    path: str
    title: str
    body: str

    def __post_init__(self) -> None:
        if (
            not self.title
            or len(self.title) > 200
            or any(character in self.title for character in ("\x00", "\r", "\n"))
            or len(self.body.encode()) > 1_048_576
            or "\x00" in self.body
        ):
            raise ValueError("invalid wiki page")


@dataclass(frozen=True, slots=True)
class RenderedWiki:
    files: tuple[tuple[str, bytes], ...]
    manifest_digest: str

    def __post_init__(self) -> None:
        paths = tuple(path for path, _payload in self.files)
        if (
            not self.files
            or paths != tuple(sorted(paths))
            or len(paths) != len(set(paths))
            or _HEX_DIGEST.fullmatch(self.manifest_digest) is None
        ):
            raise ValueError("invalid rendered wiki")


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    publication_id: UUID
    tenant_id: UUID
    run_id: UUID
    profile_id: UUID
    generation: int
    publication_sequence: int
    lifecycle_epoch: int
    work_epoch: int
    profile_version: int
    manifest_input_digest: str
    manifest_digest: str
    storage_ref: str
    visibility_state: str

    def __post_init__(self) -> None:
        if (
            self.publication_id.version != 4
            or self.generation < 1
            or self.publication_sequence < 1
            or self.visibility_state not in {"staged", "active", "superseded"}
            or _HEX_DIGEST.fullmatch(self.manifest_input_digest) is None
            or _HEX_DIGEST.fullmatch(self.manifest_digest) is None
            or self.storage_ref != f"/tenants/{self.tenant_id}/wiki/generations/{self.generation}"
        ):
            raise ValueError("invalid publication record")


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    publication: PublicationRecord
    payload: bytes
    digest: str

    def __post_init__(self) -> None:
        if not self.payload or _HEX_DIGEST.fullmatch(self.digest) is None:
            raise ValueError("invalid export artifact")
