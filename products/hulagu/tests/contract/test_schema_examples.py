from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

PRODUCT_ROOT = Path(__file__).parents[2]
SCHEMA_DIR = PRODUCT_ROOT / "schemas"
EXPECTED_SCHEMAS = {
    "action-token-v1.schema.json",
    "backup-manifest-v1.schema.json",
    "candidate-bundle-v1.schema.json",
    "deletion-tombstone-v1.schema.json",
    "durable-event-v1.schema.json",
    "health-report-v1.schema.json",
    "parsed-cv-v1.schema.json",
    "provider-response-v1.schema.json",
    "receipt-v1.schema.json",
    "search-plan-v1.schema.json",
    "telegram-update-v1.schema.json",
    "wiki-manifest-v1.schema.json",
}


def test_exact_declared_schema_inventory() -> None:
    observed = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}
    assert observed == EXPECTED_SCHEMAS


@pytest.mark.parametrize("name", sorted(EXPECTED_SCHEMAS))
def test_schema_embedded_examples_validate(name: str) -> None:
    from hulagu import schema_validator

    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    examples = schema.get("examples")
    assert examples, f"{name} must freeze at least one synthetic example"
    validator = schema_validator(name.removesuffix(".schema.json"))
    for example in examples:
        validator.validate(example)


@pytest.mark.parametrize(
    ("field", "value"),
    [("action_id", "not-a-uuid"), ("expires_at", "not-a-date-time")],
)
def test_action_token_rejects_malformed_declared_formats(field: str, value: str) -> None:
    from hulagu import schema_validator

    schema = json.loads((SCHEMA_DIR / "action-token-v1.schema.json").read_text(encoding="utf-8"))
    invalid = deepcopy(schema["examples"][0])
    invalid[field] = value
    assert list(schema_validator("action-token-v1").iter_errors(invalid)), (
        f"malformed {field} was accepted"
    )


def test_schema_loader_rejects_undeclared_schema_name() -> None:
    from hulagu import load_schema

    with pytest.raises(ValueError, match="undeclared schema"):
        load_schema("invented-v1")


def test_schema_loader_uses_only_exact_inventory() -> None:
    from hulagu import declared_schema_names, load_schema

    assert set(declared_schema_names()) == {
        name.removesuffix(".schema.json") for name in EXPECTED_SCHEMAS
    }
    for name in declared_schema_names():
        assert load_schema(name)["$schema"] == "https://json-schema.org/draft/2020-12/schema"
