from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.wiki.export import WikiExporter
from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import AtomicWikiPublisher, MemoryPublicationStore, PublicationCrash

TENANT_A = UUID("70000000-0000-4000-8000-00000000004a")
TENANT_B = UUID("70000000-0000-4000-8000-00000000004b")


def request(tenant: UUID, marker: str) -> PublicationRequest:
    return PublicationRequest(
        tenant_id=tenant,
        run_id=UUID(f"71000000-0000-4000-8000-00000000000{marker}"),
        profile_id=UUID(f"72000000-0000-4000-8000-00000000000{marker}"),
        lifecycle_epoch=8,
        work_epoch=13,
        profile_version=21,
        manifest_input_digest=marker.lower() * 64,
    )


def pages(marker: str, body: str) -> tuple[WikiPage, ...]:
    return (
        WikiPage("index.md", marker, body),
        WikiPage("profile.md", "Profile", "Synthetic profile."),
        WikiPage("searches/run-1.md", "Search", "Synthetic search."),
        WikiPage("jobs/job-1.md", "Job", "Synthetic job."),
        WikiPage("decisions.md", "Decisions", "None."),
    )


def publisher(tmp_path: Path, tenant: UUID) -> AtomicWikiPublisher:
    tenant_root = tmp_path / str(tenant)
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    store = MemoryPublicationStore()
    store.set_authority(tenant, lifecycle_epoch=8, work_epoch=13, profile_version=21, state="READY")
    return AtomicWikiPublisher(tenant_root, tenant, store)


def test_results_notification_and_export_delivery_occur_only_after_commit(tmp_path: Path) -> None:
    pub = publisher(tmp_path, TENANT_A)
    notified: list[int] = []
    sent: list[bytes] = []
    record = pub.publish(
        request(TENANT_A, "a"),
        pages("Results", "top synthetic candidate"),
        on_committed=lambda active: notified.append(active.generation),
    )
    artifact = WikiExporter(pub).deliver(TENANT_A, sent.append)

    assert notified == [record.generation]
    assert sent == [artifact.payload]
    with zipfile.ZipFile(io.BytesIO(artifact.payload)) as archive:
        assert set(archive.namelist()) == {
            "index.md",
            "profile.md",
            "searches/run-1.md",
            "jobs/job-1.md",
            "decisions.md",
            "manifest.json",
        }
        assert b"top synthetic candidate" in archive.read("index.md")
        assert b"storage_ref" not in archive.read("manifest.json")


def test_failed_database_cas_never_notifies_or_sends(tmp_path: Path) -> None:
    pub = publisher(tmp_path, TENANT_A)
    notified: list[int] = []

    def crash(point: str) -> None:
        if point == "before:database_cas":
            raise PublicationCrash(point)

    with pytest.raises(PublicationCrash):
        AtomicWikiPublisher(pub.tenant_root_hint, TENANT_A, pub.store, fault=crash).publish(
            request(TENANT_A, "a"),
            pages("No result", "must not send"),
            on_committed=lambda active: notified.append(active.generation),
        )
    assert notified == []
    with pytest.raises(LookupError, match="active"):
        WikiExporter(pub).deliver(TENANT_A, lambda _payload: pytest.fail("must not send"))


def test_tenant_cannot_request_another_tenants_export(tmp_path: Path) -> None:
    pub = publisher(tmp_path, TENANT_B)
    pub.publish(request(TENANT_B, "b"), pages("Private", "tenant B only"))
    sent: list[bytes] = []

    with pytest.raises(PermissionError, match="tenant"):
        WikiExporter(pub).deliver(TENANT_A, sent.append)
    assert sent == []


def test_deleting_tenant_cannot_activate_repair_current_or_export(tmp_path: Path) -> None:
    pub = publisher(tmp_path, TENANT_A)
    pub.store.set_authority(TENANT_A, lifecycle_epoch=9, work_epoch=13, profile_version=21, state="DELETING")
    sent: list[bytes] = []

    with pytest.raises(PermissionError, match="authority"):
        pub.publish(request(TENANT_A, "a"), pages("Deleted", "forbidden"))
    assert not (pub.tenant_root_hint / "wiki" / "CURRENT").exists()
    with pytest.raises(LookupError, match="active"):
        WikiExporter(pub).deliver(TENANT_A, sent.append)
    assert sent == []
