"""Phase 2.5 Step 8 — Messages helper backed by ~/.kublai/messages.jsonl."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class MessagesStore:
    def __init__(self, jsonl_path: str | Path):
        self.jsonl_path = Path(jsonl_path).expanduser()

    def append(self, record: dict[str, Any]) -> None:
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_recent(self, *, human_id: str | None = None,
                    limit: int = 100, offset: int = 0,
                    topic: str | None = None) -> list[dict[str, Any]]:
        if not self.jsonl_path.exists():
            return []
        out: list[dict[str, Any]] = []
        # Read in reverse for newest-first.
        try:
            lines = self.jsonl_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        skipped = 0
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if human_id and rec.get("humanId") != human_id and rec.get("human_id") != human_id:
                continue
            if topic and topic not in (rec.get("topics") or []):
                continue
            if skipped < offset:
                skipped += 1
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out

    def search(self, query: str, *, human_id: str | None = None,
               limit: int = 50, offset: int = 0,
               scope: str | None = None) -> list[dict[str, Any]]:
        """Phase 5 — fulltext-equivalent substring search across messages.jsonl.

        Replaces server.js Neo4j ``message_text_search`` fulltext index. Splits
        ``query`` into whitespace-separated terms and requires every term to
        appear (case-insensitive) in any of the searched fields:
        ``content_scrubbed``, ``contentScrubbed``, ``summary``, ``topics``.

        ``scope`` (optional) filters by an explicit ``scope`` field on records,
        if present (forward-compat hook; ignored when records lack the field).
        """
        if not self.jsonl_path.exists():
            return []
        if not query or not query.strip():
            return []
        terms = [t.lower() for t in query.split() if t.strip()]
        if not terms:
            return []
        try:
            lines = self.jsonl_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        out: list[dict[str, Any]] = []
        skipped = 0
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if human_id and rec.get("humanId") != human_id and rec.get("human_id") != human_id:
                continue
            if scope is not None and rec.get("scope") != scope:
                continue
            haystack_parts: list[str] = []
            for key in ("content_scrubbed", "contentScrubbed", "summary"):
                v = rec.get(key)
                if isinstance(v, str):
                    haystack_parts.append(v)
            topics = rec.get("topics")
            if isinstance(topics, list):
                haystack_parts.append(" ".join(str(t) for t in topics))
            haystack = " ".join(haystack_parts).lower()
            if not all(term in haystack for term in terms):
                continue
            if skipped < offset:
                skipped += 1
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out
