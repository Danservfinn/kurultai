from __future__ import annotations

import importlib.util
import json
import os
import plistlib
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Self

import pytest

ROOT = Path(__file__).parents[2]
INSTALL = ROOT / "deploy" / "scripts" / "install.py"
UNINSTALL = ROOT / "deploy" / "scripts" / "uninstall.py"
LAUNCHD = ROOT / "deploy" / "launchd"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Inspector:
    def __init__(self, *, vault_uuid: str = "OWNER-UUID", encrypted: bool = True) -> None:
        self.vault_uuid = vault_uuid
        self.encrypted = encrypted
        self.engine_inspections = 0

    def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
        assert path == Path("/Volumes/KurultaiVault")
        return self.vault_uuid, self.encrypted, 2_000_000, 1_000_000

    def inspect_engine(self, executable: Path, socket_path: Path) -> tuple[str, str]:
        self.engine_inspections += 1
        assert executable.is_absolute() and socket_path.is_absolute()
        return "sha256:" + "d" * 64, "engine-fixture-v1"


def test_install_is_dry_run_by_default_and_apply_persists_exact_enrollment_mode_0600(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install")
    executable = tmp_path / "engine"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    socket_path = tmp_path / "engine.sock"
    socket_path.touch()
    record = tmp_path / "install.json"
    arguments = [
        "--enroll-vault-uuid", "OWNER-UUID",
        "--enroll-container-cli", str(executable),
        "--engine-socket", str(socket_path),
    ]

    dry = module.run(arguments, inspector=Inspector(), record_path=record)
    assert dry["mutation_performed"] is False
    assert not record.exists()
    applied = module.run([*arguments, "--apply"], inspector=Inspector(), record_path=record)
    assert applied["mutation_performed"] is True
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    stored = json.loads(record.read_text())
    assert stored["vault_uuid"] == "OWNER-UUID"
    assert stored["container_cli"] == str(executable)
    assert stored["engine_socket"] == str(socket_path)
    assert stored["container_cli_sha256"] == "sha256:" + "d" * 64


def test_install_rejects_unverified_or_ambient_engine_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load(INSTALL, "hulagu_install_reject")
    target = tmp_path / "target"
    target.write_text("#!/bin/sh\n")
    target.chmod(0o700)
    symlink = tmp_path / "docker"
    symlink.symlink_to(target)
    socket_path = tmp_path / "engine.sock"
    socket_path.touch()
    record = tmp_path / "install.json"
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(ValueError, match="symlink"):
        module.run(
            ["--enroll-container-cli", str(symlink), "--engine-socket", str(socket_path), "--apply"],
            inspector=Inspector(),
            record_path=record,
        )
    assert not record.exists()


def test_two_concurrent_owner_approved_enrollments_merge_without_lost_authority(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install_concurrent")
    executable = tmp_path / "engine"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o700)
    socket_path = tmp_path / "engine.sock"
    socket_path.touch()
    record = tmp_path / "install.json"
    rendezvous = threading.Barrier(2)

    class ConcurrentInspector(Inspector):
        def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
            result = super().inspect_vault(path)
            rendezvous.wait(timeout=5)
            return result

        def inspect_engine(self, executable: Path, socket_path: Path) -> tuple[str, str]:
            result = super().inspect_engine(executable, socket_path)
            rendezvous.wait(timeout=5)
            return result

    errors: list[BaseException] = []

    def enroll(arguments: list[str]) -> None:
        try:
            module.run(arguments, inspector=ConcurrentInspector(), record_path=record)
        except Exception as error:  # noqa: BLE001 -- propagate worker-thread failures to the asserting thread
            errors.append(error)

    vault = threading.Thread(target=enroll, args=(["--enroll-vault-uuid", "OWNER-UUID", "--apply"],))
    engine = threading.Thread(
        target=enroll,
        args=(["--enroll-container-cli", str(executable), "--engine-socket", str(socket_path), "--apply"],),
    )
    vault.start()
    engine.start()
    vault.join(timeout=10)
    engine.join(timeout=10)

    assert not vault.is_alive() and not engine.is_alive()
    assert errors == []
    stored = json.loads(record.read_text())
    assert stored["vault_uuid"] == "OWNER-UUID"
    assert stored["container_cli"] == str(executable)


def test_postgres_bootstrap_is_separate_and_startup_never_initializes_pgdata(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install_bootstrap")
    record = tmp_path / "install.json"
    with pytest.raises(PermissionError, match="enrollment"):
        module.run(["--bootstrap-postgres", "--apply"], inspector=Inspector(), record_path=record)
    assert not record.exists()

    postgres = plistlib.loads((LAUNCHD / "com.kurultai.hulagu-postgres.plist.template").read_bytes())
    arguments = postgres["ProgramArguments"]
    rendered = " ".join(arguments)
    assert arguments[0].startswith("/")
    assert "initdb" not in rendered
    assert "listen_addresses=" in rendered
    assert "/Volumes/KurultaiVault/hulagu/postgres" in rendered
    assert "/Volumes/KurultaiVault/hulagu/run/postgres" in rendered


def test_postgres_bootstrap_rechecks_vault_under_lock_and_runs_effect_before_record(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install_bootstrap_effect")
    record = tmp_path / "install.json"
    record.write_text(json.dumps({"schema_version": "HulaguInstall/v1", "vault_uuid": "OWNER-UUID"}))
    record.chmod(0o600)
    events: list[str] = []

    class Effect:
        def apply(self) -> None:
            assert json.loads(record.read_text()).get("postgres_bootstrapped") is None
            events.append("bootstrap")

    report = module.run(
        ["--bootstrap-postgres", "--apply"],
        inspector=Inspector(),
        record_path=record,
        bootstrap_effect=Effect(),
    )
    assert events == ["bootstrap"]
    assert json.loads(record.read_text())["postgres_bootstrapped"] is True
    assert report["mutation_performed"] is True


def test_native_postgres_bootstrap_creates_unix_only_artifacts_and_applies_migrations(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install_native_bootstrap")
    postgres_home = tmp_path / "postgres-home"
    binaries = postgres_home / "bin"
    binaries.mkdir(parents=True)
    command_log = tmp_path / "commands.log"
    initdb = binaries / "initdb"
    initdb.write_text(f"#!/bin/sh\nprintf 'initdb %s\\n' \"$*\" >> {command_log}\nmkdir -p \"$2\"\ntouch \"$2/postgresql.auto.conf\"\n")
    pg_ctl = binaries / "pg_ctl"
    pg_ctl.write_text(f"#!/bin/sh\nprintf 'pg_ctl %s\\n' \"$*\" >> {command_log}\n")
    psql = binaries / "psql"
    psql.write_text(f"#!/bin/sh\nprintf 'psql %s\\n' \"$*\" >> {command_log}\ncat >> {command_log}\n")
    for executable in (initdb, pg_ctl, psql):
        executable.chmod(0o700)
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001.sql").write_text("SELECT 'migration-one';\n")
    (migrations / "0002.sql").write_text("SELECT 'migration-two';\n")
    data_root = tmp_path / "vault" / "hulagu"
    effect = module.NativePostgresBootstrap(
        data_root=data_root,
        postgres_home=postgres_home,
        migrations_dir=migrations,
        secret_reader=lambda _item: "synthetic-password-authority",
    )
    effect.apply()
    configuration = (data_root / "postgres" / "postgresql.auto.conf").read_text()
    log = command_log.read_text()
    assert "listen_addresses = ''" in configuration
    assert f"unix_socket_directories = '{data_root / 'run' / 'postgres'}'" in configuration
    assert "--auth-host=reject" in log
    assert "CREATE ROLE hulagu_app LOGIN PASSWORD" in log
    assert log.index("migration-one") < log.index("migration-two")
    for directory in (data_root, data_root / "run" / "postgres", data_root / "logs", data_root / "private"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_install_no_arg_plan_is_complete_not_empty(tmp_path: Path) -> None:
    module = load(INSTALL, "hulagu_install_report")
    report = module.run([], inspector=Inspector(), record_path=tmp_path / "install.json")
    assert report["current_enrollment"]["schema_version"] == "HulaguInstall/v1"
    assert report["proposed_enrollment"]["schema_version"] == "HulaguInstall/v1"
    assert report["role_mapping"]
    assert len(report["keychain_items"]) == len(module.SECRET_INVENTORY)
    assert len(report["service_mutations"]) == 4


def test_launchd_dependencies_and_absolute_fixed_executables_are_explicit() -> None:
    payloads = {
        path.stem: plistlib.loads(path.read_bytes())
        for path in LAUNCHD.glob("com.kurultai.hulagu-*.plist.template")
    }
    assert len(payloads) == 4
    for payload in payloads.values():
        assert payload["ProgramArguments"][0].startswith("/")
        assert payload["EnvironmentVariables"]["PATH"] == "/usr/bin:/bin"
    for name in ("app", "runner", "deletion"):
        payload = payloads[f"com.kurultai.hulagu-{name}.plist"]
        assert "OtherJobEnabled" not in payload["KeepAlive"]
        assert "hulagu.launchd_runtime" in " ".join(payload["ProgramArguments"])
    assert "--postgres-socket" in payloads["com.kurultai.hulagu-app.plist"]["ProgramArguments"]
    assert "--postgres-socket" in payloads["com.kurultai.hulagu-runner.plist"]["ProgramArguments"]
    deletion_arguments = payloads["com.kurultai.hulagu-deletion.plist"]["ProgramArguments"]
    assert "--app-socket" in deletion_arguments
    assert "--queue-dir" in deletion_arguments


def test_launchd_runner_command_fails_closed_without_business_authorities(tmp_path: Path) -> None:
    postgres_socket = tmp_path / "postgres"
    postgres_socket.mkdir()
    command = [
        sys.executable,
        "-m",
        "hulagu.launchd_runtime",
        "runner",
        "--pg-isready",
        "/usr/bin/true",
        "--postgres-socket",
        str(postgres_socket),
        "--poll-interval",
        "0.05",
    ]
    failed = subprocess.run(
        command,
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        check=False,
        timeout=3,
    )
    assert failed.returncode == 1


def test_launchd_app_and_runner_execute_composed_business_cycles(tmp_path: Path) -> None:
    from hulagu import launchd_runtime

    postgres_socket = tmp_path / "postgres"
    postgres_socket.mkdir()
    common = [
        "--pg-isready",
        "/usr/bin/true",
        "--postgres-socket",
        str(postgres_socket),
        "--poll-interval",
        "0.05",
    ]
    effects: list[str] = []

    class AppService:
        def run_once(self) -> None:
            effects.append("app:poll")
            launchd_runtime._request_stop(0, None)

        def close(self) -> None:
            effects.append("app:close")

    launchd_runtime._STOP = False
    assert launchd_runtime.run(["app", *common], app_service=AppService()) == 0
    assert effects == ["app:poll", "app:close"]

    class RunnerService:
        def run_once(self) -> str:
            effects.append("runner:job")
            launchd_runtime._request_stop(0, None)
            return "idle"

        def close(self) -> None:
            effects.append("runner:close")

    launchd_runtime._STOP = False
    assert launchd_runtime.run(["runner", *common], runner_service=RunnerService()) == 0
    assert effects[-2:] == ["runner:job", "runner:close"]


def test_native_runtime_services_drive_real_app_poller_socket_and_parser_entrypoints() -> None:
    from hulagu.native_runtime import NativeAppService, NativeRunnerService

    effects: list[str] = []

    class App:
        def start(self) -> None:
            effects.append("app:start")

        def poll_once(self) -> int:
            effects.append("app:poll")
            return 0

        def stop(self) -> None:
            effects.append("app:stop")

    class CompletionServer:
        def bind(self) -> None:
            effects.append("socket:bind")

        def serve_once(self) -> None:
            effects.append("socket:serve")

        def close(self) -> None:
            effects.append("socket:close")

    service = NativeAppService(App(), CompletionServer(), start_socket_worker=False)
    service.run_once()
    service.serve_completion_once()
    service.close()
    assert effects == ["app:start", "socket:bind", "app:poll", "socket:serve", "socket:close", "app:stop"]

    class Runner:
        def run_once(self) -> str:
            effects.append("runner:run")
            return "succeeded"

    runner_service = NativeRunnerService(Runner())
    assert runner_service.run_once() == "succeeded"
    runner_service.close()
    assert effects[-1] == "runner:run"


def test_production_app_binding_lookup_validates_a_live_completion() -> None:
    from hulagu.deletion_app import FixedCompletionRequest, RouteBindingValidator, route_binding_digest
    from hulagu.native_runtime import PostgresRouteBindingLookup

    deletion_id = "92000000-0000-4000-8000-000000000016"
    binding_key = b"synthetic-app-binding-key-material"
    digest = route_binding_digest(binding_key, bot_id=777, route=12345, generation=4)

    class Cursor:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def execute(self, query: str, parameters: tuple[object, ...]) -> None:
            assert query == (
                "SELECT route_key_version,route_binding_digest "
                "FROM hulagu_api.app_deletion_route_binding(%s::uuid)"
            )
            assert parameters == (deletion_id,)

        def fetchone(self) -> tuple[int, str]:
            return 2, digest

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

    lookup = PostgresRouteBindingLookup(Connection(), bot_id=777)
    validator = RouteBindingValidator({2: binding_key}, lookup=lookup)
    validator.validate(FixedCompletionRequest(deletion_id, 12345, 4, "deletion-complete-v1"))


def test_production_postgres_binding_lookup_enforces_exact_completion_authority() -> None:
    import hashlib

    import psycopg

    from hulagu.deletion_app import FixedCompletionRequest, RouteBindingValidator, route_binding_digest
    from hulagu.native_runtime import PostgresRouteBindingLookup

    helpers = load(ROOT / "tests" / "integration" / "test_migrations.py", "hulagu_native_postgres_helpers")
    tenant_id = "92000000-0000-4000-8000-000000000016"
    replacement_deletion_id = "92000000-0000-4000-8000-000000000099"
    nonce_hash = hashlib.sha256(b"native-postgres-binding-nonce").hexdigest()
    erasure_token = "synthetic-native-postgres-erasure-token"
    erasure_hash = hashlib.sha256(erasure_token.encode()).hexdigest()
    delivery_hash = hashlib.sha256(b"synthetic-native-postgres-delivery-token").hexdigest()
    binding_key = b"synthetic-app-binding-key-material"
    digest = route_binding_digest(binding_key, bot_id=777, route=12345, generation=4)

    with helpers.postgres_cluster() as dsn:
        helpers._seed_single_use_deletion_tenant(dsn, tenant_id, epoch=6, nonce_hash=nonce_hash)
        deletion_id = helpers.psql(
            dsn,
            "BEGIN;"
            f"SET LOCAL app.tenant_id='{tenant_id}';"
            f"SELECT hulagu_api.request_deletion('{nonce_hash}','encrypted-route-envelope','{digest}');"
            "COMMIT;",
            user="hulagu_app",
        ).stdout.strip()
        helpers.psql(
            dsn,
            f"SELECT hulagu_api.claim_deletion_erasure('{deletion_id}','{erasure_hash}');"
            f"SELECT hulagu_api.complete_deletion_erasure('{deletion_id}','{erasure_token}');"
            f"SELECT hulagu_api.claim_deletion_delivery('{deletion_id}','{delivery_hash}');",
            user="hulagu_deletion",
        )

        with psycopg.connect(dsn, user="hulagu_app") as connection:
            validator = RouteBindingValidator(
                {1: binding_key},
                lookup=PostgresRouteBindingLookup(connection, bot_id=777),
            )
            validator.validate(FixedCompletionRequest(deletion_id, 12345, 4, "deletion-complete-v1"))
            for substituted in (
                FixedCompletionRequest(deletion_id, 54321, 4, "deletion-complete-v1"),
                FixedCompletionRequest(deletion_id, 12345, 5, "deletion-complete-v1"),
                FixedCompletionRequest(replacement_deletion_id, 12345, 4, "deletion-complete-v1"),
            ):
                with pytest.raises(PermissionError, match="binding validation failed"):
                    validator.validate(substituted)


def test_native_telegram_adapter_performs_real_poller_business_requests() -> None:
    from hulagu.native_runtime import NativeTelegramAdapter

    requests: list[tuple[str, dict[str, object]]] = []

    def request(method: str, payload: dict[str, object]) -> object:
        requests.append((method, payload))
        if method == "getMe":
            return {"id": 777}
        if method == "getWebhookInfo":
            return {"url": ""}
        if method == "getUpdates":
            return [{"update_id": 4}]
        if method == "sendMessage":
            return {"message_id": 9}
        raise AssertionError(method)

    adapter = NativeTelegramAdapter("synthetic-bot-token", request=request)
    assert adapter.get_me() == 777
    assert adapter.get_webhook_info() == ""
    assert adapter.get_updates(4) == [{"update_id": 4}]
    adapter.send_message(42, "done", "delivery-1")
    assert requests == [
        ("getMe", {}),
        ("getWebhookInfo", {}),
        ("getUpdates", {"offset": 4, "timeout": 20, "allowed_updates": ["message", "callback_query"]}),
        ("sendMessage", {"chat_id": 42, "text": "done"}),
    ]


def test_launchd_app_command_fails_closed_before_fake_socket_readiness(tmp_path: Path) -> None:
    postgres_socket = tmp_path / "postgres"
    postgres_socket.mkdir()
    app_socket = Path("/tmp") / f"hulagu-test-{os.getpid()}-{time.monotonic_ns()}.sock"
    common = [
        "--pg-isready",
        "/usr/bin/true",
        "--postgres-socket",
        str(postgres_socket),
        "--poll-interval",
        "0.05",
    ]
    app = subprocess.run(
        [sys.executable, "-m", "hulagu.launchd_runtime", "app", *common, "--app-socket", str(app_socket)],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "src"},
        check=False,
        timeout=3,
    )
    assert app.returncode == 1
    assert not app_socket.exists()


def test_uninstall_preserves_customer_data_unless_destructive_confirmation_is_exact(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall")
    data_root = tmp_path / "customer-data"
    data_root.mkdir()
    (data_root / "must-survive").write_text("synthetic")
    removed: list[Path] = []

    report = module.run([], data_root=data_root, remove_path=lambda path: removed.append(path))
    assert report["customer_data_deleted"] is False
    assert removed == [] and data_root.exists()

    stopped: list[str] = []
    config_a = tmp_path / "app.plist"
    config_b = tmp_path / "install.json"
    applied = module.run(
        ["--apply"],
        data_root=data_root,
        stop_service=lambda label: (stopped.append(label) or True),
        code_config_paths=(config_a, config_b),
        remove_code_config=removed.append,
    )
    assert applied["mutation_performed"] is True
    assert stopped == [
        "com.kurultai.hulagu-deletion",
        "com.kurultai.hulagu-runner",
        "com.kurultai.hulagu-app",
        "com.kurultai.hulagu-postgres",
    ]
    assert removed == [config_a, config_b]
    assert data_root.exists()

    with pytest.raises(PermissionError, match="confirmation"):
        module.run(["--delete-customer-data", "--apply"], data_root=data_root, remove_path=lambda path: removed.append(path))
    assert data_root.exists()

    effects: list[object] = []
    with pytest.raises(ValueError, match="unsafe"):
        module.run(
            ["--delete-customer-data", "--confirm", "DELETE-HULAGU-CUSTOMER-DATA", "--apply"],
            data_root=Path("/"),
            stop_service=effects.append,
            code_config_paths=(config_a,),
            remove_code_config=effects.append,
        )
    assert effects == []


def test_uninstall_service_stop_failure_aborts_before_config_or_data_effects(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_stop_failure")
    effects: list[object] = []

    def failed_stop(label: str) -> bool:
        effects.append(("stop", label))
        raise RuntimeError("synthetic launchctl failure")

    with pytest.raises(RuntimeError, match="launchctl"):
        module.run(
            ["--apply"],
            data_root=tmp_path / "data",
            stop_service=failed_stop,
            code_config_paths=(tmp_path / "config",),
            remove_code_config=lambda path: effects.append(("config", path)),
        )
    assert effects == [("stop", "com.kurultai.hulagu-deletion")]


def test_destructive_uninstall_rechecks_enrolled_vault_and_orders_effects(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_destructive")
    vault = tmp_path / "vault"
    data_root = vault / "hulagu"
    data_root.mkdir(parents=True)
    record = tmp_path / "install.json"
    record.write_text(
        json.dumps({"schema_version": "HulaguInstall/v1", "vault_path": str(vault), "vault_uuid": "OWNER-UUID"})
    )
    record.chmod(0o600)
    effects: list[str] = []

    class Vault:
        def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
            assert path == vault
            effects.append("inspect")
            return "OWNER-UUID", True, 100, 50

    report = module.run(
        ["--delete-customer-data", "--confirm", "DELETE-HULAGU-CUSTOMER-DATA", "--apply"],
        data_root=data_root,
        record_path=record,
        inspector=Vault(),
        stop_service=lambda label: (effects.append(f"stop:{label}") or True),
        code_config_paths=(tmp_path / "config",),
        remove_code_config=lambda _path: effects.append("config"),
        remove_path=lambda _path, _identity: effects.append("data"),
    )
    assert report["customer_data_deleted"] is True
    assert effects[:4] == [
        "stop:com.kurultai.hulagu-deletion",
        "stop:com.kurultai.hulagu-runner",
        "stop:com.kurultai.hulagu-app",
        "stop:com.kurultai.hulagu-postgres",
    ]
    assert effects[4:] == ["inspect", "data", "config"]


def test_destructive_uninstall_rejects_vault_identity_and_symlink_path_drift(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_drift")
    vault = tmp_path / "vault"
    data_root = vault / "hulagu"
    data_root.mkdir(parents=True)
    record = tmp_path / "install.json"
    record.write_text(
        json.dumps({"schema_version": "HulaguInstall/v1", "vault_path": str(vault), "vault_uuid": "OWNER-UUID"})
    )
    record.chmod(0o600)

    class DriftedVault:
        def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
            return "OTHER-UUID", True, 100, 50

    with pytest.raises(PermissionError, match="identity drifted"):
        module.run(
            ["--delete-customer-data", "--confirm", "DELETE-HULAGU-CUSTOMER-DATA", "--apply"],
            data_root=data_root,
            record_path=record,
            inspector=DriftedVault(),
            stop_service=lambda _label: True,
            code_config_paths=(),
        )

    external = tmp_path / "external"
    external.mkdir()
    link = tmp_path / "link"
    link.symlink_to(external, target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        module._confined_rmtree(link, (0, 0))
    assert external.exists()


def test_confined_rmtree_keeps_authorized_inode_bound_through_final_root_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_final_gap")
    vault = tmp_path / "vault"
    data_root = vault / "hulagu"
    data_root.mkdir(parents=True)
    (data_root / "authorized").write_text("original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "unauthorized").write_text("replacement")
    original = vault / "original"
    identity = module._confined_identity(data_root)
    real_rmtree = module.shutil.rmtree

    def swap_at_path_named_removal(name: str, *, dir_fd: int) -> None:
        os.rename(data_root.name, original.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        replacement.rename(data_root)
        real_rmtree(name, dir_fd=dir_fd)

    monkeypatch.setattr(module.shutil, "rmtree", swap_at_path_named_removal)
    try:
        module._confined_rmtree(data_root, identity)
    except PermissionError:
        pass

    replacement_canaries = [replacement / "unauthorized", data_root / "unauthorized"]
    assert any(path.read_text() == "replacement" for path in replacement_canaries if path.exists())
    assert not (original / "authorized").exists()
    assert not (data_root / "authorized").exists()


def test_code_config_directory_removal_does_not_delete_a_final_gap_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_config_final_gap")
    config = tmp_path / "config"
    config.mkdir()
    (config / "authorized").write_text("original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "unauthorized").write_text("replacement")
    original = tmp_path / "original"
    real_rmtree = module.shutil.rmtree

    def swap_at_path_named_removal(path: Path) -> None:
        path.rename(original)
        replacement.rename(path)
        real_rmtree(path)

    monkeypatch.setattr(module.shutil, "rmtree", swap_at_path_named_removal)
    try:
        module._remove_code_config(config)
    except PermissionError:
        pass

    replacement_canaries = [replacement / "unauthorized", config / "unauthorized"]
    assert any(path.read_text() == "replacement" for path in replacement_canaries if path.exists())


def test_destructive_uninstall_preserves_retry_authority_until_data_removal_succeeds(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_retry_authority")
    vault = tmp_path / "vault"
    data_root = vault / "hulagu"
    data_root.mkdir(parents=True)
    record = tmp_path / "install.json"
    record.write_text(
        json.dumps({"schema_version": "HulaguInstall/v1", "vault_path": str(vault), "vault_uuid": "OWNER-UUID"})
    )
    record.chmod(0o600)
    config = tmp_path / "app.plist"
    config.write_text("synthetic")
    removed_config: list[Path] = []

    class Vault:
        def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
            assert path == vault
            return "OWNER-UUID", True, 100, 50

    def fail_data_removal(_path: Path, _identity: tuple[int, int]) -> None:
        raise OSError("synthetic data removal failure")

    with pytest.raises(OSError, match="synthetic data removal failure"):
        module.run(
            ["--delete-customer-data", "--confirm", "DELETE-HULAGU-CUSTOMER-DATA", "--apply"],
            data_root=data_root,
            record_path=record,
            inspector=Vault(),
            stop_service=lambda _label: True,
            code_config_paths=(config, record),
            remove_code_config=removed_config.append,
            remove_path=fail_data_removal,
        )

    assert removed_config == []
    assert record.exists()


def test_destructive_uninstall_binds_validated_identity_at_deletion_effect(tmp_path: Path) -> None:
    module = load(UNINSTALL, "hulagu_uninstall_effect_identity")
    vault = tmp_path / "vault"
    data_root = vault / "hulagu"
    data_root.mkdir(parents=True)
    (data_root / "authorized").write_text("original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "unauthorized").write_text("replacement")
    record = tmp_path / "install.json"
    record.write_text(
        json.dumps({"schema_version": "HulaguInstall/v1", "vault_path": str(vault), "vault_uuid": "OWNER-UUID"})
    )
    record.chmod(0o600)
    original = tmp_path / "original"

    class Vault:
        def inspect_vault(self, path: Path) -> tuple[str, bool, int, int]:
            assert path == vault
            return "OWNER-UUID", True, 100, 50

    def swap_at_effect(path: Path, expected_identity: tuple[int, int]) -> None:
        path.rename(original)
        replacement.rename(path)
        module._confined_rmtree(path, expected_identity)

    with pytest.raises(PermissionError, match="identity drifted"):
        module.run(
            ["--delete-customer-data", "--confirm", "DELETE-HULAGU-CUSTOMER-DATA", "--apply"],
            data_root=data_root,
            record_path=record,
            inspector=Vault(),
            stop_service=lambda _label: True,
            code_config_paths=(),
            remove_path=swap_at_effect,
        )
    assert (original / "authorized").read_text() == "original"
    assert (data_root / "unauthorized").read_text() == "replacement"
