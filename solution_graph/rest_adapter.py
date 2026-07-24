from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .schema_runtime import ContractError, loads_strict_json, validate_contract_schema
from .service import SolutionGraphService

_LOOPBACK_HOSTS = {"127.0.0.1"}
_MAX_BODY_BYTES = 1_048_576
_SIMULATE_ROUTE = re.compile(r"^/v1/plans/(?P<plan_id>plan_[0-9a-f]{20}):simulate$")


def _error(message: str, *, reason_code: str = "contract_invalid") -> dict[str, Any]:
    return {
        "schema": "ValidationResult/v1",
        "status": "invalid",
        "reason_codes": [reason_code],
        "detail": message[:512],
    }


def _headers(service: SolutionGraphService | None = None) -> dict[str, str]:
    result = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-KSG-Authority": "none",
        "X-KSG-Policy-Version": "solution-graph-policy/v0.2",
    }
    if service is not None:
        result["X-KSG-Registry-Snapshot"] = service.registry_snapshot
    return result


def _json_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def handle_rest_request(
    service: SolutionGraphService,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    *,
    content_type: str = "application/json",
    content_length: int | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    headers = _headers(service)
    if method != "POST":
        return 405, headers, _error("method not allowed", reason_code="method_not_allowed")
    if not _json_content_type(content_type):
        return 415, headers, _error("JSON content type is required", reason_code="unsupported_media_type")
    if content_length is not None and content_length > _MAX_BODY_BYTES:
        return 413, headers, _error("request body exceeds 1 MiB limit", reason_code="payload_too_large")
    payload = body if body is not None else {}
    try:
        if path == "/v1/objectives:resolve":
            return 200, headers, service.resolve(payload)
        match = _SIMULATE_ROUTE.fullmatch(path)
        if match:
            simulation = service.simulate(match.group("plan_id"), payload)
            return (200 if simulation["status"] == "pass" else 400), headers, simulation
        return 404, headers, _error("unknown route", reason_code="route_not_found")
    except (ContractError, KeyError, TypeError, ValueError) as exc:
        error = _error(str(exc))
        validate_contract_schema(error)
        return 400, headers, error


class SolutionGraphRESTHandler(BaseHTTPRequestHandler):
    server_version = "KurultaiSolutionGraphREST/0.3"

    @property
    def service(self) -> SolutionGraphService:
        return self.server.service  # type: ignore[attr-defined, no-any-return]

    def _emit(self, status: int, headers: dict[str, str], response: dict[str, Any]) -> None:
        data = json.dumps(response, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        self._emit(405, _headers(self.service), _error("method not allowed", reason_code="method_not_allowed"))

    def do_POST(self) -> None:  # noqa: N802
        content_type = self.headers.get("Content-Type")
        if not _json_content_type(content_type):
            self._emit(415, _headers(self.service), _error("JSON content type is required", reason_code="unsupported_media_type"))
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._emit(400, _headers(self.service), _error("invalid Content-Length"))
            return
        if size < 0 or size > _MAX_BODY_BYTES:
            self._emit(413, _headers(self.service), _error("request body exceeds 1 MiB limit", reason_code="payload_too_large"))
            return
        try:
            raw = self.rfile.read(size) if size else b"{}"
            body = loads_strict_json(raw)
            if not isinstance(body, dict):
                raise ContractError("request body must be a JSON object")
            self._emit(*handle_rest_request(
                self.service,
                "POST",
                self.path,
                body,
                content_type=content_type or "",
                content_length=size,
            ))
        except (ContractError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._emit(400, _headers(self.service), _error(str(exc)))

    def log_message(self, _format: str, *_args: object) -> None:
        return


class _SolutionGraphHTTPServer(ThreadingHTTPServer):
    service: SolutionGraphService


def make_rest_server(host: str, port: int, registry_root: Path | str) -> ThreadingHTTPServer:
    if host not in _LOOPBACK_HOSTS:
        raise ContractError("REST adapter server must bind to loopback only")
    server = _SolutionGraphHTTPServer((host, port), SolutionGraphRESTHandler)
    server.service = SolutionGraphService.from_registry_root(registry_root)
    return server


def parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(description="Loopback-only Solution Graph REST adapter")
    arg_parser.add_argument("--registry", required=True, type=Path)
    arg_parser.add_argument("--host", default="127.0.0.1")
    arg_parser.add_argument("--port", default=8765, type=int)
    arg_parser.add_argument("--self-test", action="store_true")
    return arg_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.self_test:
            service = SolutionGraphService.from_registry_root(args.registry)
            response = {
                "schema": "ValidationResult/v1",
                "status": "valid",
                "snapshot_id": service.registry_snapshot,
            }
            validate_contract_schema(response)
            print(json.dumps(response, ensure_ascii=False, sort_keys=True))
            return 0
        server = make_rest_server(args.host, args.port, args.registry)
    except ContractError as exc:
        print(json.dumps(_error(str(exc)), ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps({
        "schema": "ValidationResult/v1",
        "status": "valid",
        "snapshot_id": server.service.registry_snapshot,  # type: ignore[attr-defined]
    }, sort_keys=True))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
