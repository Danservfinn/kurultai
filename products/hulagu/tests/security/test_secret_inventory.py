from __future__ import annotations

import json
from pathlib import Path

from hulagu.control.doctor import SECRET_INVENTORY, secret_inventory_projection

ROOT = Path(__file__).parents[2]


def test_secret_inventory_names_every_versioned_family_with_least_privilege_reader() -> None:
    expected = {
        "telegram_bot_token": "hulagu-app",
        "search_provider_token": "hulagu-app",
        "research_oauth_refresh_token": "hulagu-app",
        "postgres_app_password": "hulagu-app",
        "postgres_runner_password": "hulagu-runner",
        "postgres_deletion_password": "hulagu-deletion-dispatcher",
        "subject_digest_hmac": "hulagu-app",
        "action_token_hmac": "hulagu-app",
        "deletion_route_binding_hmac": "hulagu-app",
        "active_route_encryption": "hulagu-app",
        "deletion_route_encryption": "hulagu-deletion-dispatcher",
        "backup_encryption": "offline-backup-operator",
        "backup_manifest_signing": "offline-backup-verifier",
    }
    assert {item.family: item.reader for item in SECRET_INVENTORY} == expected
    assert len({item.keychain_item for item in SECRET_INVENTORY}) == len(expected)
    assert all(item.version >= 1 and item.keychain_item.endswith(f".v{item.version}") for item in SECRET_INVENTORY)


def test_secret_inventory_projection_contains_names_not_values() -> None:
    projection = secret_inventory_projection()
    serialized = json.dumps(projection, sort_keys=True)
    assert projection["schema_version"] == "HulaguSecretInventory/v1"
    assert "value" not in serialized.lower()
    assert "material" not in serialized.lower()
    assert "hulagu-app" in serialized


def test_launchd_templates_contain_only_item_names_and_separate_runtime_readers() -> None:
    templates = {
        path.name: path.read_text()
        for path in sorted((ROOT / "deploy" / "launchd").glob("com.kurultai.hulagu-*.plist.template"))
    }
    assert set(templates) == {
        "com.kurultai.hulagu-app.plist.template",
        "com.kurultai.hulagu-deletion.plist.template",
        "com.kurultai.hulagu-postgres.plist.template",
        "com.kurultai.hulagu-runner.plist.template",
    }
    inventory_names = {item.keychain_item for item in SECRET_INVENTORY}
    combined = "\n".join(templates.values())
    assert any(name in combined for name in inventory_names)
    assert "postgres_migrator" not in combined
    assert "backup_encryption" not in combined
    assert "backup_manifest_signing" not in combined
    assert "active-route-encryption" not in templates["com.kurultai.hulagu-deletion.plist.template"]
    assert "deletion-route-encryption" not in templates["com.kurultai.hulagu-app.plist.template"]


def test_task10_artifacts_do_not_embed_synthetic_secret_value() -> None:
    canary = "sk" + "-task10-static-secret-canary"
    paths = [
        *(ROOT / "src" / "hulagu" / "control").glob("*.py"),
        *(ROOT / "deploy" / "launchd").glob("*.plist.template"),
        ROOT / "deploy" / "scripts" / "install.py",
        ROOT / "deploy" / "scripts" / "uninstall.py",
    ]
    assert paths
    assert all(canary not in path.read_text() for path in paths if path.exists())
