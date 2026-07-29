"""Fixture-only public-search adapter with pre-effect budget reservation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from .schemas import (
    BudgetExceeded,
    Candidate,
    ProviderOutcome,
    ProviderReceipt,
    SearchPlan,
    SearchResult,
)

_PROVIDER_COST_UNITS = 10
_MAX_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    outcome: ProviderOutcome
    payload: bytes | None = None

    @classmethod
    def success(cls, items: list[dict[str, object]]) -> ProviderAttempt:
        return cls(
            ProviderOutcome.SUCCEEDED,
            json.dumps({"schema_version": "FixtureProviderItems/v1", "items": items}, separators=(",", ":")).encode(),
        )

    @classmethod
    def raw(cls, payload: bytes) -> ProviderAttempt:
        return cls(ProviderOutcome.SUCCEEDED, payload)


class FixtureSearchProvider:
    """No network capability: returns only preloaded synthetic bytes."""

    def __init__(self, attempts: list[ProviderAttempt]) -> None:
        self._attempts = list(attempts)
        self.calls = 0
        self.observed_reservations: list[tuple[int, int]] = []

    def request(self, query: str, *, request_number: int, cost_units_reserved: int) -> ProviderAttempt:
        if not query or self.calls >= len(self._attempts):
            return ProviderAttempt(ProviderOutcome.FAILED)
        self.calls += 1
        self.observed_reservations.append((request_number, cost_units_reserved))
        return self._attempts[self.calls - 1]


class SearchCoordinator:
    def __init__(self, provider: FixtureSearchProvider, *, clock: Callable[[], int]) -> None:
        self._provider = provider
        self._clock = clock

    def run(self, plan: SearchPlan) -> SearchResult:
        if plan.provider != "fixture-public-search-adapter":
            raise ValueError("provider is not fixture-approved")
        started = self._clock()
        usage = plan.budgets.new_usage()
        receipts: list[ProviderReceipt] = []
        candidates: dict[str, Candidate] = {}
        query = plan.queries[0]
        while True:
            if self._clock() - started > plan.budgets.wall_seconds:
                raise BudgetExceeded(
                    "search wall-clock budget exhausted",
                    usage=usage,
                    receipts=tuple(receipts),
                )
            try:
                usage.reserve_provider(_PROVIDER_COST_UNITS)
            except BudgetExceeded as error:
                raise BudgetExceeded(str(error), usage=usage, receipts=tuple(receipts)) from None
            attempt = self._provider.request(
                query,
                request_number=usage.provider_requests_used,
                cost_units_reserved=usage.provider_cost_units_used,
            )
            digest = hashlib.sha256(attempt.payload).hexdigest() if attempt.payload is not None else None
            if attempt.outcome in {ProviderOutcome.AMBIGUOUS, ProviderOutcome.TIMEOUT}:
                receipts.append(ProviderReceipt("delivery_unknown", usage.provider_requests_used, _PROVIDER_COST_UNITS, digest))
                if attempt.outcome is ProviderOutcome.AMBIGUOUS:
                    continue
                return SearchResult(plan, (), tuple(receipts), usage)
            if attempt.outcome is not ProviderOutcome.SUCCEEDED or attempt.payload is None:
                receipts.append(ProviderReceipt("failed", usage.provider_requests_used, _PROVIDER_COST_UNITS, digest))
                return SearchResult(plan, (), tuple(receipts), usage)
            try:
                items = _validate_response(attempt.payload, plan.budgets.max_results_per_query)
                for item in items:
                    candidate = _candidate(item)
                    candidates.setdefault(candidate.normalized_url_hash, candidate)
                    if len(candidates) >= plan.budgets.max_candidates:
                        break
            except (TypeError, ValueError):
                receipts.append(ProviderReceipt("failed", usage.provider_requests_used, _PROVIDER_COST_UNITS, digest))
                return SearchResult(plan, (), tuple(receipts), usage)
            receipts.append(ProviderReceipt("succeeded", usage.provider_requests_used, _PROVIDER_COST_UNITS, digest))
            return SearchResult(plan, tuple(candidates.values()), tuple(receipts), usage)


def _validate_response(payload: bytes, max_items: int) -> list[dict[str, object]]:
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise ValueError("provider response oversized")
    try:
        decoded: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid provider response") from None
    if not isinstance(decoded, dict) or set(decoded) != {"schema_version", "items"}:
        raise ValueError("invalid provider response")
    items = decoded.get("items")
    if decoded.get("schema_version") != "FixtureProviderItems/v1" or not isinstance(items, list) or len(items) > max_items:
        raise ValueError("invalid provider response")
    if any(not isinstance(item, dict) for item in items):
        raise TypeError("invalid provider item")
    return items


def _candidate(item: dict[str, object]) -> Candidate:
    required = {"url", "title", "company", "location", "remote_signal", "snippet"}
    if set(item) != required or any(not isinstance(item[key], str) for key in required):
        raise ValueError("invalid provider item schema")
    return Candidate(
        canonical_url=str(item["url"]),
        title=str(item["title"]),
        company=str(item["company"]),
        location=str(item["location"]),
        remote_signal=str(item["remote_signal"]),
        source_provider="fixture-public-search-adapter",
        retrieved_at="fixture-time",
        snippet=str(item["snippet"]),
        evidence_grade="provider_returned",
    )


__all__ = ["BudgetExceeded", "FixtureSearchProvider", "ProviderAttempt", "ProviderOutcome", "SearchCoordinator"]
