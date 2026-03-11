#!/usr/bin/env python3
"""
Save Esoteric Knowledge to Neo4j

Stores esoteric/occult research findings in Neo4j knowledge graph.

Usage:
    python3 save-esoteric-knowledge.py --entity "Ordo Sacer Astaci" --type organization --attributes '{"meaning": "Sacred Order of the Crayfish"}'
    python3 save-esoteric-knowledge.py --concept "Cancer Zodiac" --associations "Moon, transformation, protection"
    python3 save-esoteric-knowledge.py --list
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver


def save_entity(name, entity_type, attributes=None, sources=None, tags=None):
    """Save an entity (organization, person, concept, symbol, etc.)."""
    driver = get_driver()
    
    entity_id = f"{entity_type.lower().replace(' ', '-')}-{name.lower().replace(' ', '-')}"
    timestamp = datetime.now().isoformat()
    
    with driver.session() as session:
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
        print(f"✅ Saved: {record['name']} ({record['id']})")
    
    driver.close()
    return entity_id


def save_relationship(from_entity, to_entity, relationship_type, attributes=None):
    """Save a relationship between two entities."""
    driver = get_driver()
    
    with driver.session() as session:
        session.run("""
            MATCH (a:EsotericEntity {id: $from_id})
            MATCH (b:EsotericEntity {id: $to_id})
            MERGE (a)-[r:RELATIONSHIP {type: $rel_type}]->(b)
            SET r.attributes = $attributes,
                r.created = datetime()
            RETURN type(r) as rel
        """,
        from_id=from_entity,
        to_id=to_entity,
        rel_type=relationship_type,
        attributes=json.dumps(attributes or {})
        )
        
        print(f"✅ Linked: {from_entity} -[{relationship_type}]-> {to_entity}")
    
    driver.close()


def save_concept(name, description, associations=None, symbols=None, tags=None):
    """Save an esoteric concept with associations."""
    driver = get_driver()
    
    concept_id = f"concept-{name.lower().replace(' ', '-')}"
    timestamp = datetime.now().isoformat()
    
    with driver.session() as session:
        result = session.run("""
            MERGE (c:EsotericConcept {id: $id, name: $name})
            SET c.description = $description,
                c.associations = $associations,
                c.symbols = $symbols,
                c.tags = $tags,
                c.updated = $timestamp
            RETURN c.id as id, c.name as name
        """,
        id=concept_id,
        name=name,
        description=description,
        associations=associations or [],
        symbols=symbols or [],
        tags=tags or [],
        timestamp=timestamp
        )
        
        record = result.single()
        print(f"✅ Saved concept: {record['name']}")
    
    driver.close()
    return concept_id


def list_entities(entity_type=None, limit=20):
    """List esoteric entities."""
    driver = get_driver()
    
    with driver.session() as session:
        if entity_type:
            result = session.run("""
                MATCH (e:EsotericEntity {type: $type})
                RETURN e ORDER BY e.updated DESC LIMIT $limit
            """, type=entity_type, limit=limit)
        else:
            result = session.run("""
                MATCH (e:EsotericEntity)
                RETURN e ORDER BY e.updated DESC LIMIT $limit
            """, limit=limit)
        
        entities = [dict(r['e']) for r in result]
        
        print(f"\n{'='*60}")
        print(f"Esoteric Knowledge Graph ({len(entities)} entities)")
        print(f"{'='*60}")
        
        for e in entities:
            print(f"\n[{e.get('type', '?').upper()}] {e.get('name', 'Unknown')}")
            print(f"  ID: {e.get('id', '?')}")
            print(f"  Tags: {', '.join(e.get('tags', []))}")
            print(f"  Updated: {e.get('updated', '?')}")
    
    driver.close()
    return entities


def list_concepts(limit=20):
    """List esoteric concepts."""
    driver = get_driver()
    
    with driver.session() as session:
        result = session.run("""
            MATCH (c:EsotericConcept)
            RETURN c ORDER BY c.updated DESC LIMIT $limit
        """, limit=limit)
        
        concepts = [dict(r['c']) for r in result]
        
        print(f"\n{'='*60}")
        print(f"Esoteric Concepts ({len(concepts)})")
        print(f"{'='*60}")
        
        for c in concepts:
            print(f"\n{c.get('name', 'Unknown')}")
            print(f"  {c.get('description', '')[:100]}...")
            print(f"  Associations: {', '.join(c.get('associations', []))}")
    
    driver.close()
    return concepts


def main():
    parser = argparse.ArgumentParser(description="Save esoteric knowledge to Neo4j")
    parser.add_argument("--entity", help="Entity name")
    parser.add_argument("--type", help="Entity type (organization, symbol, concept, person, place)")
    parser.add_argument("--concept", help="Concept name")
    parser.add_argument("--description", help="Concept description")
    parser.add_argument("--attributes", help="JSON attributes")
    parser.add_argument("--associations", help="Comma-separated associations")
    parser.add_argument("--symbols", help="Comma-separated symbols")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--sources", help="Comma-separated sources")
    parser.add_argument("--relate", help="Create relationship: from_id:to_id:rel_type")
    parser.add_argument("--list", action="store_true", help="List entities")
    parser.add_argument("--list-concepts", action="store_true", help="List concepts")
    parser.add_argument("--filter-type", help="Filter by type when listing")
    
    args = parser.parse_args()
    
    if args.list:
        list_entities(args.filter_type)
        return
    
    if args.list_concepts:
        list_concepts()
        return
    
    if args.entity and args.type:
        attributes = json.loads(args.attributes) if args.attributes else {}
        sources = args.sources.split(",") if args.sources else []
        tags = args.tags.split(",") if args.tags else []
        save_entity(args.entity, args.type, attributes, sources, tags)
        return
    
    if args.concept:
        associations = args.associations.split(",") if args.associations else []
        symbols = args.symbols.split(",") if args.symbols else []
        tags = args.tags.split(",") if args.tags else []
        save_concept(args.concept, args.description or "", associations, symbols, tags)
        return
    
    if args.relate:
        parts = args.relate.split(":")
        if len(parts) == 3:
            save_relationship(parts[0], parts[1], parts[2])
        else:
            print("Error: --relate format is from_id:to_id:rel_type")
        return
    
    print("Usage: python3 save-esoteric-knowledge.py --entity NAME --type TYPE [--attributes JSON]")
    print("       python3 save-esoteric-knowledge.py --concept NAME --description DESC")
    print("       python3 save-esoteric-knowledge.py --list")


if __name__ == "__main__":
    main()
