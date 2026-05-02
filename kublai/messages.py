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
