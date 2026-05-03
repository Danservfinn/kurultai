from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from kublai.brain_service import BrainService
from kublai.knowledge import KnowledgeStore
from kublai.v4 import HARD_PRIVATE_CANARY
from kublai.v4_gateway import is_loopback_host, serve_gateway, sign_request


def make_service(tmp_path: Path, monkeypatch) -> BrainService:
    monkeypatch.setenv("BRAIN_PRIVATE_INDEX_DB", str(tmp_path / "private-index.db"))
    wiki = tmp_path / "brain"
    wiki.mkdir()
    KnowledgeStore(wiki).atomic_write(
        wiki / "public.md",
        KnowledgeStore.render(
            {
                "type": "concept",
                "title": "Public Page",
                "status": "active",
                "created": "2026-05-03",
                "updated": "2026-05-03",
                "sources": 1,
                "tags": ["public"],
                "publish": True,
            },
            "# Public Page\n\nBrain-service public context.",
        ),
    )
    (wiki / "hard-private").mkdir()
    KnowledgeStore(wiki).atomic_write(
        wiki / "hard-private" / "canary.md",
        KnowledgeStore.render(
            {
                "type": "concept",
                "title": "Canary",
                "status": "active",
                "created": "2026-05-03",
                "updated": "2026-05-03",
                "sources": 1,
                "tags": ["pii"],
            },
            f"# Canary\n\n{HARD_PRIVATE_CANARY}",
        ),
    )
    service = BrainService(wiki, tmp_path / "telemetry.db", tmp_path / "index.db")
    service.reindex()
    service.reindex_private()
    return service


def test_public_search_and_publish_never_expose_canary(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path, monkeypatch)
    assert service.verify_index()["hard_private_rows"] == 0
    assert service.v4.public_search(query=HARD_PRIVATE_CANARY) == []
    dry = service.v4.publish_dry_run(output_root=tmp_path / "public-out")
    assert dry["ok"] is True
    assert all("hard-private" not in json.dumps(item) for item in dry["files"])
    applied = service.v4.publish_apply(output_root=tmp_path / "public-out")
    assert applied["written"] == 1
    assert HARD_PRIVATE_CANARY not in (tmp_path / "public-out" / "public.md").read_text()


def test_capture_defaults_ambiguous_content_to_hard_private(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path, monkeypatch)
    plan = service.v4.capture_dry_run(content="Ambiguous MCP-derived material", title="Inbox Thing")
    assert plan["privacy_class"] == "hard-private"
    assert plan["rel_path"].startswith("hard-private/inbox/")


def test_gateway_hmac_and_private_rejection(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path, monkeypatch)
    server = serve_gateway(service, host="127.0.0.1", port=0, secret="test-secret")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = json.dumps({"query": "Brain-service", "privacy_scope": "public"}).encode()
        ts = str(time.time())
        sig = sign_request("test-secret", "POST", "/api/ask", body, ts)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "X-Kublai-Timestamp": ts, "X-Kublai-Signature": sig},
        )
        assert json.loads(urllib.request.urlopen(req, timeout=5).read())["ok"] is True

        private_body = json.dumps({"query": "x", "privacy_scope": "hard-private"}).encode()
        ts = str(time.time())
        sig = sign_request("test-secret", "POST", "/api/ask", private_body, ts)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=private_body,
            method="POST",
            headers={"Content-Type": "application/json", "X-Kublai-Timestamp": ts, "X-Kublai-Signature": sig},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
            raise AssertionError("private request should fail")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_gateway_requires_secret_for_non_loopback_bind(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path, monkeypatch)
    assert is_loopback_host("127.0.0.1")
    try:
        serve_gateway(service, host="0.0.0.0", port=0, secret="")
        raise AssertionError("non-loopback gateway without HMAC secret should fail")
    except ValueError as exc:
        assert "requires HMAC secret" in str(exc)


def test_llm_request_log_omits_raw_prompt(tmp_path: Path, monkeypatch) -> None:
    from kublai import llm

    log = tmp_path / "llm.ndjson"
    monkeypatch.setenv("KUBLAI_LLM_REQUEST_LOG", str(log))
    monkeypatch.setenv("KUBLAI_LLM_MOCK_RESPONSE", "ok")
    import asyncio

    assert asyncio.run(llm.llm_call(command="ask", user="raw prompt text")) == "ok"
    record = json.loads(log.read_text())
    assert "user" not in record
    assert record["user_chars"] == len("raw prompt text")
