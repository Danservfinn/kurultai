"""Retention policy and atomic storage-pressure/quota admission."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import uuid4


class PressureState(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    CRITICAL = "critical"


class AdmissionOperation(str, Enum):
    UPLOAD = "upload"
    SEARCH = "search"
    STATUS = "status"
    CANCEL = "cancel"
    DELETE = "delete"


@dataclass(slots=True)
class _Usage:
    quota: int
    accounted: int
    reserved: int = 0


class StorageAdmissionController:
    """Reference atomic controller; PostgreSQL uses the equivalent 0013 functions."""

    def __init__(self) -> None:
        self._usage: dict[str, _Usage] = {}
        self._reservations: dict[tuple[str, str], int] = {}
        self._pressure = PressureState.NORMAL
        self._measured_bytes = 0
        self._backup_read_only = False

    def configure(self, tenant: str, *, quota_bytes: int, accounted_bytes: int) -> None:
        if not tenant or quota_bytes < 1 or not 0 <= accounted_bytes <= quota_bytes:
            raise ValueError("invalid storage configuration")
        self._usage[tenant] = _Usage(quota_bytes, accounted_bytes)

    def set_pressure(self, state: PressureState, *, measured_bytes: int) -> None:
        if measured_bytes < 0:
            raise ValueError("invalid storage measurement")
        self._pressure = state
        self._measured_bytes = measured_bytes

    def set_backup_read_only(self, enabled: bool) -> None:
        self._backup_read_only = enabled

    def reserve(self, tenant: str, operation: AdmissionOperation, requested_bytes: int) -> str:
        if operation not in {AdmissionOperation.UPLOAD, AdmissionOperation.SEARCH} or requested_bytes < 1:
            raise ValueError("invalid storage admission")
        if self._backup_read_only:
            raise PermissionError("backup read-only lock held")
        if self._pressure is not PressureState.NORMAL:
            raise PermissionError("global storage pressure refuses admission")
        usage = self._usage[tenant]
        if usage.accounted + usage.reserved + requested_bytes > usage.quota:
            raise PermissionError("tenant storage quota exceeded")
        reservation = str(uuid4())
        usage.reserved += requested_bytes
        self._reservations[(tenant, reservation)] = requested_bytes
        return reservation

    def settle(self, tenant: str, reservation: str, *, actual_bytes: int) -> None:
        if self._backup_read_only:
            raise PermissionError("backup read-only lock held")
        reserved = self._reservations[(tenant, reservation)]
        usage = self._usage[tenant]
        if actual_bytes < 0 or actual_bytes > reserved or usage.accounted + actual_bytes > usage.quota:
            raise PermissionError("invalid storage settlement")
        usage.reserved -= reserved
        usage.accounted += actual_bytes
        del self._reservations[(tenant, reservation)]

    def admit_control(self, operation: AdmissionOperation) -> bool:
        return operation in {AdmissionOperation.STATUS, AdmissionOperation.CANCEL, AdmissionOperation.DELETE}

    def usage(self, tenant: str) -> tuple[int, int, int]:
        usage = self._usage[tenant]
        return usage.accounted, usage.reserved, usage.quota
