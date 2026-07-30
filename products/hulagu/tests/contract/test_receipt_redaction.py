from __future__ import annotations

import json

import pytest

from hulagu.control.receipts import ReceiptRejected, build_release_receipt


def test_release_receipt_redacts_nested_customer_and_secret_material() -> None:
    synthetic_secret = "sk" + "-synthetic-canary-not-a-real-key"
    receipt = build_release_receipt(
        generated_at="2026-07-30T12:00:00Z",
        correlation_id="release-opaque-001",
        summary={
            "run_counts": {"succeeded": 3, "failed": 1},
            "latency_ms": {"p95": 125},
            "customer_email": "person@example.test",
            "nested": {"telegram_id": 424242, "authorization": synthetic_secret},
            "source_url": "https://jobs.example.test/role?utm_source=private&ref=person",
        },
        evidence_refs=("sha256:" + "a" * 64,),
    )

    serialized = json.dumps(receipt, sort_keys=True)
    assert receipt["schema_version"] == "HulaguReleaseReceipt/v1"
    assert receipt["correlation_id"] == "release-opaque-001"
    assert receipt["summary"]["run_counts"] == {"failed": 1, "succeeded": 3}
    assert receipt["summary"]["customer_email"] == "[REDACTED]"
    assert receipt["summary"]["nested"] == {
        "authorization": "[REDACTED]",
        "telegram_id": "[REDACTED]",
    }
    assert receipt["summary"]["source_url"] == "https://jobs.example.test/role"
    assert "person@example.test" not in serialized
    assert synthetic_secret not in serialized
    assert "424242" not in serialized
    assert "utm_source" not in serialized


def test_release_receipt_rejects_unbounded_or_unversioned_evidence() -> None:
    with pytest.raises(ReceiptRejected, match="evidence"):
        build_release_receipt(
            generated_at="2026-07-30T12:00:00Z",
            correlation_id="release-opaque-002",
            summary={"run_counts": {"succeeded": 1}},
            evidence_refs=("relative/private/path",),
        )


def test_release_receipt_is_deterministic_for_same_redacted_input() -> None:
    arguments = {
        "generated_at": "2026-07-30T12:00:00Z",
        "correlation_id": "release-opaque-003",
        "summary": {"state_counts": {"READY": 2}, "proof_debt": ["G3 native service evidence"]},
        "evidence_refs": ("sha256:" + "b" * 64,),
    }
    assert build_release_receipt(**arguments) == build_release_receipt(**arguments)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    (
        ("note", "call +1-415-555-0199", "[REDACTED]"),
        ("note", "telegram route 424242", "[REDACTED]"),
        ("note", "/Volumes/KurultaiVault/private/customer", "[REDACTED]"),
        ("note", "https://jobs.example.test/role?query=private", "https://jobs.example.test/role"),
        ("te\N{ZERO WIDTH SPACE}legram", "424242", "[REDACTED]"),
        ("ｐｈｏｎｅ", "+1-415-555-0199", "[REDACTED]"),
    ),
)
def test_release_receipt_redacts_value_and_unicode_key_bypasses(key: str, value: str, expected: str) -> None:
    receipt = build_release_receipt(
        generated_at="2026-07-30T12:00:00Z",
        correlation_id="release-opaque-adversarial",
        summary={key: value},
        evidence_refs=("sha256:" + "c" * 64,),
    )
    assert isinstance(receipt["summary"], dict)
    assert receipt["summary"][key] == expected
