from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from hulagu.deletion_app import (
    DeletionDispatcher,
    FixedCompletionRequest,
    MemoryDeletionDeliveryStore,
    RouteEnvelopeKeys,
)

ROOT = Path(__file__).parents[2]
_SPEC = importlib.util.spec_from_file_location("hulagu_task9_pg_helpers", ROOT / "tests" / "integration" / "test_migrations.py")
assert _SPEC is not None and _SPEC.loader is not None
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
postgres_cluster = _HELPERS.postgres_cluster
psql = _HELPERS.psql


def test_route_envelope_uses_random_dek_with_separate_active_and_deletion_wrappers() -> None:
    issuer = RouteEnvelopeKeys.for_issuer(
        active_keys={3: b"a" * 32},
        deletion_keys={7: b"d" * 32},
    )
    ordinary = RouteEnvelopeKeys.for_active({3: b"a" * 32})
    deletion = RouteEnvelopeKeys.for_deletion({7: b"d" * 32})
    envelope = issuer.seal(
        12345,
        generation=9,
        bot_id=777,
        active_key_version=3,
        deletion_key_version=7,
    )
    second = issuer.seal(
        12345,
        generation=9,
        bot_id=777,
        active_key_version=3,
        deletion_key_version=7,
    )
    deletion_projection = envelope.deletion_projection()

    assert envelope.route_ciphertext != second.route_ciphertext
    assert envelope.active_wrapped_dek != envelope.deletion_wrapped_dek
    assert ordinary.open_active(envelope) == (12345, 9)
    assert deletion.open_deletion(deletion_projection) == (12345, 9)
    assert "active" not in json.loads(deletion_projection)
    with pytest.raises(PermissionError, match="active"):
        deletion.open_active(envelope)
    with pytest.raises(PermissionError, match="deletion"):
        ordinary.open_deletion(deletion_projection)


def test_dispatcher_can_only_claim_opaque_id_and_encrypted_deletion_route() -> None:
    store = MemoryDeletionDeliveryStore()
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={4: b"d" * 32})
    keys = RouteEnvelopeKeys.for_deletion({4: b"d" * 32})
    envelope = issuer.seal(
        12345,
        generation=9,
        bot_id=777,
        active_key_version=1,
        deletion_key_version=4,
    ).deletion_projection()
    store.enqueue("deletion-1", envelope, expires_at=999)
    sent: list[FixedCompletionRequest] = []
    dispatcher = DeletionDispatcher(store, keys, sent.append, clock=lambda: 100)
    assert dispatcher.dispatch("deletion-1") == "delivered"
    assert sent == [FixedCompletionRequest("deletion-1", 12345, 9, "deletion-complete-v1")]
    assert store.claim_projection("deletion-1") == {"deletion_id", "encrypted_route"}
    assert not hasattr(dispatcher, "tenant_repository")
    assert not hasattr(dispatcher, "active_route_keys")


def test_dispatcher_rejects_arbitrary_route_substitution_for_valid_deletion_id() -> None:
    store = MemoryDeletionDeliveryStore()
    issuer = RouteEnvelopeKeys.for_issuer(active_keys={1: b"a" * 32}, deletion_keys={2: b"x" * 32})
    keys = RouteEnvelopeKeys.for_deletion({2: b"x" * 32})
    envelope = issuer.seal(
        111,
        generation=1,
        bot_id=777,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    store.enqueue("deletion-1", envelope, expires_at=999)
    replacement = issuer.seal(
        222,
        generation=1,
        bot_id=777,
        active_key_version=1,
        deletion_key_version=2,
    ).deletion_projection()
    store.substitute_ciphertext("deletion-1", replacement)
    dispatcher = DeletionDispatcher(store, keys, lambda request: None, clock=lambda: 100)
    assert dispatcher.dispatch("deletion-1") == "failed"


def test_normal_sender_source_has_no_deletion_route_key_reader() -> None:
    sender_source = (ROOT / "src" / "hulagu" / "telegram" / "sender.py").read_text()
    assert "RouteEnvelopeKeys" not in sender_source
    assert "deletion_route" not in sender_source


def test_real_postgres_roles_enforce_deletion_route_and_tenant_privilege_separation() -> None:
    tenant = "90000000-0000-4000-8000-000000000009"
    nonce_hash = hashlib.sha256(b"role-separation-deletion-nonce").hexdigest()
    erasure_token = "role-separation-erasure-token"
    erasure_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch,deletion_nonce_hash) "
            f"VALUES('{tenant}','READY',3,'{nonce_hash}');"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant}',repeat('a',64),repeat('b',64));",
        )
        deletion_id = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant}';"
            f"SELECT hulagu_api.request_deletion('{nonce_hash}','encrypted-deletion-route',repeat('c',64));"
            "COMMIT;",
            user="hulagu_app",
        ).stdout.strip()
        assert deletion_id
        assert psql(dsn, "SELECT count(*) FROM hulagu.tenants", user="hulagu_deletion", check=False).returncode != 0
        assert psql(dsn, "SELECT count(*) FROM hulagu.deletion_jobs", user="hulagu_deletion", check=False).returncode != 0
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}')",
            user="hulagu_app",
            check=False,
        ).returncode != 0
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}')",
            user="hulagu_deletion",
        ).stdout.strip() == tenant
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}')",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
        claimed = json.loads(
            psql(
                dsn,
                f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}',repeat('d',64))",
                user="hulagu_deletion",
            ).stdout
        )
        assert claimed == {"status": "claimed", "encrypted_route": "encrypted-deletion-route"}
        forged = "90000000-0000-4000-8000-000000000099"
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_delivery('{forged}',repeat('e',64)) IS NULL",
            user="hulagu_deletion",
        ).stdout.strip() == "t"


def test_real_postgres_global_deletion_rows_survive_tenant_erasure_and_minimize() -> None:
    tenant = "90000000-0000-4000-8000-000000000010"
    nonce_hash = hashlib.sha256(b"global-state-deletion-nonce").hexdigest()
    token = "synthetic-delivery-token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    erasure_token = "synthetic-erasure-token"
    erasure_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    with postgres_cluster() as dsn:
        psql(
            dsn,
            f"INSERT INTO hulagu.tenants(id,state,lifecycle_epoch,deletion_nonce_hash) "
            f"VALUES('{tenant}','READY',4,'{nonce_hash}');"
            "INSERT INTO hulagu.identity_bindings(tenant_id,subject_digest,subject_fence_digest) "
            f"VALUES('{tenant}',repeat('a',64),repeat('b',64));"
            "INSERT INTO hulagu.customer_profiles(tenant_id,profile_version,profile_json,state) "
            f"VALUES('{tenant}',1,'{{\"synthetic\":true}}','confirmed');",
        )
        deletion_id = psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant}';"
            f"SELECT hulagu_api.request_deletion('{nonce_hash}','encrypted-deletion-route',repeat('c',64));"
            "COMMIT;",
            user="hulagu_app",
        ).stdout.strip()
        psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}');"
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}');"
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{token_hash}');",
            user="hulagu_deletion",
        )
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','{token}','delivered')",
            user="hulagu_deletion",
        ).stdout.strip() == "delivered"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.tenants WHERE id='{tenant}'").stdout.strip() == "0"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.customer_profiles WHERE tenant_id='{tenant}'").stdout.strip() == "0"
        assert psql(
            dsn,
            f"SELECT (target_tenant_id IS NULL) AND encrypted_route IS NULL AND subject_fence_digest IS NULL "
            f"FROM hulagu.deletion_jobs WHERE deletion_id='{deletion_id}'",
        ).stdout.strip() == "t"
        assert psql(dsn, f"SELECT count(*) FROM hulagu.deletion_receipts WHERE deletion_id='{deletion_id}'").stdout.strip() == "1"


def test_real_postgres_expired_deletion_authority_cannot_claim_or_finalize() -> None:
    deletion_id = "90000000-0000-4000-8000-000000000011"
    with postgres_cluster() as dsn:
        psql(
            dsn,
            "INSERT INTO hulagu.deletion_jobs(deletion_id,target_tenant_id,subject_fence_digest,encrypted_route,"
            "route_binding_digest,state,expires_at) VALUES"
            f"('{deletion_id}','90000000-0000-4000-8000-000000000012',repeat('a',64),'cipher',repeat('b',64),"
            "'pending',now()-interval '1 second')",
        )
        assert psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}',repeat('c',64)) IS NULL",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
        assert psql(
            dsn,
            f"SELECT hulagu_api.complete_deletion_delivery('{deletion_id}','expired-token','expired') IS NULL",
            user="hulagu_deletion",
        ).stdout.strip() == "t"
