import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import pytest

from kublai.brain_service import BrainService, classify_page
from kublai.brain_service_client import call
from kublai.knowledge import KnowledgeStore, PathPolicyError


NODE_BIN = shutil.which("node") or "/opt/homebrew/bin/node"


def test_classify_page_marks_hard_private_sources():
    assert classify_page("hard-private/finance/x.md", {}) == "hard-private"
    assert classify_page("entities/contact.md", {"type": "human-contact"}) == "hard-private"
    assert classify_page("raw/tax-note.md", {"tags": ["tax"]}) == "hard-private"
    assert classify_page("concepts/private-note.md", {"tags": ["research"]}) == "private"
    assert classify_page("concepts/public-note.md", {"publish": True}) == "public"


def test_knowledge_write_is_deterministic_and_path_guarded(tmp_path):
    store = KnowledgeStore(tmp_path / "brain")
    path = store.record_completed_task(
        task_id="abc-123",
        agent="temujin",
        delegated_by="kublai",
        completed_at_ms=1_775_000_000_000,
        deliverable="done",
        results={"ok": True},
    )
    same = store.record_completed_task(
        task_id="abc-123",
        agent="temujin",
        delegated_by="kublai",
        completed_at_ms=1_775_000_000_000,
        deliverable="done again",
        results={"ok": True},
    )

    assert path == same
    assert path.relative_to(tmp_path / "brain").as_posix().startswith("operations/tasks/")
    assert "task_id: abc-123" in path.read_text()
    with pytest.raises(PathPolicyError):
        store.write_page("../escape.md", {}, "bad", typed_field="x", typed_id="y")


def test_sweep_materializes_completed_task_once(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    service.telemetry.create_task("task-1", description="sweep", delegated_by="kublai")
    claim = service.telemetry.claim_task("temujin", now_ms=1_000)
    service.telemetry.complete_task(
        claim.id,
        "temujin",
        claim.claim_token,
        summary="materialize me",
        target_wiki_path="operations/tasks/2026/04/task-task-1.md",
        now_ms=1_100,
    )

    assert service.sweep() == 1
    assert service.sweep() == 0
    task_pages = list((tmp_path / "brain" / "operations/tasks").rglob("*.md"))
    assert len(task_pages) == 1


def test_reindex_and_vector_orphan_check(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    for i in range(1_000):
        page = service.knowledge.record_reflection(
            agent="jochi",
            reflection_id=f"reflection-{i}",
            body=f"reflection body {i}",
        )
        page.write_text(page.read_text().replace("updated:", "publish: true\nupdated:", 1))

    assert service.reindex() == 1_000
    assert service.index.vector_orphans() == 0

    with service.index.connect() as conn:
        conn.execute("DELETE FROM nodes WHERE node_pk IN (SELECT node_pk FROM nodes LIMIT 10)")
    assert service.index.vector_orphans() == 10


def test_public_reindex_skips_hard_private_before_body_index(tmp_path):
    brain = tmp_path / "brain"
    public_dir = brain / "concepts"
    hard_dir = brain / "hard-private"
    public_dir.mkdir(parents=True)
    hard_dir.mkdir(parents=True)
    (public_dir / "published.md").write_text(
        "---\ntype: concept\nstatus: active\ncreated: 2026-05-03\nupdated: 2026-05-03\nsources: 1\npublish: true\ntags: [research]\n---\n\npublic sentinel\n",
        encoding="utf-8",
    )
    (public_dir / "private.md").write_text(
        "---\ntype: concept\nstatus: active\ncreated: 2026-05-03\nupdated: 2026-05-03\nsources: 1\ntags: [research]\n---\n\nordinary private sentinel\n",
        encoding="utf-8",
    )
    (hard_dir / "secret.md").write_text(
        "---\ntype: note\nstatus: active\ncreated: 2026-05-03\nupdated: 2026-05-03\nsources: 1\ntags: [financial]\n---\n\nhard private sentinel\n",
        encoding="utf-8",
    )
    service = BrainService(brain, tmp_path / "telemetry.db", tmp_path / "brain-index.db")

    assert service.reindex() == 1
    assert service.verify_index()["ok"] is True
    assert service.search(query="public")[0]["rel_path"] == "concepts/published.md"
    assert service.search(query="ordinary") == []
    assert service.search(query="hard") == []


def test_search_treats_hyphenated_query_as_literal_text(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )

    assert service.search(query="hard-private") == []


def test_verify_index_fails_when_public_db_contains_hard_private_row(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    service.knowledge.record_reflection(
        agent="jochi",
        reflection_id="reflection-privacy-check",
        body="fixture reflection",
    )
    service.reindex()
    with service.index.connect() as conn:
        conn.execute(
            """
            INSERT INTO nodes (
              id, type, rel_path, title, status, agent, typed_id,
              created, updated, frontmatter, body_hash, body_text, mtime_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hard-private/test",
                "note",
                "hard-private/test.md",
                "private",
                "active",
                "",
                None,
                "2026-05-03",
                "2026-05-03",
                json.dumps({"type": "note", "tags": ["financial"]}),
                "hash",
                "secret",
                1,
            ),
        )

    result = service.verify_index()
    assert result["ok"] is False
    assert result["hard_private_rows"] == 1


def test_verify_index_fails_when_public_db_contains_private_row(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    with service.index.connect() as conn:
        conn.execute(
            """
            INSERT INTO nodes (
              id, type, rel_path, title, status, agent, typed_id,
              created, updated, frontmatter, body_hash, body_text, mtime_ns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "concepts/private",
                "concept",
                "concepts/private.md",
                "private",
                "active",
                "",
                None,
                "2026-05-03",
                "2026-05-03",
                json.dumps({"type": "concept", "tags": ["research"]}),
                "hash",
                "private",
                1,
            ),
        )

    result = service.verify_index()
    assert result["ok"] is False
    assert result["private_rows"] == 1


def test_list_by_tag_rpc_defaults_to_public_scope(tmp_path):
    brain = tmp_path / "brain"
    (brain / "concepts").mkdir(parents=True)
    (brain / "hard-private").mkdir(parents=True)
    (brain / "concepts" / "safe.md").write_text(
        "---\ntype: concept\npublish: true\ntags: [finance]\n---\n\npublic finance\n",
        encoding="utf-8",
    )
    (brain / "hard-private" / "secret.md").write_text(
        "---\ntype: note\ntags: [finance]\n---\n\nsecret finance\n",
        encoding="utf-8",
    )
    (brain / "concepts" / "sensitive.md").write_text(
        "---\ntype: note\ntags: [finance, financial]\n---\n\nsensitive finance\n",
        encoding="utf-8",
    )
    service = BrainService(brain, tmp_path / "telemetry.db", tmp_path / "brain-index.db")

    public_default = service.index.list_by_tag_in_wiki(service.knowledge, tag="finance")
    hard_private = service.index.list_by_tag_in_wiki(
        service.knowledge,
        tag="finance",
        privacy_scope="hard-private",
    )
    assert [row["rel_path"] for row in public_default] == ["concepts/safe.md"]
    assert {row["rel_path"] for row in hard_private} == {
        "concepts/sensitive.md",
        "hard-private/secret.md",
    }


def test_private_indexer_indexes_only_hard_private_and_audits_reads(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    (brain / "concepts").mkdir(parents=True)
    (brain / "hard-private").mkdir(parents=True)
    (brain / "concepts" / "safe.md").write_text(
        "---\ntype: concept\npublish: true\ntags: [research]\n---\n\npublic apple\n",
        encoding="utf-8",
    )
    (brain / "hard-private" / "secret.md").write_text(
        "---\ntype: note\ntags: [financial]\n---\n\nprivate banana\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BRAIN_PRIVATE_INDEX_DB", str(tmp_path / "private.db"))
    monkeypatch.setenv("KUBLAI_PRIVATE_ACCESS_LOG", str(tmp_path / "private-access.ndjson"))
    service = BrainService(brain, tmp_path / "telemetry.db", tmp_path / "brain-index.db")

    assert service.reindex() == 1
    assert service.reindex_private() == 1
    assert service.verify_index()["ok"] is True
    assert service.verify_private_index()["ok"] is True
    assert service.search(query="banana") == []
    rows = service.search_private(query="banana")
    assert [row["rel_path"] for row in rows] == ["hard-private/secret.md"]
    assert "knowledge.search_private" in (tmp_path / "private-access.ndjson").read_text()


def test_unix_socket_rpc_serves_js_clients(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    # macOS Unix sockets have a short path limit; keep this in /tmp even when
    # pytest's tmp_path is deeply nested.
    socket_path = Path("/tmp") / f"bs-{os.getpid()}-{uuid.uuid4().hex[:8]}.sock"
    server = service.serve_socket(socket_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        created = call(
            socket_path,
            "telemetry.create_task",
            {"task_id": "task-1", "description": "rpc", "delegated_by": "kublai"},
        )
        assert created == {"ok": True, "result": "task-1"}

        node_script = f"""
        const telemetry = require('./kublai/telemetry-client');
        process.env.BRAIN_SERVICE_SOCKET = {json.dumps(str(socket_path))};
        telemetry.claimTask({{agent: 'temujin'}})
          .then(result => {{
            console.log(JSON.stringify({{id: result.id, token: !!result.claim_token}}));
          }})
          .catch(error => {{
            console.error(error.stack || error.message);
            process.exit(1);
          }});
        """
        result = subprocess.run(
            [NODE_BIN, "-e", node_script],
            cwd=".",
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(result.stdout) == {"id": "task-1", "token": True}

        found = call(
            socket_path,
            "knowledge.search",
            {"query": "rpc", "limit": 5},
        )
        assert found == {"ok": True, "result": []}
    finally:
        server.shutdown()
        server.server_close()
        if socket_path.exists():
            socket_path.unlink()


def test_brain_service_cli_healthcheck(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "kublai.brain_service",
            "--wiki-root",
            str(tmp_path / "brain"),
            "--telemetry-db",
            str(tmp_path / "telemetry.db"),
            "--index-db",
            str(tmp_path / "brain-index.db"),
            "healthcheck",
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_brain_service_verify_index_and_replay_dual_write(tmp_path):
    service = BrainService(
        tmp_path / "brain",
        tmp_path / "telemetry.db",
        tmp_path / "brain-index.db",
    )
    page = service.knowledge.record_reflection(
        agent="jochi",
        reflection_id="reflection-1",
        body="fixture reflection",
    )
    page.write_text(page.read_text().replace("updated:", "publish: true\nupdated:", 1))
    service.reindex()

    assert service.verify_index()["ok"] is True
    assert service.get_node("reflection", "reflection-1")["rel_path"].startswith("operations/reflections/")
    assert service.list_nodes(node_type="reflection")[0]["typed_id"] == "reflection-1"
    assert service.search(query="fixture", node_type="reflection")[0]["typed_id"] == "reflection-1"

    rel_path = page.relative_to(tmp_path / "brain").as_posix()
    body = page.read_text().split("\n---\n", 1)[1]
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    log_path = tmp_path / "dual-write.jsonl"
    log_path.write_text(json.dumps({"wiki_path": rel_path, "body_hash": digest}) + "\n")

    assert service.replay_dual_write(log_path) == {
        "ok": True,
        "checked": 1,
        "mismatches": 0,
        "details": [],
    }
