#!/usr/bin/env python3
"""
Knowledge CLI - Unified knowledge storage CLI.

Consolidates save-strategic-insight.py, save-esoteric-knowledge.py, and
save_knowledge.py into a single CLI with subcommands.

Usage:
    python3 knowledge_cli.py strategic --name "Key Insight" --data '{"insight": "..."}'
    python3 knowledge_cli.py esoteric --entity "Entity Name" --type organization
    python3 knowledge_cli.py knowledge --topic "Research Topic" --content "..."

    python3 knowledge_cli.py list --type strategic
    python3 knowledge_cli.py search --query "insight"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from neo4j_task_tracker import get_driver, close_driver


class KnowledgeCLI:
    """Unified knowledge storage interface."""

    def __init__(self):
        self.driver = get_driver()

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            close_driver()
            self.driver = None

    # ==========================================================================
    # Strategic Insights
    # ==========================================================================

    def save_strategic_insight(
        self,
        insight_type: str,
        name: str,
        data: Dict[str, Any],
        source: str = "manual",
        tags: Optional[list] = None
    ) -> str:
        """Save a strategic insight to Neo4j.

        Args:
            insight_type: Type of insight (opportunity, decision, insight)
            name: Insight name
            data: Insight data dict
            source: Source of insight
            tags: Optional tags

        Returns:
            Insight ID
        """
        insight_id = f"{insight_type.lower()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        timestamp = datetime.now().isoformat()

        with self.driver.session() as session:
            result = session.run("""
                MERGE (i:StrategicInsight {id: $id})
                SET i.type = $type,
                    i.name = $name,
                    i.data = $data,
                    i.source = $source,
                    i.tags = $tags,
                    i.created = $timestamp,
                    i.updated = $timestamp,
                    i.status = 'active'
                RETURN i.id as id, i.name as name
            """,
            id=insight_id,
            type=insight_type,
            name=name,
            data=json.dumps(data),
            source=source,
            tags=tags or [],
            timestamp=timestamp
            )

            record = result.single()
            if record:
                print(f"✅ Saved: {record['name']} (ID: {record['id']})")
                return insight_id
        return None

    def list_strategic_insights(self, insight_type: Optional[str] = None) -> list[Dict]:
        """List strategic insights.

        Args:
            insight_type: Optional filter by type

        Returns:
            List of insight dicts
        """
        with self.driver.session() as session:
            if insight_type:
                result = session.run("""
                    MATCH (i:StrategicInsight {type: $type})
                    WHERE i.status = 'active'
                    RETURN i.id, i.name, i.type, i.source, i.created
                    ORDER BY i.created DESC
                """, type=insight_type)
            else:
                result = session.run("""
                    MATCH (i:StrategicInsight)
                    WHERE i.status = 'active'
                    RETURN i.id, i.name, i.type, i.source, i.created
                    ORDER BY i.created DESC
                """)

            return [dict(r) for r in result]

    # ==========================================================================
    # Esoteric Knowledge
    # ==========================================================================

    def save_esoteric_entity(
        self,
        name: str,
        entity_type: str,
        attributes: Optional[Dict] = None,
        sources: Optional[list] = None,
        tags: Optional[list] = None
    ) -> str:
        """Save an esoteric entity.

        Args:
            name: Entity name
            entity_type: Type (organization, person, concept, symbol)
            attributes: Optional attributes dict
            sources: Optional source list
            tags: Optional tags

        Returns:
            Entity ID
        """
        entity_id = f"{entity_type.lower().replace(' ', '-')}-{name.lower().replace(' ', '-')}"
        timestamp = datetime.now().isoformat()

        with self.driver.session() as session:
            result = session.run("""
                MERGE (e:EsotericEntity {id: $id, name: $name})
                SET e.type = $type,
                    e.attributes = $attributes,
                    e.sources = $sources,
                    e.tags = $tags,
                    e.updated = $timestamp
                RETURN e.id as id, e.name as name
            """,
            id=entity_id,
            name=name,
            type=entity_type,
            attributes=json.dumps(attributes or {}),
            sources=sources or [],
            tags=tags or [],
            timestamp=timestamp
            )

            record = result.single()
            if record:
                print(f"✅ Saved: {record['name']} ({record['id']})")
                return entity_id
        return None

    def save_esoteric_relationship(
        self,
        from_entity: str,
        to_entity: str,
        relationship_type: str,
        attributes: Optional[Dict] = None
    ) -> bool:
        """Save a relationship between entities.

        Args:
            from_entity: Source entity ID
            to_entity: Target entity ID
            relationship_type: Relationship type
            attributes: Optional relationship attributes

        Returns:
            True on success
        """
        with self.driver.session() as session:
            session.run("""
                MATCH (a:EsotericEntity {id: $from_id})
                MATCH (b:EsotericEntity {id: $to_id})
                MERGE (a)-[r:RELATIONSHIP {type: $rel_type}]->(b)
                SET r.attributes = $attributes,
                    r.created = datetime()
            """,
            from_id=from_entity,
            to_id=to_entity,
            rel_type=relationship_type,
            attributes=json.dumps(attributes or {})
            )

            print(f"✅ Linked: {from_entity} -[{relationship_type}]-> {to_entity}")
            return True

    def list_esoteric_entities(self, entity_type: Optional[str] = None) -> list[Dict]:
        """List esoteric entities.

        Args:
            entity_type: Optional filter by type

        Returns:
            List of entity dicts
        """
        with self.driver.session() as session:
            if entity_type:
                result = session.run("""
                    MATCH (e:EsotericEntity {type: $type})
                    RETURN e.id, e.name, e.type, e.updated
                    ORDER BY e.updated DESC
                """, type=entity_type)
            else:
                result = session.run("""
                    MATCH (e:EsotericEntity)
                    RETURN e.id, e.name, e.type, e.updated
                    ORDER BY e.updated DESC
                """)

            return [dict(r) for r in result]

    # ==========================================================================
    # General Knowledge
    # ==========================================================================

    def save_knowledge(
        self,
        topic: str,
        content: str,
        category: str = "general",
        keywords: Optional[list] = None,
        source: Optional[str] = None
    ) -> str:
        """Save general knowledge.

        Args:
            topic: Knowledge topic
            content: Knowledge content (markdown supported)
            category: Knowledge category
            keywords: Optional keywords list
            source: Optional source URL

        Returns:
            Knowledge ID
        """
        import uuid
        knowledge_id = f"knowledge-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().isoformat()

        with self.driver.session() as session:
            result = session.run("""
                CREATE (k:Knowledge {
                    id: $id,
                    topic: $topic,
                    content: $content,
                    category: $category,
                    keywords: $keywords,
                    source: $source,
                    created: $timestamp
                })
                RETURN k.id as id
            """,
            id=knowledge_id,
            topic=topic,
            content=content,
            category=category,
            keywords=keywords or [],
            source=source,
            timestamp=timestamp
            )

            record = result.single()
            if record:
                print(f"✅ Saved knowledge: {topic} (ID: {record['id']})")
                return knowledge_id
        return None

    def search_knowledge(self, query: str, limit: int = 10) -> list[Dict]:
        """Search knowledge by keyword.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of matching knowledge dicts
        """
        with self.driver.session() as session:
            result = session.run("""
                CALL db.index.fulltext.queryNodes('knowledge_search', $query)
                YIELD node, score
                RETURN node.id, node.topic, node.category, score
                ORDER BY score DESC
                LIMIT $limit
            """,
            query=query,
            limit=limit
            )

            return [dict(r) for r in result]


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Unified knowledge storage CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Strategic subcommand
    strategic_parser = subparsers.add_parser(
        "strategic",
        help="Save strategic insight"
    )
    strategic_parser.add_argument("--type", required=True,
                                   choices=["opportunity", "decision", "insight"])
    strategic_parser.add_argument("--name", required=True)
    strategic_parser.add_argument("--data", required=True,
                                   help="JSON data string")
    strategic_parser.add_argument("--source", default="manual")
    strategic_parser.add_argument("--tags", nargs="*")

    # Esoteric subcommand
    esoteric_parser = subparsers.add_parser(
        "esoteric",
        help="Save esoteric knowledge"
    )
    esoteric_parser.add_argument("--entity", required=True)
    esoteric_parser.add_argument("--type", required=True)
    esoteric_parser.add_argument("--attributes", help="JSON attributes")
    esoteric_parser.add_argument("--sources", nargs="*")
    esoteric_parser.add_argument("--tags", nargs="*")

    # Knowledge subcommand
    knowledge_parser = subparsers.add_parser(
        "knowledge",
        help="Save general knowledge"
    )
    knowledge_parser.add_argument("--topic", required=True)
    knowledge_parser.add_argument("--content", required=True)
    knowledge_parser.add_argument("--category", default="general")
    knowledge_parser.add_argument("--keywords", nargs="*")
    knowledge_parser.add_argument("--source")

    # List subcommand
    list_parser = subparsers.add_parser(
        "list",
        help="List knowledge entries"
    )
    list_parser.add_argument("--type", choices=["strategic", "esoteric"])
    list_parser.add_argument("--filter")

    args = parser.parse_args()

    cli = KnowledgeCLI()

    try:
        if args.command == "strategic":
            data = json.loads(args.data)
            cli.save_strategic_insight(
                insight_type=args.type,
                name=args.name,
                data=data,
                source=args.source,
                tags=args.tags
            )

        elif args.command == "esoteric":
            attrs = json.loads(args.attributes) if args.attributes else None
            cli.save_esoteric_entity(
                name=args.entity,
                entity_type=args.type,
                attributes=attrs,
                sources=args.sources,
                tags=args.tags
            )

        elif args.command == "knowledge":
            cli.save_knowledge(
                topic=args.topic,
                content=args.content,
                category=args.category,
                keywords=args.keywords,
                source=args.source
            )

        elif args.command == "list":
            if args.type == "strategic":
                insights = cli.list_strategic_insights()
                for i in insights:
                    print(f"  {i['id']}: {i['name']} ({i['type']})")
            elif args.type == "esoteric":
                entities = cli.list_esoteric_entities()
                for e in entities:
                    print(f"  {e['id']}: {e['name']} ({e['type']})")
            else:
                print("Specify --type strategic or esoteric")

    finally:
        cli.close()


if __name__ == "__main__":
    main()
