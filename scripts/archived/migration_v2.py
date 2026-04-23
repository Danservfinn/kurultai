#!/usr/bin/env python3
"""
Migration V2 — Migrates existing conversation files to Neo4j graph.

Reads all ~/.openclaw/agents/main/memory/humans/index/*.json files,
creates Human + Identifier nodes, detects historical threads,
generates embeddings, and optionally runs LLM topic extraction.

Usage:
    python3 migration_v2.py                     # Full migration
    python3 migration_v2.py --skip-extraction   # Skip LLM extraction
    python3 migration_v2.py --dry-run           # Preview only
    python3 migration_v2.py --phone +19194133445  # Single user
"""

import os
import sys
import json
import uuid
import time
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver, close_driver
from neo4j_human_v2 import HumanStoreV2
from embedding_generator import generate_embedding, embedding_is_zero
from pii_scrubber import PIIScrubber
from field_encryption import encrypt_field

logger = logging.getLogger(__name__)

INDEX_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans" / "index"
ARCHIVE_DIR = Path.home() / ".openclaw" / "agents" / "main" / "memory" / "humans" / "archive"
THREAD_GAP_HOURS = 2.0


class MigrationV2:
    """Migrates file-based conversation data to Neo4j."""

    def __init__(self, dry_run: bool = False, skip_extraction: bool = False):
        self.dry_run = dry_run
        self.skip_extraction = skip_extraction
        self.driver = get_driver()
        self.human_store = HumanStoreV2()
        self.scrubber = PIIScrubber()
        self.stats = {
            "humans_created": 0,
            "messages_migrated": 0,
            "threads_created": 0,
            "embeddings_generated": 0,
            "errors": 0,
        }

    def close(self):
        self.human_store.close()
        close_driver()
        self.driver = None

    def migrate_all(self) -> Dict[str, Any]:
        """Migrate all conversation files."""
        t0 = time.monotonic()

        # Find all conversation index files
        json_files = sorted(INDEX_DIR.glob("*.json"))
        # Filter out task_links and event_links files
        conv_files = [
            f for f in json_files
            if not f.name.endswith("_task_links.json")
            and not f.name.endswith("_event_links.json")
        ]

        logger.info(f"Found {len(conv_files)} conversation files to migrate")

        for conv_file in conv_files:
            try:
                self._migrate_file(conv_file)
            except Exception as e:
                logger.error(f"Failed to migrate {conv_file.name}: {e}")
                self.stats["errors"] += 1

        self.stats["total_ms"] = round((time.monotonic() - t0) * 1000)
        return self.stats

    def migrate_phone(self, phone: str) -> Dict[str, Any]:
        """Migrate a single phone number."""
        normalized = phone.lstrip("+").replace("-", "").replace(" ", "")
        conv_file = INDEX_DIR / f"{normalized}.json"

        if not conv_file.exists():
            return {"error": f"No conversation file for {phone}"}

        self._migrate_file(conv_file)

        # Also check archives
        for archive_file in ARCHIVE_DIR.glob(f"{normalized}-archive-*.json"):
            self._migrate_archive(archive_file, phone)

        return self.stats

    def _migrate_file(self, conv_file: Path):
        """Migrate a single conversation index file."""
        phone = conv_file.stem  # e.g., "19194133445"
        if phone.startswith("+"):
            pass
        elif not phone.startswith("+"):
            phone = "+" + phone

        logger.info(f"Migrating {conv_file.name} ({phone})")

        try:
            conversations = json.loads(conv_file.read_text())
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse {conv_file.name}: {e}")
            self.stats["errors"] += 1
            return

        if not isinstance(conversations, list):
            logger.warning(f"Unexpected format in {conv_file.name}")
            return

        # Create Human + Identifier
        if not self.dry_run:
            display_name = self._extract_display_name(conversations, phone)
            human = self.human_store.find_or_create_by_phone(phone, display_name)
            human_id = human["id"]
            self.stats["humans_created"] += 1
        else:
            human_id = f"dry-run-{phone}"

        # Detect threads and create messages
        self._process_messages(human_id, phone, conversations)

    def _migrate_archive(self, archive_file: Path, phone: str):
        """Migrate an archive file."""
        try:
            conversations = json.loads(archive_file.read_text())
        except (json.JSONDecodeError, Exception):
            return

        if not isinstance(conversations, list):
            return

        human = self.human_store.find_human_by_identifier("SIGNAL_PHONE", phone)
        if not human:
            return

        self._process_messages(human["id"], phone, conversations)

    def _process_messages(
        self, human_id: str, phone: str, conversations: List[Dict[str, Any]]
    ):
        """Process and ingest a list of conversation messages."""
        # Sort by timestamp
        sorted_msgs = sorted(
            conversations,
            key=lambda m: m.get("timestamp", ""),
        )

        current_thread_id = None
        last_timestamp = None

        for msg in sorted_msgs:
            content = msg.get("content", "")
            direction = msg.get("direction", "inbound")
            channel = msg.get("channel", "signal")
            timestamp = msg.get("timestamp", datetime.now(timezone.utc).isoformat())

            if not content:
                continue

            # Thread detection
            need_new_thread = False
            if last_timestamp:
                try:
                    last_dt = datetime.fromisoformat(last_timestamp)
                    curr_dt = datetime.fromisoformat(timestamp)
                    gap_hours = (curr_dt - last_dt).total_seconds() / 3600
                    if gap_hours >= THREAD_GAP_HOURS:
                        need_new_thread = True
                except (ValueError, TypeError):
                    need_new_thread = True
            else:
                need_new_thread = True

            if need_new_thread and not self.dry_run:
                # Close previous thread
                if current_thread_id:
                    with self.driver.session() as session:
                        session.run(
                            "MATCH (t:Thread {id: $id}) SET t.status = 'ARCHIVED'",
                            id=current_thread_id,
                        )

                current_thread_id = str(uuid.uuid4())
                with self.driver.session() as session:
                    session.run(
                        """
                        CREATE (t:Thread {
                            id: $id, humanId: $human_id,
                            status: 'ARCHIVED',
                            startedAt: datetime($ts),
                            messageCount: 0,
                            createdAt: datetime(),
                            updatedAt: datetime()
                        })
                        """,
                        id=current_thread_id,
                        human_id=human_id,
                        ts=timestamp,
                    )
                self.stats["threads_created"] += 1

            if not self.dry_run:
                # PII scrub
                scrubbed, _ = self.scrubber.scrub(content)

                # Encrypt
                encrypted = encrypt_field(content)

                # Embed
                embedding = generate_embedding(content)
                if not embedding_is_zero(embedding):
                    self.stats["embeddings_generated"] += 1

                # Create Message node
                msg_id = str(uuid.uuid4())
                with self.driver.session() as session:
                    session.run(
                        """
                        MATCH (h:Human {id: $human_id})
                        CREATE (m:Message {
                            id: $msg_id, humanId: $human_id,
                            content: $encrypted, contentScrubbed: $scrubbed,
                            direction: $direction, channel: $channel,
                            timestamp: datetime($ts),
                            embedding: $embedding,
                            extractionStatus: $ext_status,
                            createdAt: datetime()
                        })
                        CREATE (m)-[:SENT_BY]->(h)
                        """,
                        human_id=human_id,
                        msg_id=msg_id,
                        encrypted=encrypted,
                        scrubbed=scrubbed,
                        direction=direction,
                        channel=channel,
                        ts=timestamp,
                        embedding=embedding,
                        ext_status="PENDING" if not self.skip_extraction else "SKIPPED",
                    )

                    # Link to thread
                    if current_thread_id:
                        session.run(
                            """
                            MATCH (m:Message {id: $msg_id})
                            MATCH (t:Thread {id: $thread_id})
                            MERGE (m)-[:IN_THREAD]->(t)
                            SET t.messageCount = t.messageCount + 1
                            """,
                            msg_id=msg_id,
                            thread_id=current_thread_id,
                        )

            self.stats["messages_migrated"] += 1
            last_timestamp = timestamp

    def _extract_display_name(
        self, conversations: List[Dict[str, Any]], phone: str
    ) -> str:
        """Try to extract a display name from conversation metadata."""
        for msg in conversations:
            name = msg.get("sender_name") or msg.get("name")
            if name and name != phone:
                return name
        return phone


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate conversations to Neo4j v2")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--skip-extraction", action="store_true", help="Skip LLM extraction")
    parser.add_argument("--phone", help="Migrate single phone number")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    migrator = MigrationV2(dry_run=args.dry_run, skip_extraction=args.skip_extraction)

    try:
        if args.phone:
            stats = migrator.migrate_phone(args.phone)
        else:
            stats = migrator.migrate_all()

        print(f"\nMigration {'preview' if args.dry_run else 'complete'}:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    finally:
        migrator.close()
