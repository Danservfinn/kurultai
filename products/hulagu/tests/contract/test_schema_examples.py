from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import jsonschema
import pytest

from hulagu.domain.deletion import MemoryDeletionWorkflow, TombstoneFence

SCHEMA_DIR = Path(__file__).parents[2] / "schemas"
EXPECTED_SCHEMAS = {
    "action-token-v1.schema.json": "ActionToken/v1",
    "backup-manifest-v1.schema.json": "BackupManifest/v1",
    "candidate-bundle-v1.schema.json": "CandidateBundle/v1",
    "deletion-tombstone-v1.schema.json": "DeletionTombstone/v1",
    "durable-event-v1.schema.json": "DurableEvent/v1",
    "health-report-v1.schema.json": "HealthReport/v1",
    "parsed-cv-v1.schema.json": "ParsedCv/v1",
    "provider-response-v1.schema.json": "ProviderResponse/v1",
    "receipt-v1.schema.json": "Receipt/v1",
    "search-plan-v1.schema.json": "SearchPlan/v1",
    "telegram-update-v1.schema.json": "TelegramUpdate/v1",
    "wiki-manifest-v1.schema.json": "WikiManifest/v1",
}


def load_schema(filename: str) -> dict[str, Any]:
    decoded = json.loads((SCHEMA_DIR / filename).read_text())
    assert isinstance(decoded, dict)
    return decoded


def validator_for(filename: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema(filename))


def first_example(filename: str) -> dict[str, Any]:
    example = copy.deepcopy(load_schema(filename)["examples"][0])
    assert isinstance(example, dict)
    return example


def test_exact_declared_schema_set_is_present() -> None:
    actual = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}
    assert actual == set(EXPECTED_SCHEMAS)


@pytest.mark.parametrize(("filename", "title"), EXPECTED_SCHEMAS.items())
def test_schema_and_embedded_examples_validate(filename: str, title: str) -> None:
    schema = load_schema(filename)
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["title"] == title
    assert schema["additionalProperties"] is False
    assert schema["examples"], "each frozen contract needs at least one valid example"
    validator = jsonschema.Draft202012Validator(schema)
    for example in schema["examples"]:
        validator.validate(example)


@pytest.mark.parametrize("filename", EXPECTED_SCHEMAS)
def test_top_level_additional_properties_are_rejected(filename: str) -> None:
    example = first_example(filename)
    example["unexpected_contract_field"] = "rejected"
    with pytest.raises(jsonschema.ValidationError):
        validator_for(filename).validate(example)


@pytest.mark.parametrize("filename", EXPECTED_SCHEMAS)
def test_each_top_level_required_property_is_enforced(filename: str) -> None:
    schema = load_schema(filename)
    validator = jsonschema.Draft202012Validator(schema)
    for required_property in schema["required"]:
        example = copy.deepcopy(schema["examples"][0])
        example.pop(required_property)
        with pytest.raises(jsonschema.ValidationError, match="is a required property"):
            validator.validate(example)


def test_action_token_requires_object_version() -> None:
    token = first_example("action-token-v1.schema.json")
    token.pop("object_version")
    with pytest.raises(jsonschema.ValidationError, match="object_version.*required property"):
        validator_for("action-token-v1.schema.json").validate(token)


def test_telegram_update_requires_chat_id() -> None:
    update = first_example("telegram-update-v1.schema.json")
    update.pop("chat_id")
    with pytest.raises(jsonschema.ValidationError, match="chat_id.*required property"):
        validator_for("telegram-update-v1.schema.json").validate(update)


def test_parsed_cv_allows_only_scalar_array_items() -> None:
    parsed_cv = first_example("parsed-cv-v1.schema.json")
    parsed_cv["fields"][0]["value"] = ["Python", 3, True, None]
    validator_for("parsed-cv-v1.schema.json").validate(parsed_cv)


@pytest.mark.parametrize("invalid_item", [{"nested": "object"}, ["nested", "array"]])
def test_parsed_cv_rejects_nested_array_items(invalid_item: object) -> None:
    parsed_cv = first_example("parsed-cv-v1.schema.json")
    parsed_cv["fields"][0]["value"] = [invalid_item]
    with pytest.raises(jsonschema.ValidationError):
        validator_for("parsed-cv-v1.schema.json").validate(parsed_cv)


def test_deletion_tombstone_accepts_only_exact_encrypted_six_field_contract() -> None:
    example = first_example("deletion-tombstone-v1.schema.json")
    assert set(example) == {
        "schema_version",
        "encrypted_subject_digest",
        "deletion_epoch",
        "completed_at",
        "backup_expiry_horizon",
        "rekey_state",
    }
    validator_for("deletion-tombstone-v1.schema.json").validate(example)


def test_deletion_tombstone_embedded_example_is_an_authenticated_synthetic_envelope() -> None:
    example = first_example("deletion-tombstone-v1.schema.json")
    fence = TombstoneFence({1: b"synthetic-tombstone-schema-key"}, active_version=1)
    assert fence.matches(example, 777, 888, now=datetime(2026, 7, 29, tzinfo=UTC))


def test_deletion_tombstone_rejects_legacy_plaintext_five_field_contract() -> None:
    legacy = {
        "schema_version": "DeletionTombstone/v1",
        "subject_digest": "b" * 64,
        "key_version": 1,
        "created_at": "2026-07-27T00:00:00Z",
        "expires_at": "2027-07-27T00:00:00Z",
    }
    with pytest.raises(jsonschema.ValidationError):
        validator_for("deletion-tombstone-v1.schema.json").validate(legacy)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "b" * 64,
        base64.urlsafe_b64encode(b"b" * 64).decode("ascii"),
        "hts1." + base64.urlsafe_b64encode(b"b" * 64).decode("ascii"),
    ],
)
def test_deletion_tombstone_rejects_plaintext_and_trivially_reversible_subject_values(unsafe_value: str) -> None:
    tombstone = {
        "schema_version": "DeletionTombstone/v1",
        "encrypted_subject_digest": unsafe_value,
        "deletion_epoch": 8,
        "completed_at": "2026-07-29T00:00:00Z",
        "backup_expiry_horizon": "2026-11-03T00:00:00Z",
        "rekey_state": "current",
    }
    with pytest.raises(jsonschema.ValidationError):
        validator_for("deletion-tombstone-v1.schema.json").validate(tombstone)


def test_persisted_memory_deletion_workflow_tombstone_validates_and_hides_subject_digest(tmp_path: Path) -> None:
    tenant_id = UUID("90000000-0000-4000-8000-000000000099")
    now = datetime(2026, 7, 29, tzinfo=UTC)
    bot_id = 777
    actor_id = 888
    state_path = tmp_path / "state.json"
    tenants_root = tmp_path / "tenants"
    fence = TombstoneFence({1: b"synthetic-tombstone-contract-key"}, active_version=1)
    workflow = MemoryDeletionWorkflow(state_path, tenants_root, tombstone_fence=fence)
    workflow.seed_tenant(
        tenant_id,
        lifecycle_epoch=7,
        nonce="single-use",
        bot_id=bot_id,
        actor_id=actor_id,
        encrypted_route="synthetic-encrypted-route",
        route_generation=3,
        route_binding_digest="c" * 64,
        rows={},
        ordinary_outbox=(),
        active_work=(),
    )
    job = workflow.confirm(tenant_id, nonce="single-use", expected_epoch=7, now=now)
    for _ in range(3):
        workflow.advance(job.deletion_id, now=now)
    workflow.record_delivery(job.deletion_id, "delivered", now=now)
    workflow.advance(job.deletion_id, now=now)

    restored = MemoryDeletionWorkflow.open(state_path, tenants_root, tombstone_fence=fence)
    tombstone = restored.tombstone(job.deletion_id)
    validator_for("deletion-tombstone-v1.schema.json").validate(tombstone)

    encrypted = str(tombstone["encrypted_subject_digest"])
    assert encrypted.startswith("hts1.")
    packed = base64.urlsafe_b64decode(encrypted.removeprefix("hts1."))
    subject_digest = hashlib.sha256(f"hulagu.deletion-subject.v1\0{bot_id}\0{actor_id}".encode()).digest()
    assert subject_digest not in packed
    assert tombstone["backup_expiry_horizon"] == (now + timedelta(days=97)).isoformat()
