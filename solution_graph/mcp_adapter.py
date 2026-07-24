from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .schema_runtime import ContractError, loads_strict_json, validate_contract_schema
from .service import SolutionGraphService

_TOOL_NAMES = (
    "solution_graph.resolve_objective",
    "solution_graph.simulate_plan",
)


def _validation_error(message: str, *, reason_code: str = "contract_invalid") -> dict[str, Any]:
    result = {
        "schema": "ValidationResult/v1",
        "status": "invalid",
        "reason_codes": [reason_code],
        "detail": message[:512],
    }
    validate_contract_schema(result)
    return result


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        },
    }


def tool_definitions() -> list[dict[str, Any]]:
    return [
        _tool(
            "solution_graph.resolve_objective",
            "Read-only recommendation; grants no execution authority. Resolve an inline objective against the startup-bound registry.",
            {
                "objective": {"type": "object"},
                "environment": {"type": "object"},
            },
            ["objective", "environment"],
        ),
        _tool(
            "solution_graph.simulate_plan",
            "Read-only recommendation; grants no execution authority. Simulate an inline plan by deterministic replay.",
            {
                "plan": {"type": "object"},
                "objective": {"type": "object"},
                "environment": {"type": "object"},
            },
            ["plan", "objective", "environment"],
        ),
    ]


def _result(request_id: Any, value: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message[:512]}}


def _content(document: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(document, ensure_ascii=False, sort_keys=True)}],
        "isError": is_error,
    }


def handle_mcp_request(service: SolutionGraphService, request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _result(request_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "kurultai-solution-graph", "version": "0.3.0"},
        })
    if method == "tools/list":
        return _result(request_id, {"tools": tool_definitions()})
    if method == "tools/call":
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _error(request_id, -32602, "params must be an object")
        name = params.get("name")
        if name not in _TOOL_NAMES:
            return _error(request_id, -32602, f"unsupported tool: {name}")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "arguments must be an object")
        try:
            if name == "solution_graph.resolve_objective":
                return _result(request_id, _content(service.resolve(arguments)))
            plan = arguments.get("plan")
            if not isinstance(plan, dict) or not isinstance(plan.get("plan_id"), str):
                raise ContractError("plan.plan_id is required")
            return _result(request_id, _content(service.simulate(plan["plan_id"], arguments)))
        except (ContractError, KeyError, TypeError, ValueError) as exc:
            return _result(request_id, _content(_validation_error(str(exc)), is_error=True))
    return _error(request_id, -32601, f"unsupported method: {method}")


def run_stdio(registry_root: Path | str) -> int:
    service = SolutionGraphService.from_registry_root(registry_root)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = loads_strict_json(line)
            if not isinstance(request, dict):
                raise ContractError("request must be an object")
            response = handle_mcp_request(service, request)
        except (ContractError, json.JSONDecodeError) as exc:
            response = _error(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            sys.stdout.flush()
    return 0


def parser() -> argparse.ArgumentParser:
    arg_parser = argparse.ArgumentParser(description="Solution Graph MCP stdio server")
    arg_parser.add_argument("--registry", required=True, type=Path)
    return arg_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return run_stdio(args.registry)
    except ContractError as exc:
        sys.stdout.write(json.dumps(_error(None, -32000, str(exc)), sort_keys=True) + "\n")
        sys.stdout.flush()
        return 2
