from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import AtomicWikiPublisher, MemoryPublicationStore

TENANT = UUID("70000000-0000-4000-8000-00000000000a")


def request() -> PublicationRequest:
    return PublicationRequest(
        tenant_id=TENANT,
        run_id=UUID("71000000-0000-4000-8000-00000000000a"),
        profile_id=UUID("72000000-0000-4000-8000-00000000000a"),
        lifecycle_epoch=1,
        work_epoch=2,
        profile_version=3,
        manifest_input_digest="b" * 64,
    )


def store() -> MemoryPublicationStore:
    result = MemoryPublicationStore()
    result.set_authority(TENANT, lifecycle_epoch=1, work_epoch=2, profile_version=3, state="READY")
    return result


def root(tmp_path: Path) -> Path:
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    return tenant_root


def pages(title: str = "Safe") -> tuple[WikiPage, ...]:
    return (
        WikiPage("index.md", title, "See [[profile]] and [[jobs/job-1]]."),
        WikiPage("profile.md", "Profile", "Synthetic profile."),
        WikiPage("searches/run-1.md", "Search", "Synthetic search."),
        WikiPage("jobs/job-1.md", "Job", "Synthetic job."),
        WikiPage("decisions.md", "Decisions", "None."),
    )


def test_publisher_rejects_tenant_root_not_owned_exclusively(tmp_path: Path) -> None:
    tenant_root = root(tmp_path)
    os.chmod(tenant_root, 0o755)
    with pytest.raises(PermissionError, match="tenant root"):
        AtomicWikiPublisher(tenant_root, TENANT, store())


def test_publisher_rejects_symlinked_wiki_component(tmp_path: Path) -> None:
    tenant_root = root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tenant_root / "wiki").symlink_to(outside, target_is_directory=True)

    with pytest.raises((PermissionError, FileExistsError, OSError)):
        AtomicWikiPublisher(tenant_root, TENANT, store()).publish(
            request(), pages()
        )
    assert list(outside.iterdir()) == []


def test_crafted_title_is_content_and_never_a_path(tmp_path: Path) -> None:
    tenant_root = root(tmp_path)
    publisher = AtomicWikiPublisher(tenant_root, TENANT, store())
    record = publisher.publish(
        request(),
        pages("../../escape"),
    )

    assert record.visibility_state == "active"
    assert not (tmp_path / "escape").exists()
    assert b"../../escape" in dict(publisher.read_active().files)["index.md"]


def test_publisher_binds_root_descriptor_even_if_path_is_replaced(tmp_path: Path) -> None:
    tenant_root = root(tmp_path)
    publisher = AtomicWikiPublisher(tenant_root, TENANT, store())
    original = tmp_path / "original"
    tenant_root.rename(original)
    replacement = root(tmp_path)

    publisher.publish(request(), pages("Bound"))

    assert (original / "wiki" / "generations" / "1" / "index.md").is_file()
    assert not (replacement / "wiki").exists()
