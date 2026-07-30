"""Native launchd composition services for the app poller and parser runner."""

from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess  # nosec B404
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast


class NativeTelegramAdapter:
    """Bounded HTTPS Telegram adapter used by the standalone poller."""

    def __init__(
        self,
        token: str,
        *,
        request: Callable[[str, dict[str, object]], object] | None = None,
    ) -> None:
        if not token or any(character in token for character in "\x00\r\n/"):
            raise ValueError("invalid Telegram token authority")
        self._token = token
        self._request_override = request

    def _request(self, method: str, payload: dict[str, object]) -> object:
        if self._request_override is not None:
            return self._request_override(method, payload)
        body = json.dumps(payload, separators=(",", ":")).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self._token}/{method}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 -- fixed HTTPS origin
                value = json.loads(response.read(1_048_577))
        except (OSError, urllib.error.URLError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Telegram API request failed") from exc
        if not isinstance(value, dict) or value.get("ok") is not True or "result" not in value:
            raise RuntimeError("Telegram API rejected request")
        return value["result"]

    def get_me(self) -> int:
        result = self._request("getMe", {})
        if not isinstance(result, dict) or not isinstance(result.get("id"), int):
            raise TypeError("Telegram getMe returned invalid identity")
        return int(result["id"])

    def get_webhook_info(self) -> str:
        result = self._request("getWebhookInfo", {})
        if not isinstance(result, dict) or not isinstance(result.get("url"), str):
            raise TypeError("Telegram webhook state is invalid")
        return str(result["url"])

    def get_updates(self, offset: int) -> list[dict[str, object]]:
        result = self._request(
            "getUpdates",
            {"offset": offset, "timeout": 20, "allowed_updates": ["message", "callback_query"]},
        )
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise RuntimeError("Telegram updates payload is invalid")
        return cast(list[dict[str, object]], result)

    def send_message(self, chat_id: int, text: str, delivery_key: str) -> None:
        if chat_id < 1 or not text or not delivery_key:
            raise ValueError("invalid Telegram send authority")
        result = self._request("sendMessage", {"chat_id": chat_id, "text": text})
        if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
            raise TypeError("Telegram send result is invalid")


class AppEntrypoint(Protocol):
    def start(self) -> None: ...
    def poll_once(self) -> int: ...
    def stop(self) -> None: ...


class CompletionServer(Protocol):
    def bind(self) -> None: ...
    def serve_once(self) -> None: ...
    def close(self) -> None: ...


class RunnerEntrypoint(Protocol):
    def run_once(self) -> str: ...


class NativeAppService:
    """Run the real Telegram poller alongside its authenticated completion socket."""

    def __init__(
        self,
        app: AppEntrypoint,
        completion_server: CompletionServer,
        *,
        start_socket_worker: bool = True,
    ) -> None:
        self._app = app
        self._server = completion_server
        self._closed = False
        self._thread: threading.Thread | None = None
        self._app.start()
        try:
            self._server.bind()
            if start_socket_worker:
                self._thread = threading.Thread(target=self._serve_completions, daemon=True)
                self._thread.start()
        except BaseException:
            self._app.stop()
            raise

    def _serve_completions(self) -> None:
        while not self._closed:
            try:
                self._server.serve_once()
            except OSError:
                if not self._closed:
                    raise
                return

    def serve_completion_once(self) -> None:
        self._server.serve_once()

    def run_once(self) -> int:
        return self._app.poll_once()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._app.stop()


class NativeRunnerService:
    """Drive the real lease-fenced parser runner composition root."""

    def __init__(self, runner: RunnerEntrypoint) -> None:
        self._runner = runner

    def run_once(self) -> str:
        return self._runner.run_once()

    def close(self) -> None:
        return None


def _read_keychain(item: str) -> str:
    result = subprocess.run(  # nosec B603
        ["/usr/bin/security", "find-generic-password", "-w", "-s", item],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin"},
    )
    value = result.stdout.rstrip("\n")
    if not 8 <= len(value) <= 4096 or any(character in value for character in "\x00\r\n"):
        raise ValueError("invalid Keychain runtime authority")
    return value


def _private_record(path: Path) -> dict[str, object]:
    if not path.is_absolute():
        raise ValueError("runtime record must be absolute")
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise PermissionError("runtime record is not a private regular file")
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != "HulaguInstall/v1":
        raise ValueError("runtime record is invalid")
    return value


def _postgres_dsn(socket_path: Path, role: str, password: str) -> str:
    if not socket_path.is_absolute() or socket_path.is_symlink() or not socket_path.is_dir():
        raise ValueError("PostgreSQL socket authority is invalid")
    escaped = password.replace("\\", "\\\\").replace("'", "\\'")
    return f"host='{socket_path}' dbname=hulagu user={role} password='{escaped}'"


class PostgresRouteBindingLookup:
    """Read only the live HMAC metadata exposed to the app role."""

    def __init__(self, connection: Any, *, bot_id: int) -> None:
        if bot_id < 1:
            raise ValueError("pinned Telegram bot id is required")
        self._connection = connection
        self._bot_id = bot_id

    def __call__(self, deletion_id: str, route_generation: int) -> Any:
        from hulagu.deletion_app import RouteBindingRecord

        if route_generation < 1:
            return None
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT route_key_version,route_binding_digest "
                "FROM hulagu_api.app_deletion_route_binding(%s::uuid)",
                (deletion_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        key_version, binding_digest = row
        if isinstance(binding_digest, bytes):
            try:
                binding_digest = binding_digest.decode("ascii", "strict")
            except UnicodeDecodeError as exc:
                raise RuntimeError("invalid app deletion binding projection") from exc
        if (
            not isinstance(key_version, int)
            or key_version < 1
            or not isinstance(binding_digest, str)
            or len(binding_digest) != 64
            or any(character not in "0123456789abcdef" for character in binding_digest)
        ):
            raise RuntimeError("invalid app deletion binding projection")
        return RouteBindingRecord(
            bot_id=self._bot_id,
            route_generation=route_generation,
            key_version=key_version,
            binding_digest=binding_digest,
        )


def compose_app(args: object) -> NativeAppService:
    from hulagu.app import HulaguApp, PostgresAdvisoryLock, PostgresStore
    from hulagu.deletion_app import (
        FixedCompletionRequest,
        RouteBindingValidator,
        UnixDeletionCompletionServer,
    )
    from hulagu.telegram.commands import CallbackCodec, IdentityDigestKeys, RouteKeys

    pinned_bot_id = getattr(args, "pinned_bot_id", None)
    postgres_socket = getattr(args, "postgres_socket", None)
    app_socket = getattr(args, "app_socket", None)
    if not isinstance(pinned_bot_id, int) or pinned_bot_id < 1:
        raise ValueError("pinned Telegram bot id is required")
    if not isinstance(postgres_socket, Path) or not isinstance(app_socket, Path):
        raise TypeError("app runtime paths are required")
    telegram_token = _read_keychain("com.kurultai.hulagu.telegram-bot-token.v1")
    postgres_password = _read_keychain("com.kurultai.hulagu.postgres-app-password.v1")
    subject_key = _read_keychain("com.kurultai.hulagu.subject-digest-hmac.v1").encode()
    callback_key = _read_keychain("com.kurultai.hulagu.action-token-hmac.v1").encode()
    active_route_key = _read_keychain("com.kurultai.hulagu.active-route-encryption.v1").encode()
    binding_key = _read_keychain("com.kurultai.hulagu.deletion-route-binding-hmac.v1").encode()
    dsn = _postgres_dsn(postgres_socket, "hulagu_app", postgres_password)
    psycopg = importlib.import_module("psycopg")
    app_connection = psycopg.connect(dsn)
    lock_connection = psycopg.connect(dsn)
    adapter = NativeTelegramAdapter(telegram_token)
    app = HulaguApp(
        adapter,
        PostgresStore(app_connection, bot_id=pinned_bot_id),
        pinned_bot_id=pinned_bot_id,
        identity_keys=IdentityDigestKeys({1: subject_key}, 1),
        callback_codec=CallbackCodec(callback_key),
        route_keys=RouteKeys({1: active_route_key}, 1, binding_key=binding_key),
        singleton_lock=PostgresAdvisoryLock(lock_connection),
        clock=lambda: int(time.time()),
    )

    validator = RouteBindingValidator(
        {1: binding_key},
        lookup=PostgresRouteBindingLookup(app_connection, bot_id=pinned_bot_id),
    )

    def send_fixed(request: FixedCompletionRequest) -> None:
        adapter.send_message(
            request.route,
            "Your Hulagu customer data deletion is complete.",
            f"deletion-complete:{request.deletion_id}",
        )

    server = UnixDeletionCompletionServer(
        app_socket,
        allowed_peer_uids={os.getuid()},
        validator=validator,
        send_fixed=send_fixed,
    )
    return NativeAppService(app, server)


def compose_runner(args: object) -> NativeRunnerService:
    from hulagu.runner_app import PostgresParserJobQueue, RunnerApp
    from hulagu.runtime.container import ParserContainerExecutor
    from hulagu.runtime.policy import EngineEnrollment

    postgres_socket = getattr(args, "postgres_socket", None)
    tenants_root = getattr(args, "tenants_root", None)
    install_record = getattr(args, "install_record", None)
    parser_image = getattr(args, "parser_image", None)
    if not all(isinstance(path, Path) for path in (postgres_socket, tenants_root, install_record)):
        raise TypeError("runner runtime paths are required")
    if not isinstance(parser_image, str):
        raise TypeError("digest-pinned parser image is required")
    postgres_socket = cast(Path, postgres_socket)
    tenants_root = cast(Path, tenants_root)
    install_record = cast(Path, install_record)
    record = _private_record(install_record)
    enrollment = EngineEnrollment(
        Path(str(record.get("container_cli", ""))),
        str(record.get("container_cli_sha256", "")).removeprefix("sha256:"),
        Path(str(record.get("engine_socket", ""))),
        parser_image,
    ).validate()
    password = _read_keychain("com.kurultai.hulagu.postgres-runner-password.v1")
    dsn = _postgres_dsn(postgres_socket, "hulagu_runner", password)
    runner = RunnerApp(
        PostgresParserJobQueue(dsn, tenant_root=tenants_root),
        ParserContainerExecutor(enrollment),
        work_root=tenants_root.parent / "run" / "runner",
        clock=lambda: int(time.time()),
    )
    return NativeRunnerService(runner)
