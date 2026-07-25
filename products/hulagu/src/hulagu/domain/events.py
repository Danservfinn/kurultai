"""Pure event value objects for Hulagu's customer state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EventKind(StrEnum):
    START = "start"
    CONSENT_ACCEPTED = "consent_accepted"
    CONSENT_DECLINED = "consent_declined"
    CV_RECORDED = "cv_recorded"
    PROFILE_ANSWERED = "profile_answered"
    PROFILE_SKIPPED = "profile_skipped"
    PROFILE_CONFIRMED = "profile_confirmed"
    PROFILE_EDITED = "profile_edited"
    SEARCH_REQUESTED = "search_requested"
    RUN_STARTED = "run_started"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    RUN_CANCELLED = "run_cancelled"
    WORKER_FAILED = "worker_failed"
    WORKER_RETRIED = "worker_retried"
    WORKER_SUCCEEDED = "worker_succeeded"
    DELETE_REQUESTED = "delete_requested"
    DELETE_CANCELLED = "delete_cancelled"
    TENANT_DELETED = "tenant_deleted"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    kind: EventKind
    tenant_lifecycle_epoch: int
    profile_revision: int
    work_epoch: int
    nonce: str | None = None
    detail: str | None = None
