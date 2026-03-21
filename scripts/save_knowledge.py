#!/usr/bin/env python3
"""
Knowledge Store — Neo4j persistence for structured knowledge extraction.

Stores knowledge units with facts, concepts, entities, principles, and quotes.
Cross-references with existing ResearchEntity/ResearchConcept nodes.

Usage:
    python3 save_knowledge.py --json '{"source": "...", ...}'
    python3 save_knowledge.py --file path.json
    python3 save_knowledge.py --query "search term"
    python3 save_knowledge.py --tags "tag1,tag2"
    python3 save_knowledge.py --related "concept name"
    python3 save_knowledge.py --stats
    python3 save_knowledge.py --ensure-indexes
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Import shared Neo4j connection
sys.path.insert(0, str(Path(__file__).parent))
from neo4j_task_tracker import get_driver, close_driver

QUEUE_DIR = Path.home() / ".openclaw" / "agents" / "mongke" / "workspace" / "knowledge-queue"


class KnowledgeStore:
    """Neo4j-backed knowledge graph store."""

    def __init__(self):
        try:
            self.driver = get_driver()
            # Quick connectivity check
            with self.driver.session() as s:
                s.run("RETURN 1")
            self._connected = True
        except Exception as e:
            print(f"[warn] Neo4j unavailable: {e}")
            self.driver = None
            self._connected = False

    def close(self):
        if self.driver:
            close_driver()
            self.driver = None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def ensure_indexes(self):
        """Create indexes and constraints for knowledge nodes."""
        if not self._connected:
            print("[error] Neo4j not connected")
            return False

        index_statements = [
            # Fulltext composite index
            """CREATE FULLTEXT INDEX knowledge_search IF NOT EXISTS
               FOR (n:KnowledgeFact|KnowledgeConcept|KnowledgeEntity|KnowledgePrinciple|KnowledgeQuote)
               ON EACH [n.claim, n.description, n.name, n.statement, n.text]""",
            # Property indexes
            "CREATE INDEX knowledge_unit_hash IF NOT EXISTS FOR (n:KnowledgeUnit) ON (n.content_hash)",
            "CREATE INDEX knowledge_concept_name IF NOT EXISTS FOR (n:KnowledgeConcept) ON (n.name)",
            "CREATE INDEX knowledge_entity_name IF NOT EXISTS FOR (n:KnowledgeEntity) ON (n.name)",
        ]

        with self.driver.session() as session:
            for stmt in index_statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    # Some index types may already exist in different form
                    print(f"[warn] Index statement skipped: {e}")

        print("[ok] Knowledge indexes ensured")
        return True

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, knowledge_json, source_desc="unknown", learned_by="mongke"):
        """Persist a structured knowledge extraction to Neo4j.

        Args:
            knowledge_json: dict with keys: source_type, summary, tags, confidence,
                facts[], concepts[], entities[], principles[], quotes[],
                relationships[]
            source_desc: human-readable source description
            learned_by: agent name
        """
        if not self._connected:
            self._queue_fallback(knowledge_json, source_desc, learned_by)
            return False

        data = knowledge_json if isinstance(knowledge_json, dict) else json.loads(knowledge_json)
        now = datetime.now().isoformat()

        # Content hash for dedup (first 1000 chars of summary + facts)
        hash_input = (data.get("summary", "") + json.dumps(data.get("facts", [])))[:1000]
        content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

        unit_id = str(uuid.uuid4())

        with self.driver.session() as session:
            # Check for duplicate
            existing = session.run(
                "MATCH (ku:KnowledgeUnit {content_hash: $h}) RETURN ku.unit_id AS uid",
                h=content_hash,
            ).single()

            if existing:
                unit_id = existing["uid"]
                print(f"[info] Updating existing KnowledgeUnit {unit_id}")
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    SET ku.source = $source,
                        ku.source_type = $source_type,
                        ku.summary = $summary,
                        ku.tags = $tags,
                        ku.confidence = $confidence,
                        ku.learned_by = $learned_by,
                        ku.learned_at = $now
                """, uid=unit_id, source=source_desc,
                    source_type=data.get("source_type", "document"),
                    summary=data.get("summary", ""),
                    tags=data.get("tags", []),
                    confidence=data.get("confidence", 0.5),
                    learned_by=learned_by, now=now)
            else:
                session.run("""
                    CREATE (ku:KnowledgeUnit {
                        unit_id: $uid,
                        source: $source,
                        source_type: $source_type,
                        summary: $summary,
                        tags: $tags,
                        confidence: $confidence,
                        content_hash: $hash,
                        learned_by: $learned_by,
                        learned_at: $now
                    })
                """, uid=unit_id, source=source_desc,
                    source_type=data.get("source_type", "document"),
                    summary=data.get("summary", ""),
                    tags=data.get("tags", []),
                    confidence=data.get("confidence", 0.5),
                    hash=content_hash, learned_by=learned_by, now=now)

            # -- Facts --
            for fact in data.get("facts", []):
                fid = str(uuid.uuid4())
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    CREATE (f:KnowledgeFact {
                        fact_id: $fid, claim: $claim,
                        confidence: $confidence, domain: $domain,
                        verifiable: $verifiable
                    })
                    CREATE (ku)-[:CONTAINS_FACT]->(f)
                """, uid=unit_id, fid=fid,
                    claim=fact.get("claim", ""),
                    confidence=fact.get("confidence", 0.5),
                    domain=fact.get("domain", ""),
                    verifiable=fact.get("verifiable", True))

            # -- Concepts --
            for concept in data.get("concepts", []):
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    MERGE (c:KnowledgeConcept {name: toLower($name)})
                    ON CREATE SET c.description = $desc, c.domain = $domain,
                                  c.aliases = $aliases
                    ON MATCH SET c.description = $desc, c.domain = $domain,
                                 c.aliases = $aliases
                    MERGE (ku)-[:CONTAINS_CONCEPT]->(c)
                """, uid=unit_id,
                    name=concept.get("name", ""),
                    desc=concept.get("description", ""),
                    domain=concept.get("domain", ""),
                    aliases=concept.get("aliases", []))

            # -- Entities --
            for entity in data.get("entities", []):
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    MERGE (e:KnowledgeEntity {name: toLower($name), type: $type})
                    ON CREATE SET e.description = $desc, e.url = $url
                    ON MATCH SET e.description = $desc, e.url = $url
                    MERGE (ku)-[:MENTIONS_ENTITY]->(e)
                """, uid=unit_id,
                    name=entity.get("name", ""),
                    type=entity.get("type", "unknown"),
                    desc=entity.get("description", ""),
                    url=entity.get("url", ""))

            # -- Principles --
            for principle in data.get("principles", []):
                pid = str(uuid.uuid4())
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    CREATE (p:KnowledgePrinciple {
                        principle_id: $pid, name: $name,
                        statement: $statement,
                        category: $category, domain: $domain
                    })
                    CREATE (ku)-[:TEACHES_PRINCIPLE]->(p)
                """, uid=unit_id, pid=pid,
                    name=principle.get("name", ""),
                    statement=principle.get("statement", ""),
                    category=principle.get("category", "principle"),
                    domain=principle.get("domain", ""))

            # -- Quotes --
            for quote in data.get("quotes", []):
                qid = str(uuid.uuid4())
                session.run("""
                    MATCH (ku:KnowledgeUnit {unit_id: $uid})
                    CREATE (q:KnowledgeQuote {
                        quote_id: $qid, text: $text,
                        author: $author, context: $context
                    })
                    CREATE (ku)-[:CONTAINS_QUOTE]->(q)
                """, uid=unit_id, qid=qid,
                    text=quote.get("text", ""),
                    author=quote.get("author", ""),
                    context=quote.get("context", ""))

            # -- Concept relationships --
            for rel in data.get("relationships", []):
                rel_type = rel.get("type", "RELATES_TO").upper().replace(" ", "_")
                # Only use safe relationship types
                if rel_type in ("RELATES_TO", "SUPPORTS", "CONTRADICTS", "DEPENDS_ON",
                                "PART_OF", "EXAMPLE_OF", "CAUSES", "ENABLES"):
                    session.run(f"""
                        MATCH (a) WHERE (a:KnowledgeConcept OR a:KnowledgeEntity)
                            AND toLower(a.name) = toLower($from)
                        MATCH (b) WHERE (b:KnowledgeConcept OR b:KnowledgeEntity)
                            AND toLower(b.name) = toLower($to)
                        MERGE (a)-[:{rel_type}]->(b)
                    """, **{"from": rel.get("from", ""), "to": rel.get("to", "")})

            # -- Cross-references to existing Research nodes --
            session.run("""
                MATCH (ke:KnowledgeEntity)
                MATCH (re:ResearchEntity)
                WHERE toLower(ke.name) = toLower(re.name)
                MERGE (ke)-[:SAME_AS]->(re)
            """)
            session.run("""
                MATCH (kc:KnowledgeConcept)
                MATCH (rc:ResearchConcept)
                WHERE toLower(kc.name) = toLower(rc.name)
                MERGE (kc)-[:SAME_AS]->(rc)
            """)

            # -- Fact-Principle links --
            session.run("""
                MATCH (ku:KnowledgeUnit {unit_id: $uid})-[:CONTAINS_FACT]->(f:KnowledgeFact)
                MATCH (ku)-[:TEACHES_PRINCIPLE]->(p:KnowledgePrinciple)
                WHERE f.domain = p.domain AND f.domain <> ''
                MERGE (f)-[:SUPPORTS]->(p)
            """, uid=unit_id)

        counts = self._count_saved(unit_id)
        print(f"[ok] Saved KnowledgeUnit {unit_id}: {counts}")
        return True

    def _count_saved(self, unit_id):
        """Count child nodes for a knowledge unit."""
        if not self._connected:
            return {}
        with self.driver.session() as session:
            result = session.run("""
                MATCH (ku:KnowledgeUnit {unit_id: $uid})
                OPTIONAL MATCH (ku)-[:CONTAINS_FACT]->(f:KnowledgeFact)
                OPTIONAL MATCH (ku)-[:CONTAINS_CONCEPT]->(c:KnowledgeConcept)
                OPTIONAL MATCH (ku)-[:MENTIONS_ENTITY]->(e:KnowledgeEntity)
                OPTIONAL MATCH (ku)-[:TEACHES_PRINCIPLE]->(p:KnowledgePrinciple)
                OPTIONAL MATCH (ku)-[:CONTAINS_QUOTE]->(q:KnowledgeQuote)
                RETURN count(DISTINCT f) AS facts, count(DISTINCT c) AS concepts,
                       count(DISTINCT e) AS entities, count(DISTINCT p) AS principles,
                       count(DISTINCT q) AS quotes
            """, uid=unit_id).single()
            return dict(result) if result else {}

    def _queue_fallback(self, knowledge_json, source_desc, learned_by):
        """Write to local queue when Neo4j is unavailable."""
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
        payload = {
            "source_desc": source_desc,
            "learned_by": learned_by,
            "queued_at": datetime.now().isoformat(),
            "knowledge": knowledge_json if isinstance(knowledge_json, dict) else json.loads(knowledge_json),
        }
        path = QUEUE_DIR / fname
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[fallback] Queued to {path}")

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def query(self, search_term, limit=10):
        """Full-text search across knowledge nodes."""
        if not self._connected:
            print("[error] Neo4j not connected")
            return []

        with self.driver.session() as session:
            results = session.run("""
                CALL db.index.fulltext.queryNodes('knowledge_search', $term)
                YIELD node, score
                RETURN labels(node) AS labels, node.name AS name,
                       node.claim AS claim, node.text AS text,
                       node.statement AS statement,
                       node.description AS description,
                       score
                ORDER BY score DESC
                LIMIT $limit
            """, term=search_term, limit=limit)
            rows = [dict(r) for r in results]
            return rows

    def query_by_tags(self, tags, limit=20):
        """Find knowledge units by tags."""
        if not self._connected:
            print("[error] Neo4j not connected")
            return []

        tag_list = [t.strip().lower() for t in tags] if isinstance(tags, list) else [t.strip().lower() for t in tags.split(",")]

        with self.driver.session() as session:
            results = session.run("""
                MATCH (ku:KnowledgeUnit)
                WHERE ANY(t IN ku.tags WHERE toLower(t) IN $tags)
                RETURN ku.unit_id AS unit_id, ku.source AS source,
                       ku.summary AS summary, ku.tags AS tags,
                       ku.confidence AS confidence, ku.learned_at AS learned_at
                ORDER BY ku.learned_at DESC
                LIMIT $limit
            """, tags=tag_list, limit=limit)
            rows = [dict(r) for r in results]
            return rows

    def query_related(self, node_name, depth=2):
        """Find nodes related to a given name up to N hops."""
        if not self._connected:
            print("[error] Neo4j not connected")
            return []

        with self.driver.session() as session:
            results = session.run("""
                MATCH (start)
                WHERE (start:KnowledgeConcept OR start:KnowledgeEntity)
                    AND toLower(start.name) = toLower($name)
                CALL apoc.path.subgraphNodes(start, {maxLevel: $depth}) YIELD node
                WHERE node <> start
                RETURN labels(node) AS labels, node.name AS name,
                       node.description AS description, node.type AS type
            """, name=node_name, depth=depth)
            rows = [dict(r) for r in results]

            # Fallback if APOC not available
            if not rows:
                results = session.run("""
                    MATCH (start)
                    WHERE (start:KnowledgeConcept OR start:KnowledgeEntity)
                        AND toLower(start.name) = toLower($name)
                    MATCH (start)-[*1..2]-(related)
                    WHERE related <> start
                    RETURN DISTINCT labels(related) AS labels,
                           related.name AS name,
                           related.description AS description,
                           related.type AS type
                    LIMIT 50
                """, name=node_name)
                rows = [dict(r) for r in results]

            return rows

    def stats(self):
        """Count nodes by knowledge label."""
        if not self._connected:
            print("[error] Neo4j not connected")
            return {}

        labels = [
            "KnowledgeUnit", "KnowledgeFact", "KnowledgeConcept",
            "KnowledgeEntity", "KnowledgePrinciple", "KnowledgeQuote",
        ]
        counts = {}
        with self.driver.session() as session:
            for label in labels:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
                counts[label] = result["c"] if result else 0

            # Cross-reference counts
            xref = session.run("""
                MATCH ()-[r:SAME_AS]->()
                WHERE startNode(r):KnowledgeEntity OR startNode(r):KnowledgeConcept
                RETURN count(r) AS c
            """).single()
            counts["SAME_AS_cross_refs"] = xref["c"] if xref else 0

        return counts


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Knowledge Store CLI")
    parser.add_argument("--json", help="Save knowledge from JSON string")
    parser.add_argument("--file", help="Save knowledge from JSON file")
    parser.add_argument("--source", default="cli", help="Source description")
    parser.add_argument("--agent", default="mongke", help="Agent name")
    parser.add_argument("--query", help="Full-text search")
    parser.add_argument("--tags", help="Query by tags (comma-separated)")
    parser.add_argument("--related", help="Find related nodes")
    parser.add_argument("--stats", action="store_true", help="Show knowledge stats")
    parser.add_argument("--ensure-indexes", action="store_true", help="Create indexes")
    parser.add_argument("--limit", type=int, default=10, help="Result limit")

    args = parser.parse_args()
    store = KnowledgeStore()

    try:
        if args.ensure_indexes:
            store.ensure_indexes()

        elif args.json:
            data = json.loads(args.json)
            store.save(data, source_desc=args.source, learned_by=args.agent)

        elif args.file:
            with open(args.file) as f:
                data = json.load(f)
            store.save(data, source_desc=args.source, learned_by=args.agent)

        elif args.query:
            results = store.query(args.query, limit=args.limit)
            if results:
                for r in results:
                    label = r["labels"][0] if r.get("labels") else "?"
                    content = r.get("name") or r.get("claim") or r.get("text") or r.get("statement") or ""
                    print(f"  [{label}] {content[:120]} (score: {r.get('score', 0):.2f})")
            else:
                print("  No results found.")

        elif args.tags:
            results = store.query_by_tags(args.tags, limit=args.limit)
            if results:
                for r in results:
                    print(f"  [{r['unit_id'][:8]}] {r.get('summary', '')[:100]} tags={r.get('tags', [])}")
            else:
                print("  No results found.")

        elif args.related:
            results = store.query_related(args.related)
            if results:
                for r in results:
                    label = r["labels"][0] if r.get("labels") else "?"
                    print(f"  [{label}] {r.get('name', '')} — {r.get('description', '')[:80]}")
            else:
                print("  No related nodes found.")

        elif args.stats:
            counts = store.stats()
            if counts:
                print("Knowledge Graph Stats:")
                for label, count in counts.items():
                    print(f"  {label}: {count}")
            else:
                print("  No stats available.")

        else:
            parser.print_help()

    finally:
        store.close()


if __name__ == "__main__":
    main()
