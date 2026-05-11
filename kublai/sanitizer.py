"""Privacy classifier and early sanitizer for Kublai brain v4.

This Phase -1 stub is intentionally conservative. Phase 4 expands publishing
rules, but the public indexer, LLM boundary, and MCP/gateway surfaces can depend
on this single classifier now.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from .context_bundle import ContextBundle, PrivacyClass, Source

HARD_PRIVATE_FOLDERS = ("hard-private/",)
HARD_PRIVATE_TYPES = {"human-contact"}
HARD_PRIVATE_TAGS = {"pii", "tax", "financial", "legal", "medical"}
PRIVATE_PATH_RE = re.compile(r"\bhard-private/[^\s)\]}>\"']+")
CANARY_RE = re.compile(r"\bKUBLAI_HARD_PRIVATE_CANARY_[A-Z0-9_:-]*\b")


class SanitizerContext(Enum):
    PUBLISH = "publish"
    QUERY_RESPONSE = "query_response"
    LLM_PROMPT = "llm_prompt"
    MCP_RESPONSE = "mcp_response"
    GATEWAY_RESPONSE = "gateway_response"


class SanitizerError(ValueError):
    """Raised when content cannot be safely scrubbed for the requested target."""


class PrivacyBoundaryError(SanitizerError):
    """Raised when private context would cross an external boundary."""


class Sanitizer:
    HARD_PRIVATE_FOLDERS = HARD_PRIVATE_FOLDERS
    HARD_PRIVATE_TYPES = HARD_PRIVATE_TYPES
    HARD_PRIVATE_TAGS = HARD_PRIVATE_TAGS

    def classify(self, rel_path: str, frontmatter: dict[str, Any] | None = None) -> PrivacyClass:
        rel_path = rel_path.strip()
        if any(rel_path.startswith(prefix) for prefix in self.HARD_PRIVATE_FOLDERS):
            return "hard-private"
        if frontmatter:
            if frontmatter.get("type") in self.HARD_PRIVATE_TYPES:
                return "hard-private"
            tags = frontmatter.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            if {str(tag) for tag in tags} & self.HARD_PRIVATE_TAGS:
                return "hard-private"
            if frontmatter.get("publish") is True or frontmatter.get("public_stub") is True:
                return "public"
        return "private"

    def scrub(
        self,
        content: str,
        *,
        target_class: PrivacyClass,
        context: SanitizerContext,
    ) -> tuple[str, list[str]]:
        findings: list[str] = []
        scrubbed = content
        if CANARY_RE.search(scrubbed):
            findings.append("hard_private_canary")
            scrubbed = CANARY_RE.sub("[REDACTED:HARD_PRIVATE_CANARY]", scrubbed)
        if PRIVATE_PATH_RE.search(scrubbed):
            findings.append("hard_private_path")
            if target_class == "public" or context in {
                SanitizerContext.PUBLISH,
                SanitizerContext.GATEWAY_RESPONSE,
                SanitizerContext.LLM_PROMPT,
            }:
                scrubbed = PRIVATE_PATH_RE.sub("[REDACTED:HARD_PRIVATE_PATH]", scrubbed)
        return scrubbed, findings

    def build_bundle(self, *sources: Source | dict[str, Any], purpose: str = "", instructions: str = "") -> ContextBundle:
        normalized: list[Source] = []
        for source in sources:
            if isinstance(source, Source):
                normalized.append(source)
                continue
            rel_path = str(source.get("rel_path") or "")
            frontmatter = dict(source.get("frontmatter") or {})
            normalized.append(
                Source(
                    rel_path=rel_path,
                    privacy_class=self.classify(rel_path, frontmatter),
                    title=source.get("title"),
                    frontmatter=frontmatter,
                    content=str(source.get("content") or ""),
                )
            )
        return ContextBundle(normalized, purpose=purpose, instructions=instructions)


DEFAULT_SANITIZER = Sanitizer()


def classify_page(rel_path: str, frontmatter: dict[str, Any] | None = None) -> PrivacyClass:
    return DEFAULT_SANITIZER.classify(rel_path, frontmatter)
