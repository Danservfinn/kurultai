from __future__ import annotations

import json
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012


class ContractError(ValueError):
    """A public Solution Graph contract failed closed validation."""


_SCHEMA_DIR = Path(__file__).with_name("schemas")
_SCHEMA_FILES = (
    "agent-context-packet-v1.schema.json",
    "agent-context-packet-v2.schema.json",
    "artifact-manifest-v1.schema.json",
    "buildroom-recommendation-projection-v1.schema.json",
    "capability-contract-v1.schema.json",
    "environment-profile-v1.schema.json",
    "evidence-fixture-set-v1.schema.json",
    "evidence-observation-v1.schema.json",
    "execution-grant-v1.schema.json",
    "fixture-registry-v1.schema.json",
    "objective-spec-v1.schema.json",
    "objective-spec-v2.schema.json",
    "plan-simulation-v1.schema.json",
    "resolution-plan-v1.schema.json",
    "resolution-plan-v2.schema.json",
    "run-receipt-v1.schema.json",
    "validation-result-v1.schema.json",
    "verification-delta-v1.schema.json",
)
_MAX_SCHEMA_ERRORS = 6
_MAX_JSON_BYTES = 1_048_576
_MAX_DEPTH = 80
_MAX_OBJECT_KEYS = 512
_MAX_ARRAY_ITEMS = 4096
_MAX_STRING_LENGTH = 16_384
_RFC3339_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _is_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339_DATETIME.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON number is forbidden: {value}")


def validate_json_value_bounds(
    value: Any,
    *,
    max_depth: int = _MAX_DEPTH,
    max_object_keys: int = _MAX_OBJECT_KEYS,
    max_array_items: int = _MAX_ARRAY_ITEMS,
    max_string_length: int = _MAX_STRING_LENGTH,
) -> None:
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise ContractError("JSON document exceeds maximum nesting depth")
        if isinstance(current, str):
            if len(current) > max_string_length:
                raise ContractError("JSON string exceeds maximum length")
        elif isinstance(current, bool) or current is None:
            continue
        elif isinstance(current, int):
            continue
        elif isinstance(current, float):
            if not math.isfinite(current):
                raise ContractError("non-finite JSON number is forbidden")
        elif isinstance(current, list):
            if len(current) > max_array_items:
                raise ContractError("JSON array exceeds maximum item count")
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, dict):
            if len(current) > max_object_keys:
                raise ContractError("JSON object exceeds maximum key count")
            stack.extend((item, depth + 1) for item in current.values())
        else:
            raise ContractError("unsupported JSON value type")


def loads_strict_json(data: str | bytes, *, max_bytes: int = _MAX_JSON_BYTES) -> Any:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > max_bytes:
        raise ContractError("JSON document exceeds maximum byte size")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except UnicodeDecodeError as exc:
        raise ContractError("JSON document must be UTF-8") from exc
    validate_json_value_bounds(value)
    return value


def load_json_file(path: Path, *, max_bytes: int = _MAX_JSON_BYTES) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ContractError("JSON path must be a regular file")
    size = path.stat().st_size
    if size > max_bytes:
        raise ContractError("JSON document exceeds maximum byte size")
    return loads_strict_json(path.read_bytes(), max_bytes=max_bytes)


def _schema_discriminator(schema: dict[str, Any]) -> str:
    discriminator = schema.get("properties", {}).get("schema", {}).get("const")
    if not isinstance(discriminator, str) or not discriminator:
        raise ContractError("schema file missing exact contract discriminator")
    return discriminator


@lru_cache(maxsize=1)
def _validators() -> dict[str, Draft202012Validator]:
    schemas: dict[str, dict[str, Any]] = {}
    discriminator_to_id: dict[str, str] = {}
    resources: list[tuple[str, Resource[dict[str, Any]]]] = []

    for filename in _SCHEMA_FILES:
        path = _SCHEMA_DIR / filename
        schema = load_json_file(path)
        if not isinstance(schema, dict):
            raise ContractError("schema file must be an object")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ContractError(f"invalid shipped JSON Schema: {filename}") from exc
        schema_id = schema.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise ContractError(f"schema file missing $id: {filename}")
        discriminator = _schema_discriminator(schema)
        if discriminator in discriminator_to_id:
            raise ContractError(f"duplicate contract discriminator: {discriminator}")
        schemas[schema_id] = schema
        discriminator_to_id[discriminator] = schema_id
        resources.append((schema_id, Resource.from_contents(schema, default_specification=DRAFT202012)))

    registry = Registry().with_resources(resources)
    # jsonschema's RFC 3339 checker is an optional dependency. Register a
    # package-local checker so `format: date-time` never silently degrades.
    format_checker = FormatChecker()
    format_checker.checks("date-time")(_is_rfc3339_datetime)
    return {
        discriminator: Draft202012Validator(
            schemas[schema_id],
            registry=registry,
            format_checker=format_checker,
        )
        for discriminator, schema_id in discriminator_to_id.items()
    }


def allowed_contract_schemas() -> tuple[str, ...]:
    return tuple(sorted(_validators()))


def check_shipped_schemas() -> None:
    _validators()


def _json_path(error: ValidationError) -> str:
    path = "$"
    for part in error.absolute_path:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def _schema_path(error: ValidationError) -> str:
    return "/".join(str(part) for part in error.absolute_schema_path)


def _reason_code(error: ValidationError) -> str:
    return {
        "additionalProperties": "unknown_field",
        "const": "const_mismatch",
        "enum": "enum_mismatch",
        "format": "format_mismatch",
        "maxItems": "array_too_long",
        "maxLength": "string_too_long",
        "maximum": "number_above_maximum",
        "minItems": "array_too_short",
        "minLength": "string_too_short",
        "minimum": "number_below_minimum",
        "oneOf": "one_of_mismatch",
        "pattern": "pattern_mismatch",
        "required": "missing_required",
        "type": "type_mismatch",
        "uniqueItems": "duplicate_array_item",
    }.get(str(error.validator), "schema_keyword_mismatch")


def _sorted_errors(errors: list[ValidationError]) -> list[ValidationError]:
    return sorted(
        errors,
        key=lambda error: (
            _json_path(error),
            _schema_path(error),
            str(error.validator),
            _reason_code(error),
        ),
    )


def _render_errors(discriminator: str, errors: list[ValidationError]) -> str:
    rendered = []
    for error in _sorted_errors(errors)[:_MAX_SCHEMA_ERRORS]:
        rendered.append(
            f"{_json_path(error)}:{_reason_code(error)}:{str(error.validator)}"
        )
    if len(errors) > _MAX_SCHEMA_ERRORS:
        rendered.append("more_errors_truncated")
    return f"schema validation failed for {discriminator}: " + "; ".join(rendered)


def validate_contract_schema(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ContractError("contract must be an object")
    validate_json_value_bounds(document)
    discriminator = document.get("schema")
    if not isinstance(discriminator, str):
        raise ContractError("contract schema discriminator is required")
    validators = _validators()
    validator = validators.get(discriminator)
    if validator is None:
        raise ContractError(f"unsupported contract schema: {discriminator}")
    try:
        errors = list(validator.iter_errors(document))
    except Unresolvable as exc:
        raise ContractError("schema reference resolution failed") from exc
    if errors:
        raise ContractError(_render_errors(discriminator, errors))
    return document
