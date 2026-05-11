"""Privacy-tagged LLM context bundles.

All LLM-facing calls should carry provenance instead of raw, untyped strings.
The sanitizer and LLM boundary can then reject private material before any
provider request is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PrivacyClass = Literal["public", "private", "hard-private"]

PRIVACY_ORDER: dict[str, int] = {
    "public": 0,
    "private": 1,
    "hard-private": 2,
}


class ContextBundleError(ValueError):
    """Raised when context provenance is missing or inconsistent."""


@dataclass(frozen=True)
class Source:
    rel_path: str
    privacy_class: PrivacyClass
    title: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    content: str = ""

    def __post_init__(self) -> None:
        rel_path = self.rel_path.strip()
        if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise ContextBundleError(f"unresolvable rel_path: {self.rel_path!r}")
        if self.privacy_class not in PRIVACY_ORDER:
            raise ContextBundleError(f"invalid privacy_class: {self.privacy_class!r}")


@dataclass(frozen=True)
class ContextBundle:
    sources: tuple[Source, ...]
    purpose: str = ""
    instructions: str = ""

    def __init__(
        self,
        sources: list[Source] | tuple[Source, ...],
        *,
        purpose: str = "",
        instructions: str = "",
    ) -> None:
        if not sources:
            raise ContextBundleError("ContextBundle requires at least one Source")
        object.__setattr__(self, "sources", tuple(sources))
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "instructions", instructions)

    @property
    def privacy_class(self) -> PrivacyClass:
        return max(self.sources, key=lambda source: PRIVACY_ORDER[source.privacy_class]).privacy_class

    def render(self) -> str:
        parts: list[str] = []
        if self.purpose:
            parts.append(f"Purpose: {self.purpose}")
        if self.instructions:
            parts.append(f"Instructions: {self.instructions}")
        for source in self.sources:
            title = source.title or source.rel_path
            parts.append(
                "\n".join(
                    [
                        f"Source: {source.rel_path}",
                        f"Privacy: {source.privacy_class}",
                        f"Title: {title}",
                        source.content,
                    ]
                ).strip()
            )
        return "\n\n---\n\n".join(parts)
