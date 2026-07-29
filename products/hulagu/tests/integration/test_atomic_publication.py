from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.persistence.rls import TenantPrincipal
from hulagu.wiki.export import WikiExporter
from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import (
    AtomicWikiPublisher,
    MemoryPublicationStore,
    PostgresPublicationStore,
    PublicationCrash,
)

TENANT = UUID("70000000-0000-4000-8000-000000000010")
CHECKPOINTS = (
    "file_fsync",
    "directory_fsync",
    "generation_rename",
    "database_cas",
    "current_replace",
    "parent_fsync",
)


def request(marker: str) -> PublicationRequest:
    return PublicationRequest(
        tenant_id=TENANT,
        run_id=UUID(f"71000000-0000-4000-8000-00000000000{marker}"),
        profile_id=UUID("72000000-0000-4000-8000-000000000010"),
        lifecycle_epoch=5,
        work_epoch=8,
        profile_version=13,
        manifest_input_digest=marker.lower() * 64,
    )


def page(marker: str) -> tuple[WikiPage, ...]:
    return (
        WikiPage("index.md", marker, f"complete-{marker}"),
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
    store.set_authority(TENANT, lifecycle_epoch=5, work_epoch=8, profile_version=13, state="READY")
    AtomicWikiPublisher(tenant_root, TENANT, store).publish(request("a"), page("old"))
    return tenant_root, store


@pytest.mark.parametrize("side", ["before", "after"])
@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_crash_matrix_exposes_only_a_complete_old_or_new_generation(
    tmp_path: Path, side: str, checkpoint: str
) -> None:
    tenant_root, store = setup(tmp_path)
    target = f"{side}:{checkpoint}"

    def crash(point: str) -> None:
        if point == target:
            raise PublicationCrash(point)

    with pytest.raises(PublicationCrash, match=checkpoint):
        AtomicWikiPublisher(tenant_root, TENANT, store, fault=crash).publish(request("b"), page("new"))

    visible = dict(AtomicWikiPublisher(tenant_root, TENANT, store).read_active().files)
    assert visible["index.md"] in {
        b"---\ntitle: old\n---\n\ncomplete-old\n",
        b"---\ntitle: new\n---\n\ncomplete-new\n",
    }
    assert b"complete-old" not in visible["index.md"] or b"complete-new" not in visible["index.md"]


def test_render_failure_never_changes_active_generation(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    with pytest.raises(ValueError, match="page path"):
        AtomicWikiPublisher(tenant_root, TENANT, store).publish(
            request("b"), (WikiPage("../partial.md", "partial", "partial"),)
        )

    visible = dict(AtomicWikiPublisher(tenant_root, TENANT, store).read_active().files)
    assert b"complete-old" in visible["index.md"]
    assert not (tmp_path / "partial.md").exists()


def test_postgres_store_commits_authoritative_active_generation_on_random_port(tmp_path: Path) -> None:
    psycopg = pytest.importorskip("psycopg")
    root = Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "hulagu_wiki_pg_helpers",
        root / "tests" / "integration" / "test_migrations.py",
    )
    assert spec is not None and spec.loader is not None
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    publication_request = request("a")
    tenant_root = tmp_path / "tenant-pg"
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)

    with helpers.postgres_cluster() as dsn:
        helpers.psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{TENANT}','READY',5);"
            "INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
            f"VALUES('{TENANT}','{publication_request.profile_id}',13,'{{}}','confirmed');"
            "INSERT INTO hulagu.search_runs(tenant_id,id,profile_id,state,query_plan,budget,work_epoch) "
            f"VALUES('{TENANT}','{publication_request.run_id}','{publication_request.profile_id}',"
            "'running','{}','{}',8);",
        )
        principal = TenantPrincipal.from_identity_resolution(str(TENANT), "telegram-customer")
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            record = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            ).publish(publication_request, page("postgres"))

        assert helpers.psql(
            dsn,
            "SELECT visibility_state || ':' || generation || ':' || publication_sequence "
            "FROM hulagu.wiki_publications",
        ).stdout.strip() == f"active:{record.generation}:{record.publication_sequence}"
        assert helpers.psql(
            dsn,
            f"SELECT current_wiki_generation FROM hulagu.tenants WHERE id='{TENANT}'",
        ).stdout.strip() == str(record.generation)

        helpers.psql(
            dsn,
            f"UPDATE hulagu.search_runs SET state='paused',work_epoch=9 WHERE id='{publication_request.run_id}'",
        )
        sent: list[bytes] = []
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            restarted = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            )
            with pytest.raises(PermissionError, match="authority|active"):
                WikiExporter(restarted).deliver(TENANT, sent.append)
        assert sent == []

        helpers.psql(
            dsn,
            f"UPDATE hulagu.tenants SET state='DELETING',lifecycle_epoch=6 WHERE id='{TENANT}'",
        )
        notified: list[int] = []
        with (
            psycopg.connect(dsn, user="hulagu_app") as connection,
            pytest.raises(PermissionError, match="authority"),
        ):
            AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            ).publish(
                publication_request,
                page("blocked"),
                on_committed=lambda active: notified.append(active.generation),
            )
        assert notified == []
        assert helpers.psql(dsn, "SELECT count(*) FROM hulagu.wiki_publications").stdout.strip() == "1"
        assert (tenant_root / "wiki" / "CURRENT").read_text() == f"{record.generation}\n"
