"""Deterministic rendering and fail-closed validation for private wiki generations."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from .model import PublicationRequest, RenderedWiki, WikiPage

_WIKILINK = re.compile(r"\[\[([^\[\]]+)\]\]")
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "schema_version",
    "tenant_id",
    "run_id",
    "profile_id",
    "profile_version",
    "lifecycle_epoch",
    "work_epoch",
    "manifest_input_digest",
    "generation",
    "publication_sequence",
    "files",
}


def _canonical_page_path(value: str) -> str:
    if not value or len(value) > 255 or "\\" in value or value.startswith("/"):
        raise ValueError("invalid page path")
    path = PurePosixPath(value)
    parts = path.parts
    if any(part in {"", ".", ".."} or _SAFE_COMPONENT.fullmatch(part) is None for part in parts):
        raise ValueError("invalid page path")
    if path.suffix != ".md" or value == "manifest.json" or parts[0].startswith("."):
        raise ValueError("invalid page path")
    if value not in {"index.md", "profile.md", "decisions.md"} and not (
        len(parts) == 2 and parts[0] in {"searches", "jobs"}
    ):
        raise ValueError("invalid page path")
    return value


def _validate_wiki_shape(paths: set[str]) -> None:
    has_core = {"index.md", "profile.md", "decisions.md"} <= paths
    has_search = any(path.startswith("searches/") for path in paths)
    has_job = any(path.startswith("jobs/") for path in paths)
    if not has_core or not has_search or not has_job:
        raise ValueError("invalid wiki shape")


def _valid_uuid4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def _valid_integer(value: object, *, minimum: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= minimum


def _validate_manifest_authority(manifest: dict[str, object]) -> None:
    input_digest = manifest.get("manifest_input_digest")
    if (
        not _valid_uuid4(manifest.get("tenant_id"))
        or not _valid_uuid4(manifest.get("run_id"))
        or not _valid_uuid4(manifest.get("profile_id"))
        or not _valid_integer(manifest.get("profile_version"), minimum=1)
        or not _valid_integer(manifest.get("lifecycle_epoch"), minimum=0)
        or not _valid_integer(manifest.get("work_epoch"), minimum=0)
        or not isinstance(input_digest, str)
        or _HEX_DIGEST.fullmatch(input_digest) is None
        or not _valid_integer(manifest.get("generation"), minimum=1)
        or not _valid_integer(manifest.get("publication_sequence"), minimum=1)
    ):
        raise ValueError("invalid manifest")


def _link_target(value: str) -> str:
    if not value or "|" in value or "#" in value or value.endswith(".md"):
        raise ValueError("invalid wikilink")
    try:
        return _canonical_page_path(f"{value}.md")
    except ValueError:
        raise ValueError("invalid wikilink") from None


def _page_bytes(page: WikiPage) -> bytes:
    return f"---\ntitle: {page.title}\n---\n\n{page.body}\n".encode()


def render_wiki(
    request: PublicationRequest,
    pages: tuple[WikiPage, ...],
    *,
    generation: int,
    publication_sequence: int,
) -> RenderedWiki:
    if generation < 1 or publication_sequence < 1 or not pages or len(pages) > 1_000:
        raise ValueError("invalid wiki generation")
    rendered: dict[str, bytes] = {}
    bodies: dict[str, str] = {}
    for page in pages:
        path = _canonical_page_path(page.path)
        if path in rendered:
            raise ValueError("duplicate page path")
        rendered[path] = _page_bytes(page)
        bodies[path] = page.body
    if "index.md" not in rendered:
        raise ValueError("wiki index missing")
    known = set(rendered)
    for body in bodies.values():
        for raw_target in _WIKILINK.findall(body):
            if _link_target(raw_target) not in known:
                raise ValueError("invalid wikilink")
    _validate_wiki_shape(known)
    entries = [
        {"path": path, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        for path, payload in sorted(rendered.items())
    ]
    manifest = {
        "schema_version": "HulaguWikiManifest/v1",
        "tenant_id": str(request.tenant_id),
        "run_id": str(request.run_id),
        "profile_id": str(request.profile_id),
        "profile_version": request.profile_version,
        "lifecycle_epoch": request.lifecycle_epoch,
        "work_epoch": request.work_epoch,
        "manifest_input_digest": request.manifest_input_digest,
        "generation": generation,
        "publication_sequence": publication_sequence,
        "files": entries,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    rendered["manifest.json"] = manifest_bytes
    result = RenderedWiki(tuple(sorted(rendered.items())), hashlib.sha256(manifest_bytes).hexdigest())
    validate_rendered(result)
    return result


def validate_rendered(rendered: RenderedWiki) -> None:
    files = dict(rendered.files)
    manifest_bytes = files.get("manifest.json")
    if manifest_bytes is None or hashlib.sha256(manifest_bytes).hexdigest() != rendered.manifest_digest:
        raise ValueError("invalid manifest")
    try:
        decoded: object = json.loads(
            manifest_bytes,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("invalid manifest") from None
    if not isinstance(decoded, dict) or set(decoded) != _MANIFEST_KEYS:
        raise ValueError("invalid manifest")
    manifest = cast(dict[str, object], decoded)
    if manifest.get("schema_version") != "HulaguWikiManifest/v1" or not isinstance(manifest.get("files"), list):
        raise ValueError("invalid manifest")
    _validate_manifest_authority(manifest)
    entries = cast(list[object], manifest["files"])
    expected_paths = set(files) - {"manifest.json"}
    observed_paths: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
            raise ValueError("invalid manifest")
        path = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("bytes")
        if (
            not isinstance(path, str)
            or path not in expected_paths
            or not isinstance(digest, str)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ValueError("invalid manifest")
        payload = files[path]
        if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError("invalid manifest")
        observed_paths.append(path)
    if observed_paths != sorted(expected_paths) or len(observed_paths) != len(set(observed_paths)):
        raise ValueError("invalid manifest")
    _validate_wiki_shape(expected_paths)
    for path, payload in files.items():
        if path == "manifest.json":
            continue
        _canonical_page_path(path)
        try:
            text = payload.decode()
        except UnicodeDecodeError:
            raise ValueError("invalid manifest") from None
        for raw_target in _WIKILINK.findall(text):
            if _link_target(raw_target) not in expected_paths:
                raise ValueError("invalid wikilink")
