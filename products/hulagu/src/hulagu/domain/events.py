"""Schema-aligned immutable events for the pure Hulagu domain."""

from __future__ import annotations

from dataclasses import dataclass

from .profile import Profile, ProfileQuestion


@dataclass(frozen=True, slots=True)
class ConsentAccepted:
    notice_version: str
    nonce: str
    now: int


@dataclass(frozen=True, slots=True)
class ConsentDeclined:
    notice_version: str
    nonce: str
    now: int


@dataclass(frozen=True, slots=True)
class CvReceived:
    document_id: str


@dataclass(frozen=True, slots=True)
class CvParsed:
    profile: Profile
    questions: tuple[ProfileQuestion, ...]


@dataclass(frozen=True, slots=True)
class CvParseFailed:
    pass


@dataclass(frozen=True, slots=True)
class AnswerSubmitted:
    question_id: str
    value: str
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class OptionalFieldSkipped:
    question_id: str
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class FieldEdited:
    field_id: str
    value: str
    expected_profile_version: int
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class ProfileConfirmed:
    expected_profile_version: int
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class SearchRequested:
    run_id: str
    expected_profile_version: int
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class RunPaused:
    run_id: str
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class RunResumed:
    run_id: str
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class RunCancelled:
    run_id: str
    nonce: str
    now: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class DeleteRequested:
    nonce: str
    now: int
    expires_at: int
    decision_nonce: str
    decision_expires_at: int


@dataclass(frozen=True, slots=True)
class DeleteConfirmed:
    nonce: str
    now: int


@dataclass(frozen=True, slots=True)
class DeleteCancelled:
    nonce: str
    now: int


@dataclass(frozen=True, slots=True)
class DeletionCompleted:
    expected_lifecycle_epoch: int


@dataclass(frozen=True, slots=True)
class WorkerRetry:
    run_id: str | None = None
