"""Public-only HTTP gateway for Kublai brain v4."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import time
import uuid
from ipaddress import ip_address
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .v4 import V4PrivacyError, V4WorkflowError


def sign_request(secret: str, method: str, path: str, body: bytes, timestamp: str) -> str:
    message = b"\n".join([method.upper().encode(), path.encode(), body, timestamp.encode()])
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def openapi_spec() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Kublai Brain Public Gateway", "version": "4.0"},
        "paths": {
            "/health": {"get": {"summary": "Gateway and brain-service health"}},
            "/api/wiki/search": {"get": {"summary": "Search explicit-public wiki index"}},
            "/api/wiki/pages": {"get": {"summary": "List or fetch explicit-public wiki pages"}},
            "/api/tags": {"get": {"summary": "List explicit-public tags"}},
            "/api/ask": {"post": {"summary": "Public-context question answering"}},
            "/api/capture": {"post": {"summary": "Capture proposal; private flags rejected"}},
            "/api/ingest/dry-run": {"post": {"summary": "Public-safe ingest dry run"}},
            "/api/publish/dry-run": {"post": {"summary": "Public publish dry run"}},
        },
    }


def contains_private_request(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {"include_private", "private", "hard_private"} and bool(item):
                return True
            if key_l == "privacy_scope" and item != "public":
                return True
            if contains_private_request(item):
                return True
    if isinstance(value, list):
        return any(contains_private_request(item) for item in value)
    if isinstance(value, str) and "hard-private/" in value:
        return True
    return False


def is_loopback_host(host: str) -> bool:
    if host in {"localhost", "::1"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


class PublicGatewayHandler(BaseHTTPRequestHandler):
    service: Any = None
    hmac_secret: str | None = None
    server_version = "KublaiBrainGateway/4.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        request_id = self.headers.get("X-Request-ID") or f"gw-{uuid.uuid4().hex}"
        try:
            parsed = urlparse(self.path)
            params = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if parsed.path == "/health":
                self._write_json({"ok": True, "request_id": request_id, "gateway": "public", "brain": self.service.health()})
                return
            if parsed.path == "/openapi.json":
                self._write_json(openapi_spec())
                return
            self._require_auth("GET", parsed.path, b"")
            if parsed.path == "/api/wiki/search":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.public_search(query=params.get("q", ""), limit=int(params.get("limit", 10)))})
                return
            if parsed.path == "/api/wiki/pages":
                if "rel_path" in params:
                    self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.public_get(rel_path=params["rel_path"])})
                else:
                    self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.public_pages(limit=int(params.get("limit", 100)))})
                return
            if parsed.path == "/api/tags":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.public_tags(limit=int(params.get("limit", 200)))})
                return
            self._write_error(HTTPStatus.NOT_FOUND, "not_found", "route not found", request_id)
        except V4PrivacyError as exc:
            self._write_error(HTTPStatus.FORBIDDEN, "privacy_boundary", str(exc), request_id)
        except Exception as exc:
            self._write_error(HTTPStatus.BAD_REQUEST, type(exc).__name__, str(exc), request_id)

    def do_POST(self) -> None:
        request_id = self.headers.get("X-Request-ID") or f"gw-{uuid.uuid4().hex}"
        body = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
        try:
            parsed = urlparse(self.path)
            self._require_auth("POST", parsed.path, body)
            payload = json.loads(body.decode("utf-8") or "{}")
            if contains_private_request(payload):
                raise V4PrivacyError("HTTPS gateway rejects private and hard-private requests")
            if parsed.path == "/api/ask":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.ask(request_id=request_id, **payload)})
                return
            if parsed.path == "/api/capture":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.capture_dry_run(request_id=request_id, **payload)})
                return
            if parsed.path == "/api/ingest/dry-run":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.ingest_dry_run(request_id=request_id, **payload)})
                return
            if parsed.path == "/api/publish/dry-run":
                self._write_json({"ok": True, "request_id": request_id, "result": self.service.v4.publish_dry_run(request_id=request_id, **payload)})
                return
            self._write_error(HTTPStatus.NOT_FOUND, "not_found", "route not found", request_id)
        except V4PrivacyError as exc:
            self._write_error(HTTPStatus.FORBIDDEN, "privacy_boundary", str(exc), request_id)
        except (V4WorkflowError, ValueError, json.JSONDecodeError) as exc:
            self._write_error(HTTPStatus.BAD_REQUEST, type(exc).__name__, str(exc), request_id)
        except Exception as exc:
            self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, type(exc).__name__, str(exc), request_id)

    def _require_auth(self, method: str, path: str, body: bytes) -> None:
        if not self.hmac_secret:
            return
        timestamp = self.headers.get("X-Kublai-Timestamp") or ""
        signature = self.headers.get("X-Kublai-Signature") or ""
        if not timestamp or not signature:
            raise V4PrivacyError("missing HMAC authentication")
        try:
            if abs(time.time() - float(timestamp)) > 300:
                raise V4PrivacyError("stale HMAC timestamp")
        except ValueError as exc:
            raise V4PrivacyError("invalid HMAC timestamp") from exc
        expected = sign_request(self.hmac_secret, method, path, body, timestamp)
        if not hmac.compare_digest(expected, signature):
            raise V4PrivacyError("invalid HMAC signature")

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_error(self, status: HTTPStatus, code: str, message: str, request_id: str) -> None:
        self._write_json({"ok": False, "request_id": request_id, "error": {"code": code, "message": message}}, status)


def serve_gateway(
    service: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    secret: str | None = None,
    certfile: str | None = None,
    keyfile: str | None = None,
) -> ThreadingHTTPServer:
    secret = secret if secret is not None else os.getenv("KUBLAI_GATEWAY_HMAC_SECRET")
    if not secret and not is_loopback_host(host):
        raise ValueError("brain public gateway requires HMAC secret for non-loopback bind")

    class Handler(PublicGatewayHandler):
        pass

    Handler.service = service
    Handler.hmac_secret = secret
    server = ThreadingHTTPServer((host, port), Handler)
    if certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    return server
