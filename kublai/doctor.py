"""Kublai operational doctor checks."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_LABELS = (
    "ai.kurultai.brain-service",
    "ai.kurultai.brain-public-gateway",
    "ai.kurultai.brain-reconciliation",
    "ai.hermes.gateway",
    "com.kurultai.daily-backup",
)
RETIRED_GRAPH_LABEL = "homebrew.mxcl.neo4j"
RETIRED_GRAPH_PORTS = ("7474", "7687")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _mode(path: Path) -> int | None:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def _port_dark(port: str) -> bool:
    result = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"])
    return result.returncode != 0 or not result.stdout.strip()


def _brain_service_ok(brain_root: Path) -> bool:
    result = _run([
        sys.executable,
        "-m",
        "kublai.brain_service",
        "--wiki-root",
        str(brain_root),
        "--telemetry-db",
        "/Users/kublai/.kublai/telemetry.db",
        "--index-db",
        "/Users/kublai/.brain-index/brain.db",
        "healthcheck",
    ])
    if result.returncode != 0:
        return False
    try:
        return bool(json.loads(result.stdout).get("ok"))
    except Exception:
        return False


def _doctor_full_ok(brain_root: Path) -> bool:
    try:
        from .brain_service import BrainService

        service = BrainService(
            brain_root,
            "/Users/kublai/.kublai/telemetry.db",
            "/Users/kublai/.brain-index/brain.db",
        )
        return bool(service.v4.doctor_full().get("ok"))
    except Exception:
        return False


def _gateway_ok() -> bool:
    result = _run(["curl", "-fsS", "http://127.0.0.1:8765/health"])
    if result.returncode != 0:
        return False
    try:
        return bool(json.loads(result.stdout).get("ok"))
    except Exception:
        return False


def _index_hard_private_rows(db_path: Path) -> int | None:
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT count(*) FROM nodes WHERE rel_path LIKE 'hard-private/%'"
            ).fetchone()
        return int(row[0])
    except Exception:
        return None


def doctor(
    *,
    brain_root: str | Path = "/Users/kublai/brain",
    private_index_dir: str | Path = "/Users/kublai/.kublai/brain-index-private",
    public_index_db: str | Path = "/Users/kublai/.brain-index/brain.db",
    private_index_db: str | Path = "/Users/kublai/.kublai/brain-index-private/brain.db",
) -> dict[str, Any]:
    brain_root = Path(brain_root)
    hard_private = brain_root / "hard-private"
    private_index_dir = Path(private_index_dir)
    public_index_db = Path(public_index_db)
    private_index_db = Path(private_index_db)
    launchctl = _run(["launchctl", "list"])
    disabled = _run(["launchctl", "print-disabled", f"gui/{os.getuid()}"])
    labels_present = {
        label: label in launchctl.stdout
        for label in EXPECTED_LABELS
    }
    filevault = _run(["fdesetup", "status"])
    tm_hard = _run(["tmutil", "isexcluded", str(hard_private)])
    tm_private_index = _run(["tmutil", "isexcluded", str(private_index_dir)])
    tailscale = _run(["tailscale", "serve", "status"]) if Path("/usr/local/bin/tailscale").exists() or Path("/opt/homebrew/bin/tailscale").exists() else None
    active_path_lint = _run([sys.executable, str(REPO_ROOT / "lints" / "no_active_graph_store.py")])
    public_hard_rows = _index_hard_private_rows(public_index_db)
    private_hard_rows = _index_hard_private_rows(private_index_db)

    checks: dict[str, bool] = {
        "brain_service_health": _brain_service_ok(brain_root),
        "v4_gateway_health": _gateway_ok(),
        "v4_full": _doctor_full_ok(brain_root),
        "brain_mode_700": _mode(brain_root) == 0o700,
        "hard_private_mode_700": _mode(hard_private) == 0o700,
        "metadata_never_index": (hard_private / ".metadata_never_index").exists(),
        "private_index_dir_exists": private_index_dir.exists(),
        "public_index_no_hard_private": public_hard_rows == 0,
        "private_index_has_hard_private": private_hard_rows is not None and private_hard_rows > 0,
        "active_path_graph_lint": active_path_lint.returncode == 0,
        "filevault_on": "FileVault is On" in filevault.stdout,
        "tm_hard_private_excluded": "[Excluded]" in tm_hard.stdout or tm_hard.returncode == 0 and "excluded" in tm_hard.stdout.lower(),
        "tm_private_index_excluded": "[Excluded]" in tm_private_index.stdout or tm_private_index.returncode == 0 and "excluded" in tm_private_index.stdout.lower(),
        "not_icloud_path": "Library/Mobile Documents" not in str(brain_root.resolve()),
        "funnel_not_serving_brain": not (tailscale and "brain-service" in tailscale.stdout.lower()),
        "retired_graph_launchd_unloaded": RETIRED_GRAPH_LABEL not in launchctl.stdout,
        "retired_graph_launchd_not_enabled": f'"{RETIRED_GRAPH_LABEL}" => enabled' not in disabled.stdout,
        **{f"retired_graph_port_{port}_dark": _port_dark(port) for port in RETIRED_GRAPH_PORTS},
        **{f"launchd_{label}": present for label, present in labels_present.items()},
    }
    return {"ok": all(checks.values()), "checks": checks}


def main() -> int:
    result = doctor()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
