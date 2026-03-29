#!/usr/bin/env python3
"""
Conversation Ingester — Neo4j-native message ingestion pipeline.

Neo4j-primary ingestion with JSONL fallback for disaster recovery.
Legacy dual-write retired 2026-03-20.

Sync Phase (<200ms target):
1. Generate embedding (nomic-embed-text via Ollama)
2. Create Message node in Neo4j
3. Link Message → Human via SENT
4. Link Message → active Thread via IN_THREAD (auto-detect new threads)
5. Write JSONL fallback line
6. Trigger engagement assessment (async)

Async Phase (background):
7. PII scrubbing (for contentScrubbed field)
8. LLM extraction (topics, sentiment, action items)
9. Topic graph update

Usage:
    from conversation_ingester import ConversationIngester

    ingester = ConversationIngester()
    result = ingester.ingest(
        phone="+19194133445",
        content="Let's discuss the deployment",
        direction="inbound",
        channel="signal",
    )
"""

import os
import sys
import uuid
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver, is_neo4j_available
from neo4j_human_v2 import HumanStoreV2
from pii_scrubber import PIIScrubber
from field_encryption import encrypt_field
from embedding_generator import generate_embedding, embedding_is_zero

logger = logging.getLogger(__name__)

# Configuration
THREAD_GAP_HOURS = 2.0  # Hours of silence before starting a new thread
THREAD_SIMILARITY_THRESHOLD = 0.35  # Cosine similarity threshold for same thread
JSONL_FALLBACK_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans" / "ingestion_log"
LEGACY_INDEX_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans" / "index"


class ConversationIngester:
    """Neo4j-native conversation ingestion with dual-write fallback."""

    def __init__(self):
        self.driver = get_driver()
        self.human_store = HumanStoreV2()
        self.pii_scrubber = PIIScrubber()
        self._ensure_dirs()

    def close(self):
        # Don't call close_driver() — let the atexit handler manage lifecycle
        self.driver = None
        self.human_store.close()

    def _ensure_dirs(self):
        JSONL_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)

    def ingest(
        self,
        phone: str,
        content: str,
        direction: str = "inbound",
        channel: str = "signal",
        has_media: bool = False,
        media_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        group_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ingest a message into the conversation graph.

        Args:
            phone: Sender/recipient phone number
            content: Message text content
            direction: 'inbound' or 'outbound'
            channel: Communication channel
            has_media: Whether message has an attachment
            media_type: Type of attachment (image, file, etc.)
            metadata: Additional metadata
            group_id: Group identifier (None = DM)

        Returns:
            Dict with message_id, human_id, thread_id, timing info
        """
        t0 = time.monotonic()

        # 1. Resolve Human (find or create by phone)
        human = self.human_store.find_or_create_by_phone(phone)
        human_id = human["id"]
        t_human = time.monotonic()

        # 2. PII scrub for contentScrubbed
        known_names = set()
        for ident in human.get("identifiers", []):
            if ident.get("type") == "NAME_VARIANT":
                known_names.add(ident["value"])
        if human.get("displayName"):
            known_names.add(human["displayName"])

        scrubber = PIIScrubber(known_names=known_names)
        content_scrubbed, pii_map = scrubber.scrub(content)

        # 3. Encrypt content for storage
        content_encrypted = encrypt_field(content) if content else None
        if content_encrypted is None and content:
            logger.error("Encryption failed — skipping content storage for privacy")

        # 4. Generate embedding
        embedding = generate_embedding(content_scrubbed) if content_scrubbed else None
        if embedding and all(v == 0.0 for v in embedding[:5]):
            embedding = None  # Don't store zero-vectors from embedding failures
        t_embed = time.monotonic()

        # 5. Create Message node (with scope for group isolation)
        message_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        scope = f"group:{group_id}" if group_id else "dm"

        with self.driver.session() as session:
            session.run(
                """
                MATCH (h:Human {id: $human_id})
                CREATE (m:Message {
                    id: $msg_id,
                    humanId: $human_id,
                    content: $content_encrypted,
                    contentScrubbed: $content_scrubbed,
                    direction: $direction,
                    channel: $channel,
                    scope: $scope,
                    groupId: $group_id,
                    timestamp: datetime($timestamp),
                    embedding: $embedding,
                    hasMedia: $has_media,
                    mediaType: $media_type,
                    extractionStatus: 'PENDING',
                    createdAt: datetime()
                })
                CREATE (m)-[:SENT_BY]->(h)
                """,
                human_id=human_id,
                msg_id=message_id,
                content_encrypted=content_encrypted,
                content_scrubbed=content_scrubbed,
                direction=direction,
                channel=channel,
                scope=scope,
                group_id=group_id,
                timestamp=now,
                embedding=embedding,
                has_media=has_media,
                media_type=media_type,
            )

            # Create/update Group node and link message if group message
            if group_id:
                self._ensure_group_node(session, group_id)
                self._link_message_to_group(session, message_id, group_id)

        t_message = time.monotonic()

        # 6. Thread detection and linking (scope-aware)
        thread_id = self._assign_thread(human_id, message_id, embedding, now, scope=scope)
        t_thread = time.monotonic()

        # 7. Write JSONL fallback
        self._write_jsonl_fallback(
            message_id, human_id, phone, content, direction, channel, now, thread_id,
            scope=scope, group_id=group_id,
        )

        # 8. Legacy dual-write retired — JSONL fallback provides DR coverage
        t_legacy = time.monotonic()

        total_ms = (t_legacy - t0) * 1000
        logger.info(
            f"Ingested message {message_id[:8]} for {human_id[:8]} "
            f"in {total_ms:.0f}ms (human:{(t_human-t0)*1000:.0f} embed:{(t_embed-t_human)*1000:.0f} "
            f"msg:{(t_message-t_embed)*1000:.0f} thread:{(t_thread-t_message)*1000:.0f})"
        )

        return {
            "message_id": message_id,
            "human_id": human_id,
            "thread_id": thread_id,
            "embedding_nonzero": not embedding_is_zero(embedding),
            "total_ms": round(total_ms, 1),
            "content_scrubbed": content_scrubbed,
        }

    def _ensure_group_node(self, session, group_id: str):
        """Create or update Group node on first/subsequent group messages."""
        session.run(
            """
            MERGE (g:Group {groupId: $group_id})
            ON CREATE SET g.createdAt = datetime(),
                          g.messageCount = 0,
                          g.status = 'ACTIVE'
            SET g.lastMessageAt = datetime(),
                g.messageCount = coalesce(g.messageCount, 0) + 1
            """,
            group_id=group_id,
        )

    def _link_message_to_group(self, session, message_id: str, group_id: str):
        """Link a Message to its Group via IN_GROUP relationship."""
        session.run(
            """
            MATCH (m:Message {id: $msg_id})
            MATCH (g:Group {groupId: $group_id})
            MERGE (m)-[:IN_GROUP]->(g)
            """,
            msg_id=message_id,
            group_id=group_id,
        )

    def _assign_thread(
        self, human_id: str, message_id: str, embedding: List[float], timestamp: str,
        scope: str = "dm",
    ) -> Optional[str]:
        """Detect or create a thread for the message.

        Uses time-gap heuristic (2h gap = new thread).
        Scope-aware: group messages get separate threads from DM messages.
        """
        with self.driver.session() as session:
            # Find active thread for this human within the same scope
            result = session.run(
                """
                MATCH (t:Thread {humanId: $human_id, status: 'ACTIVE'})
                WHERE t.scope = $scope
                OPTIONAL MATCH (m:Message)-[:IN_THREAD]->(t)
                WITH t, max(m.timestamp) AS lastMsg
                ORDER BY lastMsg DESC
                LIMIT 1
                RETURN t.id AS threadId, toString(lastMsg) AS lastMessageTime
                """,
                human_id=human_id,
                scope=scope,
            )
            record = result.single()

            thread_id = None
            create_new = True

            if record and record["threadId"]:
                thread_id = record["threadId"]
                last_msg_time = record["lastMessageTime"]

                if last_msg_time:
                    try:
                        last_dt = datetime.fromisoformat(last_msg_time.replace("Z", "+00:00"))
                        now_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        gap_hours = (now_dt - last_dt).total_seconds() / 3600

                        if gap_hours < THREAD_GAP_HOURS:
                            create_new = False
                    except (ValueError, TypeError):
                        pass

            if create_new:
                # Close existing active thread
                if thread_id:
                    session.run(
                        """
                        MATCH (t:Thread {id: $thread_id})
                        SET t.status = 'DORMANT', t.updatedAt = datetime()
                        """,
                        thread_id=thread_id,
                    )

                # Create new thread (with scope for group isolation)
                thread_id = str(uuid.uuid4())
                session.run(
                    """
                    CREATE (t:Thread {
                        id: $thread_id,
                        humanId: $human_id,
                        scope: $scope,
                        status: 'ACTIVE',
                        startedAt: datetime($timestamp),
                        summary: null,
                        summaryEmbedding: null,
                        messageCount: 0,
                        createdAt: datetime(),
                        updatedAt: datetime()
                    })
                    """,
                    thread_id=thread_id,
                    human_id=human_id,
                    scope=scope,
                    timestamp=timestamp,
                )

            # Link message to thread
            session.run(
                """
                MATCH (m:Message {id: $msg_id})
                MATCH (t:Thread {id: $thread_id})
                MERGE (m)-[:IN_THREAD]->(t)
                SET t.messageCount = t.messageCount + 1,
                    t.updatedAt = datetime()
                """,
                msg_id=message_id,
                thread_id=thread_id,
            )

            return thread_id

    def _write_jsonl_fallback(
        self,
        message_id: str,
        human_id: str,
        phone: str,
        content: str,
        direction: str,
        channel: str,
        timestamp: str,
        thread_id: Optional[str],
        scope: str = "dm",
        group_id: Optional[str] = None,
    ):
        """Write JSONL fallback line for disaster recovery.

        DR NOTE: phone_hash is a truncated SHA-256 — NOT reversible.
        If Neo4j is lost, phone-to-identity mapping requires a separate backup
        (e.g., Signal contact list). human_id UUID is still present for
        correlation if Neo4j Human nodes can be recovered.
        """
        try:
            import hashlib
            # Hash phone number instead of storing plaintext
            phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:16]
            content_encrypted = encrypt_field(content) if content else None
            line = json.dumps({
                "message_id": message_id,
                "human_id": human_id,
                "phone_hash": phone_hash,
                "direction": direction,
                "channel": channel,
                "timestamp": timestamp,
                "thread_id": thread_id,
                "scope": scope,
                "group_id": group_id,
                "content_encrypted": content_encrypted,
                "content_hash": hashlib.sha256(content.encode()).hexdigest() if content else None,
            })
            fallback_file = JSONL_FALLBACK_DIR / f"{datetime.now().strftime('%Y-%m')}.jsonl"
            # Use restricted permissions on file creation
            fd = os.open(str(fallback_file), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error(f"JSONL fallback write failed: {e}")

    # _write_legacy_json retired — Neo4j is primary, JSONL fallback for DR
    # conversation_privacy.py still reads legacy files for export (backward compat)

    def get_human_message_stats(self, human_id: str, scope: str = None) -> Dict[str, Any]:
        """Get message statistics for a human, optionally filtered by scope."""
        scope_filter = ""
        params = {"human_id": human_id}
        if scope:
            scope_filter = "AND m.scope = $scope"
            params["scope"] = scope

        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH (m:Message {{humanId: $human_id}})
                WHERE true {scope_filter}
                RETURN count(m) AS messageCount,
                       max(m.timestamp) AS lastMessageTime
                """,
                **params,
            )
            record = result.single()
            if not record:
                return {"message_count": 0, "last_message_days": None}

            count = record["messageCount"]
            last_time = record["lastMessageTime"]

            last_days = None
            if last_time:
                try:
                    now = datetime.now(timezone.utc)
                    # Neo4j datetime to Python
                    if hasattr(last_time, 'to_native'):
                        last_dt = last_time.to_native()
                    else:
                        last_dt = datetime.fromisoformat(str(last_time).replace("Z", "+00:00"))
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    last_days = (now - last_dt).total_seconds() / 86400
                except Exception as e:
                    logger.debug(f"Date parse error: {e}")

            return {"message_count": count, "last_message_days": last_days}


# Module-level convenience functions
_default_ingester: Optional[ConversationIngester] = None


def get_ingester() -> ConversationIngester:
    global _default_ingester
    if _default_ingester is None:
        _default_ingester = ConversationIngester()
        import atexit
        atexit.register(lambda: _default_ingester.close() if _default_ingester else None)
    return _default_ingester


def ingest_message(
    phone: str, content: str, direction: str = "inbound", channel: str = "signal",
    group_id: Optional[str] = None, **kwargs,
) -> Dict[str, Any]:
    """Convenience function for single message ingestion."""
    return get_ingester().ingest(phone, content, direction, channel, group_id=group_id, **kwargs)


if __name__ == "__main__":
    print("Conversation Ingester self-test:")

    ingester = ConversationIngester()

    result = ingester.ingest(
        phone="+19999999999",
        content="Hello from the ingester test! Let's discuss authentication.",
        direction="inbound",
        channel="signal",
    )
    print(f"  Message ID: {result['message_id'][:8]}")
    print(f"  Human ID: {result['human_id'][:8]}")
    print(f"  Thread ID: {result['thread_id'][:8] if result['thread_id'] else 'None'}")
    print(f"  Embedding: {'OK' if result['embedding_nonzero'] else 'zero-vector'}")
    print(f"  Total time: {result['total_ms']}ms")
    print(f"  Scrubbed: {result['content_scrubbed']}")

    # Check stats
    stats = ingester.get_human_message_stats(result["human_id"])
    print(f"  Stats: {stats}")

    ingester.close()
    print("\nDone.")
