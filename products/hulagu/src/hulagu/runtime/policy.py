"""Typed runtime policy values; no ambient discovery or customer authority."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Self

RESEARCH_MODEL = "gpt-5.6-sol"
_PROVIDER_ERROR = object()
DISCLOSURE_FIELDS = (
    "company_name",
    "job_title",
    "listing_location",
    "listing_url",
    "listing_text_excerpt",
)


@dataclass(frozen=True, slots=True)
class EngineEnrollment:
    cli_path: Path
    cli_sha256: str
    socket_path: Path
    image: str
    approved_socket_path: Path | None = None

    def validate(self) -> Self:
        if not self.cli_path.is_absolute() or not self.cli_path.is_file():
            raise ValueError("container executable is absent or unapproved")
        observed = hashlib.sha256(self.cli_path.read_bytes()).hexdigest()
        if observed != self.cli_sha256:
            raise ValueError("container executable digest drift")
        approved = self.approved_socket_path or self.socket_path
        if not self.socket_path.is_absolute() or self.socket_path != approved or not self.socket_path.exists():
            raise ValueError("container socket is absent or unapproved")
        if self.socket_path.is_symlink():
            raise ValueError("container socket symlink drift")
        pinned_prefix = self.image.startswith("hulagu-parser@sha256:") or self.image.startswith("sha256:")
        if not pinned_prefix or len(self.image.rsplit(":", 1)[-1]) != 64:
            raise ValueError("parser image is not digest-pinned")
        return self

    @property
    def endpoint(self) -> str:
        return f"unix://{self.socket_path}"


@dataclass(frozen=True, slots=True)
class ParserInvocation:
    image: str
    name: str
    job_kind: str = "parser"


@dataclass(frozen=True, slots=True)
class ContainerEffectiveState:
    network_mode: str
    environment_keys: tuple[str, ...]
    mounts: tuple[tuple[Path, str, bool], ...]
    user: str
    cap_drop: tuple[str, ...]
    no_new_privileges: bool
    read_only: bool
    pids_limit: int
    memory_bytes: int
    cpu_count: float
    tmpfs_bytes: int
    open_files: int
    supplementary_groups: tuple[int, ...]

class ContextAuditSink(Protocol):
    def record(self, payload: dict[str, str]) -> None: ...


class RecordingAuditSink:
    def __init__(self) -> None:
        self.payloads: list[dict[str, str]] = []

    def record(self, payload: dict[str, str]) -> None:
        self.payloads.append(dict(payload))


class OpportunityProvenance(StrEnum):
    PUBLIC_WEB = "public_web"
    CUSTOMER_DERIVED = "customer_derived"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OpportunitySource:
    provenance: OpportunityProvenance
    company_name: str
    job_title: str
    listing_location: str
    listing_url: str
    listing_text_excerpt: str
    request_scope: str = ""


@dataclass(frozen=True, slots=True)
class ResearchDisclosure:
    company_name: str
    job_title: str
    listing_location: str
    listing_url: str
    listing_text_excerpt: str

    @classmethod
    def from_public_opportunity(cls, opportunity: PublicOpportunity) -> ResearchDisclosure:
        disclosure = cls(
            _redact_secret(opportunity.company_name),
            _redact_secret(opportunity.job_title),
            _redact_secret(opportunity.listing_location),
            _redact_secret(opportunity.listing_url),
            _redact_secret(opportunity.listing_text_excerpt),
        )
        disclosure.as_public_dict()
        return disclosure

    def as_public_dict(self) -> dict[str, str]:
        values = {name: str(getattr(self, name)) for name in DISCLOSURE_FIELDS}
        if any(not value for value in values.values()) or len(values["listing_text_excerpt"]) > 4_000:
            raise ValueError("invalid ResearchDisclosure/v1")
        if any(_contains_secret_marker(value) for value in values.values()):
            raise ValueError("ResearchDisclosure/v1 contains credential-shaped data")
        return values


@dataclass(frozen=True, slots=True)
class PublicOpportunity:
    company_name: str
    job_title: str
    listing_location: str
    listing_url: str
    listing_text_excerpt: str


class PublicOpportunityBuilder:
    @staticmethod
    def build(source: OpportunitySource) -> PublicOpportunity:
        if not isinstance(source, OpportunitySource) or source.provenance is not OpportunityProvenance.PUBLIC_WEB:
            raise ValueError("public source authority required")
        return PublicOpportunity(
            source.company_name,
            source.job_title,
            source.listing_location,
            source.listing_url,
            source.listing_text_excerpt,
        )


class ResearchModelClient(Protocol):
    def call(
        self,
        model: str,
        disclosure: ResearchDisclosure,
        *,
        timeout_seconds: int,
    ) -> dict[str, object]: ...


class ResearchMediatorProtocol(Protocol):
    def research_company_v1(self, disclosure: ResearchDisclosure) -> dict[str, object] | None: ...


class ResearchMediator:
    def __init__(
        self,
        client: ResearchModelClient,
        *,
        context_audit: ContextAuditSink,
        max_attempts: int = 2,
        timeout_seconds: int = 15,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        if max_attempts not in range(1, 4) or timeout_seconds not in range(1, 61):
            raise ValueError("research bounds invalid")
        self._client = client
        self._audit = context_audit
        self._max_attempts = max_attempts
        self._timeout = timeout_seconds
        self._cancelled = cancelled or (lambda: False)

    def research_company_v1(self, disclosure: ResearchDisclosure) -> dict[str, object] | None:
        payload = disclosure.as_public_dict()
        if self._cancelled():
            return None
        self._audit.record(payload)
        for _attempt in range(self._max_attempts):
            if self._cancelled():
                return None
            result: object
            try:
                result = self._client.call(RESEARCH_MODEL, disclosure, timeout_seconds=self._timeout)
            except asyncio.CancelledError:
                return None
            except Exception:  # noqa: BLE001 -- provider boundary fails closed without retaining text
                result = _PROVIDER_ERROR
            if result is _PROVIDER_ERROR:
                continue
            return _validate_research_proposal(result)
        return None


class ResearchPolicy:
    def __init__(self, mediator: ResearchMediatorProtocol | None) -> None:
        self._mediator = mediator

    @classmethod
    def disabled(
        cls,
        *,
        client_factory: Callable[[], ResearchModelClient],
        context_audit: ContextAuditSink,
    ) -> ResearchPolicy:
        del client_factory, context_audit
        return cls(None)

    @classmethod
    def enabled(cls, mediator: ResearchMediatorProtocol) -> ResearchPolicy:
        return cls(mediator)

    def research(self, sources: list[OpportunitySource]) -> list[dict[str, object] | None]:
        if self._mediator is None:
            return []
        opportunities = [PublicOpportunityBuilder.build(source) for source in sources]
        return [
            self._mediator.research_company_v1(ResearchDisclosure.from_public_opportunity(opportunity))
            for opportunity in opportunities
        ]


def _validate_research_proposal(result: object) -> dict[str, object] | None:
    allowed = {"schema_version", "company_summary", "red_flags", "interview_process"}
    if not isinstance(result, dict) or set(result) != allowed or result.get("schema_version") != "ResearchProposal/v1":
        return None
    for key in allowed - {"schema_version"}:
        value = result.get(key)
        if not isinstance(value, str):
            return None
        lowered = value.lower()
        if not lowered.startswith(("verified:", "inferred:", "rejected:")):
            return None
    serialized = repr(result)
    forbidden_result = re.search(
        r"(?i)(\b(?:probability|growth|fit|interview_pct)\b|\b\d+(?:\.\d+)?\s*%|"
        r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*_CANARY(?:_[A-Za-z0-9]+)*\b)",
        serialized,
    )
    if _contains_secret_marker(serialized) or forbidden_result:
        return None
    return dict(result)


def _contains_secret_marker(value: str) -> bool:
    return bool(
        re.search(
            r"(?i)(authorization|bearer|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|"
            r"credential|oauth|password|secret|sk-[A-Za-z0-9_-]+)",
            value,
        )
    )


def _redact_secret(value: str) -> str:
    return "[REDACTED]" if _contains_secret_marker(value) else value


def safe_container_name(digest: str, job_kind: str = "parser") -> str:
    if job_kind not in {"parser", "ranker"}:
        raise ValueError("unsupported sandbox job kind")
    return f"hulagu-{job_kind}-{digest[:12]}-{os.getpid()}"
