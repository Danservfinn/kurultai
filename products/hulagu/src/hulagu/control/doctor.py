"""Read-only operational doctor contracts and redacted secret inventory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class SecretSpec:
    family: str
    reader: str
    keychain_item: str
    version: int
    rotation: str


def _secret(family: str, reader: str, slug: str, rotation: str = "versioned-overlap") -> SecretSpec:
    return SecretSpec(family, reader, f"com.kurultai.hulagu.{slug}.v1", 1, rotation)


SECRET_INVENTORY: Final[tuple[SecretSpec, ...]] = (
    _secret("telegram_bot_token", "hulagu-app", "telegram-bot-token", "owner-gated-replacement"),
    _secret("search_provider_token", "hulagu-app", "search-provider-token", "provider-gated-replacement"),
    _secret("research_oauth_refresh_token", "hulagu-app", "research-oauth-refresh-token", "interactive-reauthorization"),
    _secret("postgres_app_password", "hulagu-app", "postgres-app-password", "independent-rotation"),
    _secret("postgres_runner_password", "hulagu-runner", "postgres-runner-password", "independent-rotation"),
    _secret("postgres_deletion_password", "hulagu-deletion-dispatcher", "postgres-deletion-password", "independent-rotation"),
    _secret("subject_digest_hmac", "hulagu-app", "subject-digest-hmac", "tombstone-aware-overlap"),
    _secret("action_token_hmac", "hulagu-app", "action-token-hmac", "short-lived-version-revocation"),
    _secret("deletion_route_binding_hmac", "hulagu-app", "deletion-route-binding-hmac"),
    _secret("active_route_encryption", "hulagu-app", "active-route-encryption"),
    _secret("deletion_route_encryption", "hulagu-deletion-dispatcher", "deletion-route-encryption", "finite-route-lifetime"),
    _secret("backup_encryption", "offline-backup-operator", "backup-encryption", "restore-before-retirement"),
    _secret("backup_manifest_signing", "offline-backup-verifier", "backup-manifest-signing", "independent-rotation"),
)


def secret_inventory_projection() -> dict[str, object]:
    """Return names/readers/versions only; secret values cannot enter this type."""

    return {
        "schema_version": "HulaguSecretInventory/v1",
        "items": [asdict(item) for item in SECRET_INVENTORY],
    }
