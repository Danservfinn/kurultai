from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CLI = BASE / "coordination_cli.py"
PY = sys.executable


def run_cli(db: Path, *args: str) -> dict:
    proc = subprocess.run(
        [PY, str(CLI), "--db", str(db), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_cli_reserve_public_send_and_mark_sent(tmp_path):
    db = tmp_path / "coordination.db"
    run_cli(db, "init")
    lock = run_cli(
        db, "claim", "--channel", "telegram", "--chat-id", "-5287556083",
        "--root-message-id", "801", "--owner", "kublai",
    )

    reserved = run_cli(
        db, "reserve-public-send", "--lock-id", str(lock["lock_id"]),
        "--actor", "kublai", "--text", "one public answer",
    )
    assert reserved["allowed"] is True

    sent = run_cli(
        db, "mark-public-sent", "--lock-id", str(lock["lock_id"]),
        "--actor", "kublai", "--send-key", reserved["send_key"],
        "--provider-message-id", "tg-801", "--summary", "answered",
    )
    assert sent["status"] == "answered"
    assert sent["final_answer_message_id"] == "tg-801"


def test_cli_reserve_public_send_denies_non_owner(tmp_path):
    db = tmp_path / "coordination.db"
    run_cli(db, "init")
    lock = run_cli(
        db, "claim", "--channel", "telegram", "--chat-id", "-5287556083",
        "--root-message-id", "802", "--owner", "kublai",
    )

    denied = run_cli(
        db, "reserve-public-send", "--lock-id", str(lock["lock_id"]),
        "--actor", "hermes", "--text", "duplicate answer",
    )
    assert denied["allowed"] is False
    assert denied["reason"] == "not_lock_owner"
