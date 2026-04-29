from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


CLI = Path(__file__).resolve().parents[1] / "coordination_cli.py"
PYTHON = "/opt/homebrew/opt/python@3.14/bin/python3.14"


def run_cli(db_path: Path, *args: str) -> dict:
    result = subprocess.run(
        [PYTHON, str(CLI), "--db", str(db_path), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_cli_claim_contribute_finalize_why(tmp_path):
    db_path = tmp_path / "coordination.db"

    init = run_cli(db_path, "init")
    assert init["ok"] is True

    claim = run_cli(
        db_path,
        "claim",
        "--channel", "telegram",
        "--chat-id", "chat",
        "--root-message-id", "root",
        "--owner", "kublai",
        "--tier", "tier2",
        "--required-contributor", "hermes",
    )
    assert claim["claimed"] is True

    lock_id = claim["lock_id"]
    contribution = run_cli(db_path, "contribute", "--lock-id", str(lock_id), "--agent", "hermes", "--body", "approved")
    assert contribution["contributor"] == "hermes"
    processed = run_cli(db_path, "process", "--lock-id", str(lock_id), "--contribution-id", str(contribution["id"]), "--actor", "kublai", "--decision", "accepted")
    assert processed["event_type"] == "contribution_processed"
    finalized = run_cli(db_path, "finalize", "--lock-id", str(lock_id), "--status", "ready_to_answer", "--summary", "ready")
    assert finalized["status"] == "ready_to_answer"

    why = run_cli(db_path, "why", "--channel", "telegram", "--chat-id", "chat", "--root-message-id", "root")
    assert why["lock"]["owner"] == "kublai"
    assert why["contributions"][0]["summary"] == "approved"


def test_cli_enqueue_send_is_idempotent(tmp_path):
    db_path = tmp_path / "coordination.db"
    first = run_cli(
        db_path,
        "enqueue-send",
        "--channel", "telegram",
        "--chat-id", "chat",
        "--root-message-id", "root",
        "--owner", "kublai",
        "--text", "one public answer",
    )
    duplicate = run_cli(
        db_path,
        "enqueue-send",
        "--channel", "telegram",
        "--chat-id", "chat",
        "--root-message-id", "root",
        "--owner", "kublai",
        "--text", "duplicate public answer",
    )

    assert first["enqueued"] is True
    assert duplicate["enqueued"] is False
    assert duplicate["id"] == first["id"]
