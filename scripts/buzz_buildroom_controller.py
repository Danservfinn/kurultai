#!/usr/bin/env python3
"""Create bounded Buzz buildrooms for opted-in Hermes Kanban tasks.

Buzz is a conversation/visibility surface only. Hermes Kanban remains the task
ledger and authority source. This controller never changes task state, creates
agent identities, imports room history into Brain, or exposes a task body.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA = "kurultai.buzz-buildrooms.v1"
STATE_SCHEMA = "kurultai.buzz-buildrooms-state.v1"
SECRET_VALUE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{12,}|Bearer\s+\S+|"
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----|(?:api[_-]?key|token|password)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
PRIVATE_PATH = re.compile(
    r"(?:/Users/[^/]+/(?:\.hermes|brain/hard-private)|/Volumes/KurultaiVault|hard-private)",
    re.IGNORECASE,
)
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TASK_ID = re.compile(r"^t_[A-Za-z0-9_-]{1,128}$")
PUBKEY = re.compile(r"^[0-9a-f]{64}$")
SAFE_SLUG = re.compile(r"[^a-z0-9]+")
ALLOWED_LINE_FIELDS = ("stop condition", "boundaries", "deliverables")


class ControllerError(RuntimeError):
    pass


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ControllerError(f"{name} must be an object")
    return value


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = _object(json.loads(path.read_text(encoding="utf-8")), "config")
    except (OSError, json.JSONDecodeError) as exc:
        raise ControllerError(f"unable to load config: {exc}") from exc
    if config.get("schema") != SCHEMA:
        raise ControllerError(f"config schema must be {SCHEMA}")
    for key in ("profile", "buzz_cli", "hermes_cli", "relay_url", "state_path"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ControllerError(f"config {key} must be a non-empty string")
    if not IDENTITY.fullmatch(config["profile"]):
        raise ControllerError("config profile is invalid")
    reviewer = config.get("default_reviewer", config["profile"])
    if not isinstance(reviewer, str) or not IDENTITY.fullmatch(reviewer) or is_sensitive(reviewer):
        raise ControllerError("config default_reviewer is invalid")
    parsed = urlparse(config["relay_url"])
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme not in {"http", "https"}:
        raise ControllerError("relay_url must use http or https")
    if parsed.scheme == "http" and not loopback:
        raise ControllerError("non-loopback relay must use https")
    if int(config.get("max_creations_per_tick", 1)) != 1:
        raise ControllerError("max_creations_per_tick must equal 1")
    for pattern in config.get("automatic_title_patterns", []):
        try:
            re.compile(str(pattern), re.IGNORECASE)
        except re.error as exc:
            raise ControllerError(f"invalid title pattern: {exc}") from exc
    templates = _object(config.get("templates", {}), "templates")
    for name, template_value in templates.items():
        template = _object(template_value, f"template {name}")
        ttl = int(template.get("ttl_seconds", 0))
        if ttl < 0:
            raise ControllerError(f"template {name} ttl_seconds cannot be negative")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", str(template.get("channel_prefix", ""))):
            raise ControllerError(f"template {name} channel_prefix is invalid")
    for name, member_value in _object(config.get("members", {}), "members").items():
        if not isinstance(name, str) or not IDENTITY.fullmatch(name) or is_sensitive(name):
            raise ControllerError("member name is invalid")
        member = _object(member_value, f"member {name}")
        if not PUBKEY.fullmatch(str(member.get("pubkey", ""))):
            raise ControllerError(f"member {name} pubkey must be 64 lowercase hex characters")
        if member.get("role", "bot") not in {"owner", "admin", "member", "guest", "bot"}:
            raise ControllerError(f"member {name} role is invalid")
    return config


def classify_task(task: dict[str, Any], config: dict[str, Any]) -> str | None:
    body = str(task.get("body") or "")
    title = str(task.get("title") or "")
    haystack = f"{title}\n{body}"
    if any(marker.casefold() in haystack.casefold() for marker in config.get("explicit_opt_out_markers", [])):
        return None
    explicit = any(marker.casefold() in haystack.casefold() for marker in config.get("explicit_opt_in_markers", []))
    matched = explicit or any(re.search(pattern, title, re.IGNORECASE) for pattern in config.get("automatic_title_patterns", []))
    if not matched:
        return None
    lowered = title.casefold()
    if re.match(r"^(incident|security)[: -]", lowered):
        return "incident" if "incident" in config["templates"] else "bug"
    if re.match(r"^(bug|fix)[: -]", lowered):
        return "bug"
    return "feature"


def _selected_lines(body: str) -> dict[str, str]:
    selected: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.strip()
        for field in ALLOWED_LINE_FIELDS:
            prefix = field + ":"
            if line.casefold().startswith(prefix):
                value = line[len(prefix) :].strip()
                if value and len(value.encode("utf-8")) <= 512 and not is_sensitive(value):
                    selected[field] = value
    return selected


def is_sensitive(text: str) -> bool:
    return bool(SECRET_VALUE.search(text) or PRIVATE_PATH.search(text))


def privacy_gate(task: dict[str, Any]) -> tuple[bool, str | None]:
    if task.get("tenant") not in {None, ""}:
        return False, "tenant-scoped tasks cannot be exported to Buzz"
    task_id = str(task.get("id") or "")
    assignee = str(task.get("assignee") or "unassigned")
    if (
        not TASK_ID.fullmatch(task_id)
        or not IDENTITY.fullmatch(assignee)
        or is_sensitive(task_id)
        or is_sensitive(assignee)
    ):
        return False, "task identity fields are unsafe for Buzz export"
    title = str(task.get("title") or "")
    body = str(task.get("body") or "")
    if is_sensitive(title) or is_sensitive(body):
        return False, "task contains private-path or secret-shaped material"
    if len(title.encode("utf-8")) > 240:
        return False, "task title exceeds public-room limit"
    return True, None


def render_kickoff(task: dict[str, Any], reviewer: str) -> str:
    selected = _selected_lines(str(task.get("body") or ""))
    task_id = str(task["id"])
    title = str(task.get("title") or "Untitled task")
    owner = str(task.get("assignee") or "unassigned")
    stop = selected.get("stop condition", "Task reaches terminal review with evidence-backed verification")
    boundaries = selected.get("boundaries", "No credentials, customer data, or private Brain content in Buzz")
    deliverables = selected.get("deliverables", "Implementation, tests, independent review, and terminal receipt")
    return (
        f"## Mission\n{title}\n\n"
        f"**Canonical task:** `{task_id}`\n"
        f"**Owner:** {owner}\n"
        f"**Reviewer:** {reviewer}\n"
        f"**Stop condition:** {stop}\n"
        f"**Boundaries:** {boundaries}\n\n"
        f"## Deliverables\n{deliverables}\n\n"
        "> Buzz is the collaboration surface. Hermes Kanban remains canonical; room messages do not change task authority.\n\n"
        f"`buzz-buildroom-kickoff-{task_binding(task_id)}`"
    )


def render_closure(task: dict[str, Any]) -> str:
    status = str(task.get("status") or "unknown")
    verdict = str(task.get("verdict") or "not-recorded")
    completed = task.get("completed_at")
    completed_text = str(completed) if isinstance(completed, int) else "not-recorded"
    return (
        "## Terminal task receipt\n\n"
        f"**Canonical task:** `{task['id']}`\n"
        f"**Task status:** `{status}`\n"
        f"**Review verdict:** `{verdict}`\n"
        f"**Completed at:** `{completed_text}`\n\n"
        "> Detailed implementation evidence remains in Hermes Kanban and its exact artifact receipts.\n\n"
        f"`buzz-buildroom-closure-{task_binding(str(task['id']))}`"
    )


def slugify(value: str, *, limit: int = 54) -> str:
    slug = SAFE_SLUG.sub("-", value.casefold()).strip("-")
    return (slug[:limit].rstrip("-") or "task")


def task_binding(task_id: str) -> str:
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]


def _read_secret_env(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if path is None or not path.exists():
        return values
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in {"BUZZ_PRIVATE_KEY", "BUZZ_AUTH_TAG"}:
                values[key] = value.strip().strip('"').strip("'")
    except OSError as exc:
        raise ControllerError(f"unable to read secret env file: {exc}") from exc
    return values


def command_env(config: dict[str, Any]) -> dict[str, str] | None:
    env = os.environ.copy()
    file_path = Path(config["secret_env_file"]).expanduser() if config.get("secret_env_file") else None
    for key, value in _read_secret_env(file_path).items():
        env.setdefault(key, value)
    env["BUZZ_RELAY_URL"] = config["relay_url"]
    if not env.get("BUZZ_PRIVATE_KEY"):
        return None
    return env


def run_json(argv: list[str], *, env: dict[str, str], stdin: str | None = None) -> dict[str, Any] | list[Any]:
    try:
        proc = subprocess.run(
            argv,
            input=stdin,
            text=True,
            capture_output=True,
            env=env,
            timeout=45,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerError(f"command failed to execute: {argv[0]}: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        try:
            parsed = json.loads(detail)
            detail = str(parsed.get("message") or parsed.get("error") or "command failed")
        except (json.JSONDecodeError, AttributeError):
            detail = detail[:500]
        raise ControllerError(f"{Path(argv[0]).name} command failed: {detail}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ControllerError(f"{Path(argv[0]).name} returned non-JSON output") from exc


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": STATE_SCHEMA, "tasks": {}, "last_tick_at": None}
    try:
        state = _object(json.loads(path.read_text(encoding="utf-8")), "state")
    except (OSError, json.JSONDecodeError) as exc:
        raise ControllerError(f"unable to load state: {exc}") from exc
    if state.get("schema") != STATE_SCHEMA or not isinstance(state.get("tasks"), dict):
        raise ControllerError("state schema is invalid")
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _executable(value: str) -> str:
    return str(Path(value).expanduser()) if value.startswith(("~", "/", ".")) else value


def _hermes(config: dict[str, Any], env: dict[str, str], *args: str) -> dict[str, Any] | list[Any]:
    hermes_env = env.copy()
    hermes_env.pop("BUZZ_PRIVATE_KEY", None)
    hermes_env.pop("BUZZ_AUTH_TAG", None)
    return run_json(
        [_executable(config["hermes_cli"]), "--profile", config["profile"], "kanban", *args],
        env=hermes_env,
    )


def _buzz(config: dict[str, Any], env: dict[str, str], *args: str, stdin: str | None = None) -> dict[str, Any] | list[Any]:
    return run_json([_executable(config["buzz_cli"]), *args], env=env, stdin=stdin)


def _active_tasks(config: dict[str, Any], env: dict[str, str]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for status in config.get("eligible_statuses", ["ready", "running"]):
        rows = _hermes(config, env, "list", "--status", status, "--json")
        if not isinstance(rows, list):
            raise ControllerError("kanban list must return an array")
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                tasks[row["id"]] = row
    return tasks


def _tracked_task(config: dict[str, Any], env: dict[str, str], task_id: str) -> dict[str, Any] | None:
    try:
        row = _hermes(config, env, "show", task_id, "--json")
    except ControllerError:
        return None
    if not isinstance(row, dict):
        return None
    task = row.get("task", row)
    return task if isinstance(task, dict) else None


def _roster_names(task: dict[str, Any], config: dict[str, Any]) -> list[str]:
    names = [config.get("profile", "kublai"), str(task.get("assignee") or "")]
    reviewer = str(config.get("default_reviewer") or "")
    if reviewer:
        names.append(reviewer)
    for name in config.get("always_include_members", []):
        names.append(str(name))
    result: list[str] = []
    for name in names:
        if name and name not in result and name in config.get("members", {}):
            result.append(name)
    return result


def _find_message_marker(
    config: dict[str, Any], env: dict[str, str], channel_id: str, marker: str
) -> str | None:
    response = _buzz(config, env, "messages", "search", "--query", marker, "--limit", "20")
    if isinstance(response, dict):
        rows = response.get("messages", response.get("results", []))
    else:
        rows = response
    if not isinstance(rows, list):
        raise ControllerError("Buzz marker search returned an invalid result set")
    matches: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_channel = row.get("channel_id") or row.get("channel") or _tag_value(row, "h")
        event_id = row.get("id") or row.get("event_id")
        if row_channel == channel_id and marker in str(row.get("content") or "") and isinstance(event_id, str):
            matches.append(event_id)
    if len(matches) > 1:
        raise ControllerError(f"multiple Buzz messages match idempotency marker {marker}")
    return matches[0] if matches else None


def _create_room(
    task: dict[str, Any],
    kind: str,
    config: dict[str, Any],
    state_path: Path,
    state: dict[str, Any],
    env: dict[str, str],
) -> dict[str, Any]:
    template = config["templates"][kind]
    task_id = str(task["id"])
    record = state["tasks"].setdefault(task_id, {
        "task_id": task_id,
        "phase": "new",
        "member_names_added": [],
        "kind": kind,
    })
    if record["phase"] == "new":
        binding = task_binding(task_id)
        name = f"{template['channel_prefix']}-{slugify(str(task.get('title') or task_id), limit=42)}-{binding}"
        description = f"Ephemeral collaboration room for Hermes Kanban task {task_id}; binding={binding}"
        existing = _buzz(config, env, "channels", "search", "--query", name, "--exact")
        if not isinstance(existing, list):
            raise ControllerError("Buzz channel search must return an array")
        if len(existing) > 1:
            raise ControllerError(f"multiple exact Buzz channels exist for task {task_id}")
        if existing:
            channel = _object(existing[0], "existing channel")
            if channel.get("name", "").casefold() != name.casefold():
                raise ControllerError("Buzz exact channel search returned a mismatched name")
            if channel.get("visibility") != "private" or channel.get("archived") is not False:
                raise ControllerError("existing Buzz task channel is not an active private room")
            if channel.get("about") != description:
                raise ControllerError("existing Buzz task channel binding is invalid")
            if not isinstance(channel.get("channel_id"), str):
                raise ControllerError("existing Buzz task channel omitted channel_id")
            record.update({
                "channel_id": channel["channel_id"],
                "channel_name": name,
                "channel_description": description,
                "task_binding": binding,
                "phase": "channel_created",
                "created_at": int(time.time()),
                "recovered_existing_channel": True,
            })
            _save_state(state_path, state)
        else:
            args = [
                "channels", "create", "--name", name, "--type", "stream", "--visibility", "private",
                "--description", description,
            ]
            ttl = int(template.get("ttl_seconds", 0))
            if ttl > 0:
                args += ["--ttl", str(ttl)]
            response = _buzz(config, env, *args)
            if not isinstance(response, dict) or not isinstance(response.get("channel_id"), str):
                raise ControllerError("Buzz channel creation omitted channel_id")
            record.update({
                "channel_id": response["channel_id"],
                "channel_name": name,
                "channel_description": description,
                "task_binding": binding,
                "phase": "channel_created",
                "created_at": int(time.time()),
                "recovered_existing_channel": False,
            })
            _save_state(state_path, state)

    if record["phase"] == "channel_created":
        preflight = _buzz(
            config,
            env,
            "channels", "search", "--query", str(record["channel_name"]),
            "--exact", "--include-archived",
        )
        if not isinstance(preflight, list) or len(preflight) != 1 or not isinstance(preflight[0], dict):
            raise ControllerError("Buzz channel readback mismatch before member or message export")
        channel = preflight[0]
        if (
            channel.get("channel_id") != record.get("channel_id")
            or channel.get("name", "").casefold() != str(record["channel_name"]).casefold()
            or channel.get("visibility") != "private"
            or channel.get("archived") is not False
            or channel.get("about") != record.get("channel_description")
        ):
            raise ControllerError("Buzz channel readback mismatch before member or message export")
        record["phase"] = "channel_verified"
        _save_state(state_path, state)

    channel_id = record["channel_id"]
    for member_name in _roster_names(task, config):
        if member_name in record["member_names_added"]:
            continue
        member = config["members"][member_name]
        _buzz(
            config,
            env,
            "channels", "add-member", "--channel", channel_id,
            "--pubkey", member["pubkey"], "--role", member.get("role", "bot"),
        )
        record["member_names_added"].append(member_name)
        _save_state(state_path, state)

    if record["phase"] == "channel_verified":
        reviewer = str(config.get("default_reviewer") or "kublai")
        marker = f"buzz-buildroom-kickoff-{task_binding(task_id)}"
        existing_event_id = _find_message_marker(config, env, channel_id, marker)
        if existing_event_id is not None:
            record.update({
                "phase": "kickoff_posted",
                "kickoff_event_id": existing_event_id,
                "recovered_existing_kickoff": True,
            })
            _save_state(state_path, state)
        else:
            kickoff = render_kickoff(task, reviewer)
            response = _buzz(config, env, "messages", "send", "--channel", channel_id, "--content", "-", stdin=kickoff)
            if not isinstance(response, dict) or response.get("accepted") is not True:
                raise ControllerError("Buzz did not accept kickoff message")
            record.update({
                "phase": "kickoff_posted",
                "kickoff_event_id": response.get("event_id"),
                "recovered_existing_kickoff": False,
            })
            _save_state(state_path, state)
    if record["phase"] == "kickoff_posted":
        readbacks = _buzz(
            config,
            env,
            "channels", "search", "--query", str(record["channel_name"]),
            "--exact", "--include-archived",
        )
        if not isinstance(readbacks, list) or len(readbacks) != 1:
            raise ControllerError("Buzz channel readback mismatch after kickoff")
        readback = readbacks[0]
        if (
            not isinstance(readback, dict)
            or readback.get("channel_id") != channel_id
            or readback.get("name", "").casefold() != str(record["channel_name"]).casefold()
            or readback.get("visibility") != "private"
            or readback.get("archived") is not False
            or readback.get("about") != record.get("channel_description")
        ):
            raise ControllerError("Buzz channel readback mismatch after kickoff")
        record["phase"] = "active"
        _save_state(state_path, state)
    return record


def _close_room(
    task: dict[str, Any],
    record: dict[str, Any],
    config: dict[str, Any],
    state_path: Path,
    state: dict[str, Any],
    env: dict[str, str],
) -> None:
    if record.get("phase") not in {"active", "closure_posted"} or task.get("status") != "done":
        return
    task_id = str(task.get("id") or "")
    expected_binding = task_binding(task_id)
    expected_description = f"Ephemeral collaboration room for Hermes Kanban task {task_id}; binding={expected_binding}"
    if (
        record.get("task_id") != task_id
        or record.get("task_binding") != expected_binding
        or record.get("channel_description") != expected_description
        or not str(record.get("channel_name", "")).endswith("-" + expected_binding)
    ):
        raise ControllerError("Buzz channel closure task binding mismatch")
    readbacks = _buzz(
        config,
        env,
        "channels", "search", "--query", str(record.get("channel_name", "")),
        "--exact", "--include-archived",
    )
    if not isinstance(readbacks, list) or len(readbacks) != 1 or not isinstance(readbacks[0], dict):
        raise ControllerError("Buzz channel closure preflight mismatch")
    readback = readbacks[0]
    if (
        readback.get("channel_id") != record.get("channel_id")
        or readback.get("name", "").casefold() != str(record.get("channel_name", "")).casefold()
        or readback.get("visibility") != "private"
        or readback.get("about") != record.get("channel_description")
    ):
        raise ControllerError("Buzz channel closure preflight mismatch")
    if readback.get("archived") is True:
        if record["phase"] != "closure_posted":
            raise ControllerError("Buzz channel closure preflight found a premature archive")
        record.update({"phase": "closed", "closed_at": int(time.time()), "recovered_existing_archive": True})
        _save_state(state_path, state)
        return
    if readback.get("archived") is not False:
        raise ControllerError("Buzz channel closure preflight could not prove active state")
    if record["phase"] == "active":
        marker = f"buzz-buildroom-closure-{task_binding(str(task['id']))}"
        existing_event_id = _find_message_marker(config, env, record["channel_id"], marker)
        if existing_event_id is not None:
            record.update({
                "phase": "closure_posted",
                "closure_event_id": existing_event_id,
                "terminal_status": task.get("status"),
                "terminal_verdict": task.get("verdict"),
                "recovered_existing_closure": True,
            })
            _save_state(state_path, state)
        else:
            receipt = render_closure(task)
            response = _buzz(
                config, env, "messages", "send", "--channel", record["channel_id"], "--content", "-", stdin=receipt
            )
            if not isinstance(response, dict) or response.get("accepted") is not True:
                raise ControllerError("Buzz did not accept terminal receipt")
            record.update({
                "phase": "closure_posted",
                "closure_event_id": response.get("event_id"),
                "terminal_status": task.get("status"),
                "terminal_verdict": task.get("verdict"),
                "recovered_existing_closure": False,
            })
            _save_state(state_path, state)
    if record["phase"] == "closure_posted" and config.get("archive_on_done", True):
        _buzz(config, env, "channels", "archive", "--channel", record["channel_id"])
    record.update({
        "phase": "closed",
        "closed_at": int(time.time()),
    })
    _save_state(state_path, state)


class TickLock:
    """OS-backed advisory lock released automatically if the process exits."""

    def __init__(self, state_path: Path) -> None:
        self.path = state_path.with_name(state_path.name + ".lock")
        self.handle: Any = None
        self.backend: str | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            if os.name == "nt":  # pragma: no cover - exercised on Windows
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write("0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                except OSError:
                    handle.close()
                    return False
                self.backend = "msvcrt"
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    return False
                self.backend = "fcntl"
            handle.seek(0)
            handle.truncate()
            json.dump({"pid": os.getpid(), "created_at": int(time.time())}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            self.handle = handle
            return True
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if self.backend == "msvcrt":  # pragma: no cover - exercised on Windows
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            elif self.backend == "fcntl":
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            self.backend = None


def _closure_ready(
    task: dict[str, Any],
    active: dict[str, dict[str, Any]],
    config: dict[str, Any],
    env: dict[str, str],
) -> bool:
    if task.get("status") != "done":
        return False
    children = task.get("children") or []
    if not isinstance(children, list):
        return False
    for child_id in children:
        if not isinstance(child_id, str):
            return False
        child = active.get(child_id) or _tracked_task(config, env, child_id)
        if child is None or child.get("status") not in {"done", "archived"}:
            return False
        if child.get("verdict") in {"request_changes", "reject"}:
            return False
    return True


def _tick_locked(config: dict[str, Any], env: dict[str, str], state_path: Path) -> dict[str, Any]:
    state = _load_state(state_path)
    active = _active_tasks(config, env)

    closed = 0
    for task_id, record in list(state["tasks"].items()):
        task = active.get(task_id) or _tracked_task(config, env, task_id)
        if (
            task is not None
            and record.get("phase") in {"active", "closure_posted"}
            and _closure_ready(task, active, config, env)
        ):
            _close_room(task, record, config, state_path, state, env)
            closed += 1

    created = 0
    blocked: list[dict[str, str]] = []
    activation_not_before = int(config.get("activation_not_before", 0))
    limit = int(config.get("max_creations_per_tick", 1))
    for task in sorted(active.values(), key=lambda row: (int(row.get("created_at") or 0), str(row.get("id")))):
        task_id = str(task["id"])
        if task_id in state["tasks"] or created >= limit:
            continue
        if int(task.get("created_at") or 0) < activation_not_before:
            continue
        kind = classify_task(task, config)
        if kind is None:
            continue
        safe, detail = privacy_gate(task)
        if not safe:
            blocked.append({"task_id": task_id, "reason": "privacy_gate"})
            continue
        _create_room(task, kind, config, state_path, state, env)
        created += 1

    state["last_tick_at"] = int(time.time())
    _save_state(state_path, state)
    if blocked and not created and not closed:
        return {"status": "blocked", "reason": "privacy_gate", "blocked": blocked, "writes": 0}
    return {"status": "ok", "created": created, "closed": closed, "blocked": blocked, "writes": created + closed}


def tick(config: dict[str, Any]) -> dict[str, Any]:
    env = command_env(config)
    if env is None:
        return {"status": "noop", "reason": "buzz_credentials_unavailable", "writes": 0}
    state_path = Path(config["state_path"]).expanduser()
    lock = TickLock(state_path)
    if not lock.acquire():
        return {"status": "noop", "reason": "controller_busy", "writes": 0}
    try:
        return _tick_locked(config, env, state_path)
    finally:
        lock.release()


def _tag_value(row: dict[str, Any], key: str) -> str | None:
    tags = row.get("tags")
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if isinstance(tag, list) and len(tag) >= 2 and tag[0] == key and isinstance(tag[1], str):
            return tag[1]
    return None


def search_messages(config: dict[str, Any], query: str) -> dict[str, Any]:
    if not query.strip() or len(query.encode("utf-8")) > 512:
        raise ControllerError("search query must be 1-512 bytes")
    env = command_env(config)
    if env is None:
        raise ControllerError("Buzz credentials unavailable")
    response = _buzz(config, env, "messages", "search", "--query", query, "--limit", "20")
    rows: Any
    if isinstance(response, dict):
        rows = response.get("messages", response.get("results", []))
    else:
        rows = response
    if not isinstance(rows, list):
        raise ControllerError("Buzz search returned an invalid result set")
    normalized = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        content = str(row.get("content") or "")
        if is_sensitive(content):
            content = "[redacted by local privacy gate]"
        normalized.append({
            "message_id": row.get("id") or row.get("event_id"),
            "channel_id": row.get("channel_id") or row.get("channel") or _tag_value(row, "h"),
            "author": row.get("author") or row.get("author_name") or row.get("pubkey"),
            "created_at": row.get("created_at") or row.get("timestamp"),
            "content": content[:2000],
        })
    return {"query": query, "results": normalized, "count": len(normalized), "read_only": True}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-config")
    sub.add_parser("tick")
    sub.add_parser("status")
    search = sub.add_parser("search")
    search.add_argument("query")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        if args.command == "validate-config":
            output: dict[str, Any] = {"status": "ok", "schema": config["schema"]}
        elif args.command == "tick":
            output = tick(config)
        elif args.command == "status":
            state = _load_state(Path(config["state_path"]).expanduser())
            output = {
                "status": "ok",
                "credentials_available": command_env(config) is not None,
                "tracked_tasks": len(state["tasks"]),
                "last_tick_at": state.get("last_tick_at"),
            }
        elif args.command == "search":
            output = search_messages(config, args.query)
        else:  # pragma: no cover
            raise ControllerError("unsupported command")
        print(json.dumps(output, sort_keys=True))
        return 0
    except ControllerError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
