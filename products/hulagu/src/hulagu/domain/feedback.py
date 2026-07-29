"""Tenant-local, deterministic, and inspectable V1 feedback features."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast
from uuid import UUID

from hulagu.persistence.db import ConnectionProtocol, CursorProtocol, tenant_transaction
from hulagu.persistence.rls import TenantPrincipal
from hulagu.search.schemas import Candidate, RankedCandidate, SearchPlan
from hulagu.wiki.model import WikiPage

from .ranking import rank_candidates

_MAX_FEATURES = 20
_MAX_COUNT = 5
_ACTION_TTL_SECONDS = 15 * 60
_ALLOWED_DECISIONS = {"saved", "rejected"}
_ALLOWED_REMOTE = {"remote", "hybrid", "onsite"}
_TITLE_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,39}")
_TITLE_STOPWORDS = {"a", "an", "and", "at", "for", "in", "of", "on", "the", "to"}


@dataclass(frozen=True, slots=True)
class DecisionEvidence:
    """The bounded public listing fields an explicit decision may update."""

    canonical_url: str
    title: str
    company: str
    location: str
    remote_signal: str
    source_provider: str
    retrieved_at: str
    snippet: str
    evidence_grade: str
    required_terms: tuple[str, ...]
    normalized_url_hash: str

    @classmethod
    def from_candidate(cls, candidate: Candidate) -> DecisionEvidence:
        return cls(
            canonical_url=candidate.canonical_url,
            title=candidate.title,
            company=candidate.company,
            location=candidate.location,
            remote_signal=candidate.remote_signal,
            source_provider=candidate.source_provider,
            retrieved_at=candidate.retrieved_at,
            snippet=candidate.snippet,
            evidence_grade=candidate.evidence_grade,
            required_terms=candidate.required_terms,
            normalized_url_hash=candidate.normalized_url_hash,
        )

    def candidate(self) -> Candidate:
        candidate = Candidate(
            canonical_url=self.canonical_url,
            title=self.title,
            company=self.company,
            location=self.location,
            remote_signal=self.remote_signal,
            source_provider=self.source_provider,
            retrieved_at=self.retrieved_at,
            snippet=self.snippet,
            evidence_grade=self.evidence_grade,
            required_terms=self.required_terms,
        )
        if candidate.normalized_url_hash != self.normalized_url_hash:
            raise ValueError("feedback evidence digest mismatch")
        return candidate


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    decision_id: UUID
    tenant_id: UUID
    candidate_id: UUID
    decision: str
    reason: str | None
    evidence: DecisionEvidence
    applied: bool

    def __post_init__(self) -> None:
        if self.decision not in _ALLOWED_DECISIONS or self.decision_id.version != 4 or self.candidate_id.version != 4:
            raise ValueError("invalid feedback decision")


@dataclass(frozen=True, slots=True)
class FeatureCount:
    value: str
    count: int
    source_decision_ids: tuple[UUID, ...]

    def __post_init__(self) -> None:
        if not self.value or not 1 <= self.count <= _MAX_COUNT or not self.source_decision_ids:
            raise ValueError("invalid feedback feature")


@dataclass(frozen=True, slots=True)
class FeedbackFeatures:
    preferred_title_tokens: tuple[FeatureCount, ...] = ()
    excluded_title_tokens: tuple[FeatureCount, ...] = ()
    location_preferences: tuple[FeatureCount, ...] = ()
    remote_preferences: tuple[FeatureCount, ...] = ()
    company_rejection_counts: tuple[FeatureCount, ...] = ()
    role_rejection_counts: tuple[FeatureCount, ...] = ()

    def as_dict(self) -> dict[str, tuple[FeatureCount, ...]]:
        return {
            "preferred_title_tokens": self.preferred_title_tokens,
            "excluded_title_tokens": self.excluded_title_tokens,
            "location_preferences": self.location_preferences,
            "remote_preferences": self.remote_preferences,
            "company_rejection_counts": self.company_rejection_counts,
            "role_rejection_counts": self.role_rejection_counts,
        }


@dataclass(frozen=True, slots=True)
class NextSearchPlan:
    """Confirmed hard constraints plus a separate, inspectable feedback overlay."""

    base: SearchPlan
    execution: SearchPlan
    feedback: FeedbackFeatures


@dataclass(frozen=True, slots=True)
class DecisionAction:
    candidate_id: UUID
    decision: str
    profile_version: int
    lifecycle_epoch: int
    expires_at: int
    token: str

    def __post_init__(self) -> None:
        if (
            self.candidate_id.version != 4
            or self.decision not in _ALLOWED_DECISIONS
            or self.profile_version < 1
            or self.lifecycle_epoch < 0
            or self.expires_at < 0
            or not hmac.compare_digest(self.token, self.token.lower())
            or len(self.token) != 64
        ):
            raise ValueError("invalid feedback action")


def _title_tokens(title: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            token
            for token in _TITLE_TOKEN.findall(title.lower())
            if token not in _TITLE_STOPWORDS
        )
    )[:8]


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())[:200]


def _bounded_counts(items: list[tuple[str, UUID]]) -> tuple[FeatureCount, ...]:
    sources: dict[str, list[UUID]] = {}
    for value, decision_id in items:
        normalized = _normalized(value)
        if normalized:
            bucket = sources.setdefault(normalized, [])
            if decision_id not in bucket:
                bucket.append(decision_id)
    return tuple(
        FeatureCount(value, min(len(decision_ids), _MAX_COUNT), tuple(decision_ids[:_MAX_COUNT]))
        for value, decision_ids in sorted(sources.items(), key=lambda item: (-len(item[1]), item[0]))[:_MAX_FEATURES]
    )


def derive_features(tenant_id: UUID, records: tuple[DecisionRecord, ...]) -> FeedbackFeatures:
    """Derive only the closed V1 feature set from explicit tenant decisions."""

    preferred: list[tuple[str, UUID]] = []
    excluded: list[tuple[str, UUID]] = []
    locations: list[tuple[str, UUID]] = []
    remotes: list[tuple[str, UUID]] = []
    companies: list[tuple[str, UUID]] = []
    roles: list[tuple[str, UUID]] = []
    for record in records:
        if record.tenant_id != tenant_id:
            continue
        evidence = record.evidence
        if record.decision == "saved":
            preferred.extend((token, record.decision_id) for token in _title_tokens(evidence.title))
            locations.append((evidence.location, record.decision_id))
            remote = _normalized(evidence.remote_signal)
            if remote in _ALLOWED_REMOTE:
                remotes.append((remote, record.decision_id))
        else:
            excluded.extend((token, record.decision_id) for token in _title_tokens(evidence.title))
            companies.append((evidence.company, record.decision_id))
            roles.append((evidence.title, record.decision_id))
    return FeedbackFeatures(
        preferred_title_tokens=_bounded_counts(preferred),
        excluded_title_tokens=_bounded_counts(excluded),
        location_preferences=_bounded_counts(locations),
        remote_preferences=_bounded_counts(remotes),
        company_rejection_counts=_bounded_counts(companies),
        role_rejection_counts=_bounded_counts(roles),
    )


def compile_next_search(base: SearchPlan, features: FeedbackFeatures) -> NextSearchPlan:
    """Compile a query overlay without rewriting confirmed hard constraints."""

    preferred = tuple(item.value for item in features.preferred_title_tokens[:3])
    excluded = tuple(f"-{item.value}" for item in features.excluded_title_tokens[:3])
    suffix = (*preferred, *excluded)
    queries = base.queries if not suffix else tuple(" ".join((query, *suffix)) for query in base.queries)
    return NextSearchPlan(base=base, execution=replace(base, queries=queries), feedback=features)


def _feature(features: tuple[FeatureCount, ...], value: str) -> FeatureCount | None:
    normalized = _normalized(value)
    return next((item for item in features if item.value == normalized), None)


def _feedback_delta(candidate: Candidate, features: FeedbackFeatures) -> tuple[float, str]:
    company = _feature(features.company_rejection_counts, candidate.company)
    if company is not None:
        delta = max(-10.0, -2.0 * company.count)
        return delta, f"rejected company {candidate.company}={delta:g}"
    role = _feature(features.role_rejection_counts, candidate.title)
    if role is not None:
        delta = max(-10.0, -1.0 * role.count)
        return delta, f"rejected role {candidate.title}={delta:g}"

    lowered_title = candidate.title.lower()
    preferred = sum(item.count for item in features.preferred_title_tokens if item.value in lowered_title)
    excluded = sum(item.count for item in features.excluded_title_tokens if item.value in lowered_title)
    location = _feature(features.location_preferences, candidate.location)
    remote = _feature(features.remote_preferences, candidate.remote_signal)
    delta = min(10.0, max(-10.0, 0.5 * preferred - 0.5 * excluded + 0.5 * (location.count if location else 0) + 0.5 * (remote.count if remote else 0)))
    if delta == 0:
        return 0.0, "no matching explicit decision=0"
    return delta, f"saved/excluded title, location, and remote features={delta:g}"


def rank_with_feedback(candidates: tuple[Candidate, ...], plan: NextSearchPlan) -> tuple[RankedCandidate, ...]:
    """Apply a capped visible feedback component without mutating source evidence."""

    baseline = rank_candidates(
        candidates,
        role_terms=plan.base.role_terms,
        location_terms=plan.base.location_terms,
        required_terms=plan.base.required_terms,
        excluded_terms=plan.base.excluded_terms,
        max_ranked=plan.base.budgets.max_ranked,
    )
    adjusted: list[RankedCandidate] = []
    for item in baseline:
        delta, attribution = _feedback_delta(item.candidate, plan.feedback)
        components = dict(item.components)
        components["tenant_feedback_match"] = round(delta, 4)
        total = round(sum(components.values()), 4)
        explanation = f"{item.explanation}; tenant feedback: {attribution}; total delta={delta:g}"
        adjusted.append(replace(item, components=components, total_score=total, explanation=explanation))
    adjusted.sort(key=lambda item: (-item.total_score, item.candidate.normalized_url_hash))
    return tuple(adjusted[: plan.base.budgets.max_ranked])


def _markdown(value: str) -> str:
    plain_text = " ".join(
        "".join(character if character.isprintable() else " " for character in value).split()
    )[:500]
    return "".join(
        character if character.isalnum() or character == " " else f"&#x{ord(character):X};"
        for character in plain_text
    )


def pages_for_feedback_republication(
    pages: tuple[WikiPage, ...],
    decisions: tuple[DecisionRecord, ...],
    ranked: tuple[RankedCandidate, ...],
    *,
    search_path: str,
) -> tuple[WikiPage, ...]:
    """Replace the private decisions/current-search pages for atomic republication."""

    paths = {page.path for page in pages}
    if search_path not in paths or "decisions.md" not in paths or not search_path.startswith("searches/"):
        raise ValueError("feedback republication pages missing")
    decision_lines = ["| Candidate | Company | Decision | Reason |", "|---|---|---|---|"]
    decision_lines.extend(
        f"| `{record.candidate_id}` | {_markdown(record.evidence.company)} | {record.decision} | {_markdown(record.reason or '—')} |"
        for record in decisions
    )
    search_lines = ["| Candidate | Company | Score | Feedback delta | Explanation |", "|---|---|---:|---:|---|"]
    search_lines.extend(
        f"| {_markdown(item.candidate.title)} | {_markdown(item.candidate.company)} | {item.total_score:g} | "
        f"tenant_feedback_match={item.components['tenant_feedback_match']:g} | {_markdown(item.explanation)} |"
        for item in ranked
    )
    replacements = {
        "decisions.md": WikiPage("decisions.md", "Decisions", "\n".join(decision_lines)),
        search_path: WikiPage(search_path, "Search results", "\n".join(search_lines)),
    }
    return tuple(replacements.get(page.path, page) for page in pages)


class FeedbackFlow:
    """The authority-validating public entry point for durable candidate feedback."""

    def __init__(
        self,
        connection: ConnectionProtocol,
        principal: TenantPrincipal,
        *,
        signing_key: bytes,
        clock: Callable[[], int],
    ) -> None:
        if len(signing_key) < 32:
            raise ValueError("feedback signing key too short")
        self._connection = connection
        self._principal = principal
        self._signing_key = signing_key
        self._clock = clock

    def _payload(
        self,
        candidate_id: UUID,
        decision: str,
        profile_version: int,
        lifecycle_epoch: int,
        expires_at: int,
    ) -> bytes:
        return "\0".join(
            (
                "HulaguFeedbackAction/v1",
                str(self._principal.tenant_id),
                str(candidate_id),
                decision,
                str(profile_version),
                str(lifecycle_epoch),
                str(expires_at),
            )
        ).encode()

    def issue_action(
        self,
        candidate_id: UUID,
        decision: str,
        *,
        profile_version: int,
        lifecycle_epoch: int,
        expires_at: int,
    ) -> DecisionAction:
        now = self._clock()
        if expires_at <= now or expires_at > now + _ACTION_TTL_SECONDS:
            raise ValueError("invalid feedback action expiry")
        payload = self._payload(candidate_id, decision, profile_version, lifecycle_epoch, expires_at)
        token = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
        return DecisionAction(candidate_id, decision, profile_version, lifecycle_epoch, expires_at, token)

    def _validate_action(self, action: DecisionAction) -> None:
        expected = hmac.new(
            self._signing_key,
            self._payload(
                action.candidate_id,
                action.decision,
                action.profile_version,
                action.lifecycle_epoch,
                action.expires_at,
            ),
            hashlib.sha256,
        ).hexdigest()
        if self._clock() > action.expires_at or not hmac.compare_digest(expected, action.token):
            raise PermissionError("feedback authority rejected")

    @staticmethod
    def _lock_ready(cursor: CursorProtocol, expected_epoch: int | None = None) -> int:
        cursor.execute(
            "SELECT state,lifecycle_epoch FROM hulagu.tenants "
            "WHERE id=current_setting('app.tenant_id')::uuid FOR UPDATE"
        )
        row = cursor.fetchone()
        if row is None:
            raise PermissionError("feedback authority rejected")
        epoch = int(row[1])
        if str(row[0]) != "READY" or (expected_epoch is not None and epoch != expected_epoch):
            raise PermissionError("feedback authority rejected")
        return epoch

    def record(
        self,
        action: DecisionAction,
        *,
        reason: str | None,
        correlation_id: str,
    ) -> DecisionRecord:
        self._validate_action(action)
        if reason is not None and (not reason.strip() or len(reason.encode()) > 500 or "\x00" in reason):
            raise ValueError("invalid feedback reason")
        with tenant_transaction(self._connection, self._principal, correlation_id=correlation_id), self._connection.cursor() as cursor:
            self._lock_ready(cursor, action.lifecycle_epoch)
            cursor.execute(
                "SELECT c.evidence,r.query_plan->>'profile_version' "
                "FROM hulagu.search_candidates AS c JOIN hulagu.search_runs AS r "
                "ON r.tenant_id=c.tenant_id AND r.id=c.run_id WHERE c.id=%s FOR UPDATE OF c",
                (action.candidate_id,),
            )
            candidate_row = cursor.fetchone()
            if candidate_row is None or int(str(candidate_row[1])) != action.profile_version:
                raise PermissionError("feedback authority rejected")
            evidence = self._parse_evidence(candidate_row[0])
            cursor.execute(
                "SELECT id,decision,reason FROM hulagu.candidate_decisions WHERE candidate_id=%s",
                (action.candidate_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if str(existing[1]) != action.decision:
                    raise PermissionError("feedback decision already recorded")
                return DecisionRecord(
                    UUID(str(existing[0])),
                    self._principal.tenant_id,
                    action.candidate_id,
                    action.decision,
                    None if existing[2] is None else str(existing[2]),
                    evidence,
                    False,
                )
            cursor.execute(
                "INSERT INTO hulagu.candidate_decisions(tenant_id,candidate_id,decision,reason) "
                "VALUES(current_setting('app.tenant_id')::uuid,%s,%s,%s) "
                "ON CONFLICT (tenant_id,candidate_id) DO NOTHING RETURNING id,reason",
                (action.candidate_id, action.decision, reason),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                cursor.execute(
                    "SELECT id,decision,reason FROM hulagu.candidate_decisions WHERE candidate_id=%s",
                    (action.candidate_id,),
                )
                raced = cursor.fetchone()
                if raced is None or str(raced[1]) != action.decision:
                    raise PermissionError("feedback decision already recorded")
                return DecisionRecord(
                    UUID(str(raced[0])),
                    self._principal.tenant_id,
                    action.candidate_id,
                    action.decision,
                    None if raced[2] is None else str(raced[2]),
                    evidence,
                    False,
                )
            return DecisionRecord(
                UUID(str(inserted[0])),
                self._principal.tenant_id,
                action.candidate_id,
                action.decision,
                None if inserted[1] is None else str(inserted[1]),
                evidence,
                True,
            )

    def decisions(self, *, correlation_id: str) -> tuple[DecisionRecord, ...]:
        with tenant_transaction(self._connection, self._principal, correlation_id=correlation_id), self._connection.cursor() as cursor:
            self._lock_ready(cursor)
            cursor.execute(
                "SELECT d.id,d.candidate_id,d.decision,d.reason,c.evidence "
                "FROM hulagu.candidate_decisions AS d JOIN hulagu.search_candidates AS c "
                "ON c.tenant_id=d.tenant_id AND c.id=d.candidate_id ORDER BY d.created_at,d.id"
            )
            rows = cursor.fetchall()
        return tuple(
            DecisionRecord(
                UUID(str(row[0])),
                self._principal.tenant_id,
                UUID(str(row[1])),
                str(row[2]),
                None if row[3] is None else str(row[3]),
                self._parse_evidence(row[4]),
                False,
            )
            for row in rows
        )

    def features(self, *, correlation_id: str) -> FeedbackFeatures:
        return derive_features(self._principal.tenant_id, self.decisions(correlation_id=correlation_id))

    @staticmethod
    def _parse_evidence(raw: object) -> DecisionEvidence:
        decoded: object = json.loads(raw.decode() if isinstance(raw, bytes) else str(raw))
        if not isinstance(decoded, dict):
            raise TypeError("invalid feedback evidence")
        expected = {
            "canonical_url",
            "title",
            "company",
            "location",
            "remote_signal",
            "source_provider",
            "retrieved_at",
            "snippet",
            "evidence_grade",
            "required_terms",
            "normalized_url_hash",
        }
        if set(decoded) != expected or not isinstance(decoded.get("required_terms"), list):
            raise ValueError("invalid feedback evidence")
        candidate = Candidate(
            canonical_url=cast(str, decoded["canonical_url"]),
            title=cast(str, decoded["title"]),
            company=cast(str, decoded["company"]),
            location=cast(str, decoded["location"]),
            remote_signal=cast(str, decoded["remote_signal"]),
            source_provider=cast(str, decoded["source_provider"]),
            retrieved_at=cast(str, decoded["retrieved_at"]),
            snippet=cast(str, decoded["snippet"]),
            evidence_grade=cast(str, decoded["evidence_grade"]),
            required_terms=tuple(cast(list[str], decoded["required_terms"])),
        )
        if decoded["normalized_url_hash"] != candidate.normalized_url_hash:
            raise ValueError("feedback evidence digest mismatch")
        return DecisionEvidence.from_candidate(candidate)
