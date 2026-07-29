from __future__ import annotations

import importlib.util
import os
import threading
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
    PublicationRejected,
)

TENANT = UUID("70000000-0000-4000-8000-000000000030")


def request(digit: str) -> PublicationRequest:
    return PublicationRequest(
        tenant_id=TENANT,
        run_id=UUID(f"71000000-0000-4000-8000-00000000000{digit}"),
        profile_id=UUID("72000000-0000-4000-8000-000000000030"),
        lifecycle_epoch=3,
        work_epoch=5,
        profile_version=7,
        manifest_input_digest=digit * 64,
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
    store.set_authority(TENANT, lifecycle_epoch=3, work_epoch=5, profile_version=7, state="READY")
    return tenant_root, store


def test_older_slower_publisher_cannot_replace_newer_active_generation(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    older_renamed = threading.Event()
    allow_older = threading.Event()
    outcome: list[PublicationRejected] = []

    def slow(point: str) -> None:
        if point == "after:generation_rename":
            older_renamed.set()
            assert allow_older.wait(timeout=5)

    def publish_older() -> None:
        try:
            AtomicWikiPublisher(tenant_root, TENANT, store, fault=slow).publish(request("1"), pages("older"))
        except PublicationRejected as exc:
            outcome.append(exc)

    thread = threading.Thread(target=publish_older)
    thread.start()
    assert older_renamed.wait(timeout=5)
    newer = AtomicWikiPublisher(tenant_root, TENANT, store).publish(request("2"), pages("newer"))
    allow_older.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], PublicationRejected)
    active = AtomicWikiPublisher(tenant_root, TENANT, store).active_record()
    assert active == newer
    assert b"newer complete" in dict(AtomicWikiPublisher(tenant_root, TENANT, store).read_active().files)["index.md"]


def test_export_pin_prevents_retention_deleting_generation_mid_read(tmp_path: Path) -> None:
    tenant_root, store = setup(tmp_path)
    publisher = AtomicWikiPublisher(tenant_root, TENANT, store)
    old = publisher.publish(request("1"), pages("old"))
    pinned = threading.Event()
    release = threading.Event()
    archive: list[bytes] = []

    def pause(point: str) -> None:
        if point == "after:pin":
            pinned.set()
            assert release.wait(timeout=5)

    def export_old() -> None:
        archive.append(WikiExporter(publisher, fault=pause).build_archive(TENANT).payload)

    thread = threading.Thread(target=export_old)
    thread.start()
    assert pinned.wait(timeout=5)
    publisher.publish(request("2"), pages("new"))
    publisher.prune_superseded()
    assert (tenant_root / "wiki" / "generations" / str(old.generation)).is_dir()
    release.set()
    thread.join(timeout=5)
    assert archive

    publisher.prune_superseded()
    assert not (tenant_root / "wiki" / "generations" / str(old.generation)).exists()


def test_postgres_export_pin_blocks_cross_connection_retention(tmp_path: Path) -> None:
    psycopg = pytest.importorskip("psycopg")
    root = Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "hulagu_wiki_concurrency_pg_helpers",
        root / "tests" / "integration" / "test_migrations.py",
    )
    assert spec is not None and spec.loader is not None
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    tenant_root = tmp_path / "tenant-pg"
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    principal = TenantPrincipal.from_identity_resolution(str(TENANT), "telegram-customer")
    pinned = threading.Event()
    release = threading.Event()
    exported: list[bytes] = []

    with helpers.postgres_cluster() as dsn:
        helpers.psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{TENANT}','READY',3);"
            "INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
            f"VALUES('{TENANT}','{request('1').profile_id}',7,'{{}}','confirmed');"
            "INSERT INTO hulagu.search_runs(tenant_id,id,profile_id,state,query_plan,budget,work_epoch) VALUES"
            f"('{TENANT}','{request('1').run_id}','{request('1').profile_id}','running','{{}}','{{}}',5),"
            f"('{TENANT}','{request('2').run_id}','{request('2').profile_id}','running','{{}}','{{}}',5);",
        )
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            old = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            ).publish(request("1"), pages("old"))

        def pause(point: str) -> None:
            if point == "after:pin":
                pinned.set()
                assert release.wait(timeout=5)

        def export_old() -> None:
            with psycopg.connect(dsn, user="hulagu_app") as connection:
                export_publisher = AtomicWikiPublisher(
                    tenant_root,
                    TENANT,
                    PostgresPublicationStore(connection, principal),
                )
                exported.append(WikiExporter(export_publisher, fault=pause).build_archive(TENANT).payload)

        thread = threading.Thread(target=export_old)
        thread.start()
        assert pinned.wait(timeout=5)
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            retention_publisher = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            )
            retention_publisher.publish(request("2"), pages("new"))
            retention_publisher.prune_superseded()
            assert (tenant_root / "wiki" / "generations" / str(old.generation)).is_dir()
            release.set()
            thread.join(timeout=5)
            assert exported and not thread.is_alive()
            retention_publisher.prune_superseded()
            assert not (tenant_root / "wiki" / "generations" / str(old.generation)).exists()


def test_postgres_reconcile_cannot_delete_a_concurrently_activating_generation(tmp_path: Path) -> None:
    psycopg = pytest.importorskip("psycopg")
    root = Path(__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "hulagu_wiki_reconcile_pg_helpers",
        root / "tests" / "integration" / "test_migrations.py",
    )
    assert spec is not None and spec.loader is not None
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    tenant_root = tmp_path / "tenant-reconcile-pg"
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    principal = TenantPrincipal.from_identity_resolution(str(TENANT), "telegram-customer")
    renamed = threading.Event()
    allow_activation = threading.Event()
    activated = threading.Event()
    before_delete = threading.Event()
    allow_delete = threading.Event()
    publish_errors: list[Exception] = []
    reconcile_errors: list[Exception] = []

    class PausedReconciler(AtomicWikiPublisher):
        def _remove_entry(self, parent_fd: int, name: str) -> None:
            if name == "2":
                before_delete.set()
                assert allow_delete.wait(timeout=5)
            super()._remove_entry(parent_fd, name)

    def pause_publish(point: str) -> None:
        if point == "after:generation_rename":
            renamed.set()
            assert allow_activation.wait(timeout=5)
        elif point == "after:database_cas":
            activated.set()

    with helpers.postgres_cluster() as dsn:
        helpers.psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{TENANT}','READY',3);"
            "INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
            f"VALUES('{TENANT}','{request('1').profile_id}',7,'{{}}','confirmed');"
            "INSERT INTO hulagu.search_runs(tenant_id,id,profile_id,state,query_plan,budget,work_epoch) VALUES"
            f"('{TENANT}','{request('1').run_id}','{request('1').profile_id}','running','{{}}','{{}}',5),"
            f"('{TENANT}','{request('2').run_id}','{request('2').profile_id}','running','{{}}','{{}}',5);",
        )
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            old = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            ).publish(request("1"), pages("old"))

        def publish_new() -> None:
            try:
                with psycopg.connect(dsn, user="hulagu_app") as connection:
                    AtomicWikiPublisher(
                        tenant_root,
                        TENANT,
                        PostgresPublicationStore(connection, principal),
                        fault=pause_publish,
                    ).publish(request("2"), pages("new"))
            except Exception as exc:  # noqa: BLE001 - thread outcome is asserted below
                publish_errors.append(exc)

        def reconcile() -> None:
            try:
                with psycopg.connect(dsn, user="hulagu_app") as connection:
                    PausedReconciler(
                        tenant_root,
                        TENANT,
                        PostgresPublicationStore(connection, principal),
                    ).reconcile()
            except Exception as exc:  # noqa: BLE001 - thread outcome is asserted below
                reconcile_errors.append(exc)

        publish_thread = threading.Thread(target=publish_new)
        reconcile_thread = threading.Thread(target=reconcile)
        publish_thread.start()
        assert renamed.wait(timeout=5)
        reconcile_thread.start()
        assert before_delete.wait(timeout=5)
        allow_activation.set()
        activation_won_stale_snapshot = activated.wait(timeout=1)
        allow_delete.set()
        publish_thread.join(timeout=5)
        reconcile_thread.join(timeout=5)

        assert not publish_thread.is_alive() and not reconcile_thread.is_alive()
        assert not activation_won_stale_snapshot
        assert not reconcile_errors
        assert len(publish_errors) == 1 and isinstance(publish_errors[0], (PermissionError, PublicationRejected))
        with psycopg.connect(dsn, user="hulagu_app") as connection:
            publisher = AtomicWikiPublisher(
                tenant_root,
                TENANT,
                PostgresPublicationStore(connection, principal),
            )
            active = publisher.active_record()
            assert active is not None and active.generation == old.generation
            assert b"old complete" in dict(publisher.read_active().files)["index.md"]
