from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

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
