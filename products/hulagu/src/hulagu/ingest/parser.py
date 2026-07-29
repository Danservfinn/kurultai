"""Strict ParsedCv/v1 validation without parser-library imports."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


class ParserResultError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedField:
    field_id: str
    value: str | int | float | bool | None | list[str | int | float | bool | None]
    source: str
    confidence: float
    source_span: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedCv:
    schema_version: str
    document_sha256: str
    fields: tuple[ParsedField, ...]


def parse_result(payload: bytes, *, expected_digest: str) -> ParsedCv:
    if len(payload) > 1_048_576:
        raise ParserResultError("parser result too large")
    try:
        value = json.loads(payload, parse_constant=_reject_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ParserResultError("malformed parser JSON") from None
    if not isinstance(value, dict) or set(value) != {"schema_version", "document_sha256", "fields"}:
        raise ParserResultError("invalid ParsedCv/v1 envelope")
    if value["schema_version"] != "ParsedCv/v1" or value["document_sha256"] != expected_digest:
        raise ParserResultError("parser result authority mismatch")
    raw_fields = value["fields"]
    if not isinstance(raw_fields, list) or len(raw_fields) > 128:
        raise ParserResultError("invalid ParsedCv/v1 fields")
    fields: list[ParsedField] = []
    for raw in raw_fields:
        if not isinstance(raw, dict) or not {"field_id", "value", "source", "confidence"} <= set(raw):
            raise ParserResultError("invalid ParsedCv/v1 field")
        if set(raw) - {"field_id", "value", "source", "confidence", "source_span"}:
            raise ParserResultError("unknown ParsedCv/v1 field property")
        field_id = raw["field_id"]
        source = raw["source"]
        confidence = raw["confidence"]
        source_span = raw.get("source_span")
        if not isinstance(field_id, str) or not 1 <= len(field_id) <= 128 or source != "cv":
            raise ParserResultError("invalid ParsedCv/v1 field authority")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ParserResultError("invalid ParsedCv/v1 confidence")
        if source_span is not None and (not isinstance(source_span, str) or len(source_span) > 256):
            raise ParserResultError("invalid ParsedCv/v1 source span")
        parsed_value = _value(raw["value"])
        fields.append(ParsedField(field_id, parsed_value, source, float(confidence), source_span))
    return ParsedCv("ParsedCv/v1", expected_digest, tuple(fields))


def _value(value: object) -> str | int | float | bool | None | list[str | int | float | bool | None]:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list) and len(value) <= 64 and all(
        item is None
        or isinstance(item, (str, bool, int))
        or (isinstance(item, float) and math.isfinite(item))
        for item in value
    ):
        return value
    raise ParserResultError("invalid ParsedCv/v1 value")


def _reject_nonfinite(_value: str) -> object:
    raise ValueError("non-finite JSON number")
