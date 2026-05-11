"""Kublai brain v4 public workflow surface.

The v4 layer is intentionally thin: it reuses the existing SQLite indexes,
wiki writer, sanitizer, and telemetry store, while making privacy decisions
explicit at every public boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .knowledge import KnowledgeStore, normalize_body, slugify
from .sanitizer import CANARY_RE, DEFAULT_SANITIZER, SanitizerContext

HARD_PRIVATE_CANARY = "KUBLAI_HARD_PRIVATE_CANARY_SYNTHETIC_DO_NOT_LEAK"
DEFAULT_PUBLIC_ROOT = Path(os.environ.get("KUBLAI_BRAIN_PUBLIC_ROOT", str(Path.home() / "brain-public")))
COMMAND_REGISTRY = (
    "wiki",
    "save",
    "ask",
    "capture",
    "ingest",
    "process-inbox",
    "connect",
    "brief",
    "write",
    "publish",
    "research",
    "lint",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bage-secret-key-[A-Za-z0-9]+\b"),
)


class V4WorkflowError(ValueError):
    """Raised for v4 workflow validation errors."""


class V4PrivacyError(V4WorkflowError):
    """Raised when a request tries to cross a privacy boundary."""


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    parsed = yaml.safe_load(text[4:end]) or {}
    return (parsed if isinstance(parsed, dict) else {}), text[end + 5 :]


def _scrub_public(content: str, *, context: SanitizerContext) -> tuple[str, list[str]]:
    return DEFAULT_SANITIZER.scrub(content, target_class="public", context=context)


def _summary(text: str, *, chars: int = 480) -> str:
    squashed = re.sub(r"\s+", " ", text).strip()
    return squashed[:chars]


class V4WorkflowService:
    def __init__(self, service: Any):
        self.service = service
        self.wiki_root = Path(service.wiki_root)
        self.manifest_path = self.wiki_root / "raw" / "v4-source-manifest.jsonl"
        self.graphify_queue_path = self.wiki_root / "raw" / "graphify-queue.jsonl"

    def command_registry(self) -> list[str]:
        return list(COMMAND_REGISTRY)

    def public_search(self, *, query: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.service.index.search(query=query, limit=limit)
        safe_rows: list[dict[str, Any]] = []
        for row in rows:
            fm = row.get("frontmatter") or {}
            if DEFAULT_SANITIZER.classify(str(row.get("rel_path") or ""), fm) != "public":
                continue
            snippet, findings = _scrub_public(str(row.get("body_text") or ""), context=SanitizerContext.GATEWAY_RESPONSE)
            safe_rows.append(
                {
                    "rel_path": row["rel_path"],
                    "title": row.get("title") or row.get("id"),
                    "type": row.get("type"),
                    "updated": row.get("updated"),
                    "score": row.get("score"),
                    "snippet": _summary(snippet),
                    "sanitizer_findings": findings,
                }
            )
        return safe_rows[:limit]

    def public_get(self, *, rel_path: str) -> dict[str, Any]:
        target = self._resolve_wiki_path(rel_path)
        fm, body = split_frontmatter(target.read_text(encoding="utf-8", errors="ignore"))
        if DEFAULT_SANITIZER.classify(rel_path, fm) != "public":
            raise V4PrivacyError("HTTPS/public get only serves explicit-public pages")
        safe_body, findings = _scrub_public(body, context=SanitizerContext.GATEWAY_RESPONSE)
        return {
            "rel_path": rel_path,
            "frontmatter": self._public_frontmatter(fm),
            "body": safe_body,
            "sanitizer_findings": findings,
        }

    def public_pages(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "rel_path": row["rel_path"],
                "title": row.get("title") or row.get("id"),
                "type": row.get("type"),
                "updated": row.get("updated"),
            }
            for row in self.service.index.list_nodes(limit=limit)
            if DEFAULT_SANITIZER.classify(row["rel_path"], row.get("frontmatter") or {}) == "public"
        ]

    def public_tags(self, *, limit: int = 200) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in self.service.index.list_nodes(limit=max(limit * 20, 500)):
            fm = row.get("frontmatter") or {}
            if DEFAULT_SANITIZER.classify(row["rel_path"], fm) != "public":
                continue
            tags = fm.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            for tag in tags:
                counts[str(tag)] = counts.get(str(tag), 0) + 1
        return [{"tag": tag, "count": count} for tag, count in sorted(counts.items())[:limit]]

    def public_stub_rebuild(self) -> dict[str, Any]:
        indexed = self.service.reindex()
        stats = self.service.verify_index()
        return {"indexed": indexed, "stats": stats}

    def ask(self, *, query: str, privacy_scope: str = "public", limit: int = 5, request_id: str | None = None) -> dict[str, Any]:
        self._require_public_scope(privacy_scope)
        started = time.monotonic()
        rows = self.public_search(query=query, limit=limit)
        answer = "No public context matched that query."
        if rows:
            citations = ", ".join(f"[[{Path(row['rel_path']).stem}]]" for row in rows[:3])
            answer = f"Public answer draft from indexed context. Relevant public pages: {citations}."
        result = {"answer": answer, "citations": rows, "privacy_scope": "public"}
        self._record_command("ask", privacy_scope="public", dry_run=True, source_count=len(rows), duration_s=time.monotonic() - started, request_id=request_id)
        return result

    def capture_dry_run(self, **params: Any) -> dict[str, Any]:
        return self._capture_plan(kind="capture", dry_run=True, **params)

    def capture_apply(self, **params: Any) -> dict[str, Any]:
        plan = self._capture_plan(kind="capture", dry_run=False, **params)
        self._write_generated_page(plan["rel_path"], plan["frontmatter"], plan["body"])
        self._append_manifest(plan)
        self._enqueue_graphify(plan["rel_path"], reason="capture.apply")
        if plan["privacy_class"] == "public":
            self.service.reindex()
        self._record_command("capture", privacy_scope=plan["privacy_class"], dry_run=False, source_count=1, output_path=plan["rel_path"], request_id=params.get("request_id"))
        plan["written"] = True
        return plan

    def ingest_dry_run(self, **params: Any) -> dict[str, Any]:
        return self._capture_plan(kind="ingest", dry_run=True, **params)

    def ingest_apply(self, **params: Any) -> dict[str, Any]:
        plan = self._capture_plan(kind="ingest", dry_run=False, **params)
        self._write_generated_page(plan["rel_path"], plan["frontmatter"], plan["body"])
        self._append_manifest(plan)
        self._enqueue_graphify(plan["rel_path"], reason="ingest.apply")
        if plan["privacy_class"] == "public":
            self.service.reindex()
        self._record_command("ingest", privacy_scope=plan["privacy_class"], dry_run=False, source_count=1, output_path=plan["rel_path"], request_id=params.get("request_id"))
        plan["written"] = True
        return plan

    def publish_dry_run(self, *, output_root: str | Path | None = None, request_id: str | None = None) -> dict[str, Any]:
        started = time.monotonic()
        output_root = Path(output_root) if output_root else DEFAULT_PUBLIC_ROOT
        files: list[dict[str, Any]] = []
        findings: list[dict[str, str]] = []
        for md in sorted(self.wiki_root.rglob("*.md")):
            if ".git" in md.parts:
                continue
            rel = md.relative_to(self.wiki_root).as_posix()
            fm, body = split_frontmatter(md.read_text(encoding="utf-8", errors="ignore"))
            if DEFAULT_SANITIZER.classify(rel, fm) != "public":
                continue
            safe_body, sanitizer_findings = _scrub_public(body, context=SanitizerContext.PUBLISH)
            page_findings = self._publish_findings(rel, fm, body, sanitizer_findings)
            findings.extend({"rel_path": rel, "finding": finding} for finding in page_findings)
            files.append(
                {
                    "rel_path": rel,
                    "output_path": str(output_root / rel),
                    "frontmatter": self._public_frontmatter(fm),
                    "body_hash": hashlib.sha256(safe_body.encode("utf-8")).hexdigest(),
                    "findings": page_findings,
                }
            )
        result = {"ok": not findings, "dry_run": True, "output_root": str(output_root), "files": files, "findings": findings}
        self._record_command("publish", privacy_scope="public", dry_run=True, source_count=len(files), duration_s=time.monotonic() - started, error_code=None if result["ok"] else "sanitizer_findings", request_id=request_id)
        return result

    def publish_apply(self, *, output_root: str | Path | None = None, request_id: str | None = None) -> dict[str, Any]:
        dry = self.publish_dry_run(output_root=output_root, request_id=request_id)
        if not dry["ok"]:
            raise V4WorkflowError("publish.apply requires zero sanitizer findings")
        output_root = Path(dry["output_root"])
        for item in dry["files"]:
            source = self._resolve_wiki_path(item["rel_path"])
            fm, body = split_frontmatter(source.read_text(encoding="utf-8", errors="ignore"))
            safe_body, _ = _scrub_public(body, context=SanitizerContext.PUBLISH)
            target = output_root / item["rel_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(KnowledgeStore.render(self._public_frontmatter(fm), safe_body), encoding="utf-8")
        self._record_command("publish", privacy_scope="public", dry_run=False, source_count=len(dry["files"]), output_path=str(output_root), request_id=request_id)
        return dry | {"dry_run": False, "written": len(dry["files"])}

    def research_public_dossier(self, *, query: str, lenses: list[str] | None = None, limit: int = 6, request_id: str | None = None) -> dict[str, Any]:
        lenses = lenses or ["evidence", "risk", "architecture"]
        contexts = []
        for lens in lenses:
            rows = self.public_search(query=f"{query} {lens}", limit=limit)
            contexts.append({"lens": lens, "context_count": len(rows), "citations": rows})
        dossier = {
            "query": query,
            "privacy_scope": "public",
            "lenses": contexts,
            "synthesis": "Public-only dossier assembled from explicit-public index rows.",
            "contradictions": [],
            "confidence": "medium" if any(item["context_count"] for item in contexts) else "low",
            "needs_private_review": [],
        }
        self._record_command("research", privacy_scope="public", dry_run=True, source_count=sum(item["context_count"] for item in contexts), request_id=request_id)
        return dossier

    def write_dry_run(self, *, topic: str, request_id: str | None = None) -> dict[str, Any]:
        exemplars = self._public_voice_exemplars()
        rows = self.public_search(query=topic, limit=5)
        body = (
            f"# {topic}\n\n"
            "This is a public-context draft. It uses only explicit-public wiki context "
            "and public voice exemplars, and it needs human review before publication.\n"
        )
        lint = self._style_lint(body, citations=rows)
        result = {"topic": topic, "draft": body, "exemplar_count": len(exemplars), "citations": rows, "lint": lint, "dry_run": True}
        self._record_command("write", privacy_scope="public", dry_run=True, source_count=len(rows) + len(exemplars), request_id=request_id)
        return result

    def lint(self) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        counts = {"public": 0, "private": 0, "hard-private": 0}
        for md in sorted(self.wiki_root.rglob("*.md")):
            if ".git" in md.parts:
                continue
            rel = md.relative_to(self.wiki_root).as_posix()
            fm, body = split_frontmatter(md.read_text(encoding="utf-8", errors="ignore"))
            privacy = DEFAULT_SANITIZER.classify(rel, fm)
            counts[privacy] = counts.get(privacy, 0) + 1
            if rel not in {"index.md", "home.md", "log.md"} and not fm:
                issues.append({"rel_path": rel, "issue": "missing_frontmatter"})
            if privacy == "public":
                for finding in self._publish_findings(rel, fm, body, []):
                    issues.append({"rel_path": rel, "issue": finding})
        public_canary_hits = self.public_search(query=HARD_PRIVATE_CANARY, limit=3)
        if public_canary_hits:
            issues.append({"rel_path": "public-index", "issue": "hard_private_canary_public_index"})
        return {"ok": not issues, "counts": counts, "issues": issues, "command_registry": self.command_registry()}

    def audit_private_summary(self, *, limit: int = 20) -> dict[str, Any]:
        path = Path(self.service.private_access_log)
        if not path.exists():
            return {"ok": True, "events": 0, "recent": []}
        lines = [line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        recent: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            recent.append({"ts": record.get("ts"), "action": record.get("action"), "requester": record.get("requester"), "result_count": len(record.get("rel_paths") or [])})
        return {"ok": True, "events": len(lines), "recent": recent}

    def doctor_full(self) -> dict[str, Any]:
        lint = self.lint()
        public_stats = self.service.verify_index()
        private_stats = self.service.verify_private_index()
        graphify = {"exists": self.graphify_queue_path.exists(), "pending": self._jsonl_count(self.graphify_queue_path)}
        private_audit = self.audit_private_summary(limit=1)
        checks = {
            "command_registry": set(COMMAND_REGISTRY).issubset(set(self.command_registry())),
            "public_index_ok": bool(public_stats.get("ok")),
            "private_index_ok": bool(private_stats.get("ok")),
            "canary_absent_public": not self.public_search(query=HARD_PRIVATE_CANARY, limit=1),
            "lint_boundary_clean": not any(
                issue.get("issue") != "missing_frontmatter"
                for issue in lint.get("issues", [])
            ),
            "graphify_queue_writable": self._jsonl_parent_writable(self.graphify_queue_path),
            "private_audit_log_readable": bool(private_audit.get("ok")),
        }
        return {"ok": all(checks.values()), "checks": checks, "lint": lint, "public_index": public_stats, "private_index": private_stats, "graphify_queue": graphify}

    def _capture_plan(self, *, kind: str, content: str, title: str | None = None, source: str | None = None, frontmatter: dict[str, Any] | None = None, dry_run: bool, privacy_scope: str | None = None, request_id: str | None = None) -> dict[str, Any]:
        if not content.strip():
            raise V4WorkflowError(f"{kind} requires content")
        fm = dict(frontmatter or {})
        date = utc_date()
        title = title or f"{kind.title()} {date}"
        fm.setdefault("type", "capture")
        fm.setdefault("status", "pending-review")
        fm.setdefault("created", date)
        fm["updated"] = date
        fm.setdefault("sources", 1)
        fm.setdefault("tags", ["kublai", kind])
        if source:
            fm.setdefault("source_label", _summary(source, chars=120))
        requested_scope = privacy_scope or DEFAULT_SANITIZER.classify("", fm)
        privacy_class = DEFAULT_SANITIZER.classify("", fm)
        if requested_scope in {"private", "hard-private"} and privacy_class == "public":
            privacy_class = requested_scope
        if privacy_class == "private":
            privacy_class = "hard-private"
        rel_path = self._generated_rel_path(kind, title, privacy_class)
        body = (
            f"# {title}\n\n"
            f"{normalize_body(content)}\n\n"
            "## Related\n\n"
            "- [[brain-service]]\n"
            "- [[kublai]]\n"
        )
        safe_body, findings = DEFAULT_SANITIZER.scrub(body, target_class="public" if privacy_class == "public" else "private", context=SanitizerContext.MCP_RESPONSE)
        if findings and privacy_class == "public":
            privacy_class = "hard-private"
            rel_path = self._generated_rel_path(kind, title, privacy_class)
        plan = {
            "ok": True,
            "kind": kind,
            "dry_run": dry_run,
            "privacy_class": privacy_class,
            "rel_path": rel_path,
            "frontmatter": fm,
            "body": safe_body if privacy_class == "public" else body,
            "source_count": 1 if source or content else 0,
            "sanitizer_findings": findings,
            "request_id": request_id or f"v4-{uuid.uuid4().hex}",
            "written": False,
        }
        self._record_command(kind, privacy_scope=privacy_class, dry_run=dry_run, source_count=plan["source_count"], output_path=rel_path, request_id=plan["request_id"])
        return plan

    def _generated_rel_path(self, kind: str, title: str, privacy_class: str) -> str:
        prefix = "hard-private/inbox" if privacy_class == "hard-private" else "captures"
        return f"{prefix}/{utc_date()}-{slugify(title)}.md"

    def _write_generated_page(self, rel_path: str, frontmatter: dict[str, Any], body: str) -> None:
        target = self._resolve_wiki_path(rel_path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.service.knowledge.atomic_write(target, KnowledgeStore.render(frontmatter, body))

    def _append_manifest(self, plan: dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": plan["kind"],
            "rel_path": plan["rel_path"],
            "privacy_class": plan["privacy_class"],
            "body_hash": hashlib.sha256(plan["body"].encode("utf-8")).hexdigest(),
            "request_id": plan.get("request_id"),
        }
        with self.manifest_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _enqueue_graphify(self, rel_path: str, *, reason: str) -> None:
        self.graphify_queue_path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now(timezone.utc).isoformat(), "rel_path": rel_path, "reason": reason}
        with self.graphify_queue_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _resolve_wiki_path(self, rel_path: str, *, must_exist: bool = True) -> Path:
        rel = Path(rel_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise V4WorkflowError(f"invalid wiki path: {rel_path}")
        target = (self.wiki_root / rel).resolve()
        if self.wiki_root != target and self.wiki_root not in target.parents:
            raise V4WorkflowError(f"path escapes wiki root: {rel_path}")
        if must_exist and not target.exists():
            raise FileNotFoundError(rel_path)
        return target

    def _public_frontmatter(self, frontmatter: dict[str, Any]) -> dict[str, Any]:
        allowed = {"type", "title", "status", "created", "updated", "sources", "tags", "publish", "public_stub", "voice_exemplar"}
        return {key: self._json_safe(value) for key, value in frontmatter.items() if key in allowed}

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return str(value)

    def _publish_findings(self, rel_path: str, frontmatter: dict[str, Any], body: str, sanitizer_findings: list[str]) -> list[str]:
        findings = list(sanitizer_findings)
        if DEFAULT_SANITIZER.classify(rel_path, frontmatter) != "public":
            findings.append("not_explicit_public")
        if CANARY_RE.search(body):
            findings.append("hard_private_canary")
        if "hard-private/" in body:
            findings.append("hard_private_path")
        for pattern in SECRET_PATTERNS:
            if pattern.search(body):
                findings.append("secret_like_value")
                break
        if not body.strip():
            findings.append("empty_body")
        return sorted(set(findings))

    def _public_voice_exemplars(self) -> list[dict[str, Any]]:
        exemplars = []
        for md in sorted((self.wiki_root / "published").glob("*.md")) if (self.wiki_root / "published").exists() else []:
            fm, body = split_frontmatter(md.read_text(encoding="utf-8", errors="ignore"))
            rel = md.relative_to(self.wiki_root).as_posix()
            if fm.get("voice_exemplar") is True and DEFAULT_SANITIZER.classify(rel, fm) == "public":
                exemplars.append({"rel_path": rel, "title": fm.get("title") or md.stem, "excerpt": _summary(body)})
        return exemplars

    def _style_lint(self, body: str, *, citations: list[dict[str, Any]]) -> dict[str, Any]:
        banned = ["synergy", "leverage", "game-changer"]
        hits = [word for word in banned if re.search(rf"\b{re.escape(word)}\b", body, re.I)]
        return {"ok": not hits and bool(citations), "banned_words": hits, "citation_count": len(citations)}

    def _record_command(self, command: str, *, privacy_scope: str, dry_run: bool, source_count: int, duration_s: float | None = None, output_path: str | None = None, error_code: str | None = None, request_id: str | None = None) -> None:
        details = {
            "command": command,
            "privacy_class": privacy_scope,
            "dry_run": dry_run,
            "source_count": source_count,
            "output_path": output_path,
            "duration_ms": int((duration_s or 0) * 1000),
            "error_code": error_code,
            "llm_destination_class": "external-public-only" if privacy_scope == "public" else "local-only",
            "request_id": request_id,
        }
        try:
            self.service.telemetry.record_audit_event(actor="kublai.v4", action=f"command.{command}", decision="apply" if not dry_run else "dry_run", details=details, resource=output_path)
        except Exception:
            pass

    def _require_public_scope(self, privacy_scope: str) -> None:
        if privacy_scope != "public":
            raise V4PrivacyError("external/public workflow accepts only privacy_scope=public")

    def _jsonl_count(self, path: Path) -> int:
        if not path.exists():
            return 0
        return sum(1 for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())

    def _jsonl_parent_writable(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        return os.access(path.parent, os.W_OK)
