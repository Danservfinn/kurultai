"""Immutable profile values and deterministic question metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class ProfileField:
    field_id: str
    value: str
    source: str
    confidence: float
    source_span: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileQuestion:
    question_id: str
    field_id: str
    required: bool


@dataclass(frozen=True, slots=True)
class Profile:
    version: int
    fields: tuple[ProfileField, ...] = ()
    intentionally_omitted: tuple[str, ...] = ()
    confirmed_version: int | None = None

    def field(self, field_id: str) -> ProfileField | None:
        return next((field for field in self.fields if field.field_id == field_id), None)

    def set_field(self, field: ProfileField, *, increment_version: bool = False) -> Profile:
        fields = tuple(existing for existing in self.fields if existing.field_id != field.field_id) + (field,)
        omitted = tuple(item for item in self.intentionally_omitted if item != field.field_id)
        return replace(
            self,
            version=self.version + int(increment_version),
            fields=fields,
            intentionally_omitted=omitted,
            confirmed_version=None if increment_version else self.confirmed_version,
        )

    def omit(self, field_id: str) -> Profile:
        if field_id in self.intentionally_omitted:
            return self
        return replace(self, intentionally_omitted=self.intentionally_omitted + (field_id,))

    def confirm(self) -> Profile:
        return replace(self, confirmed_version=self.version)
