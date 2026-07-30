"""Least-privilege deletion completion dispatcher boundary."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import importlib
import json
import os
import socket
import stat
import struct
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from hulagu.domain.deletion import erase_tenant_directory


def _xor(value: bytes, key: bytes, nonce: bytes, domain: bytes) -> bytes:
    stream = bytearray()
    counter = 0
    while len(stream) < len(value):
        stream.extend(hmac.new(key, domain + b"\0" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(byte ^ stream[index] for index, byte in enumerate(value))


def _seal_etm(value: bytes, key: bytes, *, domain: bytes, aad: bytes = b"") -> str:
    nonce = os.urandom(16)
    encryption_key = hmac.new(key, domain + b"\0encryption", hashlib.sha256).digest()
    authentication_key = hmac.new(key, domain + b"\0authentication", hashlib.sha256).digest()
    ciphertext = _xor(value, encryption_key, nonce, domain)
    tag = hmac.new(authentication_key, domain + b"\0" + aad + nonce + ciphertext, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")


def _open_etm(value: str, key: bytes, *, domain: bytes, aad: bytes = b"") -> bytes:
    try:
        packed = base64.urlsafe_b64decode(value.encode("ascii"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid authenticated envelope") from exc
    if len(packed) < 49:
        raise ValueError("invalid authenticated envelope")
    nonce, ciphertext, tag = packed[:16], packed[16:-32], packed[-32:]
    encryption_key = hmac.new(key, domain + b"\0encryption", hashlib.sha256).digest()
    authentication_key = hmac.new(key, domain + b"\0authentication", hashlib.sha256).digest()
    expected = hmac.new(
        authentication_key, domain + b"\0" + aad + nonce + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("invalid authenticated envelope")
    return _xor(ciphertext, encryption_key, nonce, domain)


def _validate_keys(keys: Mapping[int, bytes] | None) -> dict[int, bytes] | None:
    if keys is None:
        return None
    if not keys or any(version < 1 or len(key) < 16 for version, key in keys.items()):
        raise ValueError("invalid route envelope keys")
    return dict(keys)


def _wrap_dek(dek: bytes, keys: Mapping[int, bytes], version: int, *, domain: bytes, aad: bytes) -> str:
    if version not in keys:
        raise ValueError("unknown route wrapping key")
    sealed = _seal_etm(dek, keys[version], domain=domain, aad=aad)
    return base64.urlsafe_b64encode(version.to_bytes(4, "big") + base64.urlsafe_b64decode(sealed)).decode("ascii")


def _unwrap_dek(value: str, keys: Mapping[int, bytes], *, domain: bytes, aad: bytes) -> bytes:
    try:
        packed = base64.urlsafe_b64decode(value.encode("ascii"))
        version = int.from_bytes(packed[:4], "big")
        key = keys[version]
    except (UnicodeError, ValueError, KeyError) as exc:
        raise ValueError("invalid wrapped route data key") from exc
    sealed = base64.urlsafe_b64encode(packed[4:]).decode("ascii")
    dek = _open_etm(sealed, key, domain=domain, aad=aad)
    if len(dek) != 32:
        raise ValueError("invalid wrapped route data key")
    return dek


@dataclass(frozen=True, slots=True)
class RouteEnvelope:
    route_ciphertext: str
    active_wrapped_dek: str
    deletion_wrapped_dek: str

    def deletion_projection(self) -> str:
        return json.dumps(
            {
                "schema_version": "DeletionRouteEnvelope/v1",
                "route_ciphertext": self.route_ciphertext,
                "deletion_wrapped_dek": self.deletion_wrapped_dek,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


class RouteEnvelopeKeys:
    """Split key views over per-route DEKs; no long-lived key encrypts a route directly."""

    def __init__(
        self,
        *,
        active_keys: Mapping[int, bytes] | None,
        deletion_keys: Mapping[int, bytes] | None,
    ) -> None:
        self._active_keys = _validate_keys(active_keys)
        self._deletion_keys = _validate_keys(deletion_keys)

    @classmethod
    def for_issuer(
        cls, *, active_keys: Mapping[int, bytes], deletion_keys: Mapping[int, bytes]
    ) -> RouteEnvelopeKeys:
        return cls(active_keys=active_keys, deletion_keys=deletion_keys)

    @classmethod
    def for_active(cls, keys: Mapping[int, bytes]) -> RouteEnvelopeKeys:
        return cls(active_keys=keys, deletion_keys=None)

    @classmethod
    def for_deletion(cls, keys: Mapping[int, bytes]) -> RouteEnvelopeKeys:
        return cls(active_keys=None, deletion_keys=keys)

    def seal(
        self,
        route: int,
        *,
        generation: int,
        bot_id: int,
        active_key_version: int,
        deletion_key_version: int,
    ) -> RouteEnvelope:
        if (
            route < 1
            or generation < 1
            or bot_id < 1
            or self._active_keys is None
            or self._deletion_keys is None
        ):
            raise ValueError("issuer route authority is required")
        plain = json.dumps(
            {"bot_id": bot_id, "route": route, "generation": generation},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        dek = os.urandom(32)
        route_ciphertext = _seal_etm(plain, dek, domain=b"hulagu.route-payload.v1")
        aad = hashlib.sha256(route_ciphertext.encode("ascii")).digest()
        return RouteEnvelope(
            route_ciphertext=route_ciphertext,
            active_wrapped_dek=_wrap_dek(
                dek,
                self._active_keys,
                active_key_version,
                domain=b"hulagu.active-route-wrap.v1",
                aad=aad,
            ),
            deletion_wrapped_dek=_wrap_dek(
                dek,
                self._deletion_keys,
                deletion_key_version,
                domain=b"hulagu.deletion-route-wrap.v1",
                aad=aad,
            ),
        )

    def _open_payload(self, route_ciphertext: str, dek: bytes) -> tuple[int, int]:
        try:
            value = json.loads(_open_etm(route_ciphertext, dek, domain=b"hulagu.route-payload.v1"))
            route = int(value["route"])
            generation = int(value["generation"])
            bot_id = int(value["bot_id"])
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid deletion route") from exc
        if route < 1 or generation < 1 or bot_id < 1:
            raise ValueError("invalid deletion route")
        return route, generation

    def open_active(self, envelope: RouteEnvelope) -> tuple[int, int]:
        if self._active_keys is None:
            raise PermissionError("active route keys are unavailable")
        aad = hashlib.sha256(envelope.route_ciphertext.encode("ascii")).digest()
        dek = _unwrap_dek(
            envelope.active_wrapped_dek,
            self._active_keys,
            domain=b"hulagu.active-route-wrap.v1",
            aad=aad,
        )
        return self._open_payload(envelope.route_ciphertext, dek)

    def open_deletion(self, projection: str) -> tuple[int, int]:
        if self._deletion_keys is None:
            raise PermissionError("deletion route keys are unavailable")
        try:
            value = json.loads(projection)
            if set(value) != {"schema_version", "route_ciphertext", "deletion_wrapped_dek"}:
                raise ValueError("unexpected deletion route fields")
            if value["schema_version"] != "DeletionRouteEnvelope/v1":
                raise ValueError("unexpected deletion route version")
            route_ciphertext = str(value["route_ciphertext"])
            wrapped_dek = str(value["deletion_wrapped_dek"])
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise ValueError("invalid deletion route projection") from exc
        aad = hashlib.sha256(route_ciphertext.encode("ascii")).digest()
        dek = _unwrap_dek(
            wrapped_dek,
            self._deletion_keys,
            domain=b"hulagu.deletion-route-wrap.v1",
            aad=aad,
        )
        return self._open_payload(route_ciphertext, dek)


    def claim_token_material(self, deletion_id: str) -> bytes:
        UUID(deletion_id)
        if self._deletion_keys is None:
            raise PermissionError("deletion route keys are unavailable")
        ordered_keys = b"".join(
            version.to_bytes(4, "big") + key
            for version, key in sorted(self._deletion_keys.items())
        )
        return hmac.new(
            ordered_keys,
            b"hulagu.deletion.claim-source.v1\0" + deletion_id.encode(),
            hashlib.sha256,
        ).digest()


@dataclass(frozen=True, slots=True)
class FixedCompletionRequest:
    deletion_id: str
    route: int
    route_generation: int
    template_version: str


@dataclass(frozen=True, slots=True)
class RouteBindingRecord:
    bot_id: int
    route_generation: int
    key_version: int
    binding_digest: str


def route_binding_digest(key: bytes, *, bot_id: int, route: int, generation: int) -> str:
    if len(key) < 16 or bot_id < 1 or route < 1 or generation < 1:
        raise ValueError("invalid route binding authority")
    value = f"hulagu.route-binding.v1\0{bot_id}\0{route}\0{generation}".encode("ascii")
    return hmac.new(key, value, hashlib.sha256).hexdigest()


class RouteBindingValidator:
    """App-side validator backed only by a bounded deletion-binding lookup."""

    def __init__(
        self,
        keys: Mapping[int, bytes],
        *,
        lookup: Callable[[str], RouteBindingRecord | None],
    ) -> None:
        validated = _validate_keys(keys)
        if validated is None:
            raise ValueError("route binding keys are required")
        self._keys = validated
        self._lookup = lookup

    def validate(self, request: FixedCompletionRequest) -> None:
        try:
            UUID(request.deletion_id)
        except ValueError as exc:
            raise PermissionError("invalid deletion binding authority") from exc
        if (
            request.route < 1
            or request.route_generation < 1
            or request.template_version != "deletion-complete-v1"
        ):
            raise PermissionError("invalid deletion binding authority")
        record = self._lookup(request.deletion_id)
        if record is None or record.route_generation != request.route_generation:
            raise PermissionError("deletion route binding validation failed")
        key = self._keys.get(record.key_version)
        if key is None:
            raise PermissionError("deletion route binding key is unavailable")
        expected = route_binding_digest(
            key,
            bot_id=record.bot_id,
            route=request.route,
            generation=request.route_generation,
        )
        if not hmac.compare_digest(expected, record.binding_digest):
            raise PermissionError("deletion route binding validation failed")


def _peer_uid(connection: socket.socket) -> int:
    if hasattr(connection, "getpeereid"):
        uid, _gid = connection.getpeereid()
        return int(uid)
    if hasattr(socket, "SO_PEERCRED"):
        packed = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", packed)
        return int(uid)
    if hasattr(socket, "LOCAL_PEERCRED"):
        packed = connection.getsockopt(0, socket.LOCAL_PEERCRED, 12)
        _version, uid, _groups = struct.unpack_from("@IIh", packed)
        return int(uid)
    raise PermissionError("Unix peer credentials are unavailable")


def _receive_line(connection: socket.socket, *, maximum: int = 4096) -> bytes:
    value = bytearray()
    while len(value) <= maximum:
        chunk = connection.recv(min(1024, maximum + 1 - len(value)))
        if not chunk:
            break
        value.extend(chunk)
        if b"\n" in chunk:
            break
    if len(value) > maximum or not value.endswith(b"\n") or b"\n" in value[:-1]:
        raise ValueError("invalid bounded deletion request")
    return bytes(value[:-1])


class UnixDeletionCompletionServer:
    """App-owned fixed operation over an authenticated local Unix socket."""

    def __init__(
        self,
        socket_path: Path,
        *,
        allowed_peer_uids: set[int],
        validator: RouteBindingValidator,
        send_fixed: Callable[[FixedCompletionRequest], None],
    ) -> None:
        if not socket_path.is_absolute() or not allowed_peer_uids:
            raise ValueError("invalid Unix deletion boundary")
        self._path = socket_path
        self._allowed_peer_uids = frozenset(allowed_peer_uids)
        self._validator = validator
        self._send_fixed = send_fixed
        self._listener: socket.socket | None = None

    def bind(self) -> None:
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._path.exists():
            metadata = self._path.lstat()
            if not stat.S_ISSOCK(metadata.st_mode):
                raise ValueError("refusing to replace non-socket boundary path")
            self._path.unlink()
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self._path))
            os.chmod(self._path, 0o600)
            listener.listen(4)
        except BaseException:
            listener.close()
            raise
        self._listener = listener

    def serve_once(self) -> None:
        if self._listener is None:
            raise RuntimeError("Unix deletion boundary is not bound")
        connection, _address = self._listener.accept()
        with connection:
            try:
                if _peer_uid(connection) not in self._allowed_peer_uids:
                    raise PermissionError("Unix deletion peer is not authorized")
                value = json.loads(_receive_line(connection))
                if set(value) != {"deletion_id", "route", "route_generation", "template_version"}:
                    raise ValueError("invalid typed deletion request")
                request = FixedCompletionRequest(
                    deletion_id=str(value["deletion_id"]),
                    route=int(value["route"]),
                    route_generation=int(value["route_generation"]),
                    template_version=str(value["template_version"]),
                )
                self._validator.validate(request)
                self._send_fixed(request)
                response = {"status": "sent"}
            except PermissionError as exc:
                response = {"status": "rejected", "error": str(exc)}
            except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, RuntimeError):
                response = {"status": "failed", "error": "invalid typed deletion request"}
            connection.sendall(json.dumps(response, sort_keys=True, separators=(",", ":")).encode() + b"\n")

    def close(self) -> None:
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        if self._path.exists() and stat.S_ISSOCK(self._path.lstat().st_mode):
            self._path.unlink()


class UnixDeletionCompletionClient:
    """Dispatcher-side client exposing only the fixed completion operation."""

    def __init__(self, socket_path: Path, *, timeout_seconds: float = 5.0) -> None:
        if not socket_path.is_absolute() or timeout_seconds <= 0:
            raise ValueError("invalid Unix deletion client")
        self._path = socket_path
        self._timeout = timeout_seconds

    def send_deletion_completion(self, request: FixedCompletionRequest) -> str:
        value = {
            "deletion_id": request.deletion_id,
            "route": request.route,
            "route_generation": request.route_generation,
            "template_version": request.template_version,
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self._timeout)
            connection.connect(str(self._path))
            connection.sendall(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")
            response = json.loads(_receive_line(connection))
        if response.get("status") == "sent":
            return "sent"
        if response.get("status") == "rejected":
            raise PermissionError(str(response.get("error", "deletion completion rejected")))
        raise RuntimeError("deletion completion failed")


_AMBIGUOUS_DELIVERY_CLAIM = "hulagu.delivery.claim.ambiguous.v1"


class PostgresDeletionDeliveryStore:
    """Frozen-0013 adapter for the hulagu_deletion role's two bounded functions."""

    def __init__(
        self,
        dsn: str,
        *,
        connect: Callable[[str], Any] | None = None,
        token_source: Callable[[str], bytes] | None = None,
        tenants_root: Path | None = None,
    ) -> None:
        if not dsn or "host=" not in dsn:
            raise ValueError("a Unix-socket PostgreSQL DSN is required")
        host = dsn.split("host=", 1)[1].split()[0].strip("'\"")
        if not host.startswith("/"):
            raise ValueError("deletion delivery PostgreSQL must use a Unix socket")
        self._dsn = dsn
        self._connect_override = connect
        self._token_source = token_source or (lambda _deletion_id: os.urandom(32))
        self._tenants_root = tenants_root

    def _connect(self) -> Any:
        if self._connect_override is not None:
            return self._connect_override(self._dsn)
        try:
            psycopg = importlib.import_module("psycopg")
        except ImportError as exc:
            raise RuntimeError("psycopg is required for PostgreSQL deletion delivery") from exc
        return psycopg.connect(self._dsn)

    @staticmethod
    def _database_text(value: object) -> str:
        if isinstance(value, bytes):
            return value.decode("ascii")
        return str(value)

    @staticmethod
    def _require_deletion_role(cursor: Any) -> None:
        cursor.execute("SELECT current_user")
        row = cursor.fetchone()
        if row is None or PostgresDeletionDeliveryStore._database_text(row[0]) != "hulagu_deletion":
            raise PermissionError("PostgreSQL connection is not the hulagu_deletion role")

    def claim_projection(self, deletion_id: str) -> set[str]:
        try:
            UUID(deletion_id)
        except ValueError:
            return set()
        return {"deletion_id", "encrypted_route"}

    def claim(self, deletion_id: str, *, now: int) -> str | None:
        del now
        UUID(deletion_id)
        token_material = self._token_source(deletion_id)
        if len(token_material) < 16:
            raise ValueError("invalid deletion delivery token source")
        erasure_token = base64.urlsafe_b64encode(
            hmac.new(token_material, b"hulagu.deletion.erasure.v1\0" + deletion_id.encode(), hashlib.sha256).digest()
        ).decode("ascii")
        token_text = base64.urlsafe_b64encode(
            hmac.new(token_material, b"hulagu.deletion.delivery.v1\0" + deletion_id.encode(), hashlib.sha256).digest()
        ).decode("ascii")
        if self._tenants_root is not None:
            erasure_token_hash = hashlib.sha256(erasure_token.encode("ascii")).hexdigest()
            with self._connect() as connection, connection.cursor() as cursor:
                self._require_deletion_role(cursor)
                cursor.execute(
                    "SELECT hulagu_api.claim_deletion_erasure(%s::uuid,%s)",
                    (deletion_id, erasure_token_hash),
                )
                erasure_row = cursor.fetchone()
            if erasure_row is not None and erasure_row[0] is not None:
                erase_tenant_directory(self._tenants_root, self._database_text(erasure_row[0]))
                with self._connect() as connection, connection.cursor() as cursor:
                    self._require_deletion_role(cursor)
                    cursor.execute(
                        "SELECT hulagu_api.complete_deletion_erasure(%s::uuid,%s)",
                        (deletion_id, erasure_token),
                    )
                    completed = cursor.fetchone()
                if completed is None or completed[0] is not True:
                    raise PermissionError("deletion erasure completion was refused")
        token_hash = hashlib.sha256(token_text.encode("ascii")).hexdigest()
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_deletion_role(cursor)
            cursor.execute(
                "SELECT hulagu_api.claim_deletion_delivery(%s::uuid,%s)",
                (deletion_id, token_hash),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            return None
        try:
            claim = json.loads(self._database_text(row[0]))
        except json.JSONDecodeError as exc:
            raise RuntimeError("invalid deletion delivery claim projection") from exc
        if claim == {"status": "ambiguous"}:
            return _AMBIGUOUS_DELIVERY_CLAIM
        if set(claim) != {"status", "encrypted_route"} or claim.get("status") != "claimed":
            raise RuntimeError("invalid deletion delivery claim projection")
        projection = claim.get("encrypted_route")
        if not isinstance(projection, str) or not projection:
            raise RuntimeError("invalid deletion delivery claim projection")
        return projection

    def finalize(self, deletion_id: str, outcome: str) -> str:
        if outcome not in {"delivered", "delivery_unknown", "failed", "expired"}:
            raise ValueError("invalid deletion delivery outcome")
        existing = self.outcome(deletion_id)
        if existing is not None:
            return existing
        token_material = self._token_source(deletion_id)
        if len(token_material) < 16:
            raise ValueError("invalid deletion delivery token source")
        token = base64.urlsafe_b64encode(
            hmac.new(token_material, b"hulagu.deletion.delivery.v1\0" + deletion_id.encode(), hashlib.sha256).digest()
        ).decode("ascii")
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_deletion_role(cursor)
            cursor.execute(
                "SELECT hulagu_api.complete_deletion_delivery(%s::uuid,%s,%s)",
                (deletion_id, token, outcome),
            )
            row = cursor.fetchone()
        terminal = None if row is None or row[0] is None else self._database_text(row[0])
        if terminal not in {"delivered", "delivery_unknown", "failed", "expired"}:
            raise PermissionError("deletion delivery finalization was refused")
        return terminal

    def outcome(self, deletion_id: str) -> str | None:
        UUID(deletion_id)
        with self._connect() as connection, connection.cursor() as cursor:
            self._require_deletion_role(cursor)
            cursor.execute(
                "SELECT hulagu_api.deletion_delivery_outcome(%s::uuid)",
                (deletion_id,),
            )
            row = cursor.fetchone()
        return None if row is None or row[0] is None else self._database_text(row[0])


class MemoryDeletionDeliveryStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, object]] = {}

    def enqueue(self, deletion_id: str, encrypted_route: str, *, expires_at: int) -> None:
        self._rows[deletion_id] = {
            "encrypted_route": encrypted_route,
            "route_digest": hashlib.sha256(encrypted_route.encode()).hexdigest(),
            "expires_at": expires_at,
            "state": "pending",
            "outcome": None,
        }

    def claim_projection(self, deletion_id: str) -> set[str]:
        if deletion_id not in self._rows:
            return set()
        return {"deletion_id", "encrypted_route"}

    def claim(self, deletion_id: str, *, now: int) -> str | None:
        row = self._rows.get(deletion_id)
        if row is None or row["state"] != "pending":
            return None
        expires_at = row["expires_at"]
        if not isinstance(expires_at, int):
            raise TypeError("invalid deletion delivery state")
        if now > expires_at:
            row["state"] = "terminal"
            row["outcome"] = "expired"
            return None
        envelope = str(row["encrypted_route"])
        if not hmac.compare_digest(str(row["route_digest"]), hashlib.sha256(envelope.encode()).hexdigest()):
            row["state"] = "terminal"
            row["outcome"] = "failed"
            return None
        row["state"] = "claimed"
        return envelope

    def finalize(self, deletion_id: str, outcome: str) -> str:
        row = self._rows[deletion_id]
        if row["state"] == "terminal":
            return str(row["outcome"])
        row["state"] = "terminal"
        row["outcome"] = outcome
        row["encrypted_route"] = None
        return outcome

    def outcome(self, deletion_id: str) -> str | None:
        row = self._rows.get(deletion_id)
        return None if row is None or row["outcome"] is None else str(row["outcome"])

    def substitute_ciphertext(self, deletion_id: str, encrypted_route: str) -> None:
        self._rows[deletion_id]["encrypted_route"] = encrypted_route


class DeletionDeliveryStore(Protocol):
    def claim(self, deletion_id: str, *, now: int) -> str | None: ...

    def finalize(self, deletion_id: str, outcome: str) -> str: ...

    def outcome(self, deletion_id: str) -> str | None: ...


class DeletionDispatcher:
    """Owns deletion-route keys but neither tenant authority nor Telegram credentials."""

    def __init__(
        self,
        store: DeletionDeliveryStore,
        route_keys: RouteEnvelopeKeys,
        send_completion: Callable[[FixedCompletionRequest], object],
        *,
        clock: Callable[[], int],
    ) -> None:
        self._store = store
        self._route_keys = route_keys
        self._send_completion = send_completion
        self._clock = clock

    def dispatch(self, deletion_id: str) -> str:
        existing = self._store.outcome(deletion_id)
        if existing is not None:
            return existing
        claimed = self._store.claim(deletion_id, now=self._clock())
        if claimed is None:
            return self._store.outcome(deletion_id) or "failed"
        if claimed == _AMBIGUOUS_DELIVERY_CLAIM:
            return self._store.finalize(deletion_id, "delivery_unknown")
        try:
            route, generation = self._route_keys.open_deletion(claimed)
            self._send_completion(FixedCompletionRequest(deletion_id, route, generation, "deletion-complete-v1"))
        except TimeoutError:
            return self._store.finalize(deletion_id, "delivery_unknown")
        except (PermissionError, RuntimeError, ValueError):
            return self._store.finalize(deletion_id, "failed")
        return self._store.finalize(deletion_id, "delivered")


def _read_private_file(path_text: str) -> bytes:
    path = Path(path_text)
    if not path.is_absolute():
        raise ValueError("runtime authority files must use absolute paths")
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
        raise PermissionError("runtime authority file must be a private regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        if os.fstat(descriptor).st_ino != metadata.st_ino:
            raise PermissionError("runtime authority file changed during open")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 65536):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _load_deletion_keys(path_text: str) -> dict[int, bytes]:
    try:
        value = json.loads(_read_private_file(path_text))
        keys = value["keys"]
        if not isinstance(keys, dict):
            raise TypeError
        decoded = {int(version): bytes.fromhex(key_hex) for version, key_hex in keys.items()}
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid deletion key file") from exc
    validated = _validate_keys(decoded)
    if validated is None:
        raise ValueError("invalid deletion key file")
    return validated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hulagu-deletion-dispatcher")
    parser.add_argument("--postgres-dsn-file", required=True)
    parser.add_argument("--deletion-key-file", required=True)
    parser.add_argument("--app-socket", type=Path, required=True)
    parser.add_argument("--tenants-root", type=Path, required=True)
    parser.add_argument("--deletion-id", required=True)
    arguments = parser.parse_args(argv)
    dsn = _read_private_file(arguments.postgres_dsn_file).decode("utf-8").strip()
    keys = RouteEnvelopeKeys.for_deletion(_load_deletion_keys(arguments.deletion_key_file))
    store = PostgresDeletionDeliveryStore(
        dsn,
        tenants_root=arguments.tenants_root,
        token_source=keys.claim_token_material,
    )
    client = UnixDeletionCompletionClient(arguments.app_socket)
    dispatcher = DeletionDispatcher(
        store,
        keys,
        client.send_deletion_completion,
        clock=lambda: int(time.time()),
    )
    outcome = dispatcher.dispatch(arguments.deletion_id)
    return 0 if outcome == "delivered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
