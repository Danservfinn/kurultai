from __future__ import annotations

from pathlib import Path

THREAT_MODEL = Path(__file__).parents[4] / "docs/hulagu/THREAT-MODEL.md"
ARCHITECTURE = Path(__file__).parents[4] / "docs/architecture/hulagu.md"
ADR = Path(__file__).parents[4] / "docs/adr/2026-07-25-hulagu-dedicated-telegram-control-plane.md"
ROOT_README = Path(__file__).parents[4] / "README.md"

REQUIRED_SECTIONS = (
    "Protected assets",
    "Actors and trust boundaries",
    "Abuse cases",
    "Controls",
    "Residual risks",
    "Secrets and rotation",
    "Explicitly out of scope",
)
SECRET_FAMILIES = (
    "Telegram bot token",
    "Search-provider token",
    "PostgreSQL password: `hulagu_app`",
    "PostgreSQL password: `hulagu_runner`",
    "PostgreSQL password: `hulagu_deletion`",
    "Subject-digest HMAC keys",
    "Action-token HMAC keys",
    "Deletion-send route-binding HMAC keys",
    "Active Telegram send-route encryption keys",
    "Deletion-completion route encryption keys",
    "Backup encryption keys",
    "Backup-manifest signing keys",
)


def test_threat_model_has_complete_security_contract() -> None:
    text = THREAT_MODEL.read_text(encoding="utf-8")
    for heading in REQUIRED_SECTIONS:
        assert f"## {heading}" in text
    for family in SECRET_FAMILIES:
        assert family in text
    for phrase in (
        "Keychain item",
        "permitted reader",
        "key ID",
        "rotation",
        "overlap",
        "revocation",
        "crash-dump",
    ):
        assert phrase in text


def test_threat_model_names_required_abuse_and_control_boundaries() -> None:
    text = THREAT_MODEL.read_text(encoding="utf-8")
    for phrase in (
        "cross-tenant",
        "prompt injection",
        "symlink",
        "PATH discovery",
        "Docker socket",
        "wrong volume UUID",
        "unencrypted volume",
        "replay",
        "stale worker",
        "secret exposure",
        "no model calls",
        "no job applications",
        "no employer contact",
        "no authenticated browsing",
    ):
        assert phrase in text


def test_architecture_names_every_required_home() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    for phrase in (
        "/Users/kublai/kurultai/kurultai-repo/products/hulagu",
        "/Volumes/KurultaiVault/hulagu",
        "macOS Keychain",
        "/Volumes/KurultaiVault/hulagu/tenants/<tenant_uuid>",
        "/Users/kublai/brain/status/hulagu",
        "/Users/kublai/brain/receipts/hulagu",
    ):
        assert phrase in text


def test_adr_records_rejected_hermes_alternatives() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "general Hermes profile" in text
    assert "pre_gateway_dispatch" in text
    assert "Rejected" in text


def test_root_navigation_links_architecture_and_adr() -> None:
    text = ROOT_README.read_text(encoding="utf-8")
    assert "docs/architecture/hulagu.md" in text
    assert "docs/adr/2026-07-25-hulagu-dedicated-telegram-control-plane.md" in text
