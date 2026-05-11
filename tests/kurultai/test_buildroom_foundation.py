from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILDROOM = ROOT / "tools" / "kurultai" / "buildroom"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_demo_room(tmp_path: Path, name: str = "room") -> Path:
    room = tmp_path / name
    shutil.copytree(BUILDROOM / "rooms" / "demo-room", room)
    return room


def test_demo_room_validates() -> None:
    result = run_script(
        "tools/kurultai/buildroom/scripts/validate_room.py",
        "tools/kurultai/buildroom/rooms/demo-room",
    )
    assert result.returncode == 0, result.stderr
    assert "validation passed" in result.stdout


def test_corrupt_fixture_fails_with_path_error(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "bad-room")
    artifact = room / "ideas" / "idea-contract.json"
    data = read_json(artifact)
    del data["title"]
    write_json(artifact, data)

    result = run_script("tools/kurultai/buildroom/scripts/validate_room.py", str(room))

    assert result.returncode == 1
    assert "idea-contract.json" in result.stderr
    assert "title" in result.stderr


def test_validation_fails_when_contract_reference_points_at_missing_artifact(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "missing-ref-room")
    idea = read_json(room / "ideas" / "idea-contract.json")
    idea["evidence_refs"].append("research/nonexistent-evidence.json")
    write_json(room / "ideas" / "idea-contract.json", idea)

    result = run_script("tools/kurultai/buildroom/scripts/validate_room.py", str(room))

    assert result.returncode == 1
    assert "idea-contract.json" in result.stderr
    assert "evidence_refs" in result.stderr
    assert "research/nonexistent-evidence.json" in result.stderr


def test_operator_summary_builder_outputs_valid_summary(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path)

    result = run_script("tools/kurultai/buildroom/scripts/build_operator_summary.py", str(room))

    assert result.returncode == 0, result.stderr
    summary = read_json(room / "operator" / "operator-summary.json")
    assert summary["room_id"] == "room"
    assert summary["status"] == "clean"
    assert any("Trust state" in item for item in summary["operator_needs_to_know"])

    validation = run_script("tools/kurultai/buildroom/scripts/validate_room.py", str(room))
    assert validation.returncode == 0, validation.stderr


def test_operator_summary_includes_watch_followups_and_existing_artifact_links(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "watch-room")
    trust_path = room / "trust" / "trust-report.json"
    trust = read_json(trust_path)
    trust["state"] = "watch"
    trust["risk_score"] = 0.42
    trust["required_followups"] = ["Run independent QA before archive."]
    write_json(trust_path, trust)

    result = run_script("tools/kurultai/buildroom/scripts/build_operator_summary.py", str(room))

    assert result.returncode == 0, result.stderr
    summary = read_json(room / "operator" / "operator-summary.json")
    assert summary["status"] == "watch"
    assert "Run independent QA before archive." in summary["operator_decisions_needed"]
    linked_artifacts = [link.removeprefix("buildroom://watch-room/") for link in summary["links"]]
    assert linked_artifacts == summary["latest_artifacts"]
    assert all((room / artifact).exists() for artifact in linked_artifacts)


def test_sanitized_export_redacts_private_paths_and_secretish_values(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path)
    dest = tmp_path / "export"
    research = read_json(room / "research" / "research-input.json")
    sample_secret = "sk-dem" + "..." + "oken"
    private_path = "/" + "Users" + "/" + "kublai" + "/private/path"
    research["source_refs"].append(f"token={sample_secret} at {private_path}")
    write_json(room / "research" / "research-input.json", research)

    result = run_script(
        "tools/kurultai/buildroom/scripts/export_sanitized_bundle.py",
        str(room),
        str(dest),
    )

    assert result.returncode == 0, result.stderr
    exported = (dest / "research" / "research-input.json").read_text(encoding="utf-8")
    assert sample_secret not in exported
    assert "[REDACTED_ABSOLUTE_PATH]" in exported
    assert "[REDACTED_SECRET]" in exported


def test_sanitized_export_skips_private_artifacts_and_redacts_secret_fields(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path)
    dest = tmp_path / "export"
    private_artifact = room / "research" / "private-evidence.json"
    write_json(
        private_artifact,
        {
            "sensitivity": "private",
            "token": "***",
            "path": "/private/operator/source.txt",
        },
    )
    research = read_json(room / "research" / "research-input.json")
    research["api_token"] = "SAMPLE_SECRET_VALUE"
    write_json(room / "research" / "research-input.json", research)

    result = run_script(
        "tools/kurultai/buildroom/scripts/export_sanitized_bundle.py",
        str(room),
        str(dest),
    )

    assert result.returncode == 0, result.stderr
    assert "skipped private artifact: research/private-evidence.json" in result.stdout
    assert not (dest / "research" / "private-evidence.json").exists()
    exported = read_json(dest / "research" / "research-input.json")
    assert exported["api_token"] == "[REDACTED_SECRET_FIELD]"


def test_approved_build_plan_creates_kanban_task_packet_with_parent_refs(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "approved-room")
    build_plan = read_json(room / "plans" / "build-plan.json")
    build_plan["task_refs"] = ["kanban:t_parent_one", "kanban:t_parent_two", "brain:project-note"]
    write_json(room / "plans" / "build-plan.json", build_plan)
    packet_path = tmp_path / "task-packet.json"

    result = run_script(
        "tools/kurultai/buildroom/scripts/kanban_adapter.py",
        "task-packet",
        str(room),
        str(packet_path),
    )

    assert result.returncode == 0, result.stderr
    packet = read_json(packet_path)
    assert packet["title"] == "buildroom: Buildroom foundation demo"
    assert packet["assignee"] == "chagatai"
    assert packet["parents"] == ["t_parent_one", "t_parent_two"]
    assert packet["idempotency_key"] == "buildroom:build-buildroom-foundation-demo"
    assert packet["metadata"]["build_id"] == "build-buildroom-foundation-demo"
    assert "Allowed paths:" in packet["body"]
    assert "kanban:t_parent_one" in packet["body"]


def test_unapproved_idea_refuses_to_generate_kanban_task_packet(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "unapproved-room")
    main_review_path = room / "reviews" / "main-review.json"
    review = read_json(main_review_path)
    review["decision"] = "needs_more_evidence"
    review["blocked_reasons"] = ["Missing operator approval."]
    write_json(main_review_path, review)

    result = run_script(
        "tools/kurultai/buildroom/scripts/kanban_adapter.py",
        "task-packet",
        str(room),
        str(tmp_path / "task-packet.json"),
    )

    assert result.returncode == 1
    assert "main-review decision is not approved_for_planning" in result.stderr
    assert "Missing operator approval" in result.stderr


def test_completed_kanban_task_generates_implementation_receipt_with_evidence_refs(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "receipt-room")
    completion_path = tmp_path / "kanban-completion.json"
    write_json(
        completion_path,
        {
            "id": "t_done123",
            "status": "done",
            "assignee": "chagatai",
            "started_at": "2026-05-10T17:20:00Z",
            "completed_at": "2026-05-10T17:25:00Z",
            "summary": "Implemented buildroom adapter with focused tests passing.",
            "metadata": {
                "changed_files": ["tools/kurultai/buildroom/scripts/kanban_adapter.py"],
                "commands_run": ["python -m py_compile tools/kurultai/buildroom/scripts/kanban_adapter.py"],
                "tests_run": ["pytest tests/kurultai/test_buildroom_foundation.py -q"],
                "commit_sha": "abc1234",
                "open_diffs_summary": "adapter script and tests",
                "deviations_from_plan": [],
                "blocked_items": [],
                "evidence_refs": ["kanban-run:151", "artifact:task-packet.json"],
            },
        },
    )

    result = run_script(
        "tools/kurultai/buildroom/scripts/kanban_adapter.py",
        "receipt",
        str(room),
        str(completion_path),
    )

    assert result.returncode == 0, result.stderr
    receipt = read_json(room / "jobs" / "implementation-receipt.json")
    assert receipt["receipt_id"] == "receipt-t_done123"
    assert receipt["build_id"] == "build-buildroom-foundation-demo"
    assert receipt["kanban_task_id"] == "t_done123"
    assert receipt["kanban_status"] == "done"
    assert receipt["files_changed"] == ["tools/kurultai/buildroom/scripts/kanban_adapter.py"]
    assert receipt["tests_run"] == ["pytest tests/kurultai/test_buildroom_foundation.py -q"]
    assert receipt["evidence_refs"] == ["kanban:t_done123", "kanban-run:151", "artifact:task-packet.json"]

    validation = run_script("tools/kurultai/buildroom/scripts/validate_room.py", str(room))
    assert validation.returncode == 0, validation.stderr


def test_independent_qa_task_packet_uses_build_plan_and_receipt_parent(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "qa-room")
    receipt = read_json(room / "jobs" / "implementation-receipt.json")
    receipt["kanban_task_id"] = "t_build123"
    write_json(room / "jobs" / "implementation-receipt.json", receipt)
    packet_path = tmp_path / "qa-task-packet.json"

    result = run_script(
        "tools/kurultai/buildroom/scripts/qa_trust.py",
        "qa-packet",
        str(room),
        str(packet_path),
    )

    assert result.returncode == 0, result.stderr
    packet = read_json(packet_path)
    assert packet["title"] == "buildroom-qa: Buildroom foundation demo"
    assert packet["assignee"] == "ogedei"
    assert packet["parents"] == ["t_build123"]
    assert packet["idempotency_key"] == "buildroom-qa:build-buildroom-foundation-demo"
    assert packet["metadata"]["build_id"] == "build-buildroom-foundation-demo"
    assert packet["metadata"]["independent_of"] == "chagatai"
    assert "Independent QA only" in packet["body"]
    assert "python scripts/validate_room.py rooms/demo-room" in packet["body"]


def test_verification_delta_confirms_passing_qa_against_receipt(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "confirmed-room")

    result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "delta", str(room))

    assert result.returncode == 0, result.stderr
    delta = read_json(room / "verification" / "verification-delta.json")
    assert delta["state"] == "confirmed"
    assert "QA report passed" in delta["confirmed_claims"]
    assert delta["unverified_claims"] == []
    assert delta["regressions"] == []


def test_trust_summary_emits_clean_for_passing_confirmed_room(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "clean-room")
    delta_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "delta", str(room))
    assert delta_result.returncode == 0, delta_result.stderr

    result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "trust", str(room))

    assert result.returncode == 0, result.stderr
    trust = read_json(room / "trust" / "trust-report.json")
    assert trust["state"] == "clean"
    assert trust["safe_to_archive"] is True
    assert trust["risk_score"] == 0.1
    assert "QA report passed" in trust["reasons"]


def test_missing_qa_emits_watch_delta_and_trust(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "missing-qa-room")
    (room / "verification" / "verification-report.json").unlink()

    delta_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "delta", str(room))
    trust_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "trust", str(room))

    assert delta_result.returncode == 0, delta_result.stderr
    assert trust_result.returncode == 0, trust_result.stderr
    delta = read_json(room / "verification" / "verification-delta.json")
    trust = read_json(room / "trust" / "trust-report.json")
    assert delta["state"] == "missing_evidence"
    assert "verification/verification-report.json missing" in delta["unverified_claims"]
    assert trust["state"] == "watch"
    assert trust["safe_to_archive"] is False
    assert "Run independent QA and regenerate verification report." in trust["required_followups"]


def test_scope_expansion_emits_investigate_trust(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "scope-room")
    receipt = read_json(room / "jobs" / "implementation-receipt.json")
    receipt["files_changed"] = ["/etc/passwd", "tools/kurultai/buildroom/scripts/qa_trust.py"]
    write_json(room / "jobs" / "implementation-receipt.json", receipt)

    delta_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "delta", str(room))
    trust_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "trust", str(room))

    assert delta_result.returncode == 0, delta_result.stderr
    assert trust_result.returncode == 0, trust_result.stderr
    delta = read_json(room / "verification" / "verification-delta.json")
    trust = read_json(room / "trust" / "trust-report.json")
    assert delta["state"] == "regression"
    assert any("outside allowed paths" in item for item in delta["regressions"])
    assert trust["state"] == "investigate"
    assert "Investigate scope/protected-path mismatch before archive." in trust["required_followups"]


def test_failed_qa_regression_emits_investigate_trust(tmp_path: Path) -> None:
    room = copy_demo_room(tmp_path, "regression-room")
    report = read_json(room / "verification" / "verification-report.json")
    report["pass"] = False
    report["failures"] = ["pytest regression in buildroom validation"]
    write_json(room / "verification" / "verification-report.json", report)

    delta_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "delta", str(room))
    trust_result = run_script("tools/kurultai/buildroom/scripts/qa_trust.py", "trust", str(room))

    assert delta_result.returncode == 0, delta_result.stderr
    assert trust_result.returncode == 0, trust_result.stderr
    delta = read_json(room / "verification" / "verification-delta.json")
    trust = read_json(room / "trust" / "trust-report.json")
    assert delta["state"] == "regression"
    assert "pytest regression in buildroom validation" in delta["regressions"]
    assert trust["state"] == "investigate"
    assert "Fix failed QA/regressions and rerun verifier." in trust["required_followups"]
