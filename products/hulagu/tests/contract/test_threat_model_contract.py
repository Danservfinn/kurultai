from __future__ import annotations

from pathlib import Path

THREAT_MODEL = Path(__file__).parents[4] / "docs" / "hulagu" / "THREAT-MODEL.md"


def section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    assert marker in markdown, f"missing {marker}"
    body = markdown.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def test_threat_model_freezes_required_security_contract() -> None:
    text = THREAT_MODEL.read_text()
    required_sections = {
        "Protected assets": ("customer data", "credentials", "control plane"),
        "Actors and trust boundaries": ("customer", "operator", "attacker", "trust boundary"),
        "Abuse cases": ("cross-tenant", "prompt injection", "replay", "deletion"),
        "Controls": ("least privilege", "fail closed", "networkless", "RLS"),
        "Residual risks": ("residual", "owner", "gate"),
        "Secrets and rotation": ("Telegram bot token", "OAuth refresh token", "rotation", "revocation"),
        "Out of scope": ("job application", "employer contact", "authenticated browsing", "general Hermes profile"),
    }
    for heading, terms in required_sections.items():
        body = section(text, heading).lower()
        for term in terms:
            assert term.lower() in body, f"{heading} must enumerate {term}"


def test_secret_inventory_names_every_frozen_key_family() -> None:
    text = section(THREAT_MODEL.read_text(), "Secrets and rotation").lower()
    for secret in (
        "telegram bot token",
        "openai oauth refresh token",
        "database role credentials",
        "active-route encryption key",
        "deletion-route encryption key",
        "route-binding hmac key",
        "subject-digest key",
        "backup encryption key",
        "backup signing key",
    ):
        assert secret in text
