from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.app import HulaguApp, MemoryStore
from hulagu.control.health import HealthCheck, HealthStatus, build_health_report
from hulagu.control.metrics import AggregateMetrics, project_control_room
from hulagu.domain.profile import Profile, ProfileField
from hulagu.domain.ranking import rank_input_payload
from hulagu.search.planner import compile_search_plan
from hulagu.search.provider import FixtureSearchProvider, ProviderAttempt, SearchCoordinator
from hulagu.search.runner import MemoryRankingJobQueue, RunnerCrash, SearchRunner
from hulagu.telegram.adapter import FakeTelegramAdapter
from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys
from hulagu.wiki.export import WikiExporter
from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import AtomicWikiPublisher, MemoryPublicationStore, PublicationCrash

TENANT = UUID("90000000-0000-4000-8000-000000000001")


def update(update_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": 42},
            "chat": {"id": 42, "type": "private"},
            "text": text,
        },
    }


def app(store: MemoryStore) -> HulaguApp:
    return HulaguApp(
        FakeTelegramAdapter(bot_id=7),
        store,
        pinned_bot_id=7,
        identity_keys=IdentityDigestKeys({1: b"synthetic-identity-key"}, 1),
        callback_codec=CallbackCodec(b"synthetic-callback-key"),
        clock=lambda: 100,
    )


class Ranker:
    def execute(self, input_payload: bytes, *, expected_digest: str, job_kind: str = "parser") -> bytes:
        assert job_kind == "ranker"
        assert hashlib.sha256(input_payload).hexdigest() == expected_digest
        return json.dumps(rank_input_payload(json.loads(input_payload)), sort_keys=True, separators=(",", ":")).encode()


def test_golden_customer_journey_survives_app_runner_and_publication_restarts(tmp_path: Path) -> None:
    store = MemoryStore()
    started = app(store).handle_update(update(1, "/start"))
    assert started.reply is not None and started.reply.callback_data is not None
    callback = {
        "update_id": 2,
        "callback_query": {
            "id": "golden-consent",
            "from": {"id": 42},
            "data": started.reply.callback_data,
            "message": {"message_id": 2, "chat": {"id": 42, "type": "private"}},
        },
    }
    assert app(store).handle_update(callback).outcome == "consent_promoted"
    assert app(store).handle_update(update(3, "/status")).reply.text == "Status: awaiting_cv"  # type: ignore[union-attr]

    profile = Profile(
        1,
        (
            ProfileField("target_role", "Platform Engineer", "customer", 1.0),
            ProfileField("location", "Remote", "customer", 1.0),
        ),
        confirmed_version=1,
    )
    plan = compile_search_plan(profile)
    search = SearchCoordinator(
        FixtureSearchProvider(
            [ProviderAttempt.success([{
                "url": "https://jobs.example.test/golden",
                "title": "Platform Engineer",
                "company": "Synthetic Co",
                "location": "Remote",
                "remote_signal": "remote",
                "snippet": "Synthetic public fixture",
            }])]
        ),
        clock=lambda: 100,
    ).run(plan)
    queue = MemoryRankingJobQueue(clock=lambda: 100)
    queue.set_authority(lifecycle_epoch=2, work_epoch=3, state="READY")
    job, _ = queue.enqueue(search.to_ranking_input("golden-run"), lifecycle_epoch=2, work_epoch=3)
    with pytest.raises(RunnerCrash):
        SearchRunner(queue, Ranker(), clock=lambda: 100, crash_after_claim=True).run_once()
    queue.advance_clock(161)
    assert SearchRunner(queue, Ranker(), clock=lambda: 161).run_once() == "succeeded"
    assert queue.state(job.job_id) == "succeeded"

    tenant_root = tmp_path / str(TENANT)
    tenant_root.mkdir(mode=0o700)
    os.chmod(tenant_root, 0o700)
    publication_store = MemoryPublicationStore()
    publication_store.set_authority(TENANT, lifecycle_epoch=2, work_epoch=3, profile_version=1, state="READY")
    request = PublicationRequest(
        tenant_id=TENANT,
        run_id=UUID("91000000-0000-4000-8000-000000000001"),
        profile_id=UUID("92000000-0000-4000-8000-000000000001"),
        lifecycle_epoch=2,
        work_epoch=3,
        profile_version=1,
        manifest_input_digest="e" * 64,
    )
    pages = (
        WikiPage("index.md", "Results", "Top candidate: Synthetic Co"),
        WikiPage("profile.md", "Profile", "Synthetic confirmed profile"),
        WikiPage("searches/run-1.md", "Search", "Fixture search"),
        WikiPage("jobs/job-1.md", "Job", "Synthetic public evidence"),
        WikiPage("decisions.md", "Decisions", "None"),
    )

    def crash(point: str) -> None:
        if point == "before:database_cas":
            raise PublicationCrash(point)

    with pytest.raises(PublicationCrash):
        AtomicWikiPublisher(tenant_root, TENANT, publication_store, fault=crash).publish(request, pages)
    restarted_publisher = AtomicWikiPublisher(tenant_root, TENANT, publication_store)
    restarted_publisher.reconcile()
    restarted_publisher.publish(request, pages)
    exported: list[bytes] = []
    WikiExporter(restarted_publisher).deliver(TENANT, exported.append)
    assert len(exported) == 1
    with zipfile.ZipFile(io.BytesIO(exported[0])) as archive:
        assert b"Synthetic Co" in archive.read("index.md")

    projection = project_control_room(
        AggregateMetrics(
            run_counts={"succeeded": 1},
            state_counts={"READY": 1},
            error_class_counts={"injected_restart": 2},
            latency_ms={"p95": 100},
            proof_debt=("G4 dedicated bot not evaluated",),
            build_refs=("sha256:" + "f" * 64,),
            correlation_ids=("golden-opaque",),
        ),
        build_health_report(
            (
                HealthCheck("database", HealthStatus.PASS),
                HealthCheck("provider", HealthStatus.PASS),
                HealthCheck("vault", HealthStatus.PASS),
            ),
            generated_at="2026-07-30T12:00:00Z",
        ),
    )
    serialized = json.dumps(projection, sort_keys=True)
    assert projection["health"]["status"] == "pass"
    assert str(TENANT) not in serialized
    assert "Synthetic Co" not in serialized
    assert "Platform Engineer" not in serialized
