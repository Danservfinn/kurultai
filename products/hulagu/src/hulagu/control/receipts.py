"""Deterministic release receipts with recursive PII/secret redaction."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import TypeAlias
from urllib.parse import urlsplit, urlunsplit

from .privacy import sensitive_key, unsafe_operator_value

ReceiptValue: TypeAlias = None | bool | int | float | str | list["ReceiptValue"] | dict[str, "ReceiptValue"]

_SECRET_VALUE = re.compile(r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|password\s*[:=]|api[_ -]?key\s*[:=])")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_EVIDENCE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReceiptRejected(ValueError):
    pass


def _redact_string(value: str) -> str:
    if len(value) > 2_000:
        raise ReceiptRejected("receipt string exceeds bound")
    if _SECRET_VALUE.search(value) or _EMAIL.search(value):
        return "[REDACTED]"
    if value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return "[REDACTED]"
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    if unsafe_operator_value(value):
        return "[REDACTED]"
    return value


def _redact(value: object, *, key: str | None = None, depth: int = 0) -> ReceiptValue:
    if depth > 8:
        raise ReceiptRejected("receipt nesting exceeds bound")
    if key is not None and sensitive_key(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        if len(value) > 100:
            raise ReceiptRejected("receipt mapping exceeds bound")
        result: dict[str, ReceiptValue] = {}
        for raw_key, nested in sorted(value.items(), key=lambda item: str(item[0])):
            if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 80:
                raise ReceiptRejected("invalid receipt key")
            result[raw_key] = _redact(nested, key=raw_key, depth=depth + 1)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        if len(value) > 100:
            raise ReceiptRejected("receipt sequence exceeds bound")
        return [_redact(item, depth=depth + 1) for item in value]
    raise ReceiptRejected("unsupported receipt value")


def build_release_receipt(
    *,
    generated_at: str,
    correlation_id: str,
    summary: Mapping[str, object],
    evidence_refs: tuple[str, ...],
) -> dict[str, object]:
    if not generated_at or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", correlation_id):
        raise ReceiptRejected("invalid receipt identity")
    if not evidence_refs or len(evidence_refs) > 50 or any(not _EVIDENCE.fullmatch(item) for item in evidence_refs):
        raise ReceiptRejected("invalid evidence reference")
    redacted = _redact(summary)
    canonical = json.dumps(redacted, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "schema_version": "HulaguReleaseReceipt/v1",
        "generated_at": generated_at,
        "correlation_id": correlation_id,
        "summary": redacted,
        "evidence_refs": sorted(evidence_refs),
        "summary_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }
