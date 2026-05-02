"""Localhost-only brain service for Phase 1 fixtures.

The daemon owns wiki indexing, materialization sweeps, SQLite backups, health,
and a small Unix-socket JSON RPC surface for same-host JS clients.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socketserver
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .knowledge import KnowledgeStore
from .monitoring import health_snapshot
from .telemetry import DEFAULT_LEASE_TTL_MS, NoPendingTaskError, StaleClaimError, TelemetryStore
from .calendar import CalendarError, CalendarService, CalendarStore, GcalcliClient
from .humans import HumansStore
from .messages import MessagesStore


class CapabilityError(RuntimeError):
    """Raised when runtime prerequisites are not present."""


class BrainIndex:
    """Rebuildable SQLite index over markdown pages."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        _load_sqlite_vec(conn)
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            vector_ddl = (
                "CREATE VIRTUAL TABLE IF NOT EXISTS node_vec USING vec0(embedding float[384]);"
                if _sqlite_vec_loaded(conn)
                else """
                CREATE TABLE IF NOT EXISTS node_vec (
                  rowid INTEGER PRIMARY KEY,
                  embedding TEXT NOT NULL CHECK(json_valid(embedding))
                ) STRICT;
                """
            )
            conn.executescript(
                f"""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS nodes (
                  node_pk INTEGER PRIMARY KEY,
                  id TEXT UNIQUE NOT NULL,
                  type TEXT NOT NULL,
                  rel_path TEXT UNIQUE NOT NULL,
                  title TEXT,
                  status TEXT,
                  agent TEXT,
                  typed_id TEXT,
                  created TEXT NOT NULL,
                  updated TEXT NOT NULL,
                  frontmatter TEXT NOT NULL CHECK(json_valid(frontmatter)),
                  body_hash TEXT NOT NULL,
                  body_text TEXT NOT NULL,
                  mtime_ns INTEGER NOT NULL
                ) STRICT;
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                  title, body_text, content='nodes', content_rowid='node_pk'
                );
                {vector_ddl}
                CREATE TABLE IF NOT EXISTS index_meta (
                  key TEXT PRIMARY KEY,
                  value TEXT
                ) STRICT;
                INSERT OR REPLACE INTO index_meta VALUES
                  ('embedding_model', 'all-MiniLM-L6-v2'),
                  ('embedding_dim', '384'),
                  ('embedding_distance', 'cosine'),
                  ('vector_backend', '{'sqlite-vec vec0' if _sqlite_vec_loaded(conn) else 'json-fallback'}'),
                  ('schema_version', '1');
                """
            )

    def reindex(self, wiki_root: str | Path) -> int:
        import hashlib

        from .knowledge import KnowledgeStore

        wiki_root = Path(wiki_root).resolve()
        count = 0
        with self.connect() as conn:
            conn.execute("DELETE FROM node_vec")
            conn.execute("DELETE FROM nodes_fts")
            conn.execute("DELETE FROM nodes")
            for path in sorted(wiki_root.rglob("*.md")):
                if ".git" in path.parts:
                    continue
                rel_path = path.relative_to(wiki_root).as_posix()
                fm = KnowledgeStore.read_frontmatter(path)
                body = _body_without_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
                node_id = rel_path.removesuffix(".md")
                typed_id = _first_present(
                    fm,
                    "task_id",
                    "reflection_id",
                    "decision_id",
                    "capability_id",
                    "rsi_id",
                    "agent_id",
                )
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                row = conn.execute(
                    """
                    INSERT INTO nodes (
                      id, type, rel_path, title, status, agent, typed_id,
                      created, updated, frontmatter, body_hash, body_text, mtime_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    RETURNING node_pk
                    """,
                    (
                        node_id,
                        str(fm.get("type", "unknown")),
                        rel_path,
                        str(fm.get("title", node_id)),
                        str(fm.get("status", "")),
                        str(fm.get("agent", "")),
                        typed_id,
                        str(fm.get("created", "")),
                        str(fm.get("updated", "")),
                        json.dumps(fm, sort_keys=True, default=str),
                        digest,
                        body,
                        path.stat().st_mtime_ns,
                    ),
                ).fetchone()
                node_pk = int(row["node_pk"])
                conn.execute(
                    "INSERT INTO nodes_fts(rowid, title, body_text) VALUES (?, ?, ?)",
                    (node_pk, str(fm.get("title", node_id)), body),
                )
                conn.execute(
                    "INSERT INTO node_vec(rowid, embedding) VALUES (?, ?)",
                    (node_pk, json.dumps(_hash_embedding(body))),
                )
                count += 1
        return count

    def vector_orphans(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT count(*) AS n
                FROM node_vec v LEFT JOIN nodes n ON n.node_pk = v.rowid
                WHERE n.node_pk IS NULL
                """
            ).fetchone()
        return int(row["n"])

    def stats(self) -> dict[str, Any]:
        with self.connect() as conn:
            nodes = conn.execute("SELECT count(*) AS n FROM nodes").fetchone()["n"]
            fts = conn.execute("SELECT count(*) AS n FROM nodes_fts").fetchone()["n"]
            vectors = conn.execute("SELECT count(*) AS n FROM node_vec").fetchone()["n"]
            backend = conn.execute("SELECT value FROM index_meta WHERE key = 'vector_backend'").fetchone()
        return {
            "nodes": int(nodes),
            "fts_rows": int(fts),
            "vector_rows": int(vectors),
            "vector_orphans": self.vector_orphans(),
            "vector_backend": backend["value"] if backend else "unknown",
        }

    def get_by_typed_id(self, node_type: str, typed_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, type, rel_path, title, status, agent, typed_id,
                       created, updated, frontmatter, body_hash, body_text
                FROM nodes
                WHERE type = ? AND typed_id = ?
                LIMIT 1
                """,
                (node_type, typed_id),
            ).fetchone()
        return _node_row_to_dict(row) if row else None

    def list_nodes(
        self,
        *,
        node_type: str | None = None,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if node_type:
            clauses.append("type = ?")
            params.append(node_type)
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, type, rel_path, title, status, agent, typed_id,
                       created, updated, frontmatter, body_hash, body_text
                FROM nodes
                {where}
                ORDER BY updated DESC, node_pk DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_node_row_to_dict(row) for row in rows]

    def search(self, query: str, *, node_type: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        clauses = ["nodes_fts MATCH ?"]
        params: list[Any] = [query]
        if node_type:
            clauses.append("n.type = ?")
            params.append(node_type)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT n.id, n.type, n.rel_path, n.title, n.status, n.agent, n.typed_id,
                       n.created, n.updated, n.frontmatter, n.body_hash, n.body_text,
                       bm25(nodes_fts) AS score
                FROM nodes_fts
                JOIN nodes n ON n.node_pk = nodes_fts.rowid
                WHERE {' AND '.join(clauses)}
                ORDER BY score
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_node_row_to_dict(row) | {"score": float(row["score"])} for row in rows]

    def backup_to(self, destination: str | Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        return destination


    def list_by_tag_in_wiki(self, knowledge_store, *, tag, privacy_scope=None, limit=50):
        return knowledge_store.list_by_tag(tag=tag, privacy_scope=privacy_scope, limit=limit)

class BrainService:
    def __init__(
        self,
        wiki_root: str | Path,
        telemetry_db: str | Path,
        index_db: str | Path,
        *,
        gcalcli_path: str | Path | None = None,
        default_calendar: str | None = None,
    ):
        self.wiki_root = Path(wiki_root).expanduser().resolve()
        self.telemetry = TelemetryStore(telemetry_db)
        self.knowledge = KnowledgeStore(self.wiki_root)
        self.index = BrainIndex(index_db)
        # Phase 2.5 Step 6: gcalcli-backed CalendarService.
        cal_store = CalendarStore(telemetry_db)
        gcalcli_bin = (
            str(gcalcli_path)
            if gcalcli_path
            else os.environ.get("GCALCLI_PATH", "/Users/kublai/.brain-migration-venv/bin/gcalcli")
        )
        cal_default = default_calendar or os.environ.get("GCALCLI_DEFAULT_CALENDAR")
        cal_client = GcalcliClient(gcalcli_path=gcalcli_bin, default_calendar=cal_default)
        self.calendar = CalendarService(
            cal_store, cal_client,
            telemetry=self.telemetry,
            default_calendar=cal_default,
        )
        # Phase 2.5 Step 8: humans + messages helpers
        self.humans = HumansStore(self.wiki_root)
        msg_path = os.environ.get("KUBLAI_MESSAGES_JSONL", str(Path.home() / ".kublai/messages.jsonl"))
        self.messages = MessagesStore(msg_path)

    def capability_check(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sqlite_version": sqlite3.sqlite_version,
            "fts5": False,
            "json": False,
            "sqlite_vec": "not_checked",
        }
        with sqlite3.connect(":memory:") as conn:
            options = [row[0] for row in conn.execute("PRAGMA compile_options")]
            result["fts5"] = any("FTS5" in option for option in options)
            result["json"] = conn.execute("SELECT json_valid(?)", ('{"ok": true}',)).fetchone()[0] == 1
            _load_sqlite_vec(conn)
            result["sqlite_vec"] = _sqlite_vec_version(conn) or "unavailable"
        if not result["fts5"] or not result["json"]:
            raise CapabilityError(f"missing SQLite capabilities: {result}")
        return result

    def reindex(self) -> int:
        return self.index.reindex(self.wiki_root)

    def get_node(self, node_type: str, typed_id: str) -> dict[str, Any] | None:
        return self.index.get_by_typed_id(node_type, typed_id)

    def list_nodes(self, **params: Any) -> list[dict[str, Any]]:
        return self.index.list_nodes(**params)

    def search(self, **params: Any) -> list[dict[str, Any]]:
        return self.index.search(**params)

    def sweep(self) -> int:
        count = 0
        for row in self.telemetry.pending_materializations():
            try:
                path = self.knowledge.record_completed_task(
                    task_id=row["id"],
                    agent=row.get("claimed_by") or row.get("assigned_to") or "unknown",
                    delegated_by=row["delegated_by"],
                    completed_at_ms=row["completed_at"],
                    deliverable=row["completion_summary"] or row["description"],
                    results=json.loads(row["results_json"] or "{}"),
                )
                self.telemetry.mark_materialized(row["id"], str(path))
                count += 1
            except Exception as exc:
                self.telemetry.mark_materialization_error(row["id"], str(exc))
        return count

    def health(self) -> dict[str, Any]:
        health = health_snapshot(self.telemetry, self.wiki_root)
        health["vector_orphans"] = self.index.vector_orphans()
        return health

    def backup(self, directory: str | Path) -> dict[str, str]:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        return {
            "telemetry": str(self.telemetry.backup_to(directory / "telemetry.db")),
            "index": str(self.index.backup_to(directory / "brain.db")),
        }

    def checkpoint(self) -> dict[str, Any]:
        telemetry_result: tuple[Any, ...]
        index_result: tuple[Any, ...]
        with self.telemetry.connect() as conn:
            telemetry_result = tuple(conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone())
        with self.index.connect() as conn:
            index_result = tuple(conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone())
        return {"telemetry": telemetry_result, "index": index_result}

    def verify_index(self) -> dict[str, Any]:
        stats = self.index.stats()
        stats["ok"] = (
            stats["nodes"] == stats["fts_rows"]
            and stats["nodes"] == stats["vector_rows"]
            and stats["vector_orphans"] == 0
        )
        return stats

    def replay_dual_write(self, log_path: str | Path | None = None) -> dict[str, Any]:
        """Verify dual-write log records against materialized wiki files.

        Phase 1 only needs the verifier surface. Phase 2 will populate the JSONL
        log during soak; each line may include wiki_path and body_hash fields.
        """
        if log_path is None:
            return {"ok": True, "checked": 0, "mismatches": 0, "missing_log": True}
        path = Path(log_path).expanduser()
        if not path.exists():
            return {"ok": True, "checked": 0, "mismatches": 0, "missing_log": True}
        mismatches: list[dict[str, str]] = []
        checked = 0
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            rel_path = record.get("wiki_path")
            expected_hash = record.get("body_hash")
            if not rel_path or not expected_hash:
                continue
            checked += 1
            target = (self.wiki_root / rel_path).resolve()
            if self.wiki_root not in target.parents or not target.exists():
                mismatches.append({"line": str(lineno), "wiki_path": str(rel_path), "error": "missing"})
                continue
            actual = _sha256(_body_without_frontmatter(target.read_text(encoding="utf-8", errors="ignore")))
            if actual != expected_hash:
                mismatches.append({"line": str(lineno), "wiki_path": str(rel_path), "error": "body_hash"})
        return {"ok": not mismatches, "checked": checked, "mismatches": len(mismatches), "details": mismatches}

    def start_background_tasks(
        self,
        *,
        sweep_interval_s: float = 30.0,
        checkpoint_interval_s: float = 300.0,
    ) -> list[threading.Thread]:
        stop = threading.Event()
        self._background_stop = stop
        threads = [
            threading.Thread(
                target=self._loop_until_stopped,
                args=(stop, sweep_interval_s, self.sweep),
                daemon=True,
                name="brain-service-sweep",
            ),
            threading.Thread(
                target=self._loop_until_stopped,
                args=(stop, checkpoint_interval_s, self.checkpoint),
                daemon=True,
                name="brain-service-checkpoint",
            ),
        ]
        for thread in threads:
            thread.start()
        return threads

    def start_file_watcher(self) -> Any | None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:
            return None

        service = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event: Any) -> None:
                if event.is_directory or not str(event.src_path).endswith(".md"):
                    return
                with contextlib.suppress(Exception):
                    service.reindex()

        observer = Observer()
        observer.schedule(Handler(), str(self.wiki_root), recursive=True)
        observer.start()
        self._watchdog_observer = observer
        return observer

    @staticmethod
    def _loop_until_stopped(stop: threading.Event, interval_s: float, callback: Any) -> None:
        while not stop.wait(interval_s):
            with contextlib.suppress(Exception):
                callback()

    def handle_rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        params = request.get("params") or {}
        try:
            if method == "telemetry.create_task":
                return {"ok": True, "result": self.telemetry.create_task(**params)}
            if method == "telemetry.claim_task":
                claimed = self.telemetry.claim_task(**params)
                return {"ok": True, "result": claimed.__dict__}
            if method == "telemetry.renew_claim":
                renewed = self.telemetry.renew_claim(**params)
                return {"ok": True, "result": renewed.__dict__}
            if method == "telemetry.complete_task":
                self.telemetry.complete_task(**params)
                return {"ok": True, "result": None}
            if method == "telemetry.heartbeat":
                self.telemetry.heartbeat(**params)
                return {"ok": True, "result": None}
            if method == "knowledge.record_reflection":
                path = self.knowledge.record_reflection(**params)
                return {"ok": True, "result": str(path)}
            if method == "knowledge.get":
                return {"ok": True, "result": self.get_node(**params)}
            if method == "knowledge.list":
                return {"ok": True, "result": self.list_nodes(**params)}
            if method == "knowledge.search":
                return {"ok": True, "result": self.search(**params)}
            if method == "knowledge.list_by_tag":
                return {"ok": True, "result": self.index.list_by_tag_in_wiki(self.knowledge, **params)}
            if method == "telemetry.list_reminders":
                return {"ok": True, "result": self.telemetry.list_reminders(**params)}
            if method == "telemetry.list_due_reminders":
                return {"ok": True, "result": self.telemetry.list_due_reminders(**params)}
            if method == "telemetry.create_reminder":
                return {"ok": True, "result": self.telemetry.create_reminder(**params)}
            if method == "telemetry.cancel_reminder":
                return {"ok": True, "result": self.telemetry.cancel_reminder(**params)}
            if method == "telemetry.mark_reminder_sent":
                return {"ok": True, "result": self.telemetry.mark_reminder_sent(**params)}
            if method == "telemetry.record_reminder_error":
                return {"ok": True, "result": self.telemetry.record_reminder_error(**params)}
            if method == "telemetry.replace_event_reminders":
                return {"ok": True, "result": self.telemetry.replace_event_reminders(**params)}
            if method == "telemetry.record_operator_action":
                return {"ok": True, "result": self.telemetry.record_operator_action(**params)}
            if method == "telemetry.list_operator_actions":
                return {"ok": True, "result": self.telemetry.list_operator_actions(**params)}
            if method == "humans.list":
                return {"ok": True, "result": self.humans.list(**params)}
            if method == "humans.get":
                return {"ok": True, "result": self.humans.get(**params)}
            if method == "humans.update_consent":
                return {"ok": True, "result": self.humans.update_consent(**params)}
            if method == "messages.list_recent":
                return {"ok": True, "result": self.messages.list_recent(**params)}
            if method == "messages.append":
                return {"ok": True, "result": self.messages.append(**params)}
            if method == "calendar.list_events":
                return {"ok": True, "result": self.calendar.list_events(**params)}
            if method == "calendar.create_event":
                return {"ok": True, "result": self.calendar.create_event(**params)}
            if method == "calendar.update_event":
                return {"ok": True, "result": self.calendar.update_event(**params)}
            if method == "calendar.cancel_event":
                return {"ok": True, "result": self.calendar.cancel_event(**params)}
            if method == "calendar.list_due_reminders":
                return {"ok": True, "result": self.calendar.list_due_reminders(**params)}
            if method == "calendar.health":
                return {"ok": True, "result": self.calendar.health()}
            if method == "health":
                return {"ok": True, "result": self.health()}
            raise ValueError(f"unknown method: {method}")
        except (NoPendingTaskError, StaleClaimError, ValueError, CalendarError) as exc:
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)}

    def serve_socket(self, socket_path: str | Path) -> socketserver.UnixStreamServer:
        socket_path = Path(socket_path)
        if socket_path.exists():
            socket_path.unlink()
        service = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                for line in self.rfile:
                    request = json.loads(line.decode("utf-8"))
                    response = service.handle_rpc(request)
                    self.wfile.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))

        server = socketserver.ThreadingUnixStreamServer(str(socket_path), Handler)
        os.chmod(socket_path, 0o600)
        return server


def _body_without_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    return text[end + 5 :] if end >= 0 else text


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _node_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["frontmatter"] = json.loads(value["frontmatter"])
    value["body_text"] = value.pop("body_text")
    return value


def _first_present(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value)
    return None


def _load_sqlite_vec(conn: sqlite3.Connection) -> bool:
    if not hasattr(conn, "load_extension"):
        return False
    try:
        if hasattr(conn, "enable_load_extension"):
            conn.enable_load_extension(True)
        import sqlite_vec

        sqlite_vec.load(conn)
        return True
    except Exception:
        return False


def _sqlite_vec_loaded(conn: sqlite3.Connection) -> bool:
    return _sqlite_vec_version(conn) is not None


def _sqlite_vec_version(conn: sqlite3.Connection) -> str | None:
    try:
        return str(conn.execute("SELECT vec_version()").fetchone()[0])
    except Exception:
        return None


def _hash_embedding(text: str, dim: int = 384) -> list[float]:
    import hashlib

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = []
    while len(values) < dim:
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dim:
                break
        digest = hashlib.sha256(digest).digest()
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain-service")
    parser.add_argument("--wiki-root", default=os.getenv("BRAIN_WIKI_ROOT", str(Path.home() / "brain")))
    parser.add_argument("--telemetry-db", default=os.getenv("KUBLAI_TELEMETRY_DB", str(Path.home() / ".kublai/telemetry.db")))
    parser.add_argument("--index-db", default=os.getenv("BRAIN_INDEX_DB", str(Path.home() / ".brain-index/brain.db")))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("healthcheck")
    sub.add_parser("reindex")
    sub.add_parser("verify-index")
    replay = sub.add_parser("replay-dual-write")
    replay.add_argument("--log", default=os.getenv("BRAIN_DUAL_WRITE_LOG"))
    sub.add_parser("sweep")
    backup = sub.add_parser("backup")
    backup.add_argument("directory")
    serve = sub.add_parser("serve")
    serve.add_argument("--socket", default=os.getenv("BRAIN_SERVICE_SOCKET", "/tmp/brain-service.sock"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BrainService(args.wiki_root, args.telemetry_db, args.index_db)
    if args.command == "healthcheck":
        service.capability_check()
        print(json.dumps(service.health(), sort_keys=True))
        return 0
    if args.command == "reindex":
        print(json.dumps({"indexed": service.reindex()}))
        return 0
    if args.command == "verify-index":
        result = service.verify_index()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "replay-dual-write":
        result = service.replay_dual_write(args.log)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["ok"] else 1
    if args.command == "sweep":
        print(json.dumps({"materialized": service.sweep()}))
        return 0
    if args.command == "backup":
        print(json.dumps(service.backup(args.directory), sort_keys=True))
        return 0
    if args.command == "serve":
        service.start_background_tasks()
        observer = service.start_file_watcher()
        server = service.serve_socket(args.socket)
        thread = threading.Thread(target=server.serve_forever, daemon=False)
        thread.start()
        try:
            while thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            server.shutdown()
            if observer is not None:
                observer.stop()
                observer.join(timeout=5)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
