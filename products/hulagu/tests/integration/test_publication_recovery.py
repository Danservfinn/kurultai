from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import AtomicWikiPublisher, MemoryPublicationStore, PublicationCrash

TENANT = UUID("70000000-0000-4000-8000-000000000020")


def request(digest: str) -> PublicationRequest:
    return PublicationRequest(
        tenant_id=TENANT,
        run_id=UUID("71000000-0000-4000-8000-000000000020"),
        profile_id=UUID("72000000-0000-4000-8000-000000000020"),
        lifecycle_epoch=2,
        work_epoch=4,
        profile_version=6,
        manifest_input_digest=digest * 64,
    )


def pages(marker: str) -> tuple[WikiPage, ...]:
    return (
        WikiPage("index.md", marker, f"{marker} complete"),
        WikiPage("profile.md", "Profile", "Synthetic profile."),
        WikiPage("searches/run-1.md", "Search", "Synthetic search."),
        WikiPage("jobs/job-1.md", "Job", "Synthetic job."),
        WikiPage("decisions.md", "Decisions", "None."),
    )


def setup(tmp_path: Path) -> tuple[Path, MemoryPublicationStore]:
    tenant_root = tmp_path / "tenant"
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    store = MemoryPublicationStore()
    store.set_authority(TENANT, lifecycle_epoch=2, work_epoch=4, profile_version=6, state="READY")
    AtomicWikiPublisher(tenant_root, TENANT, store).publish(request("a"), pages("old"))
    return tenant_root, store


def fail_at(target: str):
    def fault(point: str) -> None:
        if point == target:
            raise PublicationCrash(point)
    return fault


def test_reconcile_removes_renamed_orphan_and_preserves_database_active(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    with pytest.raises(PublicationCrash):
        AtomicWikiPublisher(tenant_root, TENANT, store, fault=fail_at("after:generation_rename")).publish(
            request("b"), pages("new")
        )
    assert (tenant_root / "wiki" / "generations" / "2").is_dir()

    publisher = AtomicWikiPublisher(tenant_root, TENANT, store)
    publisher.reconcile()

    assert not (tenant_root / "wiki" / "generations" / "2").exists()
    assert (tenant_root / "wiki" / "CURRENT").read_text() == "1\n"
    assert b"old complete" in dict(publisher.read_active().files)["index.md"]


def test_reconcile_repairs_current_from_database_after_commit_crash(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    with pytest.raises(PublicationCrash):
        AtomicWikiPublisher(tenant_root, TENANT, store, fault=fail_at("before:current_replace")).publish(
            request("b"), pages("new")
        )
    assert (tenant_root / "wiki" / "CURRENT").read_text() == "1\n"

    publisher = AtomicWikiPublisher(tenant_root, TENANT, store)
    publisher.reconcile()

    assert (tenant_root / "wiki" / "CURRENT").read_text() == "2\n"
    assert b"new complete" in dict(publisher.read_active().files)["index.md"]


def test_reconcile_never_selects_latest_directory_without_database_authority(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    generations = tenant_root / "wiki" / "generations"
    forged = generations / "999"
    forged.mkdir()
    (forged / "index.md").write_text("forged")

    publisher = AtomicWikiPublisher(tenant_root, TENANT, store)
    publisher.reconcile()

    assert not forged.exists()
    assert (tenant_root / "wiki" / "CURRENT").read_text() == "1\n"
