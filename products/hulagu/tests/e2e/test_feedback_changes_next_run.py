from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

import pytest

from hulagu.domain.feedback import (
    FeedbackFlow,
    compile_next_search,
    pages_for_feedback_republication,
    rank_with_feedback,
)
from hulagu.domain.profile import Profile, ProfileField
from hulagu.persistence.rls import TenantPrincipal
from hulagu.search.planner import compile_search_plan
from hulagu.search.provider import FixtureSearchProvider, ProviderAttempt, SearchCoordinator
from hulagu.search.schemas import Candidate
from hulagu.wiki.model import PublicationRequest, WikiPage
from hulagu.wiki.publish import AtomicWikiPublisher, MemoryPublicationStore

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_task8_pg_helpers", ROOT / "tests" / "e2e" / "test_start_and_resume.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
PsqlConnection = _HELPERS.PsqlConnection
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql

TENANT_A = UUID("84000000-0000-4000-8000-00000000000a")
TENANT_B = UUID("84000000-0000-4000-8000-00000000000b")
PROFILE_A = UUID("85000000-0000-4000-8000-00000000000a")
PROFILE_B = UUID("85000000-0000-4000-8000-00000000000b")
RUN_A = UUID("86000000-0000-4000-8000-00000000000a")
RUN_B = UUID("86000000-0000-4000-8000-00000000000b")
CANDIDATE_A = UUID("87000000-0000-4000-8000-00000000000a")
CANDIDATE_A_SECOND = UUID("87000000-0000-4000-8000-00000000001a")
CANDIDATE_B = UUID("87000000-0000-4000-8000-00000000000b")
SIGNING_KEY = b"task-8-synthetic-feedback-key-material"


def principal(tenant: UUID) -> TenantPrincipal:
    return TenantPrincipal.from_identity_resolution(str(tenant), "telegram-customer")


def candidate(path: str, company: str) -> Candidate:
    return Candidate(
        canonical_url=f"https://jobs.example.test/{path}",
        title="Senior Platform Engineer",
        company=company,
        location="Remote",
        remote_signal="remote",
        source_provider="fixture-public-search-adapter",
        retrieved_at="2026-07-29T00:00:00Z",
        snippet="Synthetic public listing evidence for Python platform work",
        evidence_grade="source",
        required_terms=("python",),
    )


def profile() -> Profile:
    return Profile(
        1,
        (
            ProfileField("target_role", "Platform Engineer", "customer", 1.0),
            ProfileField("location", "Remote", "customer", 1.0),
            ProfileField("required_skills", "Python", "customer", 1.0),
            ProfileField("excluded_terms", "Clearance", "customer", 1.0),
            ProfileField("remote_policy", "remote", "customer", 1.0),
        ),
        confirmed_version=1,
    )


def sql_json(value: object) -> str:
    return "'" + json.dumps(value, separators=(",", ":"), sort_keys=True).replace("'", "''") + "'::jsonb"


def seed(dsn: str) -> None:
    item_a = candidate("first-a", "RejectCo")
    item_a_second = candidate("second-a", "RejectCo")
    item_b = candidate("first-b", "KeepCo")
    for tenant, profile_id, run_id, candidate_id, item in (
        (TENANT_A, PROFILE_A, RUN_A, CANDIDATE_A, item_a),
        (TENANT_B, PROFILE_B, RUN_B, CANDIDATE_B, item_b),
    ):
        psql(dsn, f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch) VALUES('{tenant}','READY',3)")
        psql(
            dsn,
            f"INSERT INTO hulagu.customer_profiles(tenant_id,id,profile_version,profile_json,state) "
            f"VALUES('{tenant}','{profile_id}',1,'{{}}','confirmed')",
        )
        psql(
            dsn,
            f"INSERT INTO hulagu.search_runs(tenant_id,id,profile_id,state,query_plan,budget,work_epoch) "
            f"VALUES('{tenant}','{run_id}','{profile_id}','results_ready','{{\"profile_version\":1}}','{{}}',2)",
        )
        psql(
            dsn,
            f"INSERT INTO hulagu.search_candidates(tenant_id,id,run_id,listing_key,evidence) "
            f"VALUES('{tenant}','{candidate_id}','{run_id}','{item.normalized_url_hash}',{sql_json(asdict(item))})",
        )
    psql(
        dsn,
        f"INSERT INTO hulagu.search_candidates(tenant_id,id,run_id,listing_key,evidence) "
        f"VALUES('{TENANT_A}','{CANDIDATE_A_SECOND}','{RUN_A}','{item_a_second.normalized_url_hash}',{sql_json(asdict(item_a_second))})",
    )


def test_real_feedback_entrypoint_is_tenant_local_idempotent_changes_second_run_and_republishes(tmp_path: Path) -> None:
    with postgres_cluster() as dsn:
        seed(dsn)
        connection_a = PsqlConnection(dsn)
        connection_b = PsqlConnection(dsn)
        try:
            flow_a = FeedbackFlow(connection_a, principal(TENANT_A), signing_key=SIGNING_KEY, clock=lambda: 100)
            flow_b = FeedbackFlow(connection_b, principal(TENANT_B), signing_key=SIGNING_KEY, clock=lambda: 100)
            action = flow_a.issue_action(
                CANDIDATE_A,
                "rejected",
                profile_version=1,
                lifecycle_epoch=3,
                expires_at=200,
            )

            with pytest.raises(PermissionError, match="authority"):
                flow_b.record(action, reason="wrong tenant", correlation_id="task8-cross-tenant")
            first = flow_a.record(action, reason="not a fit", correlation_id="task8-first")
            replay = flow_a.record(action, reason="must not replace", correlation_id="task8-replay")

            assert first.applied is True
            assert replay.applied is False
            assert replay.decision_id == first.decision_id
            assert replay.reason == "not a fit"
            assert psql(dsn, f"SELECT count(*) FROM hulagu.candidate_decisions WHERE tenant_id='{TENANT_A}'").stdout.strip() == "1"
            assert psql(dsn, f"SELECT count(*) FROM hulagu.candidate_decisions WHERE tenant_id='{TENANT_B}'").stdout.strip() == "0"

            base = compile_search_plan(profile())
            second_plan = compile_next_search(base, flow_a.features(correlation_id="task8-features-a"))
            untouched_b = compile_next_search(base, flow_b.features(correlation_id="task8-features-b"))
            provider = FixtureSearchProvider(
                [
                    ProviderAttempt.success(
                        [
                            {
                                "url": "https://jobs.example.test/second-rejectco",
                                "title": "Senior Platform Engineer",
                                "company": "RejectCo",
                                "location": "Remote",
                                "remote_signal": "remote",
                                "snippet": "Python platform work",
                            },
                            {
                                "url": "https://jobs.example.test/second-otherco",
                                "title": "Senior Platform Engineer",
                                "company": "OtherCo",
                                "location": "Remote",
                                "remote_signal": "remote",
                                "snippet": "Python platform work",
                            },
                        ]
                    )
                ]
            )
            search = SearchCoordinator(provider, clock=lambda: 100).run(second_plan.execution)
            ranked = rank_with_feedback(search.candidates, second_plan)

            assert second_plan.execution.queries != base.queries
            assert untouched_b.execution.queries == base.queries
            assert ranked[0].candidate.company == "OtherCo"
            rejected = next(item for item in ranked if item.candidate.company == "RejectCo")
            assert rejected.components["tenant_feedback_match"] == -2.0
            assert "rejected company RejectCo=-2" in rejected.explanation

            pages = pages_for_feedback_republication(
                (
                    WikiPage("index.md", "Index", "[[profile]] [[decisions]] [[searches/run-2]] [[jobs/job-1]]"),
                    WikiPage("profile.md", "Profile", "Confirmed constraints remain unchanged."),
                    WikiPage("decisions.md", "Decisions", "None."),
                    WikiPage("searches/run-2.md", "Search", "Before feedback."),
                    WikiPage("jobs/job-1.md", "Job", "Original public source evidence."),
                ),
                flow_a.decisions(correlation_id="task8-decisions"),
                ranked,
                search_path="searches/run-2.md",
            )
            tenant_root = tmp_path / str(TENANT_A)
            tenant_root.mkdir(mode=0o700)
            os.chmod(tenant_root, 0o700)
            store = MemoryPublicationStore()
            store.set_authority(TENANT_A, lifecycle_epoch=3, work_epoch=2, profile_version=1, state="READY")
            publisher = AtomicWikiPublisher(tenant_root, TENANT_A, store)
            publication = publisher.publish(
                PublicationRequest(
                    tenant_id=TENANT_A,
                    run_id=RUN_A,
                    profile_id=PROFILE_A,
                    lifecycle_epoch=3,
                    work_epoch=2,
                    profile_version=1,
                    manifest_input_digest="a" * 64,
                ),
                pages,
            )
            active = publisher.read_active()
            rendered = dict(active.files)

            assert publication.visibility_state == "active"
            assert b"rejected" in rendered["decisions.md"]
            assert b"tenant_feedback_match=-2" in rendered["searches/run-2.md"]
            assert b"Original public source evidence" in rendered["jobs/job-1.md"]

            pending = flow_a.issue_action(
                CANDIDATE_A_SECOND,
                "saved",
                profile_version=1,
                lifecycle_epoch=3,
                expires_at=200,
            )
            psql(dsn, f"UPDATE hulagu.tenants SET state='DELETING',lifecycle_epoch=4 WHERE id='{TENANT_A}'")
            with pytest.raises(PermissionError, match="authority"):
                flow_a.record(pending, reason=None, correlation_id="task8-deleting-new")
            with pytest.raises(PermissionError, match="authority"):
                flow_a.record(action, reason=None, correlation_id="task8-deleting-replay")
            assert psql(dsn, f"SELECT count(*) FROM hulagu.candidate_decisions WHERE tenant_id='{TENANT_A}'").stdout.strip() == "1"
        finally:
            connection_a.close()
            connection_b.close()
