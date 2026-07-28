"""Identity, callback-authority, and encrypted return-route primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True, slots=True)
class IdentityDigest:
    version: int
    value: str


class IdentityDigestKeys:
    def __init__(self, keys: dict[int, bytes], active_version: int) -> None:
        self._keys = dict(keys)
        self._active = active_version
        self._revoked: set[int] = set()
        self._require_active()

    def _require_active(self) -> bytes:
        if self._active in self._revoked or self._active not in self._keys:
            raise ValueError("missing active identity key")
        return self._keys[self._active]

    def activate(self, version: int) -> None:
        if version in self._revoked or version not in self._keys:
            raise ValueError("unknown identity key")
        self._active = version

    def revoke(self, version: int) -> None:
        self._revoked.add(version)

    def digest(self, bot_id: int, actor_id: int) -> IdentityDigest:
        payload = f"hulagu.telegram-principal.v1\0{self._active}\0{bot_id}\0{actor_id}".encode()
        return IdentityDigest(self._active, hmac.new(self._require_active(), payload, hashlib.sha256).hexdigest())

    def candidates(self, bot_id: int, actor_id: int) -> tuple[IdentityDigest, ...]:
        """Return active then overlapping non-revoked digests for binding resolution."""
        versions = (self._active, *(version for version in sorted(self._keys) if version != self._active))
        candidates: list[IdentityDigest] = []
        for version in versions:
            if version in self._revoked:
                continue
            payload = f"hulagu.telegram-principal.v1\0{version}\0{bot_id}\0{actor_id}".encode()
            candidates.append(IdentityDigest(version, hmac.new(self._keys[version], payload, hashlib.sha256).hexdigest()))
        return tuple(candidates)

    def matches(self, stored: IdentityDigest, bot_id: int, actor_id: int) -> bool:
        if stored.version in self._revoked or stored.version not in self._keys:
            return False
        payload = f"hulagu.telegram-principal.v1\0{stored.version}\0{bot_id}\0{actor_id}".encode()
        candidate = hmac.new(self._keys[stored.version], payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(stored.value, candidate)


@dataclass(frozen=True, slots=True)
class CallbackAction:
    action: str
    enrollment_id: str
    nonce: str
    actor_id: int
    expires_at: int


class CallbackCodec:
    def __init__(self, key: bytes) -> None:
        if len(key) < 8:
            raise ValueError("callback key is too short")
        self._key = key

    def issue(self, action: CallbackAction) -> str:
        body = json.dumps({"a": action.action, "e": action.enrollment_id, "n": action.nonce, "u": action.actor_id, "x": action.expires_at}, separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(self._key, b"hulagu.callback.v1\0" + body, hashlib.sha256).digest()[:16]
        return f"v1.{_b64(body)}.{_b64(signature)}"

    def verify(self, token: str, *, actor_id: int, now: int) -> CallbackAction:
        try:
            version, body_text, signature_text = token.split(".")
            body = _unb64(body_text)
            signature = _unb64(signature_text)
            payload = json.loads(body)
        except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid callback") from exc
        expected = hmac.new(self._key, b"hulagu.callback.v1\0" + body, hashlib.sha256).digest()[:16]
        if version != "v1" or not hmac.compare_digest(signature, expected) or not isinstance(payload, dict):
            raise ValueError("invalid callback")
        try:
            action = CallbackAction(str(payload["a"]), str(payload["e"]), str(payload["n"]), int(payload["u"]), int(payload["x"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid callback") from exc
        if action.actor_id != actor_id or now > action.expires_at:
            raise ValueError("invalid callback")
        return action


@dataclass(frozen=True, slots=True)
class SealedRoute:
    active_key_version: int
    route_generation: int
    ciphertext: str
    active_wrapped_data_key: str
    binding_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "active_key_version": self.active_key_version,
            "route_generation": self.route_generation,
            "ciphertext": self.ciphertext,
            "active_wrapped_data_key": self.active_wrapped_data_key,
            "binding_digest": self.binding_digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> SealedRoute:
        if not isinstance(value, dict):
            raise TypeError("invalid sealed route")
        try:
            active_key_version = value["active_key_version"]
            route_generation = value["route_generation"]
            ciphertext = value["ciphertext"]
            active_wrapped_data_key = value["active_wrapped_data_key"]
            binding_digest = value["binding_digest"]
        except KeyError as exc:
            raise ValueError("invalid sealed route") from exc
        if (
            not isinstance(active_key_version, int)
            or isinstance(active_key_version, bool)
            or active_key_version < 1
            or not isinstance(route_generation, int)
            or isinstance(route_generation, bool)
            or route_generation < 1
            or not isinstance(ciphertext, str)
            or not ciphertext
            or not isinstance(active_wrapped_data_key, str)
            or not active_wrapped_data_key
            or not isinstance(binding_digest, str)
            or len(binding_digest) != 64
        ):
            raise ValueError("invalid sealed route")
        return cls(
            active_key_version,
            route_generation,
            ciphertext,
            active_wrapped_data_key,
            binding_digest,
        )


def _xor_stream(value: bytes, key: bytes, nonce: bytes, domain: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(value):
        output.extend(hashlib.sha256(key + nonce + domain + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(item ^ output[index] for index, item in enumerate(value))


class RouteKeys:
    """Versioned authenticated route sealing with explicit overlap and revocation."""

    def __init__(self, keys: dict[int, bytes], active_version: int, *, binding_key: bytes) -> None:
        self._keys = dict(keys)
        self._active = active_version
        if len(binding_key) < 16:
            raise ValueError("route binding key is too short")
        self._binding_key = binding_key
        self._revoked: set[int] = set()
        self._key(active_version)

    def _key(self, version: int) -> bytes:
        if version in self._revoked:
            raise ValueError("route key revoked")
        try:
            return self._keys[version]
        except KeyError as exc:
            raise ValueError("unknown route key") from exc

    def activate(self, version: int) -> None:
        self._key(version)
        self._active = version

    def revoke(self, version: int) -> None:
        self._revoked.add(version)

    def seal(self, bot_id: int, chat_id: int, *, generation: int) -> SealedRoute:
        if bot_id < 1 or chat_id < 1 or generation < 1:
            raise ValueError("invalid route authority")
        wrapping_key = self._key(self._active)
        data_key = secrets.token_bytes(32)
        route_nonce = secrets.token_bytes(16)
        plain = json.dumps(
            {"b": bot_id, "c": chat_id, "g": generation},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        cipher = _xor_stream(plain, data_key, route_nonce, b"hulagu.route.data.v1")
        route_tag = hmac.new(
            data_key,
            b"hulagu.route.data.v1\0" + route_nonce + cipher,
            hashlib.sha256,
        ).digest()
        wrap_nonce = secrets.token_bytes(16)
        wrapped_data_key = _xor_stream(data_key, wrapping_key, wrap_nonce, b"hulagu.route.wrap.v1")
        wrap_tag = hmac.new(
            wrapping_key,
            b"hulagu.route.wrap.v1\0" + wrap_nonce + wrapped_data_key,
            hashlib.sha256,
        ).digest()
        binding_payload = f"hulagu.route.binding.v1\0{bot_id}\0{chat_id}\0{generation}".encode()
        binding_digest = hmac.new(self._binding_key, binding_payload, hashlib.sha256).hexdigest()
        return SealedRoute(
            self._active,
            generation,
            _b64(route_nonce + cipher + route_tag),
            _b64(wrap_nonce + wrapped_data_key + wrap_tag),
            binding_digest,
        )

    def open(self, sealed: SealedRoute, *, expected_bot_id: int) -> tuple[int, int]:
        wrapping_key = self._key(sealed.active_key_version)
        wrapped = _unb64(sealed.active_wrapped_data_key)
        if len(wrapped) != 80:
            raise ValueError("invalid sealed route")
        wrap_nonce, wrapped_data_key, wrap_tag = wrapped[:16], wrapped[16:-32], wrapped[-32:]
        expected_wrap_tag = hmac.new(
            wrapping_key,
            b"hulagu.route.wrap.v1\0" + wrap_nonce + wrapped_data_key,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(wrap_tag, expected_wrap_tag):
            raise ValueError("invalid sealed route")
        data_key = _xor_stream(wrapped_data_key, wrapping_key, wrap_nonce, b"hulagu.route.wrap.v1")
        packed = _unb64(sealed.ciphertext)
        if len(packed) < 49:
            raise ValueError("invalid sealed route")
        route_nonce, cipher, route_tag = packed[:16], packed[16:-32], packed[-32:]
        expected_route_tag = hmac.new(
            data_key,
            b"hulagu.route.data.v1\0" + route_nonce + cipher,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(route_tag, expected_route_tag):
            raise ValueError("invalid sealed route")
        plain = _xor_stream(cipher, data_key, route_nonce, b"hulagu.route.data.v1")
        try:
            payload = json.loads(plain)
            bot_id, chat_id, generation = int(payload["b"]), int(payload["c"]), int(payload["g"])
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid sealed route") from exc
        if bot_id != expected_bot_id or generation != sealed.route_generation:
            raise ValueError("route bot mismatch")
        binding_payload = f"hulagu.route.binding.v1\0{bot_id}\0{chat_id}\0{generation}".encode()
        expected_binding = hmac.new(self._binding_key, binding_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sealed.binding_digest, expected_binding):
            raise ValueError("route binding mismatch")
        return chat_id, generation
