"""LLM boundary for Kublai v4.

This module centralizes model defaults, retries, structured-output validation,
and privacy checks. It does not silently fall through to an external provider:
callers must either configure a provider later or supply a transport in tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
from typing import Any, Awaitable, Callable

from .context_bundle import ContextBundle
from .sanitizer import PrivacyBoundaryError, Sanitizer, SanitizerContext


class LlmError(Exception):
    """Base LLM exception."""


class RateLimitError(LlmError):
    pass


class RefusedError(LlmError):
    pass


class MalformedError(LlmError):
    pass


class LlmTimeoutError(LlmError):
    pass


class ContextOverflowError(LlmError):
    pass


class MissingProviderError(LlmError):
    pass


MODEL_DEFAULTS = {
    "ask": "claude-opus-4-7",
    "ingest": "claude-opus-4-7",
    "research_lens": "claude-opus-4-7",
    "research_synthesis": "claude-opus-4-7",
    "process_inbox": "claude-opus-4-7",
    "connect": "claude-opus-4-7",
    "brief": "claude-opus-4-7",
    "write": "claude-opus-4-7",
}

Transport = Callable[..., str | Awaitable[str]]


def model_for(command: str) -> str:
    return MODEL_DEFAULTS.get(command, MODEL_DEFAULTS["ask"])


def ensure_external_safe(bundle: ContextBundle, *, destination: str) -> None:
    if destination != "external":
        return
    if bundle.privacy_class != "public":
        raise PrivacyBoundaryError(
            f"refusing external LLM call with {bundle.privacy_class} context"
        )


async def llm_call(
    *,
    command: str,
    system: str = "",
    user: str | None = None,
    bundle: ContextBundle | None = None,
    destination: str = "external",
    max_tokens: int = 4096,
    timeout_seconds: int = 120,
    transport: Transport | None = None,
) -> str:
    sanitizer = Sanitizer()
    if bundle is not None:
        ensure_external_safe(bundle, destination=destination)
        user = bundle.render()
    if user is None:
        raise MalformedError("llm_call requires user text or ContextBundle")
    user, findings = sanitizer.scrub(
        user,
        target_class="public" if destination == "external" else "private",
        context=SanitizerContext.LLM_PROMPT,
    )
    if findings and destination == "external":
        raise PrivacyBoundaryError(f"refusing external LLM call after sanitizer findings: {findings}")

    request = {
        "command": command,
        "model": model_for(command),
        "system": system,
        "user": user,
        "max_tokens": max_tokens,
    }
    _append_request_log(request)

    if transport is None:
        mock_response = os.getenv("KUBLAI_LLM_MOCK_RESPONSE")
        if mock_response is not None:
            return mock_response
        raise MissingProviderError("no LLM transport configured")

    try:
        result = transport(**request)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, timeout=timeout_seconds)
        return await asyncio.wait_for(asyncio.to_thread(lambda: result), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise LlmTimeoutError(str(exc)) from exc


async def llm_call_structured(
    *,
    command: str,
    system: str = "",
    user: str | None = None,
    bundle: ContextBundle | None = None,
    schema: dict[str, Any],
    max_retries: int = 2,
    validator: Callable[[dict[str, Any]], None] | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    prompt = user
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        raw = await llm_call(
            command=command,
            system=system,
            user=prompt,
            bundle=bundle if attempt == 0 else None,
            transport=transport,
        )
        try:
            parsed = json.loads(raw)
            _validate_schema_shape(parsed, schema)
            if validator:
                validator(parsed)
            return parsed
        except Exception as exc:
            last_error = exc
            prompt = (
                f"{user or (bundle.render() if bundle else '')}\n\n"
                f"Previous response was invalid: {exc}. Return only valid JSON matching the schema."
            )
    raise MalformedError(str(last_error))


async def llm_call_fresh_context(
    *,
    command: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    transport: Transport | None = None,
) -> str:
    return await llm_call(
        command=command,
        system=system,
        user=user,
        max_tokens=max_tokens,
        transport=transport,
    )


def _validate_schema_shape(parsed: dict[str, Any], schema: dict[str, Any]) -> None:
    required = schema.get("required") or []
    missing = [key for key in required if key not in parsed]
    if missing:
        raise MalformedError(f"missing required keys: {missing}")


def _append_request_log(request: dict[str, Any]) -> None:
    log_path = os.getenv("KUBLAI_LLM_REQUEST_LOG")
    if not log_path:
        return
    safe_request = {
        "command": request.get("command"),
        "model": request.get("model"),
        "max_tokens": request.get("max_tokens"),
        "system_sha256": hashlib.sha256(str(request.get("system") or "").encode("utf-8")).hexdigest(),
        "system_chars": len(str(request.get("system") or "")),
        "user_sha256": hashlib.sha256(str(request.get("user") or "").encode("utf-8")).hexdigest(),
        "user_chars": len(str(request.get("user") or "")),
    }
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_request, sort_keys=True) + "\n")
