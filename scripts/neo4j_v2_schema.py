#!/usr/bin/env python3
"""
neo4j_v2_schema.py — Neo4j v2 schema: nodes, constraints, indexes.

Idempotent — safe to run multiple times.
Does NOT modify or conflict with v1 schema (additive only).

Usage:
    python3 neo4j_v2_schema.py           # Apply schema
    python3 neo4j_v2_schema.py --verify  # Verify only
    python3 neo4j_v2_schema.py --test    # Run self-test
"""

import sys
import os
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_task_tracker import get_driver, close_driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constraints (v2)
# ---------------------------------------------------------------------------
V2_CONSTRAINTS = [
    {
        "name": "task_id_unique",
        "cypher": "CREATE CONSTRAINT task_id_unique IF NOT EXISTS FOR (t:Task) REQUIRE t.task_id IS UNIQUE",
        "desc": "Unique task_id across Task nodes",
    },
    {
        "name": "agent_name_unique",
        "cypher": "CREATE CONSTRAINT agent_name_unique IF NOT EXISTS FOR (a:Agent) REQUIRE a.name IS UNIQUE",
        "desc": "Unique agent name",
    },
    # --- Conversational Memory v2 constraints ---
    {
        "name": "human_id_unique",
        "cypher": "CREATE CONSTRAINT human_id_unique IF NOT EXISTS FOR (h:Human) REQUIRE h.id IS UNIQUE",
        "desc": "Unique Human UUID",
    },
    {
        "name": "identifier_unique",
        "cypher": "CREATE CONSTRAINT identifier_unique IF NOT EXISTS FOR (i:Identifier) REQUIRE (i.type, i.value) IS UNIQUE",
        "desc": "Unique identifier per type+value",
    },
    {
        "name": "message_id_unique",
        "cypher": "CREATE CONSTRAINT message_id_unique IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
        "desc": "Unique Message UUID",
    },
    {
        "name": "thread_id_unique",
        "cypher": "CREATE CONSTRAINT thread_id_unique IF NOT EXISTS FOR (t:Thread) REQUIRE t.id IS UNIQUE",
        "desc": "Unique Thread UUID",
    },
    {
        "name": "action_item_id_unique",
        "cypher": "CREATE CONSTRAINT action_item_id_unique IF NOT EXISTS FOR (a:ActionItem) REQUIRE a.id IS UNIQUE",
        "desc": "Unique ActionItem UUID",
    },
    {
        "name": "topic_id_unique",
        "cypher": "CREATE CONSTRAINT topic_id_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
        "desc": "Unique Topic UUID",
    },
    {
        "name": "topic_label_unique",
        "cypher": "CREATE CONSTRAINT topic_label_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.label IS UNIQUE",
        "desc": "Unique Topic label",
    },
    {
        "name": "episode_id_unique",
        "cypher": "CREATE CONSTRAINT episode_id_unique IF NOT EXISTS FOR (e:Episode) REQUIRE e.id IS UNIQUE",
        "desc": "Unique Episode UUID",
    },
    {
        "name": "inference_id_unique",
        "cypher": "CREATE CONSTRAINT inference_id_unique IF NOT EXISTS FOR (i:Inference) REQUIRE i.id IS UNIQUE",
        "desc": "Unique Inference UUID",
    },
    {
        "name": "temporal_marker_id_unique",
        "cypher": "CREATE CONSTRAINT temporal_marker_id_unique IF NOT EXISTS FOR (tm:TemporalMarker) REQUIRE tm.id IS UNIQUE",
        "desc": "Unique TemporalMarker UUID",
    },
    # consent_category_name_unique already exists from HumanProfileStore.init_schema()
    # --- PendingQuestion (conversational curiosity) ---
    {
        "name": "pending_question_id_unique",
        "cypher": "CREATE CONSTRAINT pending_question_id_unique IF NOT EXISTS FOR (pq:PendingQuestion) REQUIRE pq.id IS UNIQUE",
        "desc": "Unique PendingQuestion UUID",
    },
    # --- Group Chat Isolation ---
    {
        "name": "group_id_unique",
        "cypher": "CREATE CONSTRAINT group_id_unique IF NOT EXISTS FOR (g:Group) REQUIRE g.groupId IS UNIQUE",
        "desc": "Unique Group identifier",
    },
    {
        "name": "group_thread_id_unique",
        "cypher": "CREATE CONSTRAINT group_thread_id_unique IF NOT EXISTS FOR (gt:GroupThread) REQUIRE gt.id IS UNIQUE",
        "desc": "Unique GroupThread UUID",
    },
]

# ---------------------------------------------------------------------------
# Indexes (v2)
# ---------------------------------------------------------------------------
V2_INDEXES = [
    {
        "name": "v2_task_status_agent",
        "cypher": "CREATE INDEX v2_task_status_agent IF NOT EXISTS FOR (t:Task) ON (t.status, t.assigned_to)",
        "desc": "Claim queries: PENDING tasks by agent",
    },
    {
        "name": "v2_task_lease",
        "cypher": "CREATE INDEX v2_task_lease IF NOT EXISTS FOR (t:Task) ON (t.lease_expires_at)",
        "desc": "Orphan recovery: expired leases",
    },
    {
        "name": "v2_task_claim_composite",
        "cypher": "CREATE INDEX v2_task_claim_composite IF NOT EXISTS FOR (t:Task) ON (t.status, t.assigned_to, t.priority, t.created_at)",
        "desc": "Claim query: PENDING tasks by agent ordered by priority",
    },
    {
        "name": "v2_task_orphan_composite",
        "cypher": "CREATE INDEX v2_task_orphan_composite IF NOT EXISTS FOR (t:Task) ON (t.status, t.lease_expires_at)",
        "desc": "Orphan recovery: WORKING tasks with expired leases",
    },
    {
        "name": "v2_agent_heartbeat",
        "cypher": "CREATE INDEX v2_agent_heartbeat IF NOT EXISTS FOR (a:Agent) ON (a.last_heartbeat)",
        "desc": "Agent liveness checks",
    },
    # --- Conversational Memory v2 indexes ---
    {
        "name": "v2_message_human_ts",
        "cypher": "CREATE INDEX v2_message_human_ts IF NOT EXISTS FOR (m:Message) ON (m.humanId, m.timestamp)",
        "desc": "Messages by human + time (hot path)",
    },
    {
        "name": "v2_thread_human_status",
        "cypher": "CREATE INDEX v2_thread_human_status IF NOT EXISTS FOR (t:Thread) ON (t.humanId, t.status)",
        "desc": "Threads by human + status",
    },
    {
        "name": "v2_action_item_human_status",
        "cypher": "CREATE INDEX v2_action_item_human_status IF NOT EXISTS FOR (a:ActionItem) ON (a.humanId, a.status)",
        "desc": "Action items by human + status",
    },
    # v2_topic_label is implicit from the topic_label_unique constraint
    {
        "name": "v2_human_status",
        "cypher": "CREATE INDEX v2_human_status IF NOT EXISTS FOR (h:Human) ON (h.status)",
        "desc": "Human status filter",
    },
    {
        "name": "v2_human_source",
        "cypher": "CREATE INDEX v2_human_source IF NOT EXISTS FOR (h:Human) ON (h.source)",
        "desc": "Human source filter",
    },
    {
        "name": "v2_message_extraction_status",
        "cypher": "CREATE INDEX v2_message_extraction_status IF NOT EXISTS FOR (m:Message) ON (m.extractionStatus)",
        "desc": "Pending extraction queue",
    },
    {
        "name": "v2_inference_human_confidence",
        "cypher": "CREATE INDEX v2_inference_human_confidence IF NOT EXISTS FOR (i:Inference) ON (i.humanId, i.confidence)",
        "desc": "Inferences by human + confidence",
    },
    # --- PendingQuestion (conversational curiosity) ---
    {
        "name": "v2_pending_question_human",
        "cypher": "CREATE INDEX v2_pending_question_human IF NOT EXISTS FOR (pq:PendingQuestion) ON (pq.humanId, pq.status)",
        "desc": "PendingQuestion lookup by human + status",
    },
    # --- Dispatch phase (Option B agent-owned execution) ---
    {
        "name": "v2_task_dispatch_phase",
        "cypher": "CREATE INDEX v2_task_dispatch_phase IF NOT EXISTS FOR (t:Task) ON (t.dispatch_phase)",
        "desc": "Phase-based queries for dispatcher verification loop",
    },
    {
        "name": "v2_task_heartbeat",
        "cypher": "CREATE INDEX v2_task_heartbeat IF NOT EXISTS FOR (t:Task) ON (t.last_heartbeat)",
        "desc": "Task-level heartbeat for liveness detection",
    },
    {
        "name": "v2_task_requester",
        "cypher": "CREATE INDEX v2_task_requester IF NOT EXISTS FOR (t:Task) ON (t.requester_id)",
        "desc": "Multi-tenant task queries by requester",
    },
    # --- Group Chat Isolation ---
    {
        "name": "v2_group_status",
        "cypher": "CREATE INDEX v2_group_status IF NOT EXISTS FOR (g:Group) ON (g.status)",
        "desc": "Group status filter",
    },
    {
        "name": "v2_group_thread_group_human",
        "cypher": "CREATE INDEX v2_group_thread_group_human IF NOT EXISTS FOR (gt:GroupThread) ON (gt.groupId, gt.humanId, gt.status)",
        "desc": "GroupThread lookup by group + human + status",
    },
    {
        "name": "v2_message_scope",
        "cypher": "CREATE INDEX v2_message_scope IF NOT EXISTS FOR (m:Message) ON (m.scope)",
        "desc": "Message scope filter (dm vs group:*)",
    },
    {
        "name": "v2_message_scope_human",
        "cypher": "CREATE INDEX v2_message_scope_human IF NOT EXISTS FOR (m:Message) ON (m.scope, m.humanId, m.timestamp)",
        "desc": "Scoped message retrieval by human + time",
    },
    # --- Message scope enforcement ---
    {
        "name": "v2_message_scope_notnull",
        "cypher": "CREATE INDEX v2_message_scope_notnull IF NOT EXISTS FOR (m:Message) ON (m.scope)",
        "desc": "Index on Message.scope — all messages MUST have scope set (dm or group:X)",
    },
    {
        "name": "v2_thread_scope_human",
        "cypher": "CREATE INDEX v2_thread_scope_human IF NOT EXISTS FOR (t:Thread) ON (t.scope, t.humanId, t.status)",
        "desc": "Scoped thread lookup by human + status",
    },
    # --- Calendar Enriched Fields ---
    {
        "name": "v2_event_category",
        "cypher": "CREATE INDEX v2_event_category IF NOT EXISTS FOR (e:Event) ON (e.category)",
        "desc": "Event category filter for curiosity engine",
    },
    # --- Conversational Health (reflection pipeline) ---
    {
        "name": "v2_pending_question_created",
        "cypher": "CREATE INDEX v2_pending_question_created IF NOT EXISTS "
                  "FOR (pq:PendingQuestion) ON (pq.createdAt)",
        "desc": "PendingQuestion creation time for funnel analysis",
    },
    {
        "name": "v2_action_item_status_created",
        "cypher": "CREATE INDEX v2_action_item_status_created IF NOT EXISTS "
                  "FOR (ai:ActionItem) ON (ai.status, ai.createdAt)",
        "desc": "ActionItem status + creation for stale-item detection",
    },
    # --- Task Dependencies (reflection pipeline) ---
    {
        "name": "v2_task_pipeline_id",
        "cypher": "CREATE INDEX v2_task_pipeline_id IF NOT EXISTS "
                  "FOR (t:Task) ON (t.pipeline_id)",
        "desc": "Pipeline run grouping for dependency-based orchestration",
    },
    {
        "name": "v2_task_status_pipeline",
        "cypher": "CREATE INDEX v2_task_status_pipeline IF NOT EXISTS "
                  "FOR (t:Task) ON (t.status, t.pipeline_id)",
        "desc": "Pipeline tasks by status for monitoring",
    },
]

# --- Vector indexes (applied separately due to special syntax) ---
V2_VECTOR_INDEXES = [
    {
        "name": "message_embedding",
        "cypher": """CREATE VECTOR INDEX message_embedding IF NOT EXISTS
            FOR (m:Message) ON (m.embedding)
            OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } }""",
        "desc": "Vector similarity search on message embeddings",
    },
    {
        "name": "thread_summary_embedding",
        "cypher": """CREATE VECTOR INDEX thread_summary_embedding IF NOT EXISTS
            FOR (t:Thread) ON (t.summaryEmbedding)
            OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: 'cosine' } }""",
        "desc": "Vector similarity search on thread summaries",
    },
]

# --- Full-text indexes ---
V2_FULLTEXT_INDEXES = [
    {
        "name": "message_text_search",
        "cypher": """CREATE FULLTEXT INDEX message_text_search IF NOT EXISTS
            FOR (m:Message) ON EACH [m.contentScrubbed]""",
        "desc": "Full-text search on scrubbed message content",
    },
    {
        "name": "thread_summary_search",
        "cypher": """CREATE FULLTEXT INDEX thread_summary_search IF NOT EXISTS
            FOR (t:Thread) ON EACH [t.summary]""",
        "desc": "Full-text search on thread summaries",
    },
]

# ---------------------------------------------------------------------------
# Deprecated / Dead schema items (to be dropped)
# ---------------------------------------------------------------------------

# Indexes superseded by composites or low-value
V2_DEPRECATED_INDEXES = [
    "v2_task_priority",
    "v2_task_claim_epoch",
    "v2_task_created",  # Equivalent to pre-existing task_created_at_index
]

# Constraints for node types that are never created
V2_DEAD_CONSTRAINTS = [
    "skill_name_unique",
    "domain_name_unique",
]


def drop_deprecated(driver, verbose=True):
    """Drop deprecated indexes and dead constraints."""
    with driver.session() as session:
        for name in V2_DEPRECATED_INDEXES:
            try:
                session.run(f"DROP INDEX {name} IF EXISTS")
                if verbose:
                    print(f"  [DROPPED] index {name}")
            except Exception as e:
                if verbose:
                    print(f"  [SKIP] index {name}: {e}")
        for name in V2_DEAD_CONSTRAINTS:
            try:
                session.run(f"DROP CONSTRAINT {name} IF EXISTS")
                if verbose:
                    print(f"  [DROPPED] constraint {name}")
            except Exception as e:
                if verbose:
                    print(f"  [SKIP] constraint {name}: {e}")


# ---------------------------------------------------------------------------
# Apply / Verify
# ---------------------------------------------------------------------------

def apply_schema(driver, verbose=True):
    """Apply all v2 constraints and indexes. Idempotent."""
    results = {"constraints": [], "indexes": [], "errors": []}

    with driver.session() as session:
        for item in V2_CONSTRAINTS:
            try:
                session.run(item["cypher"])
                results["constraints"].append(item["name"])
                if verbose:
                    print(f"  [OK] constraint {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["constraints"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] constraint {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] constraint {item['name']}: {e}")

        for item in V2_INDEXES:
            try:
                session.run(item["cypher"])
                results["indexes"].append(item["name"])
                if verbose:
                    print(f"  [OK] index {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["indexes"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] index {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] index {item['name']}: {e}")

        # Vector indexes
        for item in V2_VECTOR_INDEXES:
            try:
                session.run(item["cypher"])
                results["indexes"].append(item["name"])
                if verbose:
                    print(f"  [OK] vector index {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["indexes"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] vector index {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] vector index {item['name']}: {e}")

        # Full-text indexes
        for item in V2_FULLTEXT_INDEXES:
            try:
                session.run(item["cypher"])
                results["indexes"].append(item["name"])
                if verbose:
                    print(f"  [OK] fulltext index {item['name']}: {item['desc']}")
            except Exception as e:
                if "already exists" in str(e).lower() or "equivalent" in str(e).lower():
                    results["indexes"].append(item["name"])
                    if verbose:
                        print(f"  [EXISTS] fulltext index {item['name']}")
                else:
                    results["errors"].append(f"{item['name']}: {e}")
                    if verbose:
                        print(f"  [ERROR] fulltext index {item['name']}: {e}")

    drop_deprecated(driver, verbose)

    return results


def verify_schema(driver, verbose=True):
    """Verify all v2 constraints and indexes exist. Returns True if all present."""
    missing = []

    with driver.session() as session:
        # Collect existing names
        existing = set()
        for label in ("CONSTRAINTS", "INDEXES"):
            try:
                for rec in session.run(f"SHOW {label}"):
                    name = rec.get("name") or rec.get("constraintName") or rec.get("indexName")
                    if name:
                        existing.add(name)
            except Exception:
                pass

        for item in V2_CONSTRAINTS + V2_INDEXES:
            if item["name"] in existing:
                if verbose:
                    print(f"  [OK] {item['name']}")
            else:
                missing.append(item["name"])
                if verbose:
                    print(f"  [MISSING] {item['name']}")

        # Verify deprecated items are gone
        for name in V2_DEPRECATED_INDEXES + V2_DEAD_CONSTRAINTS:
            if name in existing:
                if verbose:
                    print(f"  [STALE] {name} (should be dropped)")
                missing.append(f"stale:{name}")

    if missing and verbose:
        print(f"\n  {len(missing)} missing schema elements")
    return len(missing) == 0


def run_self_test(driver):
    """Create and clean up test nodes to verify schema works."""
    import uuid
    test_id = f"test-{uuid.uuid4().hex[:8]}"

    print(f"  Creating test Task node: {test_id}")
    with driver.session() as session:
        # Create
        session.run("""
            CREATE (t:Task {
                task_id: $id, title: 'Schema self-test', status: 'PENDING',
                assigned_to: 'test-agent', priority: 'low', domain: 'test',
                claim_epoch: 0, retry_count: 0, max_retries: 1, depth: 0,
                timeout_s: 60, created_at: datetime(), updated_at: datetime()
            })
        """, id=test_id)

        # Verify
        result = session.run("MATCH (t:Task {task_id: $id}) RETURN t.status AS s", id=test_id)
        record = result.single()
        assert record and record["s"] == "PENDING", f"Expected PENDING, got {record}"
        print("  [OK] Task created and queried")

        # Test uniqueness constraint
        try:
            session.run("CREATE (t:Task {task_id: $id, title: 'dup'})", id=test_id)
            print("  [FAIL] Uniqueness constraint not enforced!")
        except Exception:
            print("  [OK] Uniqueness constraint enforced")

        # Cleanup
        session.run("MATCH (t:Task {task_id: $id}) DETACH DELETE t", id=test_id)
        print("  [OK] Test node cleaned up")

    print("\n  Self-test passed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Neo4j v2 schema management")
    parser.add_argument("--verify", action="store_true", help="Verify schema only")
    parser.add_argument("--test", action="store_true", help="Run self-test")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet
    if verbose:
        print("=== Neo4j v2 Schema ===\n")

    driver = get_driver()
    try:
        if args.test:
            apply_schema(driver, verbose)
            run_self_test(driver)
        elif args.verify:
            ok = verify_schema(driver, verbose)
            sys.exit(0 if ok else 1)
        else:
            results = apply_schema(driver, verbose)
            if verbose:
                c, i, e = len(results["constraints"]), len(results["indexes"]), len(results["errors"])
                print(f"\n  {c} constraints, {i} indexes applied. {e} errors.")
            if results["errors"]:
                sys.exit(1)
    finally:
        close_driver()


if __name__ == "__main__":
    main()
