"""Typed markdown write helpers for the Kublai brain wiki."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ALLOWED_SUBTREES = (
    "operations/reflections",
    "operations/decisions",
    "operations/rsi-cycles",
    "operations/capabilities",
    "operations/tasks",
    "agents",
)


class KnowledgeError(Exception):
    """Base exception for knowledge write failures."""


class PathPolicyError(KnowledgeError):
    """Raised when a write attempts to escape the allowed wiki subtrees."""


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "item"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def normalize_body(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.rstrip().splitlines())


class KnowledgeStore:
    """Writes operational knowledge pages under a configured wiki root."""

    def __init__(self, wiki_root: str | Path):
        self.wiki_root = Path(wiki_root).expanduser().resolve()
        self.wiki_root.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.wiki_root / ".knowledge-write.lock"

    @contextmanager
    def write_lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock_file:
            try:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass

    def record_reflection(
        self,
        *,
        agent: str,
        body: str,
        reflection_id: str | None = None,
        status: str = "active",
        tags: list[str] | None = None,
    ) -> Path:
        reflection_id = reflection_id or str(uuid.uuid4())
        date = utc_date()
        return self.write_page(
            f"operations/reflections/{date}-{slugify(agent)}-{slugify(reflection_id)}.md",
            {
                "type": "reflection",
                "reflection_id": reflection_id,
                "agent": agent,
                "status": status,
                "created": date,
                "updated": date,
                "sources": 1,
                "tags": tags or ["kublai", "reflection"],
            },
            body,
            typed_field="reflection_id",
            typed_id=reflection_id,
            scan_existing=False,
        )

    def record_decision(
        self,
        *,
        agent: str,
        title: str,
        body: str,
        decision_id: str | None = None,
        status: str = "active",
    ) -> Path:
        decision_id = decision_id or str(uuid.uuid4())
        date = utc_date()
        return self.write_page(
            f"operations/decisions/{date}-{slugify(decision_id)}.md",
            {
                "type": "decision",
                "decision_id": decision_id,
                "agent": agent,
                "title": title,
                "status": status,
                "created": date,
                "updated": date,
                "sources": 1,
                "tags": ["kublai", "decision"],
            },
            body,
            typed_field="decision_id",
            typed_id=decision_id,
            scan_existing=False,
        )

    def record_capability(
        self,
        *,
        capability_id: str,
        title: str,
        body: str,
        status: str = "active",
        learned_by: str | None = None,
    ) -> Path:
        date = utc_date()
        frontmatter: dict[str, Any] = {
            "type": "capability",
            "capability_id": capability_id,
            "title": title,
            "status": status,
            "created": date,
            "updated": date,
            "sources": 1,
            "tags": ["kublai", "capability"],
        }
        if learned_by:
            frontmatter["learned_by"] = learned_by
        return self.write_page(
            f"operations/capabilities/{slugify(capability_id)}.md",
            frontmatter,
            body,
            typed_field="capability_id",
            typed_id=capability_id,
            scan_existing=False,
        )

    def record_completed_task(
        self,
        *,
        task_id: str,
        agent: str,
        delegated_by: str,
        completed_at_ms: int,
        deliverable: str,
        results: dict[str, Any] | None = None,
        historical: bool = False,
    ) -> Path:
        completed = datetime.fromtimestamp(completed_at_ms / 1000, timezone.utc)
        date = completed.date().isoformat()
        rel_path = f"operations/tasks/{completed:%Y/%m}/task-{slugify(task_id)}.md"
        body = (
            f"# Task {task_id}\n\n"
            f"## Deliverable\n\n{deliverable}\n\n"
            f"## Results\n\n```yaml\n{yaml.safe_dump(results or {}, sort_keys=True)}```\n"
        )
        return self.write_page(
            rel_path,
            {
                "type": "task",
                "task_id": task_id,
                "status": "completed",
                "agent": agent,
                "delegated_by": delegated_by,
                "created": date,
                "updated": date,
                "sources": 1,
                "historical": historical,
                "completion_body_hash": body_hash(body),
                "tags": ["kublai", "task"],
            },
            body,
            typed_field="task_id",
            typed_id=task_id,
            scan_existing=False,
        )

    def update_agent_profile(self, *, agent: str, body: str, status: str = "active") -> Path:
        date = utc_date()
        return self.write_page(
            f"agents/{slugify(agent)}.md",
            {
                "type": "agent",
                "agent_id": slugify(agent),
                "status": status,
                "created": date,
                "updated": date,
                "sources": 1,
                "tags": ["kublai", "agent"],
            },
            body,
            typed_field="agent_id",
            typed_id=slugify(agent),
            scan_existing=False,
        )

    def write_page(
        self,
        rel_path: str | Path,
        frontmatter: dict[str, Any],
        body: str,
        *,
        typed_field: str,
        typed_id: str,
        scan_existing: bool = True,
    ) -> Path:
        target = self.resolve_allowed(rel_path)
        content = self.render(frontmatter, body)
        if target.exists():
            parsed = self.read_frontmatter(target)
            if parsed.get(typed_field) == typed_id:
                if target.read_text(encoding="utf-8") != content:
                    self.atomic_write(target, content)
                return target
            raise KnowledgeError(f"target path exists for a different {typed_field}: {target}")
        if scan_existing:
            existing = self.find_by_frontmatter(typed_field, typed_id)
            if existing is not None:
                return existing
        target.parent.mkdir(parents=True, exist_ok=True)
        self.atomic_write(target, content)
        return target

    def atomic_write(self, target: Path, content: str) -> None:
        with self.write_lock():
            fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    tmp.write(content)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_name, target)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)

    def resolve_allowed(self, rel_path: str | Path) -> Path:
        rel = Path(rel_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise PathPolicyError(f"invalid wiki path: {rel_path}")
        rel_text = rel.as_posix()
        if not any(rel_text == prefix or rel_text.startswith(prefix + "/") for prefix in ALLOWED_SUBTREES):
            raise PathPolicyError(f"path outside allowed operational subtrees: {rel_path}")
        target = (self.wiki_root / rel).resolve()
        if self.wiki_root not in target.parents:
            raise PathPolicyError(f"path escapes wiki root: {rel_path}")
        return target

    def find_by_frontmatter(self, field: str, value: str) -> Path | None:
        for path in self.wiki_root.rglob("*.md"):
            if "_archive" in path.parts:
                continue
            parsed = self.read_frontmatter(path)
            if parsed.get(field) == value:
                return path
        return None

    @staticmethod
    def read_frontmatter(path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {}
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---\n", 4)
        if end < 0:
            return {}
        data = yaml.safe_load(text[4:end]) or {}
        return data if isinstance(data, dict) else {}

    def list_proposals(
        self,
        *,
        status: str | None = None,
        since_ms: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List wiki pages that represent proposals.

        Proposals live as wiki pages with frontmatter ``type: proposal`` (or
        with ``proposal`` in the tags list as a legacy fallback). Optional
        ``status`` filters on frontmatter ``status``; ``since_ms`` filters by
        page mtime so callers can poll for recent activity. Returns a flat
        list of ``{rel_path, title, type, status, tags, updated, created,
        mtime_ms}`` summaries — no body, intentionally light.

        Replaces the LLM-emitted ``MATCH (p:Proposal) ...`` Cypher path used
        by ``kurultai-proposal-decree-review/SKILL.md``.
        """
        results: list[dict[str, Any]] = []
        for md in self.wiki_root.rglob("*.md"):
            rel = md.relative_to(self.wiki_root).as_posix()
            if rel.startswith("hard-private/"):
                continue
            try:
                fm = _read_frontmatter(md.read_text(encoding="utf-8"))
            except Exception:
                continue
            tags = fm.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            is_proposal = (fm.get("type") == "proposal") or ("proposal" in tags)
            if not is_proposal:
                continue
            if status is not None and fm.get("status") != status:
                continue
            try:
                mtime_ms = int(md.stat().st_mtime * 1000)
            except OSError:
                continue
            if since_ms is not None and mtime_ms < since_ms:
                continue
            results.append({
                "rel_path": rel,
                "title": fm.get("title") or md.stem,
                "type": fm.get("type"),
                "status": fm.get("status"),
                "tags": tags,
                "updated": fm.get("updated"),
                "created": fm.get("created"),
                "mtime_ms": mtime_ms,
            })
        results.sort(key=lambda r: r["mtime_ms"], reverse=True)
        return results[:limit]

    def list_by_tag(
        self,
        *,
        tag: str,
        privacy_scope: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for md in self.wiki_root.rglob("*.md"):
            rel = md.relative_to(self.wiki_root).as_posix()
            is_hard = rel.startswith("hard-private/")
            if privacy_scope == "public" and is_hard:
                continue
            if privacy_scope == "hard-private" and not is_hard:
                continue
            try:
                fm = _read_frontmatter(md.read_text(encoding="utf-8"))
            except Exception:
                continue
            tags = fm.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            if tag in tags:
                results.append({
                    "rel_path": rel,
                    "title": fm.get("title") or md.stem,
                    "type": fm.get("type"),
                    "status": fm.get("status"),
                    "tags": tags,
                })
                if len(results) >= limit:
                    break
        return results

    @staticmethod
    def render(frontmatter: dict[str, Any], body: str) -> str:
        yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
        return f"---\n{yaml_text}\n---\n\n{normalize_body(body)}\n"

import re as _re_kt

_KT_FRONTMATTER_RE = _re_kt.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", _re_kt.DOTALL)


def _read_frontmatter(text: str) -> dict[str, Any]:
    m = _KT_FRONTMATTER_RE.match(text)
    if not m:
        return {}
    fm: dict[str, Any] = {}
    current_key = None
    for line in m.group(1).splitlines():
        if not line.strip():
            current_key = None
            continue
        if line.startswith(" ") and current_key is not None and line.lstrip().startswith("- "):
            fm.setdefault(current_key, []).append(line.lstrip()[2:].strip())
            continue
        if ": " in line:
            k, _, v = line.partition(": ")
            k = k.strip()
            v = v.strip()
            if v == "":
                fm[k] = []
                current_key = k
            elif v.startswith("[") and v.endswith("]"):
                inner = v[1:-1].strip()
                fm[k] = [x.strip() for x in inner.split(",")] if inner else []
                current_key = None
            else:
                fm[k] = v.strip("\"\'")
                current_key = None
    return fm
