"""Strict typed values at the fixture-provider and ranker boundaries."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class BudgetExceeded(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        usage: BudgetUsage | None = None,
        receipts: tuple[ProviderReceipt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.usage = usage
        self.receipts = receipts


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    max_queries: int = 8
    max_provider_requests_total: int = 10
    max_provider_cost_units: int = 100
    max_results_per_query: int = 25
    max_candidates: int = 100
    max_ranked: int = 20
    max_attempts_per_job: int = 3
    max_container_attempts_total: int = 12
    max_publication_attempts: int = 3
    wall_seconds: int = 300

    def __post_init__(self) -> None:
        ceilings = (8, 10, 100, 25, 100, 20, 3, 12, 3, 300)
        values = tuple(asdict(self).values())
        if any(not isinstance(value, int) or value < 1 or value > ceiling for value, ceiling in zip(values, ceilings, strict=True)):
            raise ValueError("invalid search budget")

    def new_usage(self) -> BudgetUsage:
        return BudgetUsage(self)


@dataclass(slots=True)
class BudgetUsage:
    limits: BudgetLimits
    provider_requests_used: int = 0
    provider_cost_units_used: int = 0
    publication_attempts_used: int = 0

    def reserve_provider(self, cost_units: int) -> None:
        if cost_units < 1:
            raise ValueError("provider cost must be positive")
        if self.provider_requests_used + 1 > self.limits.max_provider_requests_total:
            raise BudgetExceeded("provider request budget exhausted")
        if self.provider_cost_units_used + cost_units > self.limits.max_provider_cost_units:
            raise BudgetExceeded("provider cost budget exhausted")
        self.provider_requests_used += 1
        self.provider_cost_units_used += cost_units

    def reserve_publication(self) -> None:
        if self.publication_attempts_used + 1 > self.limits.max_publication_attempts:
            raise BudgetExceeded("publication budget exhausted")
        self.publication_attempts_used += 1


@dataclass(frozen=True, slots=True)
class SearchPlan:
    schema_version: str
    profile_version: int
    role_terms: tuple[str, ...]
    location_terms: tuple[str, ...]
    remote_policy: str
    required_terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]
    provider: str
    budgets: BudgetLimits
    queries: tuple[str, ...]

    @classmethod
    def with_budgets(cls, plan: SearchPlan, budgets: BudgetLimits) -> SearchPlan:
        return replace(plan, budgets=budgets)


@dataclass(frozen=True, slots=True)
class Candidate:
    canonical_url: str
    title: str
    company: str
    location: str
    remote_signal: str
    source_provider: str
    retrieved_at: str
    snippet: str
    evidence_grade: str
    required_terms: tuple[str, ...] = ()
    normalized_url_hash: str = ""

    def __post_init__(self) -> None:
        canonical = canonicalize_url(self.canonical_url)
        object.__setattr__(self, "canonical_url", canonical)
        object.__setattr__(self, "normalized_url_hash", hashlib.sha256(canonical.encode()).hexdigest())
        fields = (self.title, self.company, self.location, self.remote_signal, self.source_provider, self.retrieved_at, self.snippet)
        if any(not value or len(value) > 4_000 for value in fields):
            raise ValueError("invalid provider candidate")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: Candidate
    components: dict[str, float]
    total_score: float
    matched_constraints: tuple[str, ...]
    missing_constraints: tuple[str, ...]
    explanation: str


@dataclass(frozen=True, slots=True)
class ProviderReceipt:
    outcome: str
    request_number: int
    cost_units_charged: int
    response_digest: str | None


@dataclass(frozen=True, slots=True)
class RankingJobInput:
    run_id: str
    profile_version: int
    candidates: tuple[Candidate, ...]
    role_terms: tuple[str, ...]
    location_terms: tuple[str, ...]
    required_terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]
    max_ranked: int

    @classmethod
    def synthetic(cls, *, run_id: str, profile_version: int) -> RankingJobInput:
        return cls(run_id, profile_version, (), (), (), (), (), 20)

    def to_bytes(self) -> bytes:
        payload = {
            "schema_version": "RankerInput/v1",
            "run_id": self.run_id,
            "profile_version": self.profile_version,
            "candidates": [asdict(candidate) for candidate in self.candidates],
            "intent": {
                "role_terms": list(self.role_terms),
                "location_terms": list(self.location_terms),
                "required_terms": list(self.required_terms),
                "excluded_terms": list(self.excluded_terms),
            },
            "max_ranked": self.max_ranked,
        }
        return json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class SearchResult:
    plan: SearchPlan
    candidates: tuple[Candidate, ...]
    receipts: tuple[ProviderReceipt, ...]
    budget: BudgetUsage

    def to_ranking_input(self, run_id: str) -> RankingJobInput:
        return RankingJobInput(
            run_id,
            self.plan.profile_version,
            self.candidates,
            self.plan.role_terms,
            self.plan.location_terms,
            self.plan.required_terms,
            self.plan.excluded_terms,
            self.plan.budgets.max_ranked,
        )


class ProviderOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    AMBIGUOUS = "delivery_unknown"


def canonicalize_url(value: str) -> str:
    if len(value) > 2_048:
        raise ValueError("provider URL oversized")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("provider URL policy")
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and (not address.is_global or address.is_private or address.is_link_local or address.is_loopback):
        raise ValueError("provider private address")
    if hostname == "localhost" or not hostname.endswith(".example.test"):
        raise ValueError("provider fixed origin")
    query = urlencode(sorted((key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_")))
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path or "/", query, ""))


_RANK_COMPONENTS = {
    "role_match",
    "required_skill_match",
    "location_match",
    "seniority_match",
    "freshness_signal",
    "tenant_feedback_match",
    "hard_exclusion_penalties",
}


def validate_ranker_output(
    payload: bytes | Path,
    *,
    allowed_urls: set[str] | None = None,
    max_ranked: int = 20,
) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise TypeError("ranker output must be regular stdout bytes")
    if len(payload) > 1_048_576:
        raise ValueError("ranker output limit")
    try:
        decoded: object = json.loads(payload, parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("invalid RankedCandidates/v1") from None
    if not isinstance(decoded, dict) or set(decoded) != {"schema_version", "ranked"}:
        raise ValueError("invalid RankedCandidates/v1")
    if decoded.get("schema_version") != "RankedCandidates/v1" or not isinstance(decoded.get("ranked"), list):
        raise ValueError("invalid RankedCandidates/v1")
    ranked = decoded["ranked"]
    if not 0 <= len(ranked) <= max_ranked <= 20:
        raise ValueError("invalid RankedCandidates/v1")
    seen: set[str] = set()
    for item in ranked:
        if not isinstance(item, dict) or set(item) != {
            "canonical_url",
            "components",
            "total_score",
            "matched_constraints",
            "missing_constraints",
            "explanation",
        }:
            raise ValueError("invalid RankedCandidates/v1")
        url = item.get("canonical_url")
        components = item.get("components")
        score = item.get("total_score")
        matched = item.get("matched_constraints")
        missing = item.get("missing_constraints")
        explanation = item.get("explanation")
        if (
            not isinstance(url, str)
            or not isinstance(components, dict)
            or set(components) != _RANK_COMPONENTS
            or isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not isinstance(matched, list)
            or not isinstance(missing, list)
            or not isinstance(explanation, str)
            or not explanation.startswith("Deterministic score: ")
            or len(explanation) > 2_000
        ):
            raise ValueError("invalid RankedCandidates/v1")
        component_values = tuple(components.values())
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in component_values):
            raise ValueError("invalid RankedCandidates/v1")
        if any(not math.isfinite(float(value)) or not -100 <= float(value) <= 100 for value in component_values):
            raise ValueError("invalid RankedCandidates/v1")
        if any(not isinstance(value, str) or not value or len(value) > 200 for value in (*matched, *missing)):
            raise ValueError("invalid RankedCandidates/v1")
        if len(set(matched)) != len(matched) or len(set(missing)) != len(missing) or set(matched) & set(missing):
            raise ValueError("invalid RankedCandidates/v1")
        try:
            canonical = canonicalize_url(url)
        except ValueError:
            raise ValueError("invalid RankedCandidates/v1") from None
        if (
            canonical != url
            or canonical in seen
            or (allowed_urls is not None and canonical not in allowed_urls)
            or not math.isfinite(float(score))
            or not -100 <= float(score) <= 100
            or round(sum(float(value) for value in component_values), 4) != float(score)
        ):
            raise ValueError("invalid RankedCandidates/v1")
        seen.add(canonical)
    return decoded
