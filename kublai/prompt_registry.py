"""Prompt template loading and hashing for Kublai LLM calls."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class PromptRegistryError(FileNotFoundError):
    """Raised when a prompt template cannot be resolved."""


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    path: Path
    text: str

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class PromptRegistry:
    def __init__(self, prompt_root: str | Path):
        self.prompt_root = Path(prompt_root).expanduser()

    def load(self, name: str) -> PromptTemplate:
        safe_name = name.strip().replace("..", "")
        path = self.prompt_root / f"{safe_name}.md"
        if not path.exists():
            raise PromptRegistryError(str(path))
        return PromptTemplate(name=safe_name, path=path, text=path.read_text(encoding="utf-8"))

    def hash(self, name: str) -> str:
        return self.load(name).hash
