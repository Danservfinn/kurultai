"""Bounded, fail-closed long-running launchd composition roots."""

from __future__ import annotations

import argparse
import os
import signal
import socket
import stat
import subprocess  # nosec B404
import time
from pathlib import Path
from typing import Protocol
from uuid import UUID

from hulagu import deletion_app

_STOP = False


class AppBusinessService(Protocol):
    def run_once(self) -> object: ...
    def close(self) -> None: ...


class RunnerBusinessService(Protocol):
    def run_once(self) -> object: ...
    def close(self) -> None: ...


def _request_stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def _private_regular(path: Path) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise PermissionError("authority file must be a private regular file")


def _postgres_ready(pg_isready: Path, socket_dir: Path, *, timeout_seconds: int) -> None:
    if (
        not pg_isready.is_absolute()
        or pg_isready.is_symlink()
        or not pg_isready.is_file()
        or not os.access(pg_isready, os.X_OK)
        or not socket_dir.is_absolute()
        or socket_dir.is_symlink()
        or not socket_dir.is_dir()
    ):
        raise RuntimeError("PostgreSQL readiness authority is invalid")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        completed = subprocess.run(  # nosec B603
            [str(pg_isready), "-q", "-h", str(socket_dir), "-d", "hulagu"],
            check=False,
            capture_output=True,
            timeout=5,
            env={"PATH": "/usr/bin:/bin"},
        )
        if completed.returncode == 0:
            return
        time.sleep(0.1)
    raise RuntimeError("PostgreSQL readiness was not proved")


def _app_ready(path: Path, *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISSOCK(metadata.st_mode):
                raise RuntimeError("app endpoint is not a Unix socket")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(str(path))
            return
        except FileNotFoundError:
            time.sleep(0.1)
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("app local-send readiness was not proved")


def _business_loop(service: AppBusinessService | RunnerBusinessService, *, interval: float) -> int:
    try:
        while not _STOP:
            service.run_once()
            if not _STOP:
                time.sleep(interval)
    finally:
        service.close()
    return 0


def _compose_app(args: argparse.Namespace) -> AppBusinessService:
    from hulagu.native_runtime import compose_app

    return compose_app(args)


def _compose_runner(args: argparse.Namespace) -> RunnerBusinessService:
    from hulagu.native_runtime import compose_runner

    return compose_runner(args)


def _dispatch_loop(args: argparse.Namespace, *, interval: float) -> int:
    for authority in (args.postgres_dsn_file, args.deletion_key_file):
        _private_regular(authority)
    if (
        not args.queue_dir.is_absolute()
        or args.queue_dir.is_symlink()
        or not args.queue_dir.is_dir()
        or stat.S_IMODE(args.queue_dir.stat().st_mode) & 0o077
    ):
        raise PermissionError("deletion queue must be a private directory")
    while not _STOP:
        _app_ready(args.app_socket, timeout_seconds=args.readiness_timeout)
        for item in sorted(args.queue_dir.glob("*.id")):
            _private_regular(item)
            deletion_id = str(UUID(item.read_text().strip()))
            result = deletion_app.main(
                [
                    "--postgres-dsn-file",
                    str(args.postgres_dsn_file),
                    "--deletion-key-file",
                    str(args.deletion_key_file),
                    "--app-socket",
                    str(args.app_socket),
                    "--tenants-root",
                    str(args.tenants_root),
                    "--deletion-id",
                    deletion_id,
                ]
            )
            if result == 0:
                item.unlink()
        time.sleep(interval)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hulagu-launchd-runtime")
    parser.add_argument("service", choices=("app", "runner", "deletion"))
    parser.add_argument("--pg-isready", type=Path, required=True)
    parser.add_argument("--postgres-socket", type=Path, required=True)
    parser.add_argument("--readiness-timeout", type=int, default=30)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--app-socket", type=Path)
    parser.add_argument("--postgres-dsn-file", type=Path)
    parser.add_argument("--deletion-key-file", type=Path)
    parser.add_argument("--tenants-root", type=Path)
    parser.add_argument("--queue-dir", type=Path)
    parser.add_argument("--pinned-bot-id", type=int)
    parser.add_argument("--install-record", type=Path)
    parser.add_argument("--parser-image")
    return parser


def run(
    argv: list[str] | None = None,
    *,
    app_service: AppBusinessService | None = None,
    runner_service: RunnerBusinessService | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.readiness_timeout <= 300 or not 0.05 <= args.poll_interval <= 60:
        raise ValueError("runtime bounds are invalid")
    _postgres_ready(args.pg_isready, args.postgres_socket, timeout_seconds=args.readiness_timeout)
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    if args.service == "app":
        if app_service is None and args.app_socket is None:
            raise ValueError("app socket is required")
        return _business_loop(app_service or _compose_app(args), interval=args.poll_interval)
    if args.service == "runner":
        return _business_loop(runner_service or _compose_runner(args), interval=args.poll_interval)
    required = (
        args.app_socket,
        args.postgres_dsn_file,
        args.deletion_key_file,
        args.tenants_root,
        args.queue_dir,
    )
    if any(value is None for value in required):
        raise ValueError("all deletion authorities are required")
    return _dispatch_loop(args, interval=args.poll_interval)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except (OSError, PermissionError, RuntimeError, TypeError, ValueError, subprocess.SubprocessError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
